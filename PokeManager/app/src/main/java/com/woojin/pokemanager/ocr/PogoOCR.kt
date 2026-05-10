package com.woojin.pokemanager.ocr

import android.graphics.Bitmap
import android.graphics.Rect
import android.util.Log
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

private const val TAG = "PokeManager-OCR"

data class PogoScreenData(
    val pokemonName: String,
    val cp: Int,
    val hp: Int,
    val dustCost: Int,
    val isShadow: Boolean,
    val isPurified: Boolean,
    // detail 화면 막대 그래프에서 직접 읽은 IV (정확도↑) — null 이면 못 읽음
    val ivBarsAtk: Int? = null,
    val ivBarsDef: Int? = null,
    val ivBarsSta: Int? = null,
    // 좌하단 별 배지의 칠해진 별 개수 (1-3) — IV 합 등급
    val starsLit: Int? = null,
    // 조사하기 화면 텍스트 분석 결과 (있으면 IV 정확도 결정)
    val appraisal: AppraisalAnalyzer.AppraisalData? = null
)

object PogoOCR {

    // 라틴 OCR — CP/HP/숫자 인식 (빠름)
    private val latinRecognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
    // 한글 OCR — 포켓몬 이름 인식 (한국어 모델)
    private val koreanRecognizer = TextRecognition.getClient(KoreanTextRecognizerOptions.Builder().build())

    // species 한글명 set — OverlayService 에서 GameMasterRepo 로 채움. 이름 추출 시 이 set 와 매칭.
    @Volatile var speciesNamesKo: Set<String> = emptySet()

    // 마지막 OCR 결과 — 분석 실패 시 디버그용 (사용자가 정보 제공할 수 있게)
    @Volatile var lastOcrLatin: String = ""
    @Volatile var lastOcrKorean: String = ""
    @Volatile var lastFailReason: String = ""

    // Pokémon GO 개체 화면에서 데이터를 OCR로 추출
    // cropRect: 분할화면에서 분석할 영역 (null이면 전체)
    suspend fun analyze(bitmap: Bitmap, cropRect: Rect? = null): PogoScreenData? {
        val src = if (cropRect != null) {
            Bitmap.createBitmap(bitmap, cropRect.left, cropRect.top, cropRect.width(), cropRect.height())
        } else bitmap

        // 두 OCR 동시 실행 — 라틴 (CP/HP/숫자) + 한글 (이름)
        val latinText = runOCR(src, latinRecognizer) ?: ""
        val koreanText = runOCR(src, koreanRecognizer) ?: ""
        lastOcrLatin = latinText
        lastOcrKorean = koreanText

        val combined = "$latinText\n$koreanText"
        Log.i(TAG, "===== analyze() bitmap=${src.width}x${src.height} =====")
        Log.i(TAG, "LATIN OCR (${latinText.length} chars):")
        latinText.lines().take(20).forEach { if (it.isNotBlank()) Log.i(TAG, "  $it") }
        Log.i(TAG, "KOREAN OCR (${koreanText.length} chars):")
        koreanText.lines().take(20).forEach { if (it.isNotBlank()) Log.i(TAG, "  $it") }
        if (combined.isBlank()) {
            lastFailReason = "OCR 결과 비어있음 (화면 캡처 실패 또는 빈 화면)"
            Log.w(TAG, "FAIL: $lastFailReason")
            return null
        }
        // text-based parsing → CP/HP/이름/별가루
        val base = parsePogoScreen(combined, src.width, src.height, koreanText) ?: return null

        // IV 막대 그래프 + 별 배지 픽셀 분석 — 진짜 IV 직접 추출
        val bars = BarGraphAnalyzer.analyzeIvBars(src)
        val badge = BarGraphAnalyzer.analyzeStarBadge(src)

        // 조사하기 화면이면 텍스트 분석 — 진짜 IV 정확도 (Calcy/PokeGenie 방식)
        val appraisal = if (AppraisalAnalyzer.isAppraisalScreen(combined)) {
            AppraisalAnalyzer.analyze(combined)
        } else null

        Log.i(TAG, "PARSED: name=${base.pokemonName} cp=${base.cp} hp=${base.hp} dust=${base.dustCost} " +
                   "shadow=${base.isShadow} purified=${base.isPurified}")
        Log.i(TAG, "BARS: atk=${bars?.atk} def=${bars?.def} sta=${bars?.sta} conf=${bars?.confidence}")
        Log.i(TAG, "STAR: ${badge?.starsLit}")
        Log.i(TAG, "APPRAISAL: tier=${appraisal?.tier} bestStat=${appraisal?.bestStat} statTier=${appraisal?.bestStatTier}")
        Log.i(TAG, "BarGraphAnalyzer.lastDebugInfo: ${BarGraphAnalyzer.lastDebugInfo}")

        return base.copy(
            ivBarsAtk = bars?.atk,
            ivBarsDef = bars?.def,
            ivBarsSta = bars?.sta,
            starsLit = badge?.starsLit,
            appraisal = appraisal
        )
    }

    private suspend fun runOCR(bitmap: Bitmap, recognizer: com.google.mlkit.vision.text.TextRecognizer): String? =
        suspendCancellableCoroutine { cont ->
            val image = InputImage.fromBitmap(bitmap, 0)
            recognizer.process(image)
                .addOnSuccessListener { result -> cont.resume(result.text) }
                .addOnFailureListener { cont.resume(null) }
        }

    private fun parsePogoScreen(text: String, width: Int, height: Int, koreanText: String = ""): PogoScreenData? {
        val lines = text.lines().map { it.trim() }.filter { it.isNotEmpty() }
        val koLines = koreanText.lines().map { it.trim() }.filter { it.isNotEmpty() }

        // 조사하기 화면은 detail 위에 모달 — CP/HP/이름이 가려져 있을 수 있음.
        // 조사하기 키워드만 있고 detail 정보 부족하면 이름만 추출 후 minimal 결과 반환.
        val isAppraisal = AppraisalAnalyzer.isAppraisalScreen(text)

        val cp = extractCP(lines) ?: run {
            if (!isAppraisal) lastFailReason = "CP 인식 실패"
            // 조사하기 화면은 CP 없어도 OK — minimal data 반환
            if (isAppraisal) return makeAppraisalOnlyData(koLines)
            return null
        }
        val hp = extractHP(lines) ?: run {
            if (!isAppraisal) lastFailReason = "HP 인식 실패 (X/Y 패턴 없음)"
            if (isAppraisal) return makeAppraisalOnlyData(koLines).copy(cp = cp)
            return null
        }
        // dust 는 강화 화면 전용 — detail 화면엔 없음. optional 로 둠 (없으면 0)
        val dust = extractDust(lines) ?: 0
        // 한글 OCR 결과에서 이름 추출 — Pokemon detail 화면 검증 ★강화
        val name = extractKoreanName(koLines) ?: extractName(lines, cp)
        // 박스 list 화면 false positive 방지 — 다음 조건 다 만족해야 detail 인정:
        //  1) 한글 이름 추출 됨 (박스 list 는 작은 폰트 + 잘린 이름이라 한글 OCR 거의 실패)
        //  2) HP "X / Y" 패턴 등장 (박스 list 는 HP 표시 X)
        //  3) Pokemon detail 의 "kg" 단위 (체중) 등장 — detail 만 표시. "m" 만 으로는 너무 약함 (오인 위험)
        if (name.isNullOrBlank() || name.length < 2) {
            lastFailReason = "한글 이름 인식 실패"
            return null
        }
        val hasWeight = lines.any { line ->
            line.contains("kg", ignoreCase = true) ||
            line.matches(Regex(""".*\d+\.\d+\s*kg.*""", RegexOption.IGNORE_CASE))
        }
        // 조사하기 화면이면 kg 가드 skip (조사하기 위에 detail 가려짐)
        if (!hasWeight && !isAppraisal) {
            lastFailReason = "체중 (kg) 인식 실패 — detail 화면 아닌 것으로 판단 (박스 list)"
            return null
        }
        lastFailReason = ""

        val isShadow = lines.any { it.contains("shadow", ignoreCase = true) || it.contains("그림자") }
            || koLines.any { it.contains("그림자") }
        val isPurified = lines.any { it.contains("purified", ignoreCase = true) || it.contains("정화") }
            || koLines.any { it.contains("정화") }

        return PogoScreenData(
            pokemonName = name,
            cp = cp, hp = hp, dustCost = dust,
            isShadow = isShadow, isPurified = isPurified
        )
    }

    // 조사하기 화면 전용 minimal 데이터 — 이름만 추출, CP/HP 는 0
    private fun makeAppraisalOnlyData(koLines: List<String>): PogoScreenData {
        val name = extractKoreanName(koLines) ?: ""
        return PogoScreenData(
            pokemonName = name,
            cp = 0, hp = 0, dustCost = 0,
            isShadow = false, isPurified = false
        )
    }

    // 한글 이름 추출 — speciesNamesKo set 와 매칭되는 단어만 인정.
    // 문제: "이상해꽃" detail 인데 "이상해씨의 사탕XL" 라인이 먼저 와서 "이상해씨" 로 매칭되는 케이스.
    // → Pass 1 (정확 매칭) 을 모든 라인에 먼저 적용 → 정확 매칭이 진짜 이름.
    private fun extractKoreanName(lines: List<String>): String? {
        val names = speciesNamesKo
        if (names.isEmpty()) return extractKoreanNameLoose(lines)

        // 사탕/별가루/장소 같은 noise 라인은 reject
        val noiseKeywords = listOf("사탕", "별의", "모래", "잡은 날", "장소", "대한민국", "인천", "서울", "경기")

        // Pass 1: 정확 매칭 (가장 신뢰 높음)
        for (rawLine in lines) {
            if (noiseKeywords.any { rawLine.contains(it) }) continue
            val ko = rawLine.filter { it.code in 0xAC00..0xD7A3 }
            if (ko.length >= 2 && ko in names) return ko
        }
        // Pass 2: substring 매칭 (noise 라인 제외 후)
        for (rawLine in lines) {
            if (noiseKeywords.any { rawLine.contains(it) }) continue
            val ko = rawLine.filter { it.code in 0xAC00..0xD7A3 }
            if (ko.length < 2) continue
            val match = names.firstOrNull { it.length >= 2 && ko.contains(it) }
            if (match != null) return match
        }
        // Pass 3: startsWith (OCR 가 짧게 자른 경우 — "썬더" → "썬더라이")
        for (rawLine in lines) {
            if (noiseKeywords.any { rawLine.contains(it) }) continue
            val ko = rawLine.filter { it.code in 0xAC00..0xD7A3 }
            if (ko.length < 2) continue
            val match = names.filter { it.startsWith(ko) && it.length <= ko.length + 4 }
                .minByOrNull { it.length }
            if (match != null) return match
        }
        return null
    }

    // 옛 fallback (DB 없을 때만)
    private fun extractKoreanNameLoose(lines: List<String>): String? {
        val koPattern = Regex("[가-힣]")
        val candidates = lines.filter { line ->
            koPattern.containsMatchIn(line)
                && line.length in 2..15
                && !line.contains(Regex("""\d{2,}"""))
        }
        val raw = candidates.maxByOrNull { it.count { c -> c.code in 0xAC00..0xD7A3 } } ?: return null
        val cleaned = raw.filter { it.code in 0xAC00..0xD7A3 }
        return if (cleaned.length >= 2) cleaned else null
    }

    private fun extractCP(lines: List<String>): Int? {
        // CP NNN / CP: NNN / cP382 / cp382 — "CP" 키워드 + 숫자 결합 형태만 인정
        // detail 화면 상단의 "CP382" 만 매칭. 사탕 ("27") / 별가루 ("2,500") false-positive 방지.
        for (line in lines) {
            val m = Regex("""(?i)\bcp\s*[:\-]?\s*(\d{1,5})\b""").find(line)
            if (m != null) {
                val v = m.groupValues[1].toIntOrNull() ?: continue
                if (v in 10..10000) return v
            }
        }
        return null
    }

    private fun extractHP(lines: List<String>): Int? {
        // 1순위: "HP" 단어가 같은 라인 X/Y (예: "78 / 78 HP")
        for (line in lines) {
            if (!line.contains("HP", ignoreCase = true)) continue
            val m = Regex("""(\d{1,4})\s*/\s*(\d{1,4})""").find(line)
            if (m != null) {
                val cur = m.groupValues[1].toIntOrNull() ?: continue
                val max = m.groupValues[2].toIntOrNull() ?: continue
                if (max in 1..9999 && cur <= max) return max
            }
        }
        // 2순위: "X / Y" 단독 라인 + 인접 라인에 HP — OCR 가 "65 / 65" 와 "HP" 분리한 경우
        for (i in lines.indices) {
            val m = Regex("""^\s*(\d{1,4})\s*/\s*(\d{1,4})\s*$""").find(lines[i]) ?: continue
            val cur = m.groupValues[1].toIntOrNull() ?: continue
            val max = m.groupValues[2].toIntOrNull() ?: continue
            if (max !in 1..9999 || cur > max) continue
            // ±1 라인에 HP 단어 있나
            val nearby = (maxOf(0, i-1)..minOf(lines.lastIndex, i+1))
                .any { lines[it].contains("HP", ignoreCase = true) }
            if (nearby && cur == max) return max
        }
        // 3순위: "X / Y" 단독에서 cur == max (포고 detail 의 풀체력 확실)
        for (line in lines) {
            val m = Regex("""^\s*(\d{1,4})\s*/\s*(\d{1,4})\s*$""").find(line) ?: continue
            val cur = m.groupValues[1].toIntOrNull() ?: continue
            val max = m.groupValues[2].toIntOrNull() ?: continue
            if (max in 10..9999 && cur == max) return max
        }
        return null
    }

    private fun extractDust(lines: List<String>): Int? {
        val dustValues = setOf(200,400,600,800,1000,1300,1600,1900,2200,2500,
            3000,3500,4000,4500,5000,6000,7000,8000,9000,10000,
            11000,12000,13000,14000,15000,16000,17000,18000,19000,20000)

        // OCR 노이즈 정규화 — Q/O→0, l/I→1, S→5, B→8 (Pokemon GO 강화 비용 텍스트 자주 잘못 인식)
        val whole = lines.joinToString(" ")
            .replace('Q', '0').replace('O', '0').replace('o', '0')
            .replace('l', '1').replace('I', '1')
            .replace('S', '5')
            .replace('B', '8')
        // 천단위 구분 제거 ("1,90Q" → "1,900" → "1900")
        val cleaned = whole.replace(Regex("""(?<=\d)[,.\s](?=\d{3}(?!\d))"""), "")
        val nums = Regex("""\d{2,7}""").findAll(cleaned).map { it.value.toInt() }.toList()

        // 별의모래 보유량 (예: 1,687,937 → 1687937) 제외
        // dustValues 에 정확 일치하는 가장 작은 수 우선 (사탕 수량 false-positive 방지: 261, 327, 19, 27, 42 같은 건 dustValues 에 없음)
        val candidates = nums.filter { it in dustValues && it < 100_000 }
        if (candidates.isEmpty()) return null

        // 강화 단어 근처 우선 — "강화" 단어가 있는 라인 + ±2줄 안에 있는 dust 값
        for (i in lines.indices) {
            if (!lines[i].contains("강화") && !lines[i].contains("power", true)) continue
            val window = (maxOf(0, i-1)..minOf(lines.lastIndex, i+2))
                .joinToString(" ") { lines[it] }
                .replace(Regex("""(?<=\d)[,.\s](?=\d{3}(?!\d))"""), "")
            val winNums = Regex("""\d{2,7}""").findAll(window).map { it.value.toInt() }.toList()
            val winCand = winNums.firstOrNull { it in dustValues && it < 100_000 }
            if (winCand != null) return winCand
        }

        // 강화 단어 매칭 실패 시 — 전체에서 가장 흔한 / 가장 작은 dust value
        return candidates.minOrNull()
    }

    private fun extractName(lines: List<String>, cp: Int): String? {
        // CP 숫자보다 앞에 있는 라인이 이름일 가능성이 높음
        // 숫자만으로 구성되지 않은 단어들 중 중간 길이의 것 선택
        for (line in lines) {
            if (line.all { it.isDigit() || it.isWhitespace() }) continue
            if (line.length in 2..20 && !line.contains(Regex("""[/\\@#$%]"""))) {
                if (!line.matches(Regex(""".*\d{3,}.*"""))) return line
            }
        }
        return null
    }

    // 현재 화면이 포고 개체 상세 화면인지 빠르게 판단
    fun isPogoInfoScreen(text: String): Boolean {
        val hasCP = text.contains(Regex("""(?i)cp\s*\d""")) ||
                    text.lines().any { it.trim().matches(Regex("""\d{1,5}""")) }
        val hasDust = text.contains(Regex("""\b(200|400|600|800|1[03-9]00|[2-9]\d00|1[0-9]000|20000)\b"""))
        val hasHP = text.contains(Regex("""\d{1,4}\s*/\s*\d{1,4}""")) ||
                    text.contains(Regex("""(?i)hp"""))
        return hasCP && (hasDust || hasHP)
    }
}
