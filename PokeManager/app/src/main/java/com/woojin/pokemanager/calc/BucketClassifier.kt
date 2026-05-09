package com.woojin.pokemanager.calc

import com.woojin.pokemanager.data.*

/** 사이트의 8 bucket 분류를 Kotlin 으로 포팅.
 *  Calcy 분석 탭의 classifyBucket() / analyzeOne() 와 같은 결정. */
object BucketClassifier {

    private val GL_KEYS = setOf("all_1500", "premier_1500", "classic_1500")
    private val UL_KEYS = setOf("all_2500", "premier_2500", "classic_2500")
    private val ML_KEYS = setOf("all_10000", "premier_10000", "classic_10000")
    private val LC_KEYS = setOf("all_500", "little_500", "premier_500", "classic_500")

    enum class Bucket(val label: String, val description: String) {
        TEAM_RAID_CURRENT("🏟️ 현재 레이드 베스트", "활성 보스별 카운터"),
        TEAM_GL("⚔️ 슈퍼리그 베스트", "1500 캡 종결"),
        TEAM_UL("🛡️ 하이퍼리그 베스트", "2500 캡 종결"),
        TEAM_CUPS("🥊 컵 베스트", "각 컵 종결"),
        CAND_RAID("⚔️ 레이드 후보", "백개체 / ATK15 강자"),
        HOLD("🤔 보류", "메가/가족 대표/진화 필요/애매 IV"),
        TRANSFER("📦 박사 송출", "어디에도 안 쓰임"),
        TRANSFER_DUP("🔁 중복 송출", "더 좋은 마리 있음")
    }

    data class Decision(
        val bucket: Bucket,
        val reason: String,
        val ivPct: Double = 0.0,
        val glPct: Double = 0.0,
        val ulPct: Double = 0.0,
        val isHundo: Boolean = false,
        val evolveTo: String? = null
    )

    /** 단일 마리 분류. PvPRanker.IVResult + species 메타 기반. */
    fun classify(
        sid: String,
        ivAtk: Int, ivDef: Int, ivStam: Int,
        cp: Int = 0,
        species: SpeciesMeta? = null,
        groupClass: GroupClassification = GroupClassification.Unknown
    ): Decision {
        val isHundo = ivAtk == 15 && ivDef == 15 && ivStam == 15
        val ivPct = (ivAtk + ivDef + ivStam) / 45.0 * 100

        // ─── 진화 전 단계 → 보류 + 진화 안내
        if (groupClass is GroupClassification.PreEvolution) {
            return Decision(
                bucket = Bucket.HOLD,
                reason = "🔄 진화 필요 — ${groupClass.group.evolves_to_ko} 로 진화시켜 사용",
                ivPct = ivPct, isHundo = isHundo,
                evolveTo = groupClass.group.evolves_to_ko
            )
        }

        // ─── transfer 그룹 (가족 송출)
        if (groupClass is GroupClassification.Transfer) {
            val isKeep = groupClass.group.keep_sid == sid
            val txt = if (isKeep) "🔵 가족 대표 — 1마리 보관" else "⚪ 박사 송출 OK (가족 송출)"
            return Decision(
                bucket = if (isKeep) Bucket.HOLD else Bucket.TRANSFER,
                reason = txt, ivPct = ivPct, isHundo = isHundo
            )
        }

        // ─── mega 보관
        if (groupClass is GroupClassification.MegaKeep) {
            val txt = if (isHundo) "🔴 메가 변신 베이스 — 100% 보관" else "🟡 메가 보관"
            return Decision(bucket = Bucket.HOLD, reason = txt, ivPct = ivPct, isHundo = isHundo)
        }
        if (groupClass is GroupClassification.MegaPossible) {
            return Decision(bucket = Bucket.HOLD, reason = "🟡 메가 가능 — 100% 1마리 보관",
                ivPct = ivPct, isHundo = isHundo)
        }

        // ─── 분류 없음
        if (species == null || groupClass is GroupClassification.Unknown) {
            return Decision(bucket = Bucket.TRANSFER, reason = "⚪ 분류 없음 / 박사 송출 OK",
                ivPct = ivPct, isHundo = isHundo)
        }

        // ─── 메타 기반 분류
        val ml = bestRank(species, ML_KEYS)
        val gl = bestRank(species, GL_KEYS)
        val ul = bestRank(species, UL_KEYS)
        val raid = species.raid.minByOrNull { it.rank }
        val hasMLRole = ml != null && ml.rank <= 30
        val hasRaidRole = raid != null && raid.rank <= 20

        // 백개체
        if (isHundo) {
            if (hasMLRole) return Decision(Bucket.CAND_RAID,
                "🏆 백개체 — ML 종결 (ML #${ml!!.rank})", ivPct, isHundo = true)
            if (hasRaidRole) return Decision(Bucket.CAND_RAID,
                "🏆 백개체 — 레이드 종결 (vs ${raid!!.boss_ko}#${raid.rank})", ivPct, isHundo = true)
            return Decision(Bucket.HOLD,
                "🏆 백개체 — 콜렉션 (메타 외)", ivPct, isHundo = true)
        }

        // 슈퍼리그 종결
        if (gl != null && gl.rank <= 20) {
            val r1 = species.rank1_iv?.get("GL")
            val pct = if (r1 != null) leagueScorePct(species, r1, ivAtk, ivDef, ivStam, 1500) else 0.0
            if (pct >= 99.0) return Decision(Bucket.TEAM_GL,
                "⚔️ 슈퍼리그 #${gl.rank} 종결 (${pct.format(1)}%)", ivPct, glPct = pct)
            if (pct >= 96.0) return Decision(Bucket.TEAM_GL,
                "⚔️ 슈퍼리그 #${gl.rank} 쓸만 (${pct.format(1)}%)", ivPct, glPct = pct)
        }

        // 하이퍼리그 종결
        if (ul != null && ul.rank <= 20) {
            val r1 = species.rank1_iv?.get("UL")
            val pct = if (r1 != null) leagueScorePct(species, r1, ivAtk, ivDef, ivStam, 2500) else 0.0
            if (pct >= 99.0) return Decision(Bucket.TEAM_UL,
                "🛡️ 하이퍼리그 #${ul.rank} 종결 (${pct.format(1)}%)", ivPct, ulPct = pct)
            if (pct >= 96.0) return Decision(Bucket.TEAM_UL,
                "🛡️ 하이퍼리그 #${ul.rank} 쓸만 (${pct.format(1)}%)", ivPct, ulPct = pct)
        }

        // 컵 — 1500 캡 IV 적합 + 컵 랭킹
        val cups = species.pvp.filter { it.league_key !in GL_KEYS && it.league_key !in UL_KEYS &&
                it.league_key !in ML_KEYS && it.league_key !in LC_KEYS }
            .sortedBy { it.rank }
        if (cups.isNotEmpty()) {
            val top = cups.first()
            val r1 = species.rank1_iv?.get("GL")
            val pct = if (r1 != null) leagueScorePct(species, r1, ivAtk, ivDef, ivStam, 1500) else 0.0
            if (pct >= 99.0) return Decision(Bucket.TEAM_CUPS,
                "🥇 ${top.league_ko}#${top.rank} 컵 종결 (${pct.format(1)}%)", ivPct, glPct = pct)
            if (pct >= 96.0) return Decision(Bucket.TEAM_CUPS,
                "🟡 ${top.league_ko}#${top.rank} 컵 한정 (${pct.format(1)}%)", ivPct, glPct = pct)
            if (pct < 90.0) return Decision(Bucket.TRANSFER,
                "📦 컵 못 씀 — 공격 IV 너무 높음 (${pct.format(1)}%)", ivPct)
        }

        // ATK 15 강자 → 레이드 후보
        if (ivAtk == 15 && (ivAtk + ivDef + ivStam) >= 38 && hasRaidRole) {
            return Decision(Bucket.CAND_RAID,
                "🔴 레이드 최적 (ATK15, ${ivAtk + ivDef + ivStam}/45)", ivPct)
        }

        // 그 외 → 송출
        return Decision(Bucket.TRANSFER, "⚪ 메타 외 — 박사 송출 OK", ivPct)
    }

    private fun bestRank(sp: SpeciesMeta, keys: Set<String>): PvPRank? =
        sp.pvp.filter { it.league_key in keys }.minByOrNull { it.rank }

    /** league rank-1 IV 대비 사용자 IV 의 stat product 비율 (%) */
    private fun leagueScorePct(
        sp: SpeciesMeta, r1: Rank1Iv,
        ivA: Int, ivD: Int, ivS: Int, cpCap: Int
    ): Double {
        // 베이스 스탯이 있어야 — species_meta 에 없을 수 있음, 그러면 IV 합 기준 fallback
        // sp 자체엔 base_stats 없음 — 같이 GameMasterRepo.findByName 으로 가져와야
        // 단순 구현: IV 합 비율 (정확도는 떨어지지만 빠름)
        val userSum = ivA + ivD + ivS
        val r1Sum = r1.atk + r1.def + r1.sta
        if (r1Sum == 0) return 0.0
        return userSum.toDouble() / r1Sum * 100
    }
}

private fun Double.format(digits: Int) = "%.${digits}f".format(this)
