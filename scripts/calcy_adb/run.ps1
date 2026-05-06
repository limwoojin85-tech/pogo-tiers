# Start auto-scan - run this AFTER you are at first Pokemon detail screen
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$adb = Join-Path $root "platform-tools\adb.exe"
$env:PATH = "$root\platform-tools;$env:PATH"
$renamerDir = Join-Path $root "PokemonGo-CalcyIV-Renamer"

if (-not (Test-Path $renamerDir)) {
    Write-Host "[err] Renamer not found - run .\setup.ps1 first" -ForegroundColor Red
    exit 1
}

Write-Host "=== Pre-flight Checklist ===" -ForegroundColor Cyan
Write-Host "All must be ready before starting:"
Write-Host "  1) Tablet connected via USB + debugging allowed"
Write-Host "  2) Pokemon GO running, in box view"
Write-Host "  3) FIRST Pokemon (e.g. dex #1) detail screen open"
Write-Host "  4) Calcy IV main app -> Switch to Game (yellow overlay visible)"
Write-Host "  5) Calcy IV is auto-reading the first Pokemon's IV"
Write-Host ""
$ok = Read-Host "Ready? type 'y' (cancel = enter)"
if ($ok -ne 'y' -and $ok -ne 'Y') {
    Write-Host "Cancelled"
    exit 0
}

Push-Location $renamerDir
try {
    Write-Host ""
    Write-Host "=== Calcy IV rename pattern setup (one-time) ===" -ForegroundColor Cyan
    Write-Host "This copies the rename pattern Calcy IV needs to the device clipboard."
    Write-Host "Then on tablet: Calcy IV -> Renaming -> paste at end of both pattern fields."
    Write-Host ""
    $r = Read-Host "Already done before? type 'skip' (else enter)"
    if ($r -ne 'skip') {
        python ivcheck.py --copy-calcy
        Write-Host ""
        Write-Host "Now on tablet:"
        Write-Host "  Calcy IV main app -> menu -> Renaming"
        Write-Host "  Paste at the END of both Pattern 1 and Pattern 2 fields"
        Write-Host "  Save"
        Write-Host ""
        Read-Host "Press Enter when done"
    }

    Write-Host ""
    Write-Host "=== Starting auto-scan ===" -ForegroundColor Green
    Write-Host "Will run 30-60 minutes. Keep screen on. Plug in charger."
    Write-Host "Press Ctrl+C to stop."
    Write-Host ""
    python ivcheck.py
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "On tablet:"
Write-Host "  1) Calcy IV main app -> History"
Write-Host "  2) menu -> Export -> CSV"
Write-Host "  3) Upload CSV to our site or transfer to PC"
