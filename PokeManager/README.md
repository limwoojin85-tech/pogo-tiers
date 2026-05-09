# PokeManager — Android 앱 (pogo_tiers 통합)

포켓몬 GO 박스 분석을 폰에서 직접 — 칼시IV / 포케지니 대체.

## 핵심 차이점

기존 칼시IV 가 못 잡는 거 다 됨:
- **그림자** (별가루 ÷1.2 보정)
- **정화** (별가루 ÷0.9 보정)
- **다이맥스** (조사 가능 — 일반 폼과 같은 메커니즘)
- **한글 이름** OCR (기존 라틴만 → 한국어 인식기 추가)

## 구조

```
PokeManager/
├── app/src/main/
│   ├── AndroidManifest.xml        권한 + 서비스
│   ├── assets/
│   │   ├── pokemon_stats.json     1571 종 (모든 폼) — base stats + 한글
│   │   ├── species_meta.json      랭킹 + PvP/raid 메타 (648 종)
│   │   ├── groups.json            transfer/mega/pre_evolution 그룹
│   │   └── cpm.json               CPM 테이블 (Lv1~51)
│   ├── java/com/woojin/pokemanager/
│   │   ├── MainActivity.kt
│   │   ├── calc/
│   │   │   ├── IVCalculator.kt    (그림자/정화 별가루 보정 포함)
│   │   │   ├── PvPRanker.kt
│   │   │   └── BucketClassifier.kt 사이트 8 bucket 분류 포팅
│   │   ├── data/
│   │   │   ├── Species.kt         + SpeciesMeta.kt + GroupsData
│   │   │   ├── GameMasterRepo.kt  1571 종 + groups + meta
│   │   │   ├── OnlineSync.kt      사이트 must_have.json fetch
│   │   │   ├── MyPokemon.kt + PokemonDao + AppDatabase
│   │   ├── ocr/
│   │   │   └── PogoOCR.kt         라틴 + 한글 OCR 동시 실행
│   │   ├── overlay/OverlayService.kt  자동 스캔 오버레이 (1초 주기)
│   │   └── list/MyPokemonActivity.kt  내 박스
│   └── res/layout/...
├── scripts/sync_data.py           pogo_tiers 데이터 → assets 변환
└── build.gradle.kts
```

## 셋업 (개발)

1. Android Studio 에서 이 폴더 열기 (`pogo_tiers/PokeManager`)
2. `File → Sync Project with Gradle Files`
3. 폰 USB 연결 + 디버깅 ON
4. `Run → Run 'app'`

처음 실행:
- "화면 위에 표시" 권한 허용
- "오버레이 시작" 버튼 → 화면 캡처 권한 허용

## 셋업 (사용)

폰 → 분할화면:
- 좌측: PokeManager 앱 (오버레이만)
- 우측: Pokemon GO (박스 detail)

PokeManager 의 FAB 아이콘을 Pokemon GO 화면 쪽으로 드래그 → 자동 분석 시작.

## 데이터 동기화

**오프라인 모드** (기본): assets 의 임베드 데이터 사용 (앱 빌드 시점 데이터).

**온라인 갱신**: 메인 화면 → "데이터 갱신" → 사이트 (limwoojin85-tech.github.io/pogo-tiers) 의 최신 must_have.json fetch.

데이터 자체는 매일 06:00 KST 자동 갱신 (사이트의 GitHub Actions).

## 데이터 재생성

`pogo_tiers/` 의 데이터를 갱신했을 때:
```bash
cd PokeManager
python scripts/sync_data.py
# assets 4개 파일 갱신됨
```

이후 다시 빌드.

## 의존성

- Kotlin 2.0.21 + AGP 8.13.2
- ML Kit text-recognition (라틴) + text-recognition-korean
- Room 2.6.1
- Gson 2.10.1
- 최소 SDK: Android 8.0 (API 26)

## 빠진 기능 (TODO)

- [ ] 다이맥스 별가루 보정 UI
- [ ] OCR 정확도 튜닝 (포고 폰트 특성)
- [ ] BucketClassifier 의 leagueScorePct — base_stats 정확한 계산 (현재 IV 합 기준 단순화)
- [ ] 결과 화면에서 "송출 OK" 시 ADB 통한 자동 송출 (옵션)
