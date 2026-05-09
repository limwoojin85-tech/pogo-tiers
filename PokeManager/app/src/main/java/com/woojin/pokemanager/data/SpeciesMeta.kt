package com.woojin.pokemanager.data

/** species_meta.json 의 entry — 사이트 분석용 메타 데이터 */
data class SpeciesMeta(
    val ko: String = "",
    val en: String = "",
    val dex: Int = 0,
    val types: List<String> = emptyList(),
    val pvp: List<PvPRank> = emptyList(),
    val raid: List<RaidRank> = emptyList(),
    val rank1_iv: Map<String, Rank1Iv>? = null,    // GL/UL/Little 종결 IV
    val is_final: Boolean = true,
    val max_cp: Int = 0,
    val max_sp: Long = 0
)

data class PvPRank(
    val league_key: String = "",
    val league_ko: String = "",
    val league_en: String = "",
    val rank: Int = 0,
    val score: Float = 0f,
    val moveset: String = ""
)

data class RaidRank(
    val boss_key: String = "",
    val boss_ko: String = "",
    val boss_en: String = "",
    val tier_ko: String = "",
    val tier_en: String = "",
    val rank: Int = 0,
    val is_essential_tier: Boolean = false
)

data class Rank1Iv(
    val lv: Float = 0f,
    val atk: Int = 0,
    val def: Int = 0,
    val sta: Int = 0
)

/** groups.json — transfer / mega / pre_evolution */
data class GroupsData(
    val transfer_groups: List<TransferGroup> = emptyList(),
    val mega_keep_groups: List<TransferGroup> = emptyList(),
    val mega_possible_groups: List<TransferGroup> = emptyList(),
    val pre_evolution_groups: List<PreEvoGroup> = emptyList()
)

data class TransferGroup(
    val family_id: String = "",
    val keep_sid: String = "",
    val keep_ko: String = "",
    val keep_en: String = "",
    val keep_dex: Int = 0,
    val members: List<GroupMember> = emptyList(),
    val evo_kind: String? = null,
    val evo_note: String? = null
)

data class PreEvoGroup(
    val family_id: String = "",
    val evolves_to_sid: String = "",
    val evolves_to_ko: String = "",
    val evolves_to_en: String = "",
    val evolves_to_dex: Int = 0,
    val members: List<GroupMember> = emptyList()
)

data class GroupMember(
    val sid: String = "",
    val dex: Int = 0,
    val ko: String = "",
    val en: String = "",
    val types: List<String> = emptyList(),
    val is_shadow: Boolean = false,
    val is_mega: Boolean = false
)
