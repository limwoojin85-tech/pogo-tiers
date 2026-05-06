# 태블릿 연결 + Calcy IV 설치 확인
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$adb = Join-Path $root "platform-tools\adb.exe"

if (-not (Test-Path $adb)) {
    Write-Host "[err] ADB 없음. 먼저 .\setup.ps1 실행" -ForegroundColor Red
    exit 1
}

Write-Host "=== 1. ADB 디바이스 ===" -ForegroundColor Cyan
& $adb devices

$devices = & $adb devices | Select-String -Pattern "device$" | Where-Object { $_ -notmatch "List" }
if ($devices.Count -eq 0) {
    Write-Host ""
    Write-Host "[err] 연결된 디바이스 없음" -ForegroundColor Red
    Write-Host "체크리스트:"
    Write-Host "  - USB-C 케이블 연결됨?"
    Write-Host "  - 태블릿 화면 켜져 있음?"
    Write-Host "  - '개발자 옵션 -> USB 디버깅' ON?"
    Write-Host "  - 태블릿에서 'USB 디버깅 허용' 다이얼로그 '확인' 했나?"
    Write-Host "  - USB 모드: '파일 전송 (MTP)' 또는 '디버깅' 모드?"
    exit 1
}

Write-Host ""
Write-Host "=== 2. 화면 해상도 ===" -ForegroundColor Cyan
$res = & $adb shell wm size
Write-Host $res

Write-Host ""
Write-Host "=== 3. Calcy IV 설치 확인 ===" -ForegroundColor Cyan
$calcy = & $adb shell pm list packages tesmath.calcy
if ($calcy) {
    Write-Host "[ok] Calcy IV 설치됨: $calcy" -ForegroundColor Green
} else {
    Write-Host "[err] Calcy IV 없음 - Play Store 에서 설치하세요" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== 4. Pokemon GO 설치 확인 ===" -ForegroundColor Cyan
$pogo = & $adb shell pm list packages com.nianticlabs.pokemongo
if ($pogo) {
    Write-Host "[ok] Pokemon GO 설치됨" -ForegroundColor Green
} else {
    Write-Host "[err] Pokemon GO 없음" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "전부 OK. 이제 .\run.ps1 실행 가능" -ForegroundColor Green
