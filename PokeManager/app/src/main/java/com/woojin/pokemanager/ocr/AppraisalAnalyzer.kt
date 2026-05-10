package com.woojin.pokemanager.ocr

/**
 * Pokemon GO "조사하기 (appraisal)" 화면 텍스트 분석.
 *
 * detail 화면과 달리 조사하기 화면엔:
 *   - 팀 리더 (블랜치 / 캔디라 / 스파크) 가 IV 등급 평가 대화
 *   - "정말 놀랍군요!" / "강하네요" / "괜찮네요" / "더 노력해야" — IV 합 등급 4단계
 *   - "공격이 가장 좋은 점이에요" — best stat 알려줌
 *   - "정말 끝내줘요" / "강해요" / "괜찮네요" / "노력해야" — best stat IV 등급
 *
 * Calcy IV / PokeGenie 가 정확한 핵심 — 이 텍스트를 OCR 해서 후보 좁힘.
 */
object AppraisalAnalyzer {

    enum class Tier(val ivSumMin: Int, val ivSumMax: Int) {
        LV4_HUNDO(37, 45),    // ★★★★ "정말 놀랍군요" — IV 합 37+
        LV3_GREAT(30, 36),    // ★★★  "강하네요"
        LV2_DECENT(23, 29),   // ★★   "괜찮네요"
        LV1_LOW(0, 22),       // ★    "더 노력"
    }

    enum class StatTier(val ivMin: Int, val ivMax: Int) {
        STAT_15(15, 15),      // "정말 끝내줘요" / "정말 놀랍군요"
        STAT_13_14(13, 14),   // "정말 강해요"
        STAT_8_12(8, 12),     // "강해요"
        STAT_0_7(0, 7),       // "더 노력해야"
    }

    enum class BestStat { ATK, DEF, STA, ATK_DEF, ATK_STA, DEF_STA, ALL }

    data class AppraisalData(
        val tier: Tier?,
        val bestStat: BestStat?,
        val bestStatTier: StatTier?
    )

    /** 화면 OCR 결과가 조사하기 화면인지 — 한국어 키워드 + 팀 리더 이름 */
    fun isAppraisalScreen(text: String): Boolean {
        val keywords = listOf(
            "정말 놀랍", "정말놀랍", "강하군요", "강하네요", "괜찮네요",
            "더 노력", "노력해야", "발전할 여지",
            "통계가",
            "끝내줘요", "정말 강",
            // 팀 리더
            "블랜치", "캔디라", "스파크"
        )
        return keywords.any { text.contains(it) }
    }

    /** 조사하기 텍스트 → IV 합 등급 + best stat */
    fun analyze(text: String): AppraisalData {
        val tier = detectTier(text)
        val bestStat = detectBestStat(text)
        val bestStatTier = detectStatTier(text)
        return AppraisalData(tier, bestStat, bestStatTier)
    }

    private fun detectTier(text: String): Tier? = when {
        text.contains("정말 놀랍") || text.contains("정말놀랍") ||
            text.contains("끝내줘") || text.contains("최고") -> Tier.LV4_HUNDO
        text.contains("정말 강") || text.contains("정말강") ||
            text.contains("강하네") || text.contains("강하군") -> Tier.LV3_GREAT
        text.contains("괜찮") || text.contains("평균") -> Tier.LV2_DECENT
        text.contains("더 노력") || text.contains("노력해야") ||
            text.contains("발전할 여지") || text.contains("평범") -> Tier.LV1_LOW
        else -> null
    }

    /** "공격이 가장 좋은" / "방어가 인상" / "HP가 인상" / 둘다 / 셋다 */
    private fun detectBestStat(text: String): BestStat? {
        val hasAtk = text.contains(Regex("공격.{0,8}(가장|좋|인상|최고)"))
        val hasDef = text.contains(Regex("방어.{0,8}(가장|좋|인상|최고)"))
        val hasSta = text.contains(Regex("(?i)(HP|체력).{0,8}(가장|좋|인상|최고)"))
        return when {
            hasAtk && hasDef && hasSta -> BestStat.ALL
            hasAtk && hasDef -> BestStat.ATK_DEF
            hasAtk && hasSta -> BestStat.ATK_STA
            hasDef && hasSta -> BestStat.DEF_STA
            hasAtk -> BestStat.ATK
            hasDef -> BestStat.DEF
            hasSta -> BestStat.STA
            else -> null
        }
    }

    /** best stat 의 IV 등급 (0-7 / 8-12 / 13-14 / 15) */
    private fun detectStatTier(text: String): StatTier? = when {
        text.contains("끝내") || text.contains("정말 놀랍") -> StatTier.STAT_15
        text.contains("정말 강") || text.contains("정말강") -> StatTier.STAT_13_14
        text.contains("강해") -> StatTier.STAT_8_12
        text.contains("노력") -> StatTier.STAT_0_7
        else -> null
    }

    /**
     * AppraisalData + 후보 IVResult 리스트 → 더 좁혀진 후보.
     * - tier 가 있으면 IV 합이 그 범위인 것만
     * - bestStat 이 있으면 그 stat 이 max 인 것만 (best stat = ATK 면 atkIV >= defIV && atkIV >= stamIV)
     * - bestStatTier 가 있으면 best stat 의 IV 가 그 범위인 것만
     */
    fun filterCandidates(
        candidates: List<com.woojin.pokemanager.calc.IVResult>,
        appraisal: AppraisalData
    ): List<com.woojin.pokemanager.calc.IVResult> {
        var result = candidates
        appraisal.tier?.let { tier ->
            result = result.filter {
                val sum = it.atkIV + it.defIV + it.stamIV
                sum in tier.ivSumMin..tier.ivSumMax
            }.ifEmpty { candidates }
        }
        appraisal.bestStat?.let { best ->
            result = result.filter { isBestStatMatch(it, best) }.ifEmpty { result }
        }
        appraisal.bestStatTier?.let { tier ->
            result = result.filter { iv ->
                val maxStat = maxOf(iv.atkIV, iv.defIV, iv.stamIV)
                maxStat in tier.ivMin..tier.ivMax
            }.ifEmpty { result }
        }
        return result
    }

    private fun isBestStatMatch(iv: com.woojin.pokemanager.calc.IVResult, best: BestStat): Boolean {
        val a = iv.atkIV; val d = iv.defIV; val s = iv.stamIV
        return when (best) {
            BestStat.ATK -> a >= d && a >= s && (a > d || a > s)
            BestStat.DEF -> d >= a && d >= s && (d > a || d > s)
            BestStat.STA -> s >= a && s >= d && (s > a || s > d)
            BestStat.ATK_DEF -> a == d && a >= s
            BestStat.ATK_STA -> a == s && a >= d
            BestStat.DEF_STA -> d == s && d >= a
            BestStat.ALL -> a == d && d == s
        }
    }
}
