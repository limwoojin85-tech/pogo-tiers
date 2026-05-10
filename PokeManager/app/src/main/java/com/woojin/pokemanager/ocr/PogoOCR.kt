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

    // Pokémon GO 개체 화면에서 데이터를 OCR로 추출
    // cropRect: 분할화면에서 분석할 영역 (null이면 전체)
    suspend fun analyze(bitmap: Bitmap, cropRect: Rect? = null): PogoScreenData? {
        val src = if (cropRect != null) {
            Bitmap.createBitmap(bitmap, cropRect.left, cropRect.top, cropRect.width(), cropRect.height())
        } else bitmap

        // 두 OCR 동시 실행 — 라틴 (CP/HP/숫자) + 한글 (이름)
        val latinText = runOCR(src, latinRecognizer) ?: ""
        val koreanText = runOCR(src, koreanRecognizer) ?: ""
        val combined = "$latinText\n$koreanText"
        if (combined.isBlank()) return null
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

        val cp = extractCP(lines) ?: return null
        val hp = extractHP(lines) ?: return null
        // dust 는 강화 화면 전용 — detail 화면엔 없음. optional 로 둠 (없으면 0)
        val dust = extractDust(lines) ?: 0
        // 한글 OCR 결과에서 이름 추출 — Pokemon detail 화면 검증 ★강화
        val name = extractKoreanName(koLines) ?: extractName(lines, cp)
        // 박스 list 화면 false positive 방지 — 다음 조건 다 만족해야 detail 인정:
        //  1) 한글 이름 추출 됨 (박스 list 는 작은 폰트 + 잘린 이름이라 한글 OCR 거의 실패)
        //  2) HP "X / Y" 패턴 등장 (박스 list 는 HP 표시 X)
        //  3) Pokemon detail 의 "kg" 단위 (체중) 등장 — detail 만 표시. "m" 만 으로는 너무 약함 (오인 위험)
        if (name.isNullOrBlank() || name.length < 2) return null
        val hasWeight = lines.any { line ->
            line.contains("kg", ignoreCase = true) ||
            line.matches(Regex(""".*\d+\.\d+\s*kg.*""", RegexOption.IGNORE_CASE))
        }
        if (!hasWeight) return null

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
    private fun extractKoreanName(lines: List<String>): String? {
        val koPattern = Regex("[가-힣]")
        val candidates = lines.filter { line ->
            koPattern.containsMatchIn(line)
                && line.length in 2..15
                && !line.contains(Regex("""\d{2,}"""))    // 숫자 너무 많은 건 제외 (CP 등)
        }
        // 한글 비율 높은 순
        return candidates.maxByOrNull { line ->
            val koCount = line.count { it.code in 0xAC00..0xD7A3 }
            koCount * 100 - line.length  // 한글 많고 짧을수록 높음
        }
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
        for (line in lines) {
            // 별가루 수치 옆에 있는 숫자
            val nums = Regex("""\d{3,6}""").findAll(line).map { it.value.toInt() }
            for (n in nums) {
                if (n in dustValues) return n
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
