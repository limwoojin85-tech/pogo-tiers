package com.woojin.pokemanager.swipe

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Path
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.KeyEvent
import android.view.accessibility.AccessibilityEvent
import androidx.core.app.NotificationCompat

/**
 * 폰 단독 자동 스와이프 — AccessibilityService 의 dispatchGesture 사용.
 * PC ADB 없이 폰만으로 박스 스와이프 자동화.
 *
 * 사용:
 *   1) 설정 → 접근성 → 설치된 앱 → PokeManager 자동 스와이프 → ON
 *   2) 메인 화면에서 "자동 스와이프 시작" 버튼
 *   3) 포켓몬GO 박스에서 첫 마리 detail 띄움
 *   4) 자동으로 좌→우 swipe 반복, 사용자가 "정지" 누를 때까지
 */
class AutoSwipeService : AccessibilityService() {

    companion object {
        private const val TAG = "AutoSwipeService"
        private const val NOTIF_CHANNEL = "pokemanager_swipe"
        private const val NOTIF_ID = 2001
        const val ACTION_STOP = "com.woojin.pokemanager.STOP_SWIPE"

        // ── 외부에서 컨트롤 (MainActivity 에서 set)
        @Volatile var isSwiping: Boolean = false
        @Volatile var instance: AutoSwipeService? = null

        // 스와이프 좌표 — 904x2316 cover 화면 기준 (Z Fold 4)
        // Pokemon GO detail 화면 중간 ~ 하단 영역에서 좌우 swipe → 다음 마리
        var swipeStartX = 750f
        var swipeEndX = 150f
        var swipeY = 1200f          // 화면 중간보다 약간 아래 (포켓몬 캐릭터 영역 피함)
        var swipeDurationMs = 300L  // 스와이프 자체 시간
        var intervalMs = 2500L      // 다음 스와이프까지 대기 (PokeManager OCR + 결과창 fade 시간 확보)
        var maxCount = 2000         // 안전 limit

        fun startSwiping() {
            instance?.beginLoop() ?: Log.w(TAG, "service not connected")
        }

        fun stopSwiping() {
            isSwiping = false
            instance?.let { svc ->
                svc.handler.removeCallbacksAndMessages(null)   // pending swipes 다 취소
                svc.cancelNotification()
            }
        }
    }

    private val handler = Handler(Looper.getMainLooper())
    private var swipeCount = 0
    private var stopReceiver: BroadcastReceiver? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        // accessibility service info 에 KeyEvent 받도록 추가 (volume key 정지)
        val info = serviceInfo
        info.flags = info.flags or
            android.accessibilityservice.AccessibilityServiceInfo.FLAG_REQUEST_FILTER_KEY_EVENTS
        serviceInfo = info
        // STOP broadcast 받기
        stopReceiver = object : BroadcastReceiver() {
            override fun onReceive(c: Context, i: Intent) {
                if (i.action == ACTION_STOP) stopSwiping()
            }
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(stopReceiver, IntentFilter(ACTION_STOP),
                Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(stopReceiver, IntentFilter(ACTION_STOP))
        }
        Log.i(TAG, "AutoSwipeService connected")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) { }

    // 볼륨 키 즉시 정지 — swipe 중에 손가락이 화면에 못 닿아도 키로 멈춤
    override fun onKeyEvent(event: KeyEvent?): Boolean {
        if (event?.action == KeyEvent.ACTION_DOWN && isSwiping) {
            when (event.keyCode) {
                KeyEvent.KEYCODE_VOLUME_DOWN, KeyEvent.KEYCODE_VOLUME_UP -> {
                    stopSwiping()
                    return true
                }
            }
        }
        return super.onKeyEvent(event)
    }

    override fun onInterrupt() {
        stopSwiping()
    }

    override fun onDestroy() {
        instance = null
        isSwiping = false
        handler.removeCallbacksAndMessages(null)
        try { stopReceiver?.let { unregisterReceiver(it) } } catch (_: Exception) {}
        cancelNotification()
        super.onDestroy()
    }

    private fun showNotification() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val ch = NotificationChannel(NOTIF_CHANNEL, "PokeManager 자동 스와이프",
            NotificationManager.IMPORTANCE_HIGH).apply {
            description = "스와이프 진행 중. 알림 탭하거나 정지 버튼 눌러 종료."
            setSound(null, null)
            enableVibration(false)
        }
        nm.createNotificationChannel(ch)

        val stopIntent = PendingIntent.getBroadcast(
            this, 0,
            Intent(ACTION_STOP).setPackage(packageName),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val notif = NotificationCompat.Builder(this, NOTIF_CHANNEL)
            .setContentTitle("🤖 자동 스와이프 진행 중")
            .setContentText("탭 또는 볼륨 키로 즉시 정지")
            .setSmallIcon(android.R.drawable.ic_media_pause)
            .setContentIntent(stopIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .addAction(android.R.drawable.ic_media_pause, "🛑 정지", stopIntent)
            .build()

        nm.notify(NOTIF_ID, notif)
    }

    private fun cancelNotification() {
        try {
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).cancel(NOTIF_ID)
        } catch (_: Exception) {}
    }

    fun beginLoop() {
        if (isSwiping) return
        isSwiping = true
        swipeCount = 0
        showNotification()
        scheduleNext()
    }

    private fun scheduleNext() {
        if (!isSwiping || swipeCount >= maxCount) {
            isSwiping = false
            cancelNotification()
            Log.i(TAG, "swipe loop end — count=$swipeCount")
            return
        }
        handler.postDelayed({ doSwipe() }, intervalMs)
    }

    private fun doSwipe() {
        if (!isSwiping) return
        val path = Path().apply {
            moveTo(swipeStartX, swipeY)
            lineTo(swipeEndX, swipeY)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, swipeDurationMs))
            .build()
        val ok = dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(g: GestureDescription?) {
                swipeCount += 1
                scheduleNext()
            }

            override fun onCancelled(g: GestureDescription?) {
                Log.w(TAG, "gesture cancelled at #$swipeCount")
                scheduleNext()
            }
        }, handler)
        if (!ok) {
            Log.w(TAG, "dispatchGesture rejected — service may not have permission")
            isSwiping = false
        }
    }
}
