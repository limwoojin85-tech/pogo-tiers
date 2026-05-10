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
import com.woojin.pokemanager.swipe.AutoSwipeService
import android.content.Intent
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
        var captureMode: String = "single"

        // ── 자동 동작 toggle — default 전부 OFF (사용자 100% 컨트롤)
        var autoScan: Boolean = false
        var autoSave: Boolean = false
        var clipboardCopy: Boolean = false
        // 방출 추천 마리 (transfer/transfer_dup) 만나면 자동 스와이프 일시정지 → 사용자가 수동 방출 → 다시 시작
        var pauseOnTransfer: Boolean = true
    }

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var mediaProjection: MediaProjection? = null
    private var imageReader: ImageReader? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var windowManager: WindowManager? = null

    // 오버레이 뷰들
    private var fabView: View? = null
    private var resultView: View? = null
    private var fabCloseView: View? = null   // FAB 드래그 시 하단 X 영역
    private var optionsView: View? = null    // FAB long-press 옵션 패널

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
            // autoScan true 일 때만 polling 시작. default 는 수동 (FAB 탭 트리거).
            if (autoScan) startAutoScan()
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
                    // 결과창 떠있는 동안엔 자동 스캔 중지 — 자기 자신 OCR 노이즈 방지
                    if (resultVisible) continue

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

        var ivResults = if (species != null) {
            IVCalculator.calculate(
                species.atk, species.def, species.sta,
                data.cp, data.hp, data.dustCost,
                data.isShadow, data.isPurified
            )
        } else emptyList()

        // 막대 그래프에서 직접 읽은 IV 가 있으면 — CP/HP 매칭 후보 중에서 막대 IV ±1 범위로 필터
        // (막대 픽셀 분석은 ±1 오차 가능)
        if (data.ivBarsAtk != null && data.ivBarsDef != null && data.ivBarsSta != null) {
            val filtered = ivResults.filter {
                kotlin.math.abs(it.atkIV - data.ivBarsAtk) <= 1 &&
                kotlin.math.abs(it.defIV - data.ivBarsDef) <= 1 &&
                kotlin.math.abs(it.stamIV - data.ivBarsSta) <= 1
            }
            if (filtered.isNotEmpty()) ivResults = filtered
        }
        // 별 배지로 추가 검증 — 1성=IV합 0~22, 2성=23~36, 3성=37~45
        if (data.starsLit != null) {
            val (lo, hi) = when (data.starsLit) {
                1 -> 0 to 22
                2 -> 23 to 36
                else -> 37 to 45
            }
            val byStars = ivResults.filter {
                val sum = it.atkIV + it.defIV + it.stamIV
                sum in lo..hi
            }
            if (byStars.isNotEmpty()) ivResults = byStars
        }

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
            private var downTime = 0L
            private var dragging = false
            private var longPressFired = false
            private val longPressRunnable = Runnable {
                longPressFired = true
                showOptionsPanel()
            }

            override fun onTouch(v: View, e: MotionEvent): Boolean {
                when (e.action) {
                    MotionEvent.ACTION_DOWN -> {
                        initX = params.x; initY = params.y
                        touchX = e.rawX; touchY = e.rawY
                        downTime = System.currentTimeMillis()
                        dragging = false
                        longPressFired = false
                        v.handler.postDelayed(longPressRunnable, 600L)
                    }
                    MotionEvent.ACTION_MOVE -> {
                        val dx = e.rawX - touchX
                        val dy = e.rawY - touchY
                        if (!dragging && (Math.abs(dx) > 20 || Math.abs(dy) > 20)) {
                            dragging = true
                            v.handler.removeCallbacks(longPressRunnable)
                            showCloseTarget()
                        }
                        if (dragging) {
                            params.x = initX + dx.toInt()
                            params.y = initY + dy.toInt()
                            fabY = params.y.toFloat()
                            windowManager?.updateViewLayout(fabView, params)
                            highlightCloseIfHover(e.rawX, e.rawY)
                        }
                    }
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                        v.handler.removeCallbacks(longPressRunnable)
                        if (dragging) {
                            // X 영역 위에서 놓았으면 service 종료
                            if (isOverCloseTarget(e.rawX, e.rawY)) {
                                hideCloseTarget()
                                stopSelf()
                                return true
                            }
                            hideCloseTarget()
                        } else if (!longPressFired) {
                            // 짧은 탭 → 수동 캡처
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
        val tvIV = resultView!!.findViewById<TextView>(R.id.tvIV)
        val tvIvBreakdown = resultView!!.findViewById<TextView>(R.id.tvIvBreakdown)
        val tvLeagueGL = resultView!!.findViewById<TextView>(R.id.tvLeagueGL)
        val tvLeagueUL = resultView!!.findViewById<TextView>(R.id.tvLeagueUL)
        val tvLeagueML = resultView!!.findViewById<TextView>(R.id.tvLeagueML)
        val tvCpLv = resultView!!.findViewById<TextView>(R.id.tvCpLv)
        val tvHint = resultView!!.findViewById<TextView>(R.id.tvHint)

        val species = GameMasterRepo.findByNameFuzzy(data.pokemonName)
        val profPrefix = when (profile) {
            "split_a" -> "[A] "
            "split_b" -> "[B] "
            else -> ""
        }
        tvName.text = profPrefix + (species?.nameKo ?: data.pokemonName.ifEmpty { "알 수 없음" })

        if (ivResults.isEmpty() || species == null) {
            tvIV.text = "—"
            tvIvBreakdown.text = "(데이터 없음)"
            tvLeagueGL.visibility = View.GONE
            tvLeagueUL.visibility = View.GONE
            tvLeagueML.visibility = View.GONE
            tvCpLv.text = "CP ${data.cp}  HP ${data.hp}"
            tvHint.text = ""
        } else {
            val top = ivResults.first()
            val pct = (top.perfection * 100)
            tvIV.text = "%.0f%%".format(pct)
            tvIvBreakdown.text = "(${top.atkIV}-${top.defIV}-${top.stamIV})"
            tvCpLv.text = "CP ${data.cp}, Lv %.1f".format(top.level)

            // 리그 한 줄씩 — leagueCap 으로 매칭 (1500/2500/MAX)
            renderLeagueLine(tvLeagueGL, "🏆", pvpResults.find { it.leagueCap == 1500 })
            renderLeagueLine(tvLeagueUL, "🥇", pvpResults.find { it.leagueCap == 2500 })
            renderLeagueLine(tvLeagueML, "🥈", pvpResults.find { it.leagueCap == Int.MAX_VALUE })

            // 결정 (보관/송출/레이드 등) — bucket classification
            val meta = GameMasterRepo.meta(species.id)
            val groupClass = GameMasterRepo.classifyGroup(species.id)
            val decision = BucketClassifier.classify(
                sid = species.id,
                ivAtk = top.atkIV, ivDef = top.defIV, ivStam = top.stamIV,
                cp = data.cp, species = meta, groupClass = groupClass
            )
            val isTransfer = decision.bucket == BucketClassifier.Bucket.TRANSFER ||
                             decision.bucket == BucketClassifier.Bucket.TRANSFER_DUP

            tvHint.text = buildString {
                append(decision.bucket.label)
                if (data.dustCost <= 0 && ivResults.size > 3) {
                    append(" • 후보 ${ivResults.size}개 (강화 가서 다시 탭)")
                }
            }
            tvHint.setTextColor(if (isTransfer) 0xFFD32F2F.toInt() else 0xFF388E3C.toInt())

            // 방출 추천 + 자동 스와이프 중 + pauseOnTransfer ON → 일시정지 + 알림
            if (isTransfer && AutoSwipeService.isSwiping && pauseOnTransfer) {
                AutoSwipeService.stopSwiping()
                Toast.makeText(this,
                    "📦 방출 추천: ${species.nameKo} (${decision.bucket.label})\n수동 방출 후 옵션에서 다시 시작",
                    Toast.LENGTH_LONG).show()
            }

            // 클립보드 (옵션)
            if (clipboardCopy) {
                val nickname = "${species.nameKo}${pct.toInt()}"
                val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(ClipData.newPlainText("PokeManager", nickname))
            }

            // 자동 저장 (옵션)
            if (autoSave) {
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
                }
            }
        }

        // 카드 탭 → 닫기 (PokeGenie 처럼)
        resultView!!.setOnClickListener { removeResultView() }

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
            y = resources.displayMetrics.heightPixels / 4
        }

        windowManager?.addView(resultView, params)
        resultVisible = true

        // 카드 자동 닫힘 (모든 모드)
        // - 자동 + 자동저장 모드: 1.5초 (다음 마리 분석 빨리 가야)
        // - 수동 모드: 6초 (사용자가 보고 다음 마리 가도록. 옛 카드 안 남게)
        // - 방출 추천 (transfer 빨강): 자동 닫기 X (사용자가 수동 방출 결정해야)
        val isTransferShown = tvHint.currentTextColor == 0xFFD32F2F.toInt()
        if (!isTransferShown) {
            val ms = if (autoScan && autoSave) 1500L else 6000L
            scope.launch { delay(ms); removeResultView() }
        }
    }

    private fun renderLeagueLine(tv: TextView, icon: String, league: com.woojin.pokemanager.calc.LeagueResult?) {
        if (league == null) {
            tv.visibility = View.GONE
            return
        }
        tv.visibility = View.VISIBLE
        tv.text = "$icon 순위 ${league.rank} (CP ${league.bestCP})"
    }

    // ──────────────────────── FAB 드래그 → 종료 X 영역
    private fun showCloseTarget() {
        if (fabCloseView != null) return
        val inflater = LayoutInflater.from(this)
        fabCloseView = inflater.inflate(R.layout.overlay_fab_close, null)
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = 80
        }
        windowManager?.addView(fabCloseView, params)
    }

    private fun hideCloseTarget() {
        fabCloseView?.let {
            try { windowManager?.removeView(it) } catch (_: Exception) {}
            fabCloseView = null
        }
    }

    private fun isOverCloseTarget(rawX: Float, rawY: Float): Boolean {
        val v = fabCloseView ?: return false
        val loc = IntArray(2); v.getLocationOnScreen(loc)
        val cx = loc[0] + v.width / 2f
        val cy = loc[1] + v.height / 2f
        val dx = rawX - cx; val dy = rawY - cy
        return Math.sqrt((dx * dx + dy * dy).toDouble()) < v.width / 2.0 + 30
    }

    private fun highlightCloseIfHover(rawX: Float, rawY: Float) {
        fabCloseView?.alpha = if (isOverCloseTarget(rawX, rawY)) 1.0f else 0.7f
    }

    // ──────────────────────── FAB long-press → 옵션 패널
    private fun showOptionsPanel() {
        if (optionsView != null) {
            hideOptionsPanel(); return
        }
        val inflater = LayoutInflater.from(this)
        optionsView = inflater.inflate(R.layout.overlay_options, null)

        val cbScan = optionsView!!.findViewById<CheckBox>(R.id.optAutoScan)
        val cbSave = optionsView!!.findViewById<CheckBox>(R.id.optAutoSave)
        val cbClip = optionsView!!.findViewById<CheckBox>(R.id.optClipboard)
        val cbPause = optionsView!!.findViewById<CheckBox>(R.id.optPauseOnTransfer)
        val btnSwipe = optionsView!!.findViewById<Button>(R.id.btnOptAutoSwipe)
        val btnDebug = optionsView!!.findViewById<Button>(R.id.btnOptDebug)
        val btnClose = optionsView!!.findViewById<Button>(R.id.btnOptionsClose)

        cbScan.isChecked = autoScan
        cbSave.isChecked = autoSave
        cbClip.isChecked = clipboardCopy
        cbPause.isChecked = pauseOnTransfer

        cbScan.setOnCheckedChangeListener { _, c ->
            val wasOff = !autoScan
            autoScan = c
            if (c && wasOff) startAutoScan()
            else if (!c) autoScanJob?.cancel()
        }
        cbSave.setOnCheckedChangeListener { _, c -> autoSave = c }
        cbClip.setOnCheckedChangeListener { _, c -> clipboardCopy = c }
        cbPause.setOnCheckedChangeListener { _, c -> pauseOnTransfer = c }

        btnSwipe.text = if (AutoSwipeService.isSwiping) "■ 자동 스와이프 정지" else "🤖 자동 스와이프 시작"
        btnSwipe.setOnClickListener { handleAutoSwipeButton(btnSwipe) }
        btnDebug.setOnClickListener { showDebugOcrInfo() }
        btnClose.setOnClickListener { hideOptionsPanel() }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 80; y = 80
        }
        windowManager?.addView(optionsView, params)
    }

    private fun hideOptionsPanel() {
        optionsView?.let {
            try { windowManager?.removeView(it) } catch (_: Exception) {}
            optionsView = null
        }
    }

    // 옵션 패널의 "자동 스와이프 시작/정지" 버튼
    private fun handleAutoSwipeButton(btn: Button) {
        if (AutoSwipeService.isSwiping) {
            AutoSwipeService.stopSwiping()
            Toast.makeText(this, "자동 스와이프 정지", Toast.LENGTH_SHORT).show()
            btn.text = "🤖 자동 스와이프 시작"
            return
        }
        if (AutoSwipeService.instance == null) {
            Toast.makeText(this,
                "설정 → 접근성 → PokeManager 자동 스와이프 → ON",
                Toast.LENGTH_LONG).show()
            val i = Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(i)
            return
        }
        Toast.makeText(this, "5초 후 시작 — 포고 박스 detail 띄우세요", Toast.LENGTH_LONG).show()
        hideOptionsPanel()
        Handler(Looper.getMainLooper()).postDelayed({
            AutoSwipeService.startSwiping()
        }, 5000L)
    }

    // 옵션 패널의 "마지막 OCR 결과 보기" 버튼 — 디버그
    private fun showDebugOcrInfo() {
        val msg = buildString {
            append("실패 사유: ${PogoOCR.lastFailReason.ifEmpty { "(성공)" }}\n\n")
            append("=== 라틴 OCR ===\n")
            append(PogoOCR.lastOcrLatin.ifEmpty { "(비어있음)" })
            append("\n\n=== 한글 OCR ===\n")
            append(PogoOCR.lastOcrKorean.ifEmpty { "(비어있음)" })
        }
        // 클립보드에 복사 — 사용자가 디스코드 등에 붙여넣어 정보 제공 가능
        val cb = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
        cb.setPrimaryClip(ClipData.newPlainText("PokeManager OCR debug", msg))
        Toast.makeText(this,
            "OCR 결과 클립보드 복사됨\n실패 사유: ${PogoOCR.lastFailReason.ifEmpty { "(성공)" }}",
            Toast.LENGTH_LONG).show()
    }

    private fun removeResultView() {
        resultView?.let {
            try { windowManager?.removeView(it) } catch (_: Exception) {}
            resultView = null
        }
        resultVisible = false
        // 같은 화면 다시 들어가면 또 분석되도록 cache 리셋
        lastAnalyzedText = ""
    }

    override fun onDestroy() {
        isRunning = false
        autoScanJob?.cancel()
        scope.cancel()
        removeResultView()
        hideCloseTarget()
        hideOptionsPanel()
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
