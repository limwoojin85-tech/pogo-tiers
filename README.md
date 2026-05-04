# pogo_tiers

포켓몬고 PvP 리그/컵 + 레이드 카운터 티어 데이터 수집기.
한글 + 영어 + 속성 상성 + 추천 기술까지 단일 HTML 로 패키징.

## 사용 — 한 방에

```powershell
cd "C:\Users\limwo\새 폴더\pogo_tiers"
python update.py
```

24시간 이상 오래된 데이터만 다시 받고 HTML 재빌드.
강제 전체 재실행: `python update.py --force`
HTML 만 재빌드 (디버깅): `python update.py --no-fetch`

## 자동 업데이트 등록 (Windows)

매일 06:00 자동 갱신 — 관리자 PowerShell:
```powershell
schtasks /Create /SC DAILY /TN "pogo_tiers" /TR "python C:\Users\limwo\새 폴더\pogo_tiers\update.py" /ST 06:00
```

## 개별 단계

```powershell
python fetch_pvpoke.py        # pvpoke 리그/컵 랭킹
python fetch_pokebattler.py   # 레이드 보스 + 카운터
python fetch_translations.py  # 한글 번역
python must_have.py           # MD 출력
python build_html.py          # HTML 생성
```

## 출력

```
data/pvpoke/{league}_{cp}.json    # pvpoke 원본 랭킹 (전체)
data/pvpoke/_gamemaster.json      # 종/기술 메타
data/pokebattler/tiers.json       # 현재 + 미래 레이드 보스 목록
data/pokebattler/counters/        # 보스별 카운터 원본

out/index.html                    # ⭐ 메인 — 단일 HTML, 검색/필터/탭
out/must_have.md                  # 마스터 리스트 (덱스 순 표, 한글)
out/must_have_essentials.md       # 핵심 33종 상세 카드 (한글)
out/raids_by_boss.md              # 보스별 카운터 + 보스 약점
out/by_league.md                  # 리그/컵별 Top
```

## 폰에서 항상 최신으로 (GitHub Pages 자동 배포)

### 1회 셋업

```powershell
cd "C:\Users\limwo\새 폴더\pogo_tiers"
git init
git add .
git commit -m "initial"

# GitHub 에서 새 public repo 생성 (예: pogo-tiers)
git remote add origin https://github.com/limwoojin85-tech/pogo-tiers.git
git branch -M main
git push -u origin main
```

### Pages 활성화

GitHub repo → Settings → Pages → Source: **GitHub Actions** 선택. 끝.

첫 배포 후 URL: `https://limwoojin85-tech.github.io/pogo-tiers/`

### 자동 갱신

- **매일 KST 06:00** Actions 가 자동 실행 → 최신 데이터 받아서 → Pages 재배포
- 수동 강제 실행: GitHub repo → Actions → "Update & Deploy" → "Run workflow"
- `*.py` 수정해서 push 하면 즉시 재빌드

### 폰에서

1. Chrome/Safari 로 위 URL 접속
2. **홈 화면에 추가** (Add to Home Screen) — 앱처럼 아이콘 생성
3. 클릭 시 항상 최신 데이터 (HTML 캐시 비활성화 메타태그 들어있음)

## HTML 로컬 사용

`out/index.html` 더블클릭. 서버 필요 없음.

탭:
- **속성별** (메인) — 18 속성 카드. 클릭하면 그 속성의 약점 보스 + 키울 가치 있는 종 + 자주 쓰이는 리그
- **리그·컵별** — 슈퍼/하이퍼/마스터 + 컵 시즌 모두, 각 Top 15
- **검색** — 내 박스 포켓몬 이름 (한/영) 입력 → 살릴지/보낼지 + 어느 IV 등급 챙길지 판단

상단:
- 검색창 (어느 탭이든 작동)
- 속성 필터
- 정렬 (도감번호 / 살릴 가치 ↓ / 한글 가나다)

투자 가이드 색깔:
- 🔴 핵심 (마스터/하이퍼/슈퍼리그 Top 5 또는 메이저 레이드 Top 5)
- 🟡 권장 (Top 6-15)
- 🔵 컵 한정 (시즌 끝나면 무가치)
- ⚪ 보내기 OK

## 기준

- PvP 마스터: 각 리그/컵 Top 15
- PvP 핵심: GL/UL/ML Top 5 만
- Raid 마스터: 보스별 카운터 Top 8 (보스 무브셋 평균 순위)
- Raid 핵심: 현재 활성 T5/그림자T5/메가/메가5/UB/엘리트 Top 5

레이드 티어 화이트리스트 (`fetch_pokebattler.py`):
T1, T3, T5, T5_FUTURE, T5_SHADOW(_FUTURE), MEGA(_FUTURE), MEGA_5(_FUTURE),
ULTRA_BEAST(_FUTURE), ELITE.
LEGACY/UNSET/MAX (다이맥스) 는 제외.

## 출처

- pvpoke: https://github.com/pvpoke/pvpoke (`src/data/rankings/`)
- PokeBattler: https://fight.pokebattler.com/ 공개 API

## 다음 단계

내 박스 IV 데이터 (Calcy IV / 수동 OCR / Pokegenie 등) 들어오면
`match.py` 추가해서 `내 보유 ✕ 티어 랭킹` 으로 추천 리스트 생성.
