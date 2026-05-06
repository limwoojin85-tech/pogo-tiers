# 자동 스캔 시작 — 박스 첫 포켓몬 진입한 상태에서 실행
# Renamer 가 ADB 로 탭 신호 보내서 박스 자동 순회
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$adb = Join-Path $root "platform-tools\adb.exe"
$env:PATH = "$root\platform-tools;$env:PATH"
$renamerDir = Join-Path $root "PokemonGo-CalcyIV-Renamer"

if (-not (Test-Path $renamerDir)) {
    Write-Host "[err] Renamer 없음 - .\setup.ps1 먼저 실행" -ForegroundColor Red
    exit 1
}

Write-Host "=== 사전 점검 ===" -ForegroundColor Cyan
Write-Host "체크리스트 (모두 ✓ 되어야 시작):"
Write-Host "  1) 태블릿 USB 연결 + 디버깅 허용"
Write-Host "  2) Pokemon GO 실행 + 박스 진입"
Write-Host "  3) 박스 첫 포켓몬 (도감 1번 또는 정렬 첫 마리) 디테일 화면"
Write-Host "  4) Calcy IV 본체 앱: Switch to Game (오버레이 동그라미 보여야 함)"
Write-Host "  5) Calcy IV 가 첫 포켓몬 IV 자동 인식 되어 보임"
Write-Host ""
$ok = Read-Host "다 됐으면 'y' 입력 (취소: 엔터)"
if ($ok -ne 'y' -and $ok -ne 'Y') {
    Write-Host "취소됨"
    exit 0
}

Push-Location $renamerDir
try {
    Write-Host ""
    Write-Host "=== Calcy IV rename pattern 복사 (1회만) ===" -ForegroundColor Cyan
    Write-Host "이 명령이 Calcy IV 가 인식할 rename 패턴을 폰 클립보드에 복사합니다."
    Write-Host "복사 후 폰: Calcy IV -> Renaming -> 양쪽 패턴 입력란 끝에 '붙여넣기'"
    Write-Host ""
    $r = Read-Host "이미 한 번 했으면 'skip', 처음이면 엔터"
    if ($r -ne 'skip') {
        python ivcheck.py --copy-calcy
        Write-Host ""
        Write-Host "이제 폰에서:"
        Write-Host "  Calcy IV 본체 앱 -> 메뉴 -> Renaming"
        Write-Host "  Pattern 1, Pattern 2 양쪽 끝에 '붙여넣기' (이미 입력된 거 뒤에)"
        Write-Host "  저장"
        Write-Host ""
        Read-Host "완료했으면 엔터"
    }

    Write-Host ""
    Write-Host "=== 자동 스캔 시작 ===" -ForegroundColor Green
    Write-Host "30분~1시간 자동 진행. 화면 끄지 마세요. 충전기 권장."
    Write-Host "Ctrl+C 로 중단 가능."
    Write-Host ""
    python ivcheck.py
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "=== 완료 ===" -ForegroundColor Green
Write-Host "이제 폰에서:"
Write-Host "  1) Calcy IV 본체 앱 -> History"
Write-Host "  2) 우상단 메뉴 -> Export -> CSV"
Write-Host "  3) CSV 파일 PC 또는 우리 사이트에 업로드"
