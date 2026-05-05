"""
pvpoke 랭킹 일괄 다운로더.

GitHub repo 의 src/data/rankings/ 는 현재 활성 컵만 있음.
pvpoke.com/data/rankings/ 는 archive 까지 호스팅 (과거 컵 포함).
→ pvpoke.com 을 source 로 사용 + 알려진 historical 컵 전부 probe.

data/pvpoke/{cup}_{cp}.json 로 저장.
"""
from __future__ import annotations

import concurrent.futures
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "data" / "pvpoke"
OUT_DIR.mkdir(parents=True, exist_ok=True)

GH_API = "https://api.github.com/repos/pvpoke/pvpoke/contents/src/data/rankings"
PVPOKE_RAW = "https://pvpoke.com/data/rankings"   # archive 까지 호스팅됨
GH_RAW = "https://raw.githubusercontent.com/pvpoke/pvpoke/master/src/data/rankings"

UA = {"User-Agent": "pogo-tiers-fetcher/1.0"}

# 알려진 컵 — 과거 시즌 + 현재 활성. 안 열릴 컵도 포함 (다시 돌아올 수 있음).
# pvpoke.com 에서 probe 해서 200 이면 받음.
KNOWN_CUPS: list[str] = [
    # ── 메이저
    "all", "premier", "little", "classic",
    # ── 세대 / 지역
    "kanto", "johto", "hoenn", "sinnoh", "unova", "kalos", "alola", "galar", "paldea",
    # ── 계절 / 테마
    "halloween", "holiday", "summer", "spring", "autumn", "winter", "valentine", "love",
    "evolution", "color", "fossil", "beast", "mythical", "mythicalexp", "mythicalblitz",
    "beginner", "ferocity", "willpower", "tinkerer", "shore",
    "kingdom", "twilight", "mountain", "forest", "sunshine", "frostlight",
    "festival", "vintage", "throwback", "psychic", "champion", "championshipseries",
    # ── 단일 타입 컵
    "single-type-bug", "single-type-dark", "single-type-dragon",
    "single-type-electric", "single-type-fairy", "single-type-fighting",
    "single-type-fire", "single-type-flying", "single-type-ghost",
    "single-type-grass", "single-type-ground", "single-type-ice",
    "single-type-normal", "single-type-poison", "single-type-psychic",
    "single-type-rock", "single-type-steel", "single-type-water",
    # ── WCS / 대회
    "naic2024", "naic2025", "naic2026", "naic",
    "laic", "laic2024", "laic2025", "laic2025remix", "laic2026",
    "euic", "euic2024", "euic2025", "euic2026",
    "ocic", "ocic2024", "ocic2025", "ocic2026",
    "worlds", "worlds2024", "worlds2025", "worlds2026",
    # ── 데본/배틀 프런티어 (현재)
    "bayou", "spellcraft", "equinox", "maelstrom", "cosy",
    "electric", "fantasy", "chrono", "catch", "jungle",
    "bfretro", "battlefrontiermaster",
    # ── 기타
    "retro", "remix",
]

# 컵별 CP 조합 — 명시 안 하면 1500 만 시도
CP_COMBOS: dict[str, list[int]] = {
    "all": [500, 1500, 2500, 10000],
    "premier": [500, 1500, 2500, 10000],
    "classic": [500, 1500, 2500, 10000],
    "little": [500],
    "battlefrontiermaster": [10000],
    "bfretro": [2500],
}
DEFAULT_CPS: list[int] = [1500]


def fetch_gamemaster() -> None:
    """gamemaster.json — 종 메타 + rank1 IV 등 핵심 메타데이터."""
    url = "https://raw.githubusercontent.com/pvpoke/pvpoke/master/src/data/gamemaster.json"
    out = OUT_DIR / "_gamemaster.json"
    print("[pvpoke] gamemaster.json 다운로드")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        out.write_bytes(r.read())


def probe_one(cup: str, cp: int) -> tuple[str, int, bytes | None]:
    """pvpoke.com 에서 cup/cp 다운로드 시도. 없으면 None."""
    url = f"{PVPOKE_RAW}/{cup}/overall/rankings-{cp}.json"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if len(data) < 100:
            return (cup, cp, None)
        return (cup, cp, data)
    except urllib.error.HTTPError as e:
        if e.code in (404, 403):
            return (cup, cp, None)
        return (cup, cp, None)
    except Exception:
        return (cup, cp, None)


def get_active_cups() -> set[str]:
    """gamemaster.json 의 cups 배열 → 현재 활성 컵 set."""
    gm_path = OUT_DIR / "_gamemaster.json"
    if not gm_path.exists():
        return set()
    try:
        gm = json.loads(gm_path.read_text(encoding="utf-8"))
        return {c["name"] for c in gm.get("cups", []) if c.get("name")}
    except Exception:
        return set()


def main() -> None:
    fetch_gamemaster()
    active = get_active_cups()
    print(f"[pvpoke] gamemaster 활성 컵 {len(active)}개")

    # cup × cp 조합 (중복 제거)
    probes: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for cup in KNOWN_CUPS + sorted(active):
        cps = CP_COMBOS.get(cup, DEFAULT_CPS)
        for cp in cps:
            if (cup, cp) in seen:
                continue
            seen.add((cup, cp))
            probes.append((cup, cp))

    print(f"[pvpoke] {len(probes)} 조합 probe (병렬)...")

    saved: list[str] = []
    archived_only: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        results = ex.map(lambda x: probe_one(*x), probes)
        for cup, cp, data in results:
            if data is None:
                continue
            out = OUT_DIR / f"{cup}_{cp}.json"
            out.write_bytes(data)
            saved.append(out.name)
            if cup not in active and cup not in {"all", "premier", "little", "classic"}:
                archived_only.append(out.name)

    manifest = {
        "active_cups": sorted(active),
        "saved": sorted(saved),
        "archived_only": sorted(archived_only),
    }
    (OUT_DIR / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[pvpoke] 완료: {len(saved)}개 저장 ({len(archived_only)}개 archive) → {OUT_DIR}")


if __name__ == "__main__":
    main()
