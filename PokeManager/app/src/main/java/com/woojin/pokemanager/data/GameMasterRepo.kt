package com.woojin.pokemanager.data

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

object GameMasterRepo {

    private var speciesList: List<Species> = emptyList()
    private var speciesMeta: Map<String, SpeciesMeta> = emptyMap()
    private var groups: GroupsData = GroupsData()
    private var cpmTable: List<Double> = emptyList()

    // sid → 진화 후 sid (pre-evolution chain)
    private var preEvoMap: Map<String, PreEvoGroup> = emptyMap()
    // sid → transfer/mega 그룹
    private var transferMap: Map<String, TransferGroup> = emptyMap()
    private var megaKeepMap: Map<String, TransferGroup> = emptyMap()
    private var megaPossibleMap: Map<String, TransferGroup> = emptyMap()

    fun load(context: Context) {
        if (speciesList.isNotEmpty()) return
        val gson = Gson()

        // 1. pokemon_stats.json — 1571 종 베이스
        context.assets.open("pokemon_stats.json").bufferedReader().use { reader ->
            val type = object : TypeToken<List<Species>>() {}.type
            speciesList = gson.fromJson(reader, type)
        }

        // 2. species_meta.json — 랭킹된 648 종 (옵션)
        runCatching {
            context.assets.open("species_meta.json").bufferedReader().use { reader ->
                val type = object : TypeToken<Map<String, SpeciesMeta>>() {}.type
                speciesMeta = gson.fromJson(reader, type)
            }
        }

        // 3. groups.json — transfer/mega/pre_evolution (옵션)
        runCatching {
            context.assets.open("groups.json").bufferedReader().use { reader ->
                groups = gson.fromJson(reader, GroupsData::class.java)
            }
            // sid 별 lookup map
            preEvoMap = buildMap {
                for (g in groups.pre_evolution_groups) {
                    for (m in g.members) put(m.sid, g)
                }
            }
            transferMap = buildMap {
                for (g in groups.transfer_groups) {
                    for (m in g.members) put(m.sid, g)
                }
            }
            megaKeepMap = buildMap {
                for (g in groups.mega_keep_groups) {
                    for (m in g.members) put(m.sid, g)
                }
            }
            megaPossibleMap = buildMap {
                for (g in groups.mega_possible_groups) {
                    for (m in g.members) put(m.sid, g)
                }
            }
        }

        // 4. cpm.json
        runCatching {
            context.assets.open("cpm.json").bufferedReader().use { reader ->
                val obj = gson.fromJson(reader, Map::class.java) as Map<*, *>
                @Suppress("UNCHECKED_CAST")
                cpmTable = (obj["cpm"] as? List<Double>) ?: emptyList()
            }
        }
    }

    fun all(): List<Species> = speciesList
    fun cpm(): List<Double> = cpmTable
    fun groups(): GroupsData = groups

    fun findByName(name: String): Species? {
        val lower = name.lowercase().trim()
        return speciesList.firstOrNull {
            it.name.lowercase() == lower || it.nameKo == name.trim() ||
            it.id.lowercase() == lower
        }
    }

    fun findByNameFuzzy(name: String): Species? {
        findByName(name)?.let { return it }
        val q = name.trim()
        val lower = q.lowercase()
        return speciesList.firstOrNull {
            it.name.lowercase().contains(lower) || it.nameKo.contains(q)
        }
    }

    fun findByDex(dex: Int): Species? = speciesList.firstOrNull { it.dex == dex }

    /** 메타 (랭킹/PvP/raid) — 랭킹 종에만 있음, 없으면 null */
    fun meta(sid: String): SpeciesMeta? = speciesMeta[sid]

    /** 분류 — 진화 전, 송출, 메가 보관, 메가 가능 */
    fun classifyGroup(sid: String): GroupClassification = when {
        preEvoMap.containsKey(sid) -> GroupClassification.PreEvolution(preEvoMap[sid]!!)
        transferMap.containsKey(sid) -> GroupClassification.Transfer(transferMap[sid]!!)
        megaKeepMap.containsKey(sid) -> GroupClassification.MegaKeep(megaKeepMap[sid]!!)
        megaPossibleMap.containsKey(sid) -> GroupClassification.MegaPossible(megaPossibleMap[sid]!!)
        speciesMeta.containsKey(sid) -> GroupClassification.Ranked
        else -> GroupClassification.Unknown
    }
}

sealed class GroupClassification {
    object Ranked : GroupClassification()                                 // 랭킹된 종 (사이트 species_out)
    data class PreEvolution(val group: PreEvoGroup) : GroupClassification()
    data class Transfer(val group: TransferGroup) : GroupClassification()
    data class MegaKeep(val group: TransferGroup) : GroupClassification()
    data class MegaPossible(val group: TransferGroup) : GroupClassification()
    object Unknown : GroupClassification()
}
