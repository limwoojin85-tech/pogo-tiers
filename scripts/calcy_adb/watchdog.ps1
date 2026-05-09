# Calcy IV 작동 감시 — 별도 PowerShell 창에서 실행
# 30초마다 스크린샷 → "클립보드에 복사" 토스트 또는 Calcy IV 박스 색깔 체크
# Calcy 죽었을 가능성 시 비프 + 콘솔 알림 (사용자가 폰 보고 다시 켜기)
#
# 사용:  별도 창 열어서 .\watchdog.ps1
#

param(
    [int]$IntervalSec = 30,
    [string]$DisplayId = "4630946213010294403"
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$adb = Join-Path $root "platform-tools\adb.exe"
$shotDir = Join-Path $root "_shots"

Write-Host "===========================================" -ForegroundColor Cyan
Write-Host "  Calcy IV Watchdog (감시 only — 스캔 X)" -ForegroundColor Cyan
Write-Host "  $IntervalSec 초마다 스크린샷 분석" -ForegroundColor Cyan
Write-Host "  Ctrl+C 로 종료" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""

$lastHash = ""
$samePicCount = 0
$totalChecks = 0

while ($true) {
    $totalChecks++
    $shotPath = Join-Path $shotDir "_watchdog.png"
    & $adb shell "screencap -p -d $DisplayId /sdcard/_w.png" 2>&1 | Out-Null
    & $adb pull /sdcard/_w.png $shotPath 2>&1 | Out-Null
    & $adb shell "rm /sdcard/_w.png" 2>&1 | Out-Null

    if (-not (Test-Path $shotPath)) {
        Write-Host "[!] 스크린샷 실패" -ForegroundColor Red
        Start-Sleep -Seconds $IntervalSec
        continue
    }

    # 파일 hash 비교 — 같은 화면이면 = 같은 Pokemon = 스와이프 안 되거나 Calcy 안 읽고 있음
    $hash = (Get-FileHash $shotPath -Algorithm MD5).Hash
    $now = Get-Date -Format "HH:mm:ss"

    if ($hash -eq $lastHash) {
        $samePicCount++
        Write-Host "[$now] [$totalChecks] 같은 화면 ${samePicCount}회 연속" -ForegroundColor Yellow
        if ($samePicCount -ge 2) {
            Write-Host ""
            Write-Host "🚨 [$now] DROPOUT 의심 — $($samePicCount * $IntervalSec)초 화면 변화 X" -ForegroundColor Red
            Write-Host "    폰 확인:" -ForegroundColor Red
            Write-Host "    - Calcy IV 오버레이 켜져 있나?" -ForegroundColor Red
            Write-Host "    - Pokemon GO 박스 화면인가?" -ForegroundColor Red
            Write-Host "    - 화면 잠긴 거 아닌가?" -ForegroundColor Red
            for ($b = 0; $b -lt 3; $b++) { [console]::beep(1500, 250); Start-Sleep -Milliseconds 100 }
        }
    } else {
        if ($samePicCount -gt 0) {
            Write-Host "[$now] [$totalChecks] ✅ 화면 변경 — 정상 진행" -ForegroundColor Green
        } else {
            Write-Host "[$now] [$totalChecks] OK"
        }
        $samePicCount = 0
    }
    $lastHash = $hash
    Start-Sleep -Seconds $IntervalSec
}
