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
    data class StarBadge(val starsLit: Int, val totalStars: Int)  // ex (1, 3) = 1성 / 3-star scale

    // ─── 막대 영역 좌표 (904x2316 비율)
    // 그래프 시작점은 화면 좌측 ~100px, 너비 ~270px (전체의 ~30%)
    // y 위치: 화면 78~91% 사이에 3 row
    private const val BAR_X_FROM = 0.110f   // ≈ 100px
    private const val BAR_X_TO   = 0.470f   // ≈ 425px (15칸 × 약 22px)
    private val BAR_Y_ATK = 0.790f to 0.812f
    private val BAR_Y_DEF = 0.838f to 0.860f
    private val BAR_Y_HP  = 0.886f to 0.908f

    // ─── 별 배지 영역 (좌하단 원형 주황 배지)
    private const val STAR_X_FROM = 0.030f
    private const val STAR_X_TO   = 0.220f
    private const val STAR_Y_FROM = 0.690f
    private const val STAR_Y_TO   = 0.780f

    /** detail 화면 캡처 비트맵에서 IV 3개 추출. 막대 안 보이면 null. */
    fun analyzeIvBars(bitmap: Bitmap): IvBars? {
        val w = bitmap.width
        val h = bitmap.height

        val atk = readBar(bitmap, w, h, BAR_Y_ATK)
        val def = readBar(bitmap, w, h, BAR_Y_DEF)
        val sta = readBar(bitmap, w, h, BAR_Y_HP)

        // confidence: 세 막대 다 0~15 사이 + 너무 균등하지 않음 (false positive 차단)
        val all = listOf(atk?.first, def?.first, sta?.first)
        if (all.any { it == null }) return null
        val sumConf = (atk!!.second + def!!.second + sta!!.second) / 3f
        if (sumConf < 0.45f) return null  // 채워진 픽셀 비율 너무 낮으면 막대 없는 화면
        return IvBars(atk.first.coerceIn(0, 15), def.first.coerceIn(0, 15), sta.first.coerceIn(0, 15), sumConf)
    }

    /** 별 배지에서 칠해진 별 개수 (1-4 또는 1-3). null 이면 배지 없음. */
    fun analyzeStarBadge(bitmap: Bitmap): StarBadge? {
        val w = bitmap.width; val h = bitmap.height
        val x0 = (STAR_X_FROM * w).toInt(); val x1 = (STAR_X_TO * w).toInt()
        val y0 = (STAR_Y_FROM * h).toInt(); val y1 = (STAR_Y_TO * h).toInt()
        if (x1 <= x0 || y1 <= y0 || x1 > w || y1 > h) return null

        // 노란/주황 (밝은 채도 높은 노란색) 픽셀 카운트
        var litPx = 0; var totalSampled = 0
        val xs = (x0 until x1 step 4)
        val ys = (y0 until y1 step 4)
        for (y in ys) for (x in xs) {
            val c = bitmap.getPixel(x, y)
            val r = Color.red(c); val g = Color.green(c); val b = Color.blue(c)
            // 진한 노랑/주황: R high, G mid-high, B low, saturation 높음
            if (r > 200 && g in 130..220 && b < 120 && (r - b) > 100) litPx++
            totalSampled++
        }
        if (totalSampled == 0) return null
        val ratio = litPx.toFloat() / totalSampled

        // 별 배지가 보이지 않으면 ratio 매우 낮음
        if (ratio < 0.05f) return null

        // 최대 별 3개 (포고는 IV 합 23+ = 2성, 37+ = 3성, 45 = 4성 — 이지만 detail 의 작은 배지는 보통 3성 표시)
        // 별 1개 ≈ ratio 0.06~0.12, 2개 ≈ 0.15~0.22, 3개 ≈ 0.25+
        val stars = when {
            ratio < 0.13f -> 1
            ratio < 0.22f -> 2
            else -> 3
        }
        return StarBadge(starsLit = stars, totalStars = 3)
    }

    /** 한 막대 row 분석 → (IV 0-15, confidence 0~1) 반환. null = 막대 없음. */
    private fun readBar(bm: Bitmap, w: Int, h: Int, yRange: Pair<Float, Float>): Pair<Int, Float>? {
        val xStart = (BAR_X_FROM * w).toInt()
        val xEnd   = (BAR_X_TO * w).toInt()
        val yMid   = (((yRange.first + yRange.second) / 2f) * h).toInt()
        if (xEnd <= xStart || yMid !in 0 until h) return null

        // 막대 height 의 가운데 line 한 줄 sampling (속도) — 노이즈 적음
        val barWidth = xEnd - xStart
        if (barWidth < 20) return null

        // 좌→우 스캔, "채워진" 픽셀 (채도 높은 주황) vs "빈" (저채도) 분리
        var lastFilledX = -1
        var filledCount = 0
        var totalCount = 0
        for (x in xStart until xEnd) {
            val c = bm.getPixel(x, yMid)
            val r = Color.red(c); val g = Color.green(c); val b = Color.blue(c)
            // 주황/노랑 채워진 픽셀 — Pokemon GO 의 IV 막대 색 (#F0A040 부근)
            // 또는 진한 회색 (필요 시 두 번째 색 검출)
            val sat = saturation(r, g, b)
            val isFilled = sat > 0.30f && r > 180 && g in 100..200 && b < 130
            if (isFilled) {
                filledCount++
                lastFilledX = x
            }
            totalCount++
        }
        if (totalCount == 0) return null
        val fillRatio = filledCount.toFloat() / totalCount

        // 막대가 거의 안 보이면 (배경만) 분석 실패
        if (fillRatio < 0.02f && lastFilledX < 0) return null

        // IV 0-15 — fillRatio × 15. 가장 가까운 정수.
        // 단 5칸 segment 마다 작은 gap (회색 칸) 이 있어 fill 비율이 정확히 N/15 가 아닐 수 있음.
        // → lastFilledX 까지의 거리 비율 사용 (더 정확)
        val iv = if (lastFilledX >= 0) {
            val pos = (lastFilledX - xStart + 1).toFloat() / barWidth
            (pos * 15f + 0.4f).toInt().coerceIn(0, 15)
        } else {
            (fillRatio * 15f + 0.5f).toInt().coerceIn(0, 15)
        }

        // confidence — fillRatio 기반 (낮으면 막대 없는 화면일 가능성)
        val conf = (fillRatio * 2f).coerceIn(0f, 1f)
        return iv to conf
    }

    private fun saturation(r: Int, g: Int, b: Int): Float {
        val mx = max(r, max(g, b)).toFloat()
        val mn = min(r, min(g, b)).toFloat()
        return if (mx <= 0.001f) 0f else (mx - mn) / mx
    }
}
