# Calcy IV ADB 자동 셋업 - Windows PowerShell
# 한 번만 실행: ADB 다운로드 + 환경 준비
# 사용: 우클릭 -> "PowerShell 로 실행" 또는 PowerShell 에서 .\setup.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ptDir = Join-Path $root "platform-tools"
$ptZip = Join-Path $root "platform-tools.zip"
$ptUrl = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"

Write-Host "=== 1. ADB Platform Tools 다운로드 ===" -ForegroundColor Cyan
if (Test-Path (Join-Path $ptDir "adb.exe")) {
    Write-Host "[skip] $ptDir 에 ADB 이미 있음" -ForegroundColor Green
} else {
    Write-Host "다운로드 중... ($ptUrl)"
    Invoke-WebRequest -Uri $ptUrl -OutFile $ptZip
    Write-Host "압축 해제 중..."
    Expand-Archive -Path $ptZip -DestinationPath $root -Force
    Remove-Item $ptZip
    Write-Host "[ok] $ptDir 에 설치됨" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== 2. Renamer 스크립트 클론 ===" -ForegroundColor Cyan
$renamerDir = Join-Path $root "PokemonGo-CalcyIV-Renamer"
if (Test-Path $renamerDir) {
    Write-Host "[skip] $renamerDir 이미 있음 -- git pull 로 갱신"
    Push-Location $renamerDir
    git pull 2>&1 | Out-Null
    Pop-Location
} else {
    git clone https://github.com/Azelphur/PokemonGo-CalcyIV-Renamer.git $renamerDir
}

Write-Host ""
Write-Host "=== 3. Python 패키지 설치 ===" -ForegroundColor Cyan
python -m pip install --user pyyaml ruamel.yaml 2>&1 | Tee-Object -FilePath (Join-Path $root "_pip.log")

Write-Host ""
Write-Host "=== 4. config 준비 ===" -ForegroundColor Cyan
$conf = Join-Path $renamerDir "config.yaml"
$confEx = Join-Path $renamerDir "config.example.yaml"
if (-not (Test-Path $conf)) {
    Copy-Item $confEx $conf
    Write-Host "[ok] config.yaml 생성됨"
} else {
    Write-Host "[skip] config.yaml 이미 있음"
}

Write-Host ""
Write-Host "=== 셋업 완료 ===" -ForegroundColor Green
Write-Host ""
Write-Host "다음 단계 (폰):"
Write-Host "  1) 태블릿: 설정 -> 태블릿 정보 -> 소프트웨어 정보 -> '빌드 번호' 7번 탭"
Write-Host "  2) 설정 -> 개발자 옵션 -> 'USB 디버깅' ON"
Write-Host "  3) USB-C 로 PC 에 연결 -> 태블릿에서 'USB 디버깅 허용?' -> '항상 허용'"
Write-Host ""
Write-Host "그 다음 PC 에서:"
Write-Host "  cd `"$root`""
Write-Host "  .\check.ps1   # 연결 확인"
Write-Host "  .\run.ps1     # 실행"
