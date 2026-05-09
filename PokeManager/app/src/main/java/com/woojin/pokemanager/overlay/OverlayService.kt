package com.woojin.pokemanager.overlay

import android.app.*
import android.content.*
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

        // 분할화면 모드: 0=전체, 1=상단/좌측, 2=하단/우측
        var splitMode: Int = 0
        var isRunning = false
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
        startForeground(NOTIF_ID, buildNotification())

        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED) ?: return START_NOT_STICKY
        val resultData = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent::class.java)
        else @Suppress("DEPRECATION") intent.getParcelableExtra(EXTRA_RESULT_DATA)

        if (resultCode == Activity.RESULT_OK && resultData != null) {
            val mgr = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            mediaProjection = mgr.getMediaProjection(resultCode, resultData)
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
        return when (splitMode) {
            1 -> Rect(0, 0, bitmapWidth, bitmapHeight / 2)       // 상단 절반
            2 -> Rect(0, bitmapHeight / 2, bitmapWidth, bitmapHeight)  // 하단 절반
            else -> null  // 전체 화면
        }
    }

    // 자동 스캔: 1초마다 화면 캡처 → 포고 화면 감지 → 자동 분석
    private fun startAutoScan() {
        autoScanJob = scope.launch(Dispatchers.IO) {
            while (isActive) {
                delay(1000)
                try {
                    val bitmap = captureBitmap() ?: continue
                    val crop = getCropRect(bitmap.width, bitmap.height)
                    val src = if (crop != null)
                        Bitmap.createBitmap(bitmap, crop.left, crop.top, crop.width(), crop.height())
                    else bitmap

                    // 빠른 텍스트 인식으로 포고 화면 여부 판단
                    val data = PogoOCR.analyze(src, null) ?: continue
                    val screenKey = "${data.cp}_${data.hp}_${data.dustCost}_${data.pokemonName}"

                    // 같은 화면이면 다시 분석 안 함
                    if (screenKey == lastAnalyzedText) continue
                    lastAnalyzedText = screenKey

                    if (data.cp > 0 && data.dustCost > 0) {
                        withContext(Dispatchers.Main) {
                            processResult(data)
                        }
                    }
                } catch (_: Exception) {}
            }
        }
    }

    private fun processResult(data: com.woojin.pokemanager.ocr.PogoScreenData) {
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

        showResult(data, ivResults, pvpResults)
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
                        val screenH = resources.displayMetrics.heightPixels
                        splitMode = when {
                            params.y < screenH * 0.4f -> 1
                            params.y > screenH * 0.6f -> 2
                            else -> 0
                        }
                    }
                    MotionEvent.ACTION_UP -> {
                        if (Math.abs(e.rawX - touchX) < 10 && Math.abs(e.rawY - touchY) < 10) {
                            // 탭: 수동 캡처 트리거
                            scope.launch(Dispatchers.IO) {
                                val bitmap = captureBitmap() ?: return@launch
                                val crop = getCropRect(bitmap.width, bitmap.height)
                                val data = PogoOCR.analyze(bitmap, crop) ?: return@launch
                                withContext(Dispatchers.Main) { processResult(data) }
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
        pvpResults: List<com.woojin.pokemanager.calc.LeagueResult>
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
        tvName.text = species?.nameKo ?: data.pokemonName.ifEmpty { "알 수 없음" }
        tvCP.text = "CP ${data.cp}  HP ${data.hp}  먼지 ${data.dustCost}"

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
                            isShadow = data.isShadow, isPurified = data.isPurified
                        )
                    )
                    withContext(Dispatchers.Main) {
                        Toast.makeText(applicationContext, "저장됨", Toast.LENGTH_SHORT).show()
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
