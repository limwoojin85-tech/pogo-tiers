package com.woojin.pokemanager.swipe

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.accessibility.AccessibilityEvent

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
        }
    }

    private val handler = Handler(Looper.getMainLooper())
    private var swipeCount = 0

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        Log.i(TAG, "AutoSwipeService connected")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // 이벤트 listening 안 함 — gesture dispatch 만 사용
    }

    override fun onInterrupt() {
        isSwiping = false
    }

    override fun onDestroy() {
        instance = null
        isSwiping = false
        super.onDestroy()
    }

    fun beginLoop() {
        if (isSwiping) return
        isSwiping = true
        swipeCount = 0
        scheduleNext()
    }

    private fun scheduleNext() {
        if (!isSwiping || swipeCount >= maxCount) {
            isSwiping = false
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
