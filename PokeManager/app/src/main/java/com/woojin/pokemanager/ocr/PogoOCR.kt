package com.woojin.pokemanager.ocr

import android.graphics.Bitmap
import android.graphics.Rect
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

data class PogoScreenData(
    val pokemonName: String,
    val cp: Int,
    val hp: Int,
    val dustCost: Int,
    val isShadow: Boolean,
    val isPurified: Boolean
)

object PogoOCR {

    // 라틴 OCR — CP/HP/숫자 인식 (빠름)
    private val latinRecognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
    // 한글 OCR — 포켓몬 이름 인식 (한국어 모델)
    private val koreanRecognizer = TextRecognition.getClient(KoreanTextRecognizerOptions.Builder().build())

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
        if (combined.isBlank()) {
            lastFailReason = "OCR 결과 비어있음 (화면 캡처 실패 또는 빈 화면)"
            return null
        }
        return parsePogoScreen(combined, src.width, src.height, koreanText)
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

        val cp = extractCP(lines) ?: run {
            lastFailReason = "CP 인식 실패"
            return null
        }
        val hp = extractHP(lines) ?: run {
            lastFailReason = "HP 인식 실패 (X/Y 패턴 없음)"
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
        if (!hasWeight) {
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

    // 한글 이름 추출 — 한글이 포함된 라인 중 가장 길고 (5자 이내) 숫자/특수문자 적은 것
    // 추출 후 한글만 남겨서 정제 (연필 아이콘 ✏, 공백, 기호 제거 → "화살꼬빈 ✏" → "화살꼬빈")
    private fun extractKoreanName(lines: List<String>): String? {
        val koPattern = Regex("[가-힣]")
        val candidates = lines.filter { line ->
            koPattern.containsMatchIn(line)
                && line.length in 2..15
                && !line.contains(Regex("""\d{2,}"""))    // 숫자 너무 많은 건 제외 (CP 등)
                // PokeManager 자체 UI 텍스트 차단 (앱 하나 모드 잘못 선택 시 false-name 방지)
                && !line.contains("캡처") && !line.contains("오버레이")
                && !line.contains("포고만") && !line.contains("앱하나")
                && !line.contains("PokeManager") && !line.contains("pokemanager")
                // 자기 result overlay 의 텍스트 (자기 자신 OCR 노이즈 방지)
                && !line.contains("포켓몬데이터")
                && !line.contains("데이터없음") && !line.contains("데이터 없음")
                && !line.contains("계산불가") && !line.contains("계산 불가")
                && !line.contains("결정:") && !line.contains("리그")
                && !line.contains("순위") && !line.contains("저장")
        }
        // 한글 비율 높은 순
        val raw = candidates.maxByOrNull { line ->
            val koCount = line.count { it.code in 0xAC00..0xD7A3 }
            koCount * 100 - line.length  // 한글 많고 짧을수록 높음
        } ?: return null

        // 한글만 남김 — "화살꼬빈 ✏" → "화살꼬빈"
        val cleaned = raw.filter { it.code in 0xAC00..0xD7A3 }
        return if (cleaned.length >= 2) cleaned else raw.trim().takeIf { it.isNotEmpty() }
    }

    private fun extractCP(lines: List<String>): Int? {
        // CP NNN 또는 CP: NNN 패턴
        for (line in lines) {
            val m = Regex("""(?i)cp\s*[:\-]?\s*(\d{1,5})""").find(line)
            if (m != null) return m.groupValues[1].toIntOrNull()
        }
        // 첫 번째 큰 숫자 (보통 상단에 위치)
        for (line in lines.take(5)) {
            val m = Regex("""^\d{1,5}$""").find(line.trim())
            if (m != null) {
                val v = m.value.toInt()
                if (v in 10..10000) return v
            }
        }
        return null
    }

    private fun extractHP(lines: List<String>): Int? {
        for (line in lines) {
            // "HP NNN/NNN" 또는 "NNN / NNN HP" 패턴
            val m = Regex("""(\d{1,4})\s*/\s*(\d{1,4})""").find(line)
            if (m != null) return m.groupValues[2].toIntOrNull()
        }
        for (line in lines) {
            val m = Regex("""(?i)hp\s*[:\-]?\s*(\d{1,4})""").find(line)
            if (m != null) return m.groupValues[1].toIntOrNull()
        }
        return null
    }

    private fun extractDust(lines: List<String>): Int? {
        val dustValues = setOf(200,400,600,800,1000,1300,1600,1900,2200,2500,
            3000,3500,4000,4500,5000,6000,7000,8000,9000,10000,
            11000,12000,13000,14000,15000,16000,17000,18000,19000,20000)

        // 1단계: 각 라인 + 라인 결합 (강화 버튼 옆 작은 박스의 "2,500" 처리)
        // OCR 가 "2,500" 을 "2,500" 또는 "2 500" 또는 "2.500" 으로 잡을 수 있음
        for (rawLine in lines) {
            // 콤마/점/공백 제거 후 숫자 검사
            val cleaned = rawLine.replace(Regex("""[,.\s](?=\d{3})"""), "")
            val nums = Regex("""\d{3,6}""").findAll(cleaned).map { it.value.toInt() }.toList()
            for (n in nums) {
                if (n in dustValues) return n
            }
            // 또한 별의모래 (총 보유량 — 1,687,937 같은 큰 수) 다음/이전 라인의 작은 수도 검사
        }

        // 2단계: 강화 버튼 영역 — "강화" 단어 + 같은/다음 라인의 별가루 비용
        // detail 화면 강화 버튼은 작아서 OCR 이 별도 라인으로 잡을 가능성. 인접 라인 페어 검사.
        for (i in lines.indices) {
            val line = lines[i]
            if (line.contains("강화") || line.contains("power", true)) {
                // 같은 + 인접 (전후 2줄) 검사
                val window = (maxOf(0, i-1)..minOf(lines.lastIndex, i+2)).joinToString(" ") { lines[it] }
                val cleaned = window.replace(Regex("""[,.\s](?=\d{3})"""), "")
                val nums = Regex("""\d{3,6}""").findAll(cleaned).map { it.value.toInt() }.toList()
                for (n in nums) {
                    // 별의모래 총량 (보통 100k+) 은 dust 가 아님
                    if (n in dustValues && n < 100000) return n
                }
            }
        }
        return null
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
