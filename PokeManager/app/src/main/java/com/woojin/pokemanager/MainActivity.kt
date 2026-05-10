package com.woojin.pokemanager

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionConfig
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.*
import android.provider.Settings
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.woojin.pokemanager.data.GameMasterRepo
import com.woojin.pokemanager.list.MyPokemonActivity
import com.woojin.pokemanager.overlay.OverlayService

class MainActivity : AppCompatActivity() {

    private lateinit var btnToggle: Button
    private lateinit var tvStatus: TextView
    private lateinit var rgCaptureMode: RadioGroup

    private val projectionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            startOverlayService(result.resultCode, result.data!!)
        } else {
            Toast.makeText(this, "화면 캡처 권한이 필요합니다", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        btnToggle = findViewById(R.id.btnToggle)
        tvStatus = findViewById(R.id.tvStatus)
        rgCaptureMode = findViewById(R.id.rgCaptureMode)

        GameMasterRepo.load(this)

        btnToggle.setOnClickListener { toggleOverlay() }
        rgCaptureMode.setOnCheckedChangeListener { _, checkedId ->
            OverlayService.captureMode =
                if (checkedId == R.id.rbModeSingle) "single" else "full"
        }
        findViewById<Button>(R.id.btnMyPokemon).setOnClickListener {
            startActivity(Intent(this, MyPokemonActivity::class.java))
        }

        updateUI()
    }

    override fun onResume() {
        super.onResume()
        updateUI()
    }

    private fun toggleOverlay() {
        if (OverlayService.isRunning) {
            stopService(Intent(this, OverlayService::class.java))
            OverlayService.isRunning = false
            updateUI()
            return
        }

        // 시작 직전 captureMode 확정
        OverlayService.captureMode =
            if (rgCaptureMode.checkedRadioButtonId == R.id.rbModeSingle) "single" else "full"

        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "화면 위에 표시 권한을 허용해주세요", Toast.LENGTH_LONG).show()
            startActivity(
                Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName"))
            )
            return
        }

        val mgr = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val intent = if (OverlayService.captureMode == "full" &&
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            // Android 14+ — 전체 화면 강제 (시스템의 user-choice dialog 우회)
            // 이게 없으면 Samsung One UI 6.x 에서 dialog 가 "앱 하나만" 만 보여줘서
            // 분할화면 양쪽 캡처 불가능. createConfigForDefaultDisplay 로 강제.
            try {
                mgr.createScreenCaptureIntent(
                    MediaProjectionConfig.createConfigForDefaultDisplay()
                )
            } catch (_: Throwable) {
                // 일부 디바이스에서 미지원 — fallback 으로 default dialog
                mgr.createScreenCaptureIntent()
            }
        } else {
            // "앱 하나" 모드 — 사용자가 dialog 에서 포고 선택
            mgr.createScreenCaptureIntent()
        }
        projectionLauncher.launch(intent)
    }

    private fun startOverlayService(resultCode: Int, data: Intent) {
        val intent = Intent(this, OverlayService::class.java).apply {
            putExtra(OverlayService.EXTRA_RESULT_CODE, resultCode)
            putExtra(OverlayService.EXTRA_RESULT_DATA, data)
        }
        startForegroundService(intent)
        updateUI()
    }

    private fun updateUI() {
        if (OverlayService.isRunning) {
            btnToggle.text = "오버레이 중지"
            val mode = if (OverlayService.captureMode == "single") "앱 하나" else "전체 화면"
            tvStatus.text = "자동 분석 실행 중 ($mode)\n포고 detail 열면 자동 분석됨"
        } else {
            btnToggle.text = "오버레이 시작"
            tvStatus.text = "중지됨"
        }
    }
}
