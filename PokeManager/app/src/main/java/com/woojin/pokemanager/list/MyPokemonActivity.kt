package com.woojin.pokemanager.list

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.woojin.pokemanager.R
import com.woojin.pokemanager.data.AppDatabase
import com.woojin.pokemanager.data.GameMasterRepo
import com.woojin.pokemanager.data.MyPokemon
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class MyPokemonActivity : AppCompatActivity() {

    private lateinit var adapter: PokemonAdapter
    private val dao by lazy { AppDatabase.get(this).pokemonDao() }

    private val csvLauncher = registerForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri -> uri?.let { importCsv(it) } }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_my_pokemon)

        val rv = findViewById<RecyclerView>(R.id.rvPokemon)
        adapter = PokemonAdapter { pokemon ->
            androidx.appcompat.app.AlertDialog.Builder(this)
                .setTitle("${GameMasterRepo.findByName(pokemon.speciesId)?.nameKo ?: pokemon.speciesId} 삭제")
                .setMessage("이 포켓몬을 삭제하시겠습니까?")
                .setPositiveButton("삭제") { _, _ ->
                    lifecycleScope.launch { dao.delete(pokemon) }
                }
                .setNegativeButton("취소", null)
                .show()
        }
        rv.layoutManager = LinearLayoutManager(this)
        rv.adapter = adapter

        lifecycleScope.launch {
            dao.getAll().collectLatest { list ->
                adapter.submitList(list)
                findViewById<TextView>(R.id.tvCount).text = "총 ${list.size}마리"
            }
        }

        findViewById<Button>(R.id.btnImportCsv).setOnClickListener {
            csvLauncher.launch("text/*")
        }
    }

    private fun importCsv(uri: Uri) {
        lifecycleScope.launch(kotlinx.coroutines.Dispatchers.IO) {
            try {
                val lines = contentResolver.openInputStream(uri)!!
                    .bufferedReader().readLines()
                if (lines.isEmpty()) return@launch

                val header = lines[0].split(",").map { it.trim().lowercase() }
                val nameIdx = header.indexOf("name").takeIf { it >= 0 } ?: return@launch
                val cpIdx = header.indexOf("cp").takeIf { it >= 0 } ?: return@launch
                val hpIdx = header.indexOf("hp").takeIf { it >= 0 } ?: -1
                val dustIdx = header.indexOfFirst { it.contains("dust") }.takeIf { it >= 0 } ?: -1
                val atkIdx = header.indexOfFirst { it.contains("atk") || it.contains("attack") }.takeIf { it >= 0 } ?: -1
                val defIdx = header.indexOfFirst { it.contains("def") }.takeIf { it >= 0 } ?: -1
                val staIdx = header.indexOfFirst { it.contains("sta") || it.contains("hp_iv") }.takeIf { it >= 0 } ?: -1

                var imported = 0
                for (line in lines.drop(1)) {
                    if (line.isBlank()) continue
                    val cols = line.split(",")
                    if (cols.size <= nameIdx || cols.size <= cpIdx) continue

                    val name = cols[nameIdx].trim()
                    val cp = cols[cpIdx].trim().toIntOrNull() ?: continue
                    val hp = if (hpIdx >= 0) cols.getOrNull(hpIdx)?.trim()?.toIntOrNull() ?: 0 else 0
                    val dust = if (dustIdx >= 0) cols.getOrNull(dustIdx)?.trim()?.toIntOrNull() ?: 1000 else 1000
                    val atkIV = if (atkIdx >= 0) cols.getOrNull(atkIdx)?.trim()?.toIntOrNull() ?: 0 else 0
                    val defIV = if (defIdx >= 0) cols.getOrNull(defIdx)?.trim()?.toIntOrNull() ?: 0 else 0
                    val staIV = if (staIdx >= 0) cols.getOrNull(staIdx)?.trim()?.toIntOrNull() ?: 0 else 0

                    val species = GameMasterRepo.findByNameFuzzy(name)
                    dao.insert(MyPokemon(
                        speciesId = species?.id ?: name.lowercase(),
                        cp = cp, hp = hp, dustCost = dust,
                        atkIV = atkIV, defIV = defIV, stamIV = staIV,
                        level = 20f,
                        perfection = (atkIV + defIV + staIV) / 45f
                    ))
                    imported++
                }

                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                    Toast.makeText(this@MyPokemonActivity, "${imported}마리 가져옴", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                    Toast.makeText(this@MyPokemonActivity, "가져오기 실패: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }
}
