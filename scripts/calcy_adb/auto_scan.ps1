# Auto-scan loop for Galaxy Fold 4 (1812x2176)
param(
    [int]$Count = 1100,
    [int]$DelayMs = 1300,
    [int]$SwipeFromX = 1500,
    [int]$SwipeToX = 300,
    [int]$SwipeY = 1000
)

$adb = Join-Path $PSScriptRoot "platform-tools\adb.exe"
$shotDir = Join-Path $PSScriptRoot "_shots"
New-Item -ItemType Directory -Force -Path $shotDir | Out-Null

if (-not (Test-Path $adb)) {
    Write-Host "[err] adb.exe not found at $adb" -ForegroundColor Red
    exit 1
}

Write-Host "=== Auto-scan: $Count Pokemon @ ${DelayMs}ms each ===" -ForegroundColor Cyan
Write-Host ("Estimated time: {0} min" -f [math]::Round($Count * $DelayMs / 60000, 1))
Write-Host ""

$start = Get-Date
$progressInterval = 50

for ($i = 1; $i -le $Count; $i++) {
    & $adb shell input swipe $SwipeFromX $SwipeY $SwipeToX $SwipeY 200 2>&1 | Out-Null

    if ($i % $progressInterval -eq 0) {
        $elapsed = (Get-Date) - $start
        $rate = if ($elapsed.TotalMinutes -gt 0) { $i / $elapsed.TotalMinutes } else { 0 }
        $remaining = if ($rate -gt 0) { ($Count - $i) / $rate } else { 0 }
        Write-Host ("[{0,4}/{1}] elapsed: {2}m  remaining: {3}m  rate: {4:N1}/min" -f `
            $i, $Count, [math]::Round($elapsed.TotalMinutes, 1), [math]::Round($remaining, 1), $rate)
        & $adb shell screencap -p /sdcard/_p.png 2>&1 | Out-Null
        & $adb pull /sdcard/_p.png "$shotDir\progress_$($i.ToString('0000')).png" 2>&1 | Out-Null
        & $adb shell rm /sdcard/_p.png 2>&1 | Out-Null
    }

    Start-Sleep -Milliseconds $DelayMs
}

$total = (Get-Date) - $start
Write-Host ""
Write-Host ("=== Done in {0} min ===" -f [math]::Round($total.TotalMinutes, 1)) -ForegroundColor Green
