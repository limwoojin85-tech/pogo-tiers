# Verify tablet connection + Calcy IV install
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$adb = Join-Path $root "platform-tools\adb.exe"

if (-not (Test-Path $adb)) {
    Write-Host "[err] ADB not found. Run .\setup.ps1 first" -ForegroundColor Red
    exit 1
}

Write-Host "=== 1. ADB Devices ===" -ForegroundColor Cyan
& $adb devices

$devices = & $adb devices | Select-String -Pattern "device$" | Where-Object { $_ -notmatch "List" }
if ($devices.Count -eq 0) {
    Write-Host ""
    Write-Host "[err] No device connected" -ForegroundColor Red
    Write-Host "Checklist:"
    Write-Host "  - USB-C cable connected?"
    Write-Host "  - Tablet screen on?"
    Write-Host "  - 'Developer options > USB debugging' ON?"
    Write-Host "  - Tablet 'Allow USB debugging?' dialog confirmed?"
    Write-Host "  - USB mode: 'File transfer (MTP)' or 'Debugging'?"
    exit 1
}

Write-Host ""
Write-Host "=== 2. Screen Resolution ===" -ForegroundColor Cyan
$res = & $adb shell wm size
Write-Host $res

Write-Host ""
Write-Host "=== 3. Calcy IV ===" -ForegroundColor Cyan
$calcy = & $adb shell pm list packages tesmath.calcy
if ($calcy) {
    Write-Host "[ok] Calcy IV installed: $calcy" -ForegroundColor Green
} else {
    Write-Host "[err] Calcy IV not installed - get from Play Store" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== 4. Pokemon GO ===" -ForegroundColor Cyan
$pogo = & $adb shell pm list packages com.nianticlabs.pokemongo
if ($pogo) {
    Write-Host "[ok] Pokemon GO installed" -ForegroundColor Green
} else {
    Write-Host "[err] Pokemon GO not installed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "All OK. Now run .\run.ps1" -ForegroundColor Green
