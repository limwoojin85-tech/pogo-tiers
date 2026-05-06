# Calcy IV 자동 스캔 (ADB)

PC가 USB로 태블릿 자동 조작. 손가락 노동 0.

## 한 번만

PowerShell 열고:

```powershell
cd "C:\Users\limwo\새 폴더\pogo_tiers\scripts\calcy_adb"
.\setup.ps1
```

→ ADB · Renamer · Python 패키지 자동 설치.

## 태블릿 사전 설정

1. **개발자 옵션 활성**
   - 설정 → 태블릿 정보 → 소프트웨어 정보 → **빌드 번호 7번 연속 탭**
   - "개발자 모드 활성됨" 토스트
2. **USB 디버깅 ON**
   - 설정 → 개발자 옵션 → **USB 디버깅** ON
3. **USB-C 연결**
   - PC와 케이블 연결
   - 태블릿: "USB 디버깅 허용?" → "**항상 허용**"
4. **Calcy IV + Pokemon GO 설치 확인** (이미 있을 듯)

## 연결 확인

```powershell
.\check.ps1
```

전부 OK 나와야 함. 안 나오면 체크리스트 따라가기.

## 실행

```powershell
.\run.ps1
```

스크립트가 안내:
1. 태블릿: Pokemon GO → 박스 → 첫 포켓몬 디테일 진입
2. Calcy IV: Switch to Game (오버레이 켜기)
3. PC: 'y' 입력
4. **PC + 태블릿 그대로 두고 30~60분 대기**

자동 진행:
- PC가 태블릿에 탭 신호 → Pokemon 디테일 → Calcy 가 IV 인식 → renaming string 으로 history 저장 → swipe 다음 포켓몬 → 반복

## 끝나고

태블릿:
1. Calcy IV 본체 앱
2. History
3. 우상단 메뉴 → **Export → CSV**
4. 파일 → 우리 사이트 (`📥 Calcy 분석` 탭) 업로드

## 잘 안 될 때

- **탭 좌표 안 맞아서 멈춤**: `PokemonGo-CalcyIV-Renamer/config.yaml` 의 X,Y 값을 태블릿 해상도에 맞게 조정.
  - 태블릿 해상도는 `check.ps1` 출력에 나옴 (예: `1812x2176`).
  - config 의 default 는 1080p (1080x1920) 기준이므로 비율로 환산.
- **Calcy IV 가 IV 못 읽음**: Calcy IV 본체 앱에서 "Autoscan" 모드 ON 확인.
- **포켓몬 스와이프 안 됨**: Pokemon GO 가 가끔 swipe 막을 때 있음. config 의 `swipe_*` 좌표 조정.
