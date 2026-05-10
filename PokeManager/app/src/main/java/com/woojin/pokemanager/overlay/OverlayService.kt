package com.woojin.pokemanager.overlay

import android.app.*
import android.content.*
import android.content.pm.ServiceInfo
import android.graphics.*
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.*
import android.view.*
import android.widget.*
import androidx.core.app.NotificationCompat
import com.woojin.pokemanager.R
import android.content.ClipData
import android.content.ClipboardManager
import com.woojin.pokemanager.calc.BucketClassifier
import com.woojin.pokemanager.calc.IVCalculator
import com.woojin.pokemanager.calc.PvPRanker
import com.woojin.pokemanager.data.AppDatabase
import com.woojin.pokemanager.data.GameMasterRepo
import com.woojin.pokemanager.data.MyPokemon
import com.woojin.pokemanager.ocr.PogoOCR
import kotlinx.coroutines.*

class OverlayService : Service() {

    companion object {
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"
        const val CHANNEL_ID = "pokemanager_overlay"
        const val NOTIF_ID = 1001

        // 분할화면 모드:
        //  0 = 전체 / 단일 (앱 하나 모드 + 일반 화면)
        //  1 = 상단 절반   2 = 하단 절반
        //  3 = 좌측 절반   4 = 우측 절반
        var splitMode: Int = 0
        var isRunning = false

        // 사용자가 매뉴얼로 선택한 캡처 모드 — "single" (앱 하나) / "full" (전체)
        // single 일 땐 splitMode 무시 (이미 단일 앱만 캡처됨)
        var captureMode: String = "full"
    }

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var mediaProjection: MediaProjection? = null
    private var imageReader: ImageReader? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var windowManager: WindowManager? = null

    // 오버레이 뷰들
    private var fabView: View? = null
    private var resultView: View? = null

    // 자동 스캔 상태
    private var autoScanJob: Job? = null
    private var lastAnalyzedText = ""
    private var resultVisible = false

    // 분할화면에서 FAB 위치로 분석 영역 결정
    private var fabY = 0f

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        GameMasterRepo.load(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Android 14 (SDK 34)+ 는 startForeground 에 type 명시 필수 (mediaProjection)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIF_ID, buildNotification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
            )
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIF_ID, buildNotification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
            )
        } else {
            startForeground(NOTIF_ID, buildNotification())
        }

        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED) ?: return START_NOT_STICKY
        val resultData = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent::class.java)
        else @Suppress("DEPRECATION") intent.getParcelableExtra(EXTRA_RESULT_DATA)

        if (resultCode == Activity.RESULT_OK && resultData != null) {
            val mgr = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            mediaProjection = mgr.getMediaProjection(resultCode, resultData)
            // Android 14+ 필수 — registerCallback 안 하면 즉시 stop 됨
            mediaProjection?.registerCallback(object : MediaProjection.Callback() {
                override fun onStop() {
                    isRunning = false
                    stopSelf()
                }
            }, Handler(Looper.getMainLooper()))
            setupCapture()
            showFab()
            startAutoScan()
            isRunning = true
        }

        return START_STICKY
    }

    private fun setupCapture() {
        val metrics = resources.displayMetrics
        val w = metrics.widthPixels
        val h = metrics.heightPixels
        val dpi = metrics.densityDpi

        imageReader = ImageReader.newInstance(w, h, PixelFormat.RGBA_8888, 2)
        virtualDisplay = mediaProjection!!.createVirtualDisplay(
            "PokeManagerCapture", w, h, dpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader!!.surface, null, null
        )
    }

    private fun captureBitmap(): Bitmap? {
        val image = imageReader?.acquireLatestImage() ?: return null
        return try {
            val planes = image.planes
            val buffer = planes[0].buffer
            val pixelStride = planes[0].pixelStride
            val rowStride = planes[0].rowStride
            val rowPadding = rowStride - pixelStride * image.width
            val bitmap = Bitmap.createBitmap(
                image.width + rowPadding / pixelStride, image.height, Bitmap.Config.ARGB_8888
            )
            bitmap.copyPixelsFromBuffer(buffer)
            Bitmap.createBitmap(bitmap, 0, 0, image.width, image.height)
        } finally {
            image.close()
        }
    }

    private fun getCropRect(bitmapWidth: Int, bitmapHeight: Int): Rect? {
        // "앱 하나" 모드 — MediaProjection 이 단일 앱만 캡처 → 분할 무시
        if (captureMode == "single") return null
        return when (splitMode) {
            1 -> Rect(0, 0, bitmapWidth, bitmapHeight / 2)            // 상단 절반
            2 -> Rect(0, bitmapHeight / 2, bitmapWidth, bitmapHeight) // 하단 절반
            3 -> Rect(0, 0, bitmapWidth / 2, bitmapHeight)            // 좌측 절반
            4 -> Rect(bitmapWidth / 2, 0, bitmapWidth, bitmapHeight)  // 우측 절반
            else -> null  // 전체 화면
        }
    }

    // 현재 splitMode 에서 분석된 결과는 어느 프로필로 저장? (분할화면당 계정 분리)
    private fun currentProfile(): String = when (splitMode) {
        1, 3 -> "split_a"  // 상단 / 좌측 = 계정 A
        2, 4 -> "split_b"  // 하단 / 우측 = 계정 B
        else -> "main"
    }

    // 분할 모드 자동 감지 — bitmap 의 가로/세로 비율로 판단
    // 폴드 inner 펼친 상태(가로 길고) + 분할 캡처 시 좌/우 분할 우세
    // 일반 폰 세로 + 분할 캡처 시 위/아래 분할 우세
    private fun detectSplitOrientation(w: Int, h: Int): Boolean = w >= h  // true=좌우분할 모드

    // 자동 스캔: 1초마다 화면 캡처 → 포고 화면 감지 → 자동 분석
    // 분할화면 모드일 때 — splitMode 가 0 (auto) 이면 양쪽 영역 다 시도해서 hit 한 쪽으로 라우팅
    private fun startAutoScan() {
        autoScanJob = scope.launch(Dispatchers.IO) {
            while (isActive) {
                delay(1000)
                try {
                    val bitmap = captureBitmap() ?: continue

                    // 캡처 mode 가 single 이면 그냥 전체 분석
                    if (captureMode == "single") {
                        analyzeRegion(bitmap, null, "main")
                        continue
                    }

                    // splitMode 가 명시 (1~4) 면 그 영역만
                    if (splitMode in 1..4) {
                        val crop = getCropRect(bitmap.width, bitmap.height)
                        analyzeRegion(bitmap, crop, currentProfile())
                        continue
                    }

                    // splitMode = 0 (auto) — 양쪽 다 시도. 둘 중 하나 hit 시 그쪽 프로필로 저장
                    // bitmap 가로 방향이면 좌/우 분할, 아니면 위/아래 분할
                    val landscape = detectSplitOrientation(bitmap.width, bitmap.height)
                    val (rectA, rectB, profA, profB) = if (landscape) {
                        Quad(
                            Rect(0, 0, bitmap.width / 2, bitmap.height),
                            Rect(bitmap.width / 2, 0, bitmap.width, bitmap.height),
                            "split_a", "split_b"
                        )
                    } else {
                        Quad(
                            Rect(0, 0, bitmap.width, bitmap.height / 2),
                            Rect(0, bitmap.height / 2, bitmap.width, bitmap.height),
                            "split_a", "split_b"
                        )
                    }

                    // 우선 전체 분석 시도 (분할 안 된 케이스 대비)
                    if (analyzeRegion(bitmap, null, "main")) continue
                    // 좌/상 → 우/하 순서
                    if (analyzeRegion(bitmap, rectA, profA)) continue
                    analyzeRegion(bitmap, rectB, profB)
                } catch (_: Exception) {}
            }
        }
    }

    // 1 영역 분석. hit (PogoScreenData 반환) 했으면 true. lastAnalyzedText 로 중복 방지.
    private suspend fun analyzeRegion(
        bitmap: Bitmap, crop: Rect?, profile: String
    ): Boolean {
        val data = PogoOCR.analyze(bitmap, crop) ?: return false
        if (data.cp <= 0) return false  // dust 는 optional 이라 cp 만 체크

        val screenKey = "$profile|${data.cp}_${data.hp}_${data.pokemonName}"
        if (screenKey == lastAnalyzedText) return true  // 같은 화면 — 처리는 skip 하지만 hit
        lastAnalyzedText = screenKey

        withContext(Dispatchers.Main) {
            processResult(data, profile)
        }
        return true
    }

    // 4-tuple helper
    private data class Quad(
        val a: Rect, val b: Rect, val pa: String, val pb: String
    )

    private fun processResult(
        data: com.woojin.pokemanager.ocr.PogoScreenData,
        profile: String = "main"
    ) {
        val species = GameMasterRepo.findByNameFuzzy(data.pokemonName)

        val ivResults = if (species != null) {
            IVCalculator.calculate(
                species.atk, species.def, species.sta,
                data.cp, data.hp, data.dustCost,
                data.isShadow, data.isPurified
            )
        } else emptyList()

        val pvpResults = if (ivResults.isNotEmpty()) {
            val top = ivResults.first()
            PvPRanker.rankAll(species!!.atk, species.def, species.sta, top.atkIV, top.defIV, top.stamIV)
        } else emptyList()

        showResult(data, ivResults, pvpResults, profile)
    }

    private fun showFab() {
        val inflater = LayoutInflater.from(this)
        fabView = inflater.inflate(R.layout.overlay_fab, null)

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 16
            y = resources.displayMetrics.heightPixels / 3
        }

        fabY = params.y.toFloat()

        fabView!!.setOnTouchListener(object : View.OnTouchListener {
            private var initX = 0; private var initY = 0
            private var touchX = 0f; private var touchY = 0f
            override fun onTouch(v: View, e: MotionEvent): Boolean {
                when (e.action) {
                    MotionEvent.ACTION_DOWN -> {
                        initX = params.x; initY = params.y
                        touchX = e.rawX; touchY = e.rawY
                    }
                    MotionEvent.ACTION_MOVE -> {
                        params.x = initX + (e.rawX - touchX).toInt()
                        params.y = initY + (e.rawY - touchY).toInt()
                        fabY = params.y.toFloat()
                        windowManager?.updateViewLayout(fabView, params)

                        // FAB 위치로 분할화면 모드 자동 설정
                        // 가로/세로 화면에 따라 좌/우 (3,4) 또는 위/아래 (1,2) 분할
                        val screenW = resources.displayMetrics.widthPixels
                        val screenH = resources.displayMetrics.heightPixels
                        val landscape = screenW >= screenH
                        splitMode = if (landscape) {
                            when {
                                params.x < screenW * 0.35f -> 3   // 좌측
                                params.x > screenW * 0.65f -> 4   // 우측
                                else -> 0
                            }
                        } else {
                            when {
                                params.y < screenH * 0.35f -> 1   // 상단
                                params.y > screenH * 0.65f -> 2   // 하단
                                else -> 0
                            }
                        }
                    }
                    MotionEvent.ACTION_UP -> {
                        if (Math.abs(e.rawX - touchX) < 10 && Math.abs(e.rawY - touchY) < 10) {
                            // 탭: 수동 캡처 트리거 (현재 splitMode 의 영역 분석)
                            scope.launch(Dispatchers.IO) {
                                val bitmap = captureBitmap() ?: return@launch
                                val crop = getCropRect(bitmap.width, bitmap.height)
                                val data = PogoOCR.analyze(bitmap, crop) ?: return@launch
                                withContext(Dispatchers.Main) {
                                    processResult(data, currentProfile())
                                }
                            }
                        }
                    }
                }
                return true
            }
        })

        windowManager?.addView(fabView, params)
    }

    private fun showResult(
        data: com.woojin.pokemanager.ocr.PogoScreenData,
        ivResults: List<com.woojin.pokemanager.calc.IVResult>,
        pvpResults: List<com.woojin.pokemanager.calc.LeagueResult>,
        profile: String = "main"
    ) {
        removeResultView()

        val inflater = LayoutInflater.from(this)
        resultView = inflater.inflate(R.layout.overlay_result, null)

        val tvName = resultView!!.findViewById<TextView>(R.id.tvName)
        val tvCP = resultView!!.findViewById<TextView>(R.id.tvCP)
        val tvIV = resultView!!.findViewById<TextView>(R.id.tvIV)
        val tvLeague = resultView!!.findViewById<TextView>(R.id.tvLeague)
        val btnSave = resultView!!.findViewById<Button>(R.id.btnSave)
        val btnClose = resultView!!.findViewById<Button>(R.id.btnClose)

        val species = GameMasterRepo.findByNameFuzzy(data.pokemonName)
        // 프로필 prefix — 분할화면 좌/우 어느 쪽에서 잡혔는지 표시
        val profPrefix = when (profile) {
            "split_a" -> "[A] "
            "split_b" -> "[B] "
            else -> ""
        }
        tvName.text = profPrefix + (species?.nameKo ?: data.pokemonName.ifEmpty { "알 수 없음" })
        tvCP.text = "CP ${data.cp}  HP ${data.hp}" +
            (if (data.dustCost > 0) "  먼지 ${data.dustCost}" else "")

        if (ivResults.isEmpty()) {
            tvIV.text = "IV 계산 불가\n(포켓몬 데이터 없음)"
        } else {
            val top = ivResults.first()
            val minPerf = ivResults.last().perfection
            val maxPerf = top.perfection
            tvIV.text = buildString {
                append("Atk ${top.atkIV} / Def ${top.defIV} / Sta ${top.stamIV}\n")
                append("%.1f%%".format(maxPerf * 100))
                if (ivResults.size > 1) append(" ~ %.1f%%".format(minPerf * 100))
                append("  (${ivResults.size}가지 가능)\n")
                append("Lv %.1f".format(top.level))
            }
        }

        if (pvpResults.isNotEmpty()) {
            tvLeague.text = pvpResults.joinToString("\n") {
                "${it.league}: 순위 ${it.rank} (CP ${it.bestCP})"
            }
        } else {
            tvLeague.text = ""
        }

        // ─── 사이트 8 bucket 결정 — 즉시 표시 (보관 / 송출 등)
        if (ivResults.isNotEmpty() && species != null) {
            val top = ivResults.first()
            val meta = GameMasterRepo.meta(species.id)
            val groupClass = GameMasterRepo.classifyGroup(species.id)
            val decision = BucketClassifier.classify(
                sid = species.id,
                ivAtk = top.atkIV, ivDef = top.defIV, ivStam = top.stamIV,
                cp = data.cp,
                species = meta,
                groupClass = groupClass
            )
            // tvLeague 아래에 결정 라벨 추가
            tvLeague.text = (tvLeague.text?.toString().orEmpty() +
                "\n\n📋 결정: ${decision.bucket.label}\n${decision.reason}").trimStart()

            // ─── 자동 클립보드 복사 (Calcy 의 auto-rename 대체)
            // 형식: "{한글이름}{IV%}" 예: "라프라스95"
            val perfPct = (top.perfection * 100).toInt()
            val nickname = "${species.nameKo}${perfPct}"
            val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.setPrimaryClip(ClipData.newPlainText("PokeManager", nickname))
            // 짧은 토스트 — 첫 스캔 시만 (반복 토스트 방지)
            Toast.makeText(this, "📋 \"${nickname}\" 복사됨", Toast.LENGTH_SHORT).show()
        }

        btnClose.setOnClickListener { removeResultView() }

        btnSave.setOnClickListener {
            if (ivResults.isNotEmpty() && species != null) {
                val top = ivResults.first()
                scope.launch(Dispatchers.IO) {
                    AppDatabase.get(applicationContext).pokemonDao().insert(
                        MyPokemon(
                            speciesId = species.id,
                            cp = data.cp, hp = data.hp, dustCost = data.dustCost,
                            atkIV = top.atkIV, defIV = top.defIV, stamIV = top.stamIV,
                            level = top.level, perfection = top.perfection,
                            isShadow = data.isShadow, isPurified = data.isPurified,
                            profile = profile
                        )
                    )
                    withContext(Dispatchers.Main) {
                        Toast.makeText(applicationContext,
                            "저장됨 (${profPrefix.trim().ifEmpty { "main" }})",
                            Toast.LENGTH_SHORT).show()
                        removeResultView()
                    }
                }
            }
        }

        val screenW = resources.displayMetrics.widthPixels
        val params = WindowManager.LayoutParams(
            (screenW * 0.9f).toInt(),
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = 100
        }

        windowManager?.addView(resultView, params)
        resultVisible = true

        // 10초 후 자동 닫기
        scope.launch {
            delay(10000)
            removeResultView()
        }
    }

    private fun removeResultView() {
        resultView?.let {
            try { windowManager?.removeView(it) } catch (_: Exception) {}
            resultView = null
        }
        resultVisible = false
    }

    override fun onDestroy() {
        isRunning = false
        autoScanJob?.cancel()
        scope.cancel()
        removeResultView()
        fabView?.let { try { windowManager?.removeView(it) } catch (_: Exception) {} }
        virtualDisplay?.release()
        mediaProjection?.stop()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?) = null

    private fun createNotificationChannel() {
        val channel = NotificationChannel(CHANNEL_ID, "PokeManager 오버레이",
            NotificationManager.IMPORTANCE_LOW).apply { description = "포켓몬 분석 오버레이" }
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        val stopIntent = PendingIntent.getBroadcast(
            this, 0, Intent(this, StopReceiver::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("PokeManager 실행 중")
            .setContentText("자동 분석 활성화됨")
            .setSmallIcon(R.mipmap.ic_launcher)
            .addAction(0, "중지", stopIntent)
            .build()
    }

    class StopReceiver : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            context.stopService(Intent(context, OverlayService::class.java))
        }
    }
}
