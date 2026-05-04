"""
다운로드된 데이터에서 사람이 읽는 요약 생성.

out/leagues_top.md  - 리그/컵별 Top N
out/raids_top.md    - 레이드 보스별 카운터 Top N
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent
PVPOKE_DIR = ROOT / "data" / "pvpoke"
PB_DIR = ROOT / "data" / "pokebattler"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

TOP_N_LEAGUE = 30
TOP_N_RAID = 15


def league_label(stem: str) -> str:
    # all_1500 → "Great League (1500)" 같이
    league, _, cp = stem.rpartition("_")
    nice = {
        "all_1500": "Great League (CP 1500)",
        "all_2500": "Ultra League (CP 2500)",
        "all_10000": "Master League (CP 10000)",
        "all_500": "Little Cup (CP 500)",
    }
    return nice.get(stem, f"{league} (CP {cp})")


def summarize_leagues() -> None:
    files = sorted(PVPOKE_DIR.glob("*_*.json"))
    files = [f for f in files if not f.name.startswith("_")]

    lines: list[str] = ["# pvpoke 리그/컵 Top {}\n".format(TOP_N_LEAGUE)]
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        lines.append(f"\n## {league_label(f.stem)}\n")
        lines.append("| # | Pokemon | Score | Fast | Charged |")
        lines.append("|---|---|---|---|---|")
        for i, mon in enumerate(data[:TOP_N_LEAGUE], 1):
            name = mon.get("speciesName") or mon.get("speciesId", "?")
            score = mon.get("score", "")
            moveset = mon.get("moveset") or []
            fast = moveset[0] if len(moveset) > 0 else ""
            charged = " / ".join(moveset[1:3]) if len(moveset) > 1 else ""
            lines.append(f"| {i} | {name} | {score} | {fast} | {charged} |")

    (OUT / "leagues_top.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[summary] leagues_top.md ({len(files)} 파일)")


def summarize_raids() -> None:
    counter_files = sorted((PB_DIR / "counters").glob("*.json"))
    if not counter_files:
        print("[summary] 카운터 데이터 없음 — fetch_pokebattler.py 먼저 실행")
        return

    lines: list[str] = ["# PokeBattler 레이드 카운터 Top {}\n".format(TOP_N_RAID)]
    by_tier: dict[str, list[Path]] = {}
    for f in counter_files:
        # 파일명: {POKEMON}_{TIER}.json
        stem = f.stem
        if "_RAID_LEVEL_" in stem:
            poke, tier = stem.split("_RAID_LEVEL_", 1)
            tier = "RAID_LEVEL_" + tier
        else:
            poke, _, tier = stem.rpartition("_")
        by_tier.setdefault(tier, []).append(f)

    for tier in sorted(by_tier):
        lines.append(f"\n## {tier}\n")
        for f in sorted(by_tier[tier]):
            data = json.loads(f.read_text(encoding="utf-8"))
            boss = f.stem.split("_RAID_LEVEL_")[0] if "_RAID_LEVEL_" in f.stem else f.stem.rsplit("_", 1)[0]
            # PokeBattler 응답 구조: {"attackers":[{"pokemonId":..., "byMove":[...] }, ...]}
            attackers = (
                data.get("attackers")
                or data.get("response", {}).get("attackers")
                or []
            )
            lines.append(f"\n### {boss}\n")
            lines.append("| # | Counter | Best Moveset | TTW (s) | Deaths |")
            lines.append("|---|---|---|---|---|")
            for i, atk in enumerate(attackers[:TOP_N_RAID], 1):
                name = atk.get("pokemonId", "?")
                by_move = atk.get("byMove") or []
                best = by_move[0] if by_move else {}
                result = best.get("result") or best
                fast = best.get("move1", "")
                charged = best.get("move2", "")
                ttw_ms = result.get("effectiveCombatTime") or result.get("combatTime") or 0
                ttw = round(ttw_ms / 1000, 1) if ttw_ms else ""
                deaths = result.get("effectiveDeaths") or result.get("deaths") or ""
                if isinstance(deaths, (int, float)):
                    deaths = round(deaths, 2)
                lines.append(f"| {i} | {name} | {fast} / {charged} | {ttw} | {deaths} |")

    (OUT / "raids_top.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[summary] raids_top.md ({len(counter_files)} 보스)")


if __name__ == "__main__":
    summarize_leagues()
    summarize_raids()
