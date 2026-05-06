# Auto-scan with dropout detection
# Calcy 조사하기 꺼지면 자동 감지 (history.csv mtime 모니터링) + 일시정지 + 비프
# 사용자가 Calcy 다시 켜고 Enter 누르면 재개
#
# 사용법: 폰에서 Calcy IV 조사하기 ON + 박스 첫 마리 띄움 → 이 스크립트 실행
#
param(
    [int]$Count = 1500,                  # 박스 마릿수보다 살짝 많게 (한 바퀴 + α)
    [int]$DelayMs = 1500,                # 스와이프 간격 (1.5s — Calcy IV 읽을 시간)
    [int]$DropoutThresholdSec = 10,      # 새 스캔 없는 채로 N초 → dropout 감지
    [int]$SwipeFromX = 1500,             # Galaxy Fold 4 (1812×2176) 기준
    [int]$SwipeToX = 300,
    [int]$SwipeY = 1000,
    [int]$ProgressEverySec = 30,         # 진행률 출력 주기 (콘솔)
    [switch]$NoBeep                       # 비프 끄기
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$adb = Join-Path $root "platform-tools\adb.exe"
$csv = Join-Path $root "history.csv"
$shotDir = Join-Path $root "_shots"
New-Item -ItemType Directory -Force -Path $shotDir | Out-Null

if (-not (Test-Path $adb)) { Write-Host "[err] adb.exe 없음 — setup.ps1 먼저" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $csv)) {
    Write-Host "[warn] history.csv 없음 — 새로 생성됨. dropout 감지 비활성화" -ForegroundColor Yellow
    $detectDropout = $false
} else { $detectDropout = $true }

# 상태
$startTime = Get-Date
$totalDropouts = 0
$totalDropoutSec = 0.0
$pausedTime = New-TimeSpan
$lastCheckMtime = if ($detectDropout) { (Get-Item $csv).LastWriteTime } else { Get-Date }
$lastActivityTime = Get-Date
$lastProgressOut = Get-Date

Write-Host "===================================" -ForegroundColor Cyan
Write-Host "  자동 스캔 (Dropout 감지 ON)"      -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host "  $Count 회 × $($DelayMs / 1000)s = 약 $([math]::Round($Count * $DelayMs / 60000, 1)) 분"
Write-Host "  Dropout 임계: $DropoutThresholdSec 초 새 스캔 없으면 자동 일시정지"
Write-Host ""
Write-Host "  Ctrl+C 로 중단 가능"
Write-Host ""

function Show-Progress($i, $total, $startTime, $pausedTime) {
    $elapsed = (Get-Date) - $startTime - $pausedTime
    $rate = if ($elapsed.TotalSeconds -gt 0) { $i / $elapsed.TotalSeconds } else { 0 }
    $remainSec = if ($rate -gt 0) { ($total - $i) / $rate } else { 0 }
    $remainMin = [math]::Round($remainSec / 60, 1)
    $pct = [math]::Round($i / $total * 100, 1)
    Write-Host ("[{0,4}/{1}] {2,5}% · 경과 {3:N1}분 · 남은 ~{4:N1}분 · {5:N1} 마리/분 · 일시정지 {6:N0}초" -f `
        $i, $total, $pct, $elapsed.TotalMinutes, $remainMin, ($rate * 60), $pausedTime.TotalSeconds)
}

for ($i = 1; $i -le $Count; $i++) {
    # 스와이프
    & $adb shell input swipe $SwipeFromX $SwipeY $SwipeToX $SwipeY 200 2>&1 | Out-Null
    Start-Sleep -Milliseconds $DelayMs

    # Dropout 감지 — history.csv mtime 변화 추적
    if ($detectDropout) {
        $currentMtime = (Get-Item $csv).LastWriteTime
        if ($currentMtime -gt $lastCheckMtime) {
            $lastCheckMtime = $currentMtime
            $lastActivityTime = Get-Date
        } else {
            $silentSec = ((Get-Date) - $lastActivityTime).TotalSeconds
            if ($silentSec -ge $DropoutThresholdSec) {
                # PAUSE
                Write-Host ""
                Write-Host "[!] $silentSec 초 동안 새 스캔 없음 — Calcy 조사하기 꺼졌나요?" -ForegroundColor Yellow
                if (-not $NoBeep) { [console]::beep(1000, 300) }
                $pauseStart = Get-Date
                Read-Host "  Calcy 다시 켜고 Enter (스킵 = s)"
                $pauseDur = (Get-Date) - $pauseStart
                $pausedTime += $pauseDur
                $totalDropouts++
                $totalDropoutSec += $silentSec
                $lastActivityTime = Get-Date
                $lastCheckMtime = (Get-Item $csv).LastWriteTime
                Write-Host "[+] 재개 — 일시정지 $([math]::Round($pauseDur.TotalSeconds, 0))초" -ForegroundColor Green
            }
        }
    }

    # 진행률 출력 (주기적)
    if (((Get-Date) - $lastProgressOut).TotalSeconds -ge $ProgressEverySec) {
        Show-Progress $i $Count $startTime $pausedTime
        $lastProgressOut = Get-Date
        # 백업 스크린샷 (디버깅용)
        & $adb shell screencap -p /sdcard/_p.png 2>&1 | Out-Null
        & $adb pull /sdcard/_p.png "$shotDir\progress_$($i.ToString('0000')).png" 2>&1 | Out-Null
        & $adb shell rm /sdcard/_p.png 2>&1 | Out-Null
    }
}

$total = (Get-Date) - $startTime
Write-Host ""
Write-Host "===================================" -ForegroundColor Green
Write-Host "  완료" -ForegroundColor Green
Write-Host "===================================" -ForegroundColor Green
Write-Host ("  총 시간: {0:N1} 분" -f $total.TotalMinutes)
Write-Host ("  스와이프 시간: {0:N1} 분" -f ($total - $pausedTime).TotalMinutes)
Write-Host ("  일시정지 누적: {0:N1} 분 ({1} 회)" -f $pausedTime.TotalMinutes, $totalDropouts)
if ($totalDropouts -gt 0) {
    Write-Host ("  Dropout 감지로 막은 헛스와이프: ~{0:N0} 회" -f ($totalDropoutSec / ($DelayMs / 1000))) -ForegroundColor Cyan
}
Write-Host ""
Write-Host "  history.csv 확인: $csv"
