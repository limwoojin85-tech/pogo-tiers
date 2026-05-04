"""
PokeBattler 레이드 보스 + 카운터 다운로더.

1. /raids 로 현재 활성 레이드 보스 목록 (티어별)
2. 보스마다 /raids/defenders/{POKEMON}/levels/{LEVEL}/attackers/levels/40/...
   로 카운터 랭킹.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "data" / "pokebattler"
COUNTERS_DIR = OUT_DIR / "counters"
COUNTERS_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://fight.pokebattler.com"
UA = {"User-Agent": "pogo-tiers-fetcher/1.0"}

# 4성 이상 — T1/T3 는 가치 없음 (거의 모든 포켓몬이 카운터)
TIER_WHITELIST = {
    "RAID_LEVEL_5",
    "RAID_LEVEL_5_FUTURE",
    "RAID_LEVEL_5_SHADOW",
    "RAID_LEVEL_5_SHADOW_FUTURE",
    "RAID_LEVEL_MEGA",
    "RAID_LEVEL_MEGA_FUTURE",
    "RAID_LEVEL_MEGA_5",
    "RAID_LEVEL_MEGA_5_FUTURE",
    "RAID_LEVEL_ULTRA_BEAST",
    "RAID_LEVEL_ULTRA_BEAST_FUTURE",
    "RAID_LEVEL_ELITE",
}

# 카운터 쿼리 — 평균 날씨 / 일반 친구도 / 현실적 랜덤 회피
COUNTER_PARAMS = {
    "sort": "OVERALL",
    "weatherCondition": "NO_WEATHER",
    "dodgeStrategy": "DODGE_REACTION_TIME",
    "aggregation": "AVERAGE",
    "randomAssistants": "-1",
    "friendLevel": "FRIENDSHIP_LEVEL_0",
    "includeLegendary": "true",
    "includeShadow": "true",
    "includeMega": "true",
}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch_tiers() -> dict:
    data = get_json(f"{BASE}/raids")
    (OUT_DIR / "tiers.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def fetch_counters(pokemon: str, tier: str) -> Path | None:
    qs = urllib.parse.urlencode(COUNTER_PARAMS)
    url = (
        f"{BASE}/raids/defenders/{pokemon}/levels/{tier}"
        f"/attackers/levels/40"
        f"/strategies/CINEMATIC_ATTACK_WHEN_POSSIBLE/DEFENSE_RANDOM_MC"
        f"?{qs}"
    )
    out = COUNTERS_DIR / f"{pokemon}_{tier}.json"
    try:
        data = get_json(url)
    except Exception as e:
        print(f"  ! {pokemon} {tier}: {e}", file=sys.stderr)
        return None
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> None:
    print("[pokebattler] 현재 레이드 티어 가져오는 중...")
    tiers = fetch_tiers()

    bosses: list[tuple[str, str]] = []  # (pokemon, tier)
    for t in tiers.get("tiers", []):
        tier = t.get("tier")
        if not tier or tier not in TIER_WHITELIST:
            continue
        for r in t.get("raids", []):
            poke = r.get("pokemon") or r.get("pokemonId")
            if poke:
                bosses.append((poke, tier))

    # 이미 받은 파일은 스킵
    existing = {p.stem for p in COUNTERS_DIR.glob("*.json")}
    todo = [b for b in bosses if f"{b[0]}_{b[1]}" not in existing]
    print(f"[pokebattler] 보스 {len(bosses)}마리 (필요 {len(todo)}, 스킵 {len(bosses) - len(todo)})")

    ok = 0
    for poke, tier in todo:
        if fetch_counters(poke, tier):
            ok += 1
            print(f"  {poke} ({tier})")
        time.sleep(0.15)  # 서버 매너

    print(f"[pokebattler] 완료: {ok}/{len(bosses)} → {COUNTERS_DIR}")


if __name__ == "__main__":
    main()
