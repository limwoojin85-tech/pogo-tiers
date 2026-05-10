package com.woojin.pokemanager.calc

import kotlin.math.floor
import kotlin.math.sqrt

data class IVResult(
    val atkIV: Int,
    val defIV: Int,
    val stamIV: Int,
    val level: Float,
    val perfection: Float,
    val cp: Int,
    val hp: Int
)

object IVCalculator {

    val CPM: Map<Float, Double> = mapOf(
        1.0f to 0.09399999678, 1.5f to 0.13513743, 2.0f to 0.16639786959,
        2.5f to 0.19265091419, 3.0f to 0.21573247862, 3.5f to 0.23657265799,
        4.0f to 0.25572005153, 4.5f to 0.27353037893, 5.0f to 0.29024988413,
        5.5f to 0.30605737492, 6.0f to 0.32108759880, 6.5f to 0.33544503152,
        7.0f to 0.34921267986, 7.5f to 0.36245773935, 8.0f to 0.37523558736,
        8.5f to 0.38759241108, 9.0f to 0.39956727623, 9.5f to 0.41119354951,
        10.0f to 0.42250001431, 10.5f to 0.43292707, 11.0f to 0.44310251,
        11.5f to 0.45305023, 12.0f to 0.46279839, 12.5f to 0.47236293,
        13.0f to 0.48175662, 13.5f to 0.49098757, 14.0f to 0.50006174,
        14.5f to 0.50898647, 15.0f to 0.51776755, 15.5f to 0.52641270,
        16.0f to 0.53492898, 16.5f to 0.54331520, 17.0f to 0.55157960,
        17.5f to 0.55972249, 18.0f to 0.56774790, 18.5f to 0.57565916,
        19.0f to 0.58345974, 19.5f to 0.59115267, 20.0f to 0.59874071,
        20.5f to 0.60623080, 21.0f to 0.61361935, 21.5f to 0.62090796,
        22.0f to 0.62809919, 22.5f to 0.63519510, 23.0f to 0.64219755,
        23.5f to 0.64910650, 24.0f to 0.65592561, 24.5f to 0.66265661,
        25.0f to 0.66930003, 25.5f to 0.67585558, 26.0f to 0.68233168,
        26.5f to 0.68872580, 27.0f to 0.69504207, 27.5f to 0.70128382,
        28.0f to 0.70745075, 28.5f to 0.71354294, 29.0f to 0.71956069,
        29.5f to 0.72551269, 30.0f to 0.73139876, 30.5f to 0.73773846,
        31.0f to 0.74400097, 31.5f to 0.75018799, 32.0f to 0.75629997,
        32.5f to 0.76234053, 33.0f to 0.76831108, 33.5f to 0.77421376,
        34.0f to 0.78004956, 34.5f to 0.78581986, 35.0f to 0.79152560,
        35.5f to 0.79717010, 36.0f to 0.80274927, 36.5f to 0.80826312,
        37.0f to 0.81371236, 37.5f to 0.81909910, 38.0f to 0.82442488,
        38.5f to 0.82969110, 39.0f to 0.83489913, 39.5f to 0.84004967,
        40.0f to 0.84514290, 40.5f to 0.85003435, 41.0f to 0.85383338,
        41.5f to 0.85854079, 42.0f to 0.86215365, 42.5f to 0.86664654,
        43.0f to 0.87013817, 43.5f to 0.87451434, 44.0f to 0.87789673,
        44.5f to 0.88215819, 45.0f to 0.88544654, 45.5f to 0.88960026,
        46.0f to 0.89280093, 46.5f to 0.89685508, 47.0f to 0.89997435,
        47.5f to 0.90393585, 48.0f to 0.90698063, 48.5f to 0.91085540,
        49.0f to 0.91382736, 49.5f to 0.91762209, 50.0f to 0.92056960,
        50.5f to 0.92337650, 51.0f to 0.92609026
    )

    private val dustToLevelRange: Map<Int, Pair<Float, Float>> = mapOf(
        200 to (1.0f to 2.5f), 400 to (3.0f to 4.5f), 600 to (5.0f to 6.5f),
        800 to (7.0f to 8.5f), 1000 to (9.0f to 10.5f), 1300 to (11.0f to 12.5f),
        1600 to (13.0f to 14.5f), 1900 to (15.0f to 16.5f), 2200 to (17.0f to 18.5f),
        2500 to (19.0f to 20.5f), 3000 to (21.0f to 22.5f), 3500 to (23.0f to 24.5f),
        4000 to (25.0f to 26.5f), 4500 to (27.0f to 28.5f), 5000 to (29.0f to 30.5f),
        6000 to (31.0f to 32.5f), 7000 to (33.0f to 34.5f), 8000 to (35.0f to 36.5f),
        9000 to (37.0f to 38.5f), 10000 to (39.0f to 40.5f), 11000 to (41.0f to 41.5f),
        12000 to (42.0f to 42.5f), 13000 to (43.0f to 43.5f), 14000 to (44.0f to 44.5f),
        15000 to (45.0f to 45.5f), 16000 to (46.0f to 46.5f), 17000 to (47.0f to 47.5f),
        18000 to (48.0f to 48.5f), 19000 to (49.0f to 49.5f), 20000 to (50.0f to 51.0f)
    )

    fun calculateCP(baseAtk: Int, baseDef: Int, baseStam: Int,
                    ivAtk: Int, ivDef: Int, ivStam: Int, level: Float): Int {
        val cpm = CPM[level] ?: return 0
        return maxOf(10, floor(
            (baseAtk + ivAtk) * sqrt((baseDef + ivDef).toDouble()) *
            sqrt((baseStam + ivStam).toDouble()) * cpm * cpm / 10.0
        ).toInt())
    }

    fun calculateHP(baseStam: Int, ivStam: Int, level: Float): Int {
        val cpm = CPM[level] ?: return 0
        return maxOf(10, floor((baseStam + ivStam) * cpm).toInt())
    }

    fun levelsForDust(dustCost: Int, isShadow: Boolean = false, isPurified: Boolean = false): List<Float> {
        // 별가루 정보 없음 (detail 화면엔 dust 표시 안 됨) — 모든 레벨 1.0~51.0 시도
        if (dustCost <= 0) {
            val all = mutableListOf<Float>()
            var lv = 1.0f
            while (lv <= 51.01f) {
                all.add(lv)
                lv += 0.5f
            }
            return all
        }
        val normalized = when {
            isShadow -> dustToLevelRange.keys.minByOrNull { kotlin.math.abs(it - (dustCost / 1.2f).toInt()) }
            isPurified -> dustToLevelRange.keys.minByOrNull { kotlin.math.abs(it - (dustCost / 0.9f).toInt()) }
            else -> dustCost
        } ?: return emptyList()
        val range = dustToLevelRange[normalized] ?: return emptyList()
        val levels = mutableListOf<Float>()
        var lv = range.first
        while (lv <= range.second + 0.01f) {
            levels.add(lv)
            lv += 0.5f
        }
        return levels
    }

    fun calculate(
        baseAtk: Int, baseDef: Int, baseStam: Int,
        observedCP: Int, observedHP: Int, dustCost: Int,
        isShadow: Boolean = false, isPurified: Boolean = false
    ): List<IVResult> {
        val levels = levelsForDust(dustCost, isShadow, isPurified)
        val results = mutableListOf<IVResult>()
        for (level in levels) {
            for (ivAtk in 0..15) {
                for (ivDef in 0..15) {
                    for (ivStam in 0..15) {
                        val cp = calculateCP(baseAtk, baseDef, baseStam, ivAtk, ivDef, ivStam, level)
                        val hp = calculateHP(baseStam, ivStam, level)
                        if (cp == observedCP && hp == observedHP) {
                            results.add(IVResult(
                                atkIV = ivAtk, defIV = ivDef, stamIV = ivStam,
                                level = level,
                                perfection = (ivAtk + ivDef + ivStam) / 45f,
                                cp = cp, hp = hp
                            ))
                        }
                    }
                }
            }
        }
        return results.sortedByDescending { it.perfection }
    }
}
