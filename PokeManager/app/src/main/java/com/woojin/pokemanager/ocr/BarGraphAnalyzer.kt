package com.woojin.pokemanager.ocr

import android.graphics.Bitmap
import android.graphics.Color
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * Pokemon GO detail 화면 하단의 IV 막대 그래프 + 별 배지 픽셀 분석.
 *
 * detail 화면에 표시되는 정보:
 *   - 공격 / 방어 / HP 각 막대 (15칸, 채워진 정도 ∝ IV 0-15)
 *   - 좌하단 별 배지 (1-4성, IV 합 0-22 / 23-36 / 37-44 / 45)
 *
 * 좌표는 Z Fold 4 cover (904x2316) 기준 비율 — 다른 화면 비율은 (w, h) 로 스케일.
 *
 * 막대 색: 채워진 부분은 채도 높은 오렌지/주황 (#F0A040 부근)
 *         비어있는 부분은 옅은 회색/투명 (#E8E8E8 부근)
 *
 * 별 배지: 노란/주황 (#FFC107 부근) = 채워진 별, 흰색/연회색 = 빈 별
 */
object BarGraphAnalyzer {

    data class IvBars(val atk: Int, val def: Int, val sta: Int, val confidence: Float)
    data class StarBadge(val starsLit: Int, val totalStars: Int)

    // 마지막 분석 결과 (디버그용 — OverlayService 의 OCR 결과 보기 버튼에서 노출)
    @Volatile var lastDebugInfo: String = ""

    // ─── 막대 영역 좌표 (904x2316 비율)
    // 사용자 노고치 스크린샷 (904x2316) 측정 기준 보정:
    //   공격 ≈ y 1675 / 2316 = 0.723
    //   방어 ≈ y 1740 / 2316 = 0.751
    //   HP   ≈ y 1810 / 2316 = 0.781
    private const val BAR_X_FROM = 0.105f   // ≈ 95px
    private const val BAR_X_TO   = 0.430f   // ≈ 388px
    private val BAR_Y_ATK = 0.713f to 0.733f
    private val BAR_Y_DEF = 0.741f to 0.761f
    private val BAR_Y_HP  = 0.770f to 0.790f

    // ─── 별 배지 영역 (좌하단 원형 주황 배지)
    // 노고치 스크린샷: 배지 가운데 약 y 1450 / 2316 = 0.626
    private const val STAR_X_FROM = 0.020f
    private const val STAR_X_TO   = 0.230f
    private const val STAR_Y_FROM = 0.585f
    private const val STAR_Y_TO   = 0.685f

    /** detail 화면 캡처 비트맵에서 IV 3개 추출. 막대 안 보이면 null. */
    fun analyzeIvBars(bitmap: Bitmap): IvBars? {
        val w = bitmap.width
        val h = bitmap.height

        val atk = readBar(bitmap, w, h, BAR_Y_ATK)
        val def = readBar(bitmap, w, h, BAR_Y_DEF)
        val sta = readBar(bitmap, w, h, BAR_Y_HP)

        lastDebugInfo = "bitmap=${w}x${h} atk=${atk?.first}@conf${"%.2f".format(atk?.second ?: 0f)} " +
                        "def=${def?.first}@conf${"%.2f".format(def?.second ?: 0f)} " +
                        "sta=${sta?.first}@conf${"%.2f".format(sta?.second ?: 0f)}"

        if (atk == null || def == null || sta == null) return null
        // 셋 다 fillRatio 매우 낮으면 막대 없는 화면 (false positive 차단)
        // confidence threshold 낮춤 (0.45 → 0.20) — 막대 자체가 짧을 때도 검출
        val avgConf = (atk.second + def.second + sta.second) / 3f
        if (avgConf < 0.05f) return null
        return IvBars(atk.first.coerceIn(0, 15), def.first.coerceIn(0, 15), sta.first.coerceIn(0, 15), avgConf)
    }

    /** 좌하단 별 배지 — 칠해진 노란별 개수 (1-3). 배지 자체가 안 보이면 null. */
    fun analyzeStarBadge(bitmap: Bitmap): StarBadge? {
        val w = bitmap.width; val h = bitmap.height
        val x0 = (STAR_X_FROM * w).toInt(); val x1 = (STAR_X_TO * w).toInt()
        val y0 = (STAR_Y_FROM * h).toInt(); val y1 = (STAR_Y_TO * h).toInt()
        if (x1 <= x0 || y1 <= y0 || x1 > w || y1 > h) return null

        // 배지 자체 색 = 주황 원형 + 별 = 노란색
        // 칠해진 별만 pure 노랑, 비어있는 별은 회색/흰색
        // 노란색 픽셀 (R&G high, B low) 카운트해서 별 개수 추정
        var yellowPx = 0; var orangePx = 0; var totalSampled = 0
        val xs = (x0 until x1 step 3)
        val ys = (y0 until y1 step 3)
        for (y in ys) for (x in xs) {
            val c = bitmap.getPixel(x, y)
            val r = Color.red(c); val g = Color.green(c); val b = Color.blue(c)
            // 노랑 (별) — R&G 둘 다 높고 B 낮음
            if (r > 220 && g > 200 && b < 130) yellowPx++
            // 주황 (배지 배경)
            else if (r > 200 && g in 100..200 && b < 100) orangePx++
            totalSampled++
        }
        if (totalSampled == 0) return null
        val orangeRatio = orangePx.toFloat() / totalSampled

        // 배지 자체가 안 보이면 (주황 픽셀 거의 없음) → null
        if (orangeRatio < 0.05f) {
            lastDebugInfo += " | star: no badge (orange=${orangeRatio})"
            return null
        }

        val yellowRatio = yellowPx.toFloat() / totalSampled
        // 별 1개 ≈ 0.04~0.09, 2개 ≈ 0.10~0.16, 3개 ≈ 0.17+
        val stars = when {
            yellowRatio < 0.07f -> 1
            yellowRatio < 0.14f -> 2
            else -> 3
        }
        lastDebugInfo += " | star: $stars (orange=${"%.2f".format(orangeRatio)} yellow=${"%.2f".format(yellowRatio)})"
        return StarBadge(starsLit = stars, totalStars = 3)
    }

    /** 한 막대 row 분석 → (IV 0-15, confidence 0~1) 반환. null = 막대 없음. */
    private fun readBar(bm: Bitmap, w: Int, h: Int, yRange: Pair<Float, Float>): Pair<Int, Float>? {
        val xStart = (BAR_X_FROM * w).toInt()
        val xEnd   = (BAR_X_TO * w).toInt()
        val y0     = (yRange.first * h).toInt()
        val y1     = (yRange.second * h).toInt()
        if (xEnd <= xStart || y0 < 0 || y1 >= h || y1 <= y0) return null

        val barWidth = xEnd - xStart
        if (barWidth < 20) return null

        // 막대 height 의 여러 row 평균 (single-line 노이즈 방지)
        // 각 x 마다 yRange 내 픽셀 모두 검사, 1개라도 fill 색이면 filled 로 카운트
        var lastFilledX = -1
        var filledCount = 0
        val rows = (y0..y1 step 2).toList()
        for (x in xStart until xEnd) {
            var anyFilled = false
            for (y in rows) {
                if (isFillColor(bm.getPixel(x, y))) { anyFilled = true; break }
            }
            if (anyFilled) {
                filledCount++
                lastFilledX = x
            }
        }
        val fillRatio = filledCount.toFloat() / barWidth

        // 막대 자체를 못 찾으면 null (좌표 틀렸다는 신호 — false 0 반환 X)
        if (lastFilledX < 0 || filledCount < 3) return null

        // IV 0-15 — 막대는 3 segment (각 5 IV) 로 나뉨. lastFilledX 위치를 0-15 로 매핑.
        val pos = (lastFilledX - xStart + 1).toFloat() / barWidth
        val iv = (pos * 15f + 0.5f).toInt().coerceIn(0, 15)

        val conf = (fillRatio * 1.5f).coerceIn(0f, 1f)
        return iv to conf
    }

    /** Pokemon GO 의 IV 막대 색 — 진한 주황/노랑.
     *  여러 색조 (가벼운 베이지 ~ 진한 주황) 다 잡히게 관대하게 매칭. */
    private fun isFillColor(c: Int): Boolean {
        val r = Color.red(c); val g = Color.green(c); val b = Color.blue(c)
        // 주황 계열: R 가장 강하고 B 가장 약함, R-B 차이 큼
        val sat = saturation(r, g, b)
        return sat > 0.25f && r >= 180 && r > b + 50 && g in 80..230 && b < 160
    }

    private fun saturation(r: Int, g: Int, b: Int): Float {
        val mx = max(r, max(g, b)).toFloat()
        val mn = min(r, min(g, b)).toFloat()
        return if (mx <= 0.001f) 0f else (mx - mn) / mx
    }
}
