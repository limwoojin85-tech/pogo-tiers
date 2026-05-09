package com.woojin.pokemanager.calc

import kotlin.math.floor

data class LeagueResult(
    val league: String,
    val leagueCap: Int,
    val bestLevel: Float,
    val bestCP: Int,
    val statProduct: Long,
    val rank: Int,
    val rankPercent: Float
)

object PvPRanker {

    fun rank(baseAtk: Int, baseDef: Int, baseStam: Int,
             ivAtk: Int, ivDef: Int, ivStam: Int,
             leagueCap: Int): LeagueResult {

        val (bestLevel, bestCP) = findBestLevel(baseAtk, baseDef, baseStam, ivAtk, ivDef, ivStam, leagueCap)
        val sp = statProduct(baseAtk, baseDef, baseStam, ivAtk, ivDef, ivStam, bestLevel)

        // build sorted list of all 4096 stat products for this species + league
        val all = ArrayList<Long>(4096)
        for (a in 0..15) for (d in 0..15) for (s in 0..15) {
            val (lv, _) = findBestLevel(baseAtk, baseDef, baseStam, a, d, s, leagueCap)
            all.add(statProduct(baseAtk, baseDef, baseStam, a, d, s, lv))
        }
        all.sortDescending()

        val rank = all.indexOfFirst { it <= sp } + 1
        val leagueName = when (leagueCap) {
            1500 -> "슈퍼리그"
            2500 -> "하이퍼리그"
            else -> "마스터리그"
        }

        return LeagueResult(
            league = leagueName,
            leagueCap = leagueCap,
            bestLevel = bestLevel,
            bestCP = bestCP,
            statProduct = sp,
            rank = rank,
            rankPercent = rank.toFloat() / 4096f * 100f
        )
    }

    fun rankAll(baseAtk: Int, baseDef: Int, baseStam: Int,
                ivAtk: Int, ivDef: Int, ivStam: Int): List<LeagueResult> {
        return listOf(
            rank(baseAtk, baseDef, baseStam, ivAtk, ivDef, ivStam, 1500),
            rank(baseAtk, baseDef, baseStam, ivAtk, ivDef, ivStam, 2500),
            rank(baseAtk, baseDef, baseStam, ivAtk, ivDef, ivStam, Int.MAX_VALUE)
        )
    }

    fun findBestLevel(baseAtk: Int, baseDef: Int, baseStam: Int,
                      ivAtk: Int, ivDef: Int, ivStam: Int, leagueCap: Int): Pair<Float, Int> {
        var bestLevel = 1.0f
        var bestCP = 10
        var lv = 1.0f
        while (lv <= 51.0f) {
            val cp = IVCalculator.calculateCP(baseAtk, baseDef, baseStam, ivAtk, ivDef, ivStam, lv)
            if (cp <= leagueCap && cp > bestCP) {
                bestCP = cp
                bestLevel = lv
            }
            lv += 0.5f
        }
        return bestLevel to bestCP
    }

    private fun statProduct(baseAtk: Int, baseDef: Int, baseStam: Int,
                            ivAtk: Int, ivDef: Int, ivStam: Int, level: Float): Long {
        val cpm = IVCalculator.CPM[level] ?: return 0L
        val atk = (baseAtk + ivAtk) * cpm
        val def = (baseDef + ivDef) * cpm
        val stam = floor((baseStam + ivStam) * cpm)
        return (atk * def * stam).toLong()
    }
}
