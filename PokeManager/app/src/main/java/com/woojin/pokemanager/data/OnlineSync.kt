package com.woojin.pokemanager.data

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * 사이트 (limwoojin85-tech.github.io/pogo-tiers) 의 최신 데이터를 가져와
 * 앱의 assets 데이터를 갱신.
 *
 * 사이트 must_have.json 이 매일 06:00 KST 자동 갱신됨.
 * 이 sync 는 사용자 트리거 (설정 → "데이터 갱신") 으로 수동 호출.
 */
object OnlineSync {

    private const val BASE_URL = "https://limwoojin85-tech.github.io/pogo-tiers"
    private const val MUST_HAVE_URL = "$BASE_URL/must_have.json"
    private const val LOCAL_DIR = "synced_data"

    /** 캐시 파일 위치 (assets 가 아닌 internal storage) */
    private fun cacheFile(context: Context, name: String): File {
        val dir = File(context.filesDir, LOCAL_DIR)
        if (!dir.exists()) dir.mkdirs()
        return File(dir, name)
    }

    /** 사이트의 최신 must_have.json 다운로드 + 캐시 */
    suspend fun syncMustHave(context: Context): SyncResult = withContext(Dispatchers.IO) {
        try {
            val conn = URL(MUST_HAVE_URL).openConnection() as HttpURLConnection
            conn.connectTimeout = 10000
            conn.readTimeout = 30000
            conn.requestMethod = "GET"
            val text = conn.inputStream.bufferedReader().readText()
            conn.disconnect()

            // 캐시 저장
            val file = cacheFile(context, "must_have.json")
            file.writeText(text)
            SyncResult.Success(file.length())
        } catch (e: Exception) {
            SyncResult.Failure(e.message ?: "알 수 없는 오류")
        }
    }

    /** 캐시된 데이터 사용 가능한지 */
    fun hasCachedData(context: Context): Boolean = cacheFile(context, "must_have.json").exists()

    /** 캐시 마지막 갱신 시간 */
    fun lastSyncTime(context: Context): Long {
        val f = cacheFile(context, "must_have.json")
        return if (f.exists()) f.lastModified() else 0
    }
}

sealed class SyncResult {
    data class Success(val sizeBytes: Long) : SyncResult()
    data class Failure(val message: String) : SyncResult()
}
