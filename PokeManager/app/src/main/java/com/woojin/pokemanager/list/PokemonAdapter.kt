package com.woojin.pokemanager.list

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.woojin.pokemanager.R
import com.woojin.pokemanager.data.GameMasterRepo
import com.woojin.pokemanager.data.MyPokemon

class PokemonAdapter(private val onLongClick: (MyPokemon) -> Unit) :
    ListAdapter<MyPokemon, PokemonAdapter.VH>(DIFF) {

    inner class VH(v: View) : RecyclerView.ViewHolder(v) {
        val tvName: TextView = v.findViewById(R.id.tvItemName)
        val tvStats: TextView = v.findViewById(R.id.tvItemStats)
        val tvIV: TextView = v.findViewById(R.id.tvItemIV)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) =
        VH(LayoutInflater.from(parent.context).inflate(R.layout.item_pokemon, parent, false))

    override fun onBindViewHolder(holder: VH, position: Int) {
        val p = getItem(position)
        val species = GameMasterRepo.findByName(p.speciesId)
        val nameStr = buildString {
            append(species?.nameKo ?: p.speciesId)
            if (p.isShadow) append(" [그림자]")
            if (p.isPurified) append(" [정화]")
            if (p.isShiny) append(" ✨")
        }
        holder.tvName.text = nameStr
        holder.tvStats.text = "CP ${p.cp}  HP ${p.hp}  Lv%.1f".format(p.level)
        holder.tvIV.text = "${p.atkIV}/${p.defIV}/${p.stamIV}  ${"%.1f".format(p.perfection * 100)}%"
        holder.itemView.setOnLongClickListener { onLongClick(p); true }
    }

    companion object {
        val DIFF = object : DiffUtil.ItemCallback<MyPokemon>() {
            override fun areItemsTheSame(a: MyPokemon, b: MyPokemon) = a.id == b.id
            override fun areContentsTheSame(a: MyPokemon, b: MyPokemon) = a == b
        }
    }
}
