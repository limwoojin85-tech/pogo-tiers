# Calcy IV ADB Auto Setup - Windows PowerShell
# Run once: Downloads ADB + clones renamer + installs Python deps
# Usage: PowerShell -> .\setup.ps1

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ptDir = Join-Path $root "platform-tools"
$ptZip = Join-Path $root "platform-tools.zip"
$ptUrl = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"

Write-Host "=== 1. ADB Platform Tools ===" -ForegroundColor Cyan
if (Test-Path (Join-Path $ptDir "adb.exe")) {
    Write-Host "[skip] ADB already installed at $ptDir" -ForegroundColor Green
} else {
    Write-Host "Downloading from $ptUrl ..."
    Invoke-WebRequest -Uri $ptUrl -OutFile $ptZip
    Write-Host "Extracting..."
    Expand-Archive -Path $ptZip -DestinationPath $root -Force
    Remove-Item $ptZip
    Write-Host "[ok] Installed to $ptDir" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== 2. Clone Renamer Script ===" -ForegroundColor Cyan
$renamerDir = Join-Path $root "PokemonGo-CalcyIV-Renamer"
if (Test-Path (Join-Path $renamerDir "ivcheck.py")) {
    Write-Host "[skip] Already cloned, pulling latest"
    Push-Location $renamerDir
    cmd /c "git pull 2>&1" | Out-Null
    Pop-Location
} else {
    cmd /c "git clone https://github.com/Azelphur/PokemonGo-CalcyIV-Renamer.git `"$renamerDir`" 2>&1" | Out-Null
}
if (Test-Path (Join-Path $renamerDir "ivcheck.py")) {
    Write-Host "[ok] Renamer ready" -ForegroundColor Green
} else {
    Write-Host "[err] Clone failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== 3. Python Packages ===" -ForegroundColor Cyan
python -m pip install --user pyyaml ruamel.yaml 2>&1 | Tee-Object -FilePath (Join-Path $root "_pip.log")

Write-Host ""
Write-Host "=== 4. Config ===" -ForegroundColor Cyan
$conf = Join-Path $renamerDir "config.yaml"
$confEx = Join-Path $renamerDir "config.example.yaml"
if (-not (Test-Path $conf)) {
    Copy-Item $confEx $conf
    Write-Host "[ok] Created config.yaml"
} else {
    Write-Host "[skip] config.yaml already exists"
}

Write-Host ""
Write-Host "=== SETUP DONE ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next - on tablet:"
Write-Host "  1) Settings > About tablet > Software info > tap 'Build number' 7 times"
Write-Host "  2) Settings > Developer options > 'USB debugging' ON"
Write-Host "  3) Connect USB-C cable to PC"
Write-Host "  4) Tablet popup: 'Allow USB debugging?' -> 'Always allow'"
Write-Host ""
Write-Host "Then on PC:"
Write-Host "  cd `"$root`""
Write-Host "  .\check.ps1   # Verify connection"
Write-Host "  .\run.ps1     # Start auto-scan"
