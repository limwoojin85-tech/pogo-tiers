"""
모든 데이터를 단일 HTML (out/index.html) 로 패키징.

- 임베디드 JSON + vanilla JS
- 탭: 핵심 / 전체 / 레이드 (보스별) / 리그별
- 검색, 타입 필터, 정렬
- 더블클릭으로 열림 (서버 X)
"""
from __future__ import annotations

import datetime
import json
import re
from collections import defaultdict
from pathlib import Path

from must_have import (
    PB,
    PVPOKE,
    OUT,
    LEAGUE_KO,
    TIER_LABEL,
    PVP_TOP_N,
    RAID_TOP_N,
    ESSENTIAL_PVP_RANK,
    ESSENTIAL_RAID_RANK,
    MAJOR_LEAGUES_KEYS,
    ESSENTIAL_RAID_TIERS,
    load_translations,
    load_gamemaster,
    move_name_pair,
    pb_to_pvpoke_id,
    species_ko_name,
)
from type_chart import weaknesses_resistances, ALL_TYPES, SE


# 투자 가이드 — 어느 IV 등급까지 모을 가치 있는지 결정
def invest_guide(sp: dict) -> dict:
    """
    출력:
      stages: [{ko, en, priority, reason}, ...]
        priority: 1=핵심 / 2=권장 / 3=선택 / 4=보내기
      verdict_ko: 한 줄 요약
      keep_score: 정렬용 점수 (높을수록 살리는 게 좋음)
    """
    stages = []
    score = 0

    # 마스터리그 또는 레이드 → 100% IV
    is_master = any(p["league_key"] == "all_10000" and p["rank"] <= 20 for p in sp["pvp"])
    is_raid_essential = any(
        r["is_essential_tier"] and r["rank"] <= 5 for r in sp["raid"]
    )
    is_raid_useful = any(
        r["is_essential_tier"] and r["rank"] <= 8 for r in sp["raid"]
    )
    if is_master or is_raid_essential:
        stages.append({
            "ko": "마스터/레이드",
            "en": "Master/Raid",
            "priority": 1,
            "reason": "100% IV (15/15/15) 우선 — CP 풀로 키움",
        })
        score += 100
    elif is_raid_useful:
        stages.append({
            "ko": "레이드 보조",
            "en": "Raid sub",
            "priority": 2,
            "reason": "고 CP IV 챙기되 1순위는 아님",
        })
        score += 40

    # 하이퍼리그
    is_ul = any(p["league_key"] in {"all_2500", "premier_2500", "classic_2500"}
                and p["rank"] <= 15 for p in sp["pvp"])
    if is_ul:
        ul_top = min((p["rank"] for p in sp["pvp"]
                      if p["league_key"] in {"all_2500", "premier_2500"}), default=99)
        stages.append({
            "ko": "하이퍼리그",
            "en": "Ultra League",
            "priority": 1 if ul_top <= 5 else 2,
            "reason": f"하이퍼리그 랭크 1 IV (저공·고방·고체) — UL 최고 #{ul_top}",
        })
        score += 80 if ul_top <= 5 else 50

    # 슈퍼리그
    is_gl = any(p["league_key"] in {"all_1500", "premier_1500", "classic_1500"}
                and p["rank"] <= 15 for p in sp["pvp"])
    if is_gl:
        gl_top = min((p["rank"] for p in sp["pvp"]
                      if p["league_key"] in {"all_1500", "premier_1500"}), default=99)
        stages.append({
            "ko": "슈퍼리그",
            "en": "Great League",
            "priority": 1 if gl_top <= 5 else 2,
            "reason": f"슈퍼리그 랭크 1 IV — GL 최고 #{gl_top}",
        })
        score += 80 if gl_top <= 5 else 50

    # 리틀컵
    is_lc = any(p["league_key"] in {"all_500", "little_500", "premier_500"}
                and p["rank"] <= 10 for p in sp["pvp"])
    if is_lc:
        stages.append({
            "ko": "리틀컵",
            "en": "Little Cup",
            "priority": 2,
            "reason": "리틀컵 랭크 1 IV (저레벨)",
        })
        score += 30

    # 컵 한정
    cup_only_leagues = [p for p in sp["pvp"]
                        if p["league_key"] not in {
                            "all_500", "all_1500", "all_2500", "all_10000",
                            "premier_500", "premier_1500", "premier_2500", "premier_10000",
                            "little_500", "classic_500", "classic_1500",
                            "classic_2500", "classic_10000",
                        }]
    if cup_only_leagues and not stages:
        # 가장 높은 순위 순으로 컵 나열
        sorted_cups = sorted(cup_only_leagues, key=lambda p: p["rank"])
        cup_strs = [f"{p['league_ko']}#{p['rank']}" for p in sorted_cups[:4]]
        cup_label = " · ".join(cup_strs)
        stages.append({
            "ko": cup_label,
            "en": "Cup only",
            "priority": 3,
            "reason": "컵 시즌에만 활약 — 시즌 끝나면 무가치",
        })
        score += 10

    if not stages:
        stages.append({
            "ko": "보내기 OK",
            "en": "Transfer OK",
            "priority": 4,
            "reason": "랭킹 외 — 보내거나 사탕 변환",
        })

    # 한 줄 요약 — 우선순위 + 구체적 등장처(랭크 포함)
    def best_rank_in(keys: set[str]) -> tuple[str, int] | None:
        cands = [(p["league_ko"], p["rank"]) for p in sp["pvp"]
                 if p["league_key"] in keys]
        if not cands:
            return None
        return min(cands, key=lambda x: x[1])

    parts = []
    if any(s["priority"] == 1 and s["ko"] == "마스터/레이드" for s in stages):
        ml = best_rank_in({"all_10000", "premier_10000", "classic_10000"})
        rd = sp["raid"][0] if sp["raid"] else None
        bits = []
        if ml: bits.append(f"{ml[0]}#{ml[1]}")
        if rd: bits.append(f"vs {rd['boss_ko']}#{rd['rank']}({rd['tier_ko']})")
        if bits: parts.append(" · ".join(bits))
    if any(s["ko"] == "하이퍼리그" for s in stages):
        ul = best_rank_in({"all_2500", "premier_2500", "classic_2500"})
        if ul: parts.append(f"{ul[0]}#{ul[1]}")
    if any(s["ko"] == "슈퍼리그" for s in stages):
        gl = best_rank_in({"all_1500", "premier_1500", "classic_1500"})
        if gl: parts.append(f"{gl[0]}#{gl[1]}")
    if any(s["ko"] == "리틀컵" for s in stages):
        lc = best_rank_in({"all_500", "little_500", "premier_500", "classic_500"})
        if lc: parts.append(f"{lc[0]}#{lc[1]}")
    cup_stage = next((s for s in stages if s["en"] == "Cup only"), None)
    if cup_stage:
        parts.append(cup_stage["ko"])
    if any(s["ko"] == "레이드 보조" for s in stages) and not any("vs" in p for p in parts):
        rd = sp["raid"][0] if sp["raid"] else None
        if rd: parts.append(f"vs {rd['boss_ko']}#{rd['rank']}({rd['tier_ko']})")

    verdict = " / ".join(parts) if parts else "보내도 OK"

    return {"stages": stages, "verdict_ko": verdict, "keep_score": score}


def collect_all(species, moves, trans):
    """모든 데이터 한 덩어리 dict 로 — JSON 임베드용."""
    moves_ko = trans["moves"]
    types_ko = trans.get("types_ko", {})

    # 진화 부모 맵 + rank 1 IV (pvpoke gamemaster 에서)
    gm = json.loads((PVPOKE / "_gamemaster.json").read_text(encoding="utf-8"))
    parent_map: dict[str, str] = {}
    rank1_iv_map: dict[str, dict] = {}
    for p in gm["pokemon"]:
        fam = p.get("family") or {}
        parent = fam.get("parent")
        if parent:
            parent_map[p["speciesId"]] = parent
        rank1_iv_map[p["speciesId"]] = p.get("defaultIVs") or {}

    def evolution_chain(sid: str) -> list[str]:
        """[base, ..., current] — 진화 사슬 (현재 포함)."""
        chain = [sid]
        seen = {sid}
        cur = sid
        while cur in parent_map and parent_map[cur] not in seen:
            cur = parent_map[cur]
            chain.append(cur)
            seen.add(cur)
        return list(reversed(chain))

    # 종 메타 + 매치업 캐시
    species_out: dict[str, dict] = {}
    for sid, info in species.items():
        types = info["types"]
        weak, resist = weaknesses_resistances(types)
        chain_ids = evolution_chain(sid)
        chain_kos = []
        chain_ens = []
        for cid in chain_ids:
            cinfo = species.get(cid, {})
            cdex = cinfo.get("dex", info["dex"])
            cen = cinfo.get("name_en", cid)
            cko = species_ko_name(cdex, cen, trans)
            chain_kos.append(cko)
            chain_ens.append(cen)
        # rank 1 IV: cp500/cp1500/cp2500 → [level, atk, def, sta]
        # cp10000 (마스터) 는 항상 50/15/15/15 → 따로 표시 X
        ivs = rank1_iv_map.get(sid) or {}
        rank1 = {}
        for cp_key, label in [("cp500", "Little"), ("cp1500", "GL"),
                              ("cp2500", "UL")]:
            v = ivs.get(cp_key)
            if v and len(v) == 4:
                rank1[label] = {
                    "lv": v[0], "atk": v[1], "def": v[2], "sta": v[3],
                }
        species_out[sid] = {
            "id": sid,
            "dex": info["dex"],
            "ko": species_ko_name(info["dex"], info["name_en"], trans),
            "en": info["name_en"],
            "types": types,
            "weak": {t: round(m, 4) for t, m in weak.items()},
            "resist": {t: round(m, 4) for t, m in resist.items()},
            "chain_ko": chain_kos,
            "chain_en": chain_ens,
            "rank1_iv": rank1,
            "pvp": [],
            "raid": [],
        }

    # PvP 데이터
    leagues_out: dict[str, dict] = {}
    for f in sorted(PVPOKE.glob("*_*.json")):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        league_key = f.stem
        ko, en = LEAGUE_KO.get(league_key, (league_key, league_key))
        # 메이저인지 표시
        is_major = league_key in MAJOR_LEAGUES_KEYS
        cup_only = "_" in league_key and league_key not in {
            "all_500", "all_1500", "all_2500", "all_10000",
            "premier_500", "premier_1500", "premier_2500", "premier_10000",
            "little_500",
        }
        league_out = {
            "key": league_key, "ko": ko, "en": en,
            "is_major": is_major, "is_cup": cup_only,
            "entries": [],
        }
        for rank, mon in enumerate(data[:PVP_TOP_N], 1):
            sid = mon.get("speciesId")
            if not sid or sid not in species_out:
                continue
            mset = mon.get("moveset") or []
            # mset[0]=fast, mset[1:3]=charged
            fast_pair = move_name_pair(moves, moves_ko, mset[0]) if mset else ("", "")
            charged_pairs = [move_name_pair(moves, moves_ko, m) for m in mset[1:3] if m]
            fast_ko = fast_pair[0] or fast_pair[1]
            fast_en = fast_pair[1]
            charged_ko = " · ".join(p[0] or p[1] for p in charged_pairs)
            charged_en = " · ".join(p[1] for p in charged_pairs)
            entry = {
                "rank": rank, "sid": sid,
                "score": mon.get("score") or mon.get("rating") or 0,
                "fast_ko": fast_ko, "fast_en": fast_en,
                "charged_ko": charged_ko, "charged_en": charged_en,
            }
            league_out["entries"].append(entry)
            species_out[sid]["pvp"].append({
                "league_key": league_key,
                "league_ko": ko, "league_en": en,
                "is_major": is_major,
                "rank": rank,
                "fast_ko": fast_ko, "fast_en": fast_en,
                "charged_ko": charged_ko, "charged_en": charged_en,
            })
        leagues_out[league_key] = league_out

    # 레이드 데이터
    bosses_out: dict[str, dict] = {}
    for f in sorted(PB.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        m = re.match(r"^(.+?)_RAID_LEVEL_(.+)$", f.stem)
        if not m:
            continue
        boss_pb, tier = m.group(1), "RAID_LEVEL_" + m.group(2)
        if tier not in TIER_LABEL:
            continue
        tier_ko, tier_en = TIER_LABEL[tier]
        boss_sid = pb_to_pvpoke_id(boss_pb)
        boss_info = species.get(boss_sid, {})
        boss_dex = boss_info.get("dex", 9999)
        boss_en = boss_info.get("name_en", boss_pb.replace("_", " ").title())
        boss_ko = species_ko_name(boss_dex, boss_en, trans) if boss_dex != 9999 else boss_en
        boss_types = boss_info.get("types", [])
        weak_b, _ = weaknesses_resistances(boss_types)

        atk_list = d.get("attackers") or []
        if not atk_list:
            continue
        boss_atk = atk_list[0]
        ranks: dict[str, list[int]] = defaultdict(list)
        movesets: dict[str, tuple[str, str, str, str]] = {}
        n = max(1, len(boss_atk.get("byMove", [])))
        for bm in boss_atk.get("byMove", []):
            for rank, defender in enumerate(bm.get("defenders", []), 1):
                pid_pb = defender.get("pokemonId")
                if not pid_pb:
                    continue
                pid_pv = pb_to_pvpoke_id(pid_pb)
                ranks[pid_pv].append(rank)
                if pid_pv not in movesets:
                    d_bm = (defender.get("byMove") or [{}])[0]
                    fk, fe = move_name_pair(moves, moves_ko, d_bm.get("move1"))
                    ck, ce = move_name_pair(moves, moves_ko, d_bm.get("move2"))
                    movesets[pid_pv] = (fk, fe, ck, ce)
        PENALTY = 999
        avg = {pid: (sum(rs) + (n - len(rs)) * PENALTY) / n for pid, rs in ranks.items()}
        ranked = sorted(avg.items(), key=lambda x: x[1])[:RAID_TOP_N]

        boss_key = f"{boss_pb}_{tier}"
        counters = []
        for new_rank, (pid, _) in enumerate(ranked, 1):
            cinfo = species.get(pid, {})
            cdex = cinfo.get("dex", 0)
            cen = cinfo.get("name_en", pid)
            cko = species_ko_name(cdex, cen, trans) if cdex else pid
            fk, fe, ck, ce = movesets[pid]
            counters.append({
                "rank": new_rank, "sid": pid, "ko": cko, "en": cen,
                "fast_ko": fk or fe, "fast_en": fe,
                "charged_ko": ck or ce, "charged_en": ce,
            })
            if pid in species_out:
                species_out[pid]["raid"].append({
                    "boss_key": boss_key,
                    "boss_ko": boss_ko, "boss_en": boss_en, "boss_dex": boss_dex,
                    "tier_en": tier_en, "tier_ko": tier_ko,
                    "is_essential_tier": tier_en in ESSENTIAL_RAID_TIERS,
                    "rank": new_rank,
                    "fast_ko": fk or fe, "fast_en": fe,
                    "charged_ko": ck or ce, "charged_en": ce,
                })
        bosses_out[boss_key] = {
            "key": boss_key,
            "boss_ko": boss_ko, "boss_en": boss_en,
            "boss_dex": boss_dex, "boss_types": boss_types,
            "boss_weak": {t: round(m, 4) for t, m in weak_b.items()},
            "tier_ko": tier_ko, "tier_en": tier_en,
            "counters": counters,
        }

    # 핵심 마킹 + 투자 가이드
    essential_ids = set()
    for sid, sdata in species_out.items():
        major_pvp = any(p["is_major"] and p["rank"] <= ESSENTIAL_PVP_RANK
                        for p in sdata["pvp"])
        major_raid = any(r["is_essential_tier"] and r["rank"] <= ESSENTIAL_RAID_RANK
                         for r in sdata["raid"])
        if major_pvp or major_raid:
            essential_ids.add(sid)
        sdata["invest"] = invest_guide(sdata)
    for sid in species_out:
        species_out[sid]["essential"] = sid in essential_ids

    # 등장한 종만 남김
    species_out = {sid: s for sid, s in species_out.items()
                   if s["pvp"] or s["raid"]}

    # 속성별 집계 — 사용자가 진짜로 원하는 뷰
    types_out: dict[str, dict] = {}
    for t in ALL_TYPES:
        # 1. 이 속성으로 강하게 때릴 수 있는 보스 (현재/예정)
        weak_bosses = []
        for bk, b in bosses_out.items():
            if t in b["boss_weak"]:
                weak_bosses.append({
                    "boss_key": bk,
                    "boss_ko": b["boss_ko"], "boss_en": b["boss_en"],
                    "boss_dex": b["boss_dex"],
                    "tier_ko": b["tier_ko"], "tier_en": b["tier_en"],
                    "mult": b["boss_weak"][t],
                })
        weak_bosses.sort(key=lambda x: (-x["mult"], x["tier_en"], x["boss_dex"] or 9999))

        # 2. 이 속성을 가진 핵심 종 (살릴 가치 ranked)
        type_species = [s for s in species_out.values() if t in s["types"]]
        type_species.sort(key=lambda s: -s["invest"]["keep_score"])
        core = [{
            "sid": s["id"], "dex": s["dex"], "ko": s["ko"], "en": s["en"],
            "types": s["types"],
            "verdict_ko": s["invest"]["verdict_ko"],
            "keep_score": s["invest"]["keep_score"],
            "essential": s["essential"],
        } for s in type_species[:30]]

        # 3. 이 속성이 핵심인 PvP 리그
        league_uses = []
        for lk, lg in leagues_out.items():
            count = sum(1 for e in lg["entries"]
                        if t in species_out.get(e["sid"], {}).get("types", []))
            if count >= 2:  # 2종 이상 등장한 리그만
                league_uses.append({
                    "league_key": lk, "league_ko": lg["ko"], "league_en": lg["en"],
                    "count": count, "is_major": lg["is_major"],
                })
        league_uses.sort(key=lambda x: (-int(x["is_major"]), -x["count"]))

        types_out[t] = {
            "type": t, "ko": types_ko.get(t, t),
            "weak_bosses": weak_bosses,
            "core_species": core,
            "league_uses": league_uses,
            "boss_count": len(weak_bosses),
            "core_count": len(type_species),
        }

    return {
        "species": species_out,
        "bosses": bosses_out,
        "leagues": leagues_out,
        "types": types_out,
        "types_ko": types_ko,
        "essentials_count": len(essential_ids),
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="cache-control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="pragma" content="no-cache">
<meta http-equiv="expires" content="0">
<meta name="theme-color" content="#1d1d1f">
<link rel="manifest" href="data:application/json,{%22name%22:%22%ED%8F%AC%EC%BC%93%EB%AA%AC%EA%B3%A0%20%EB%B0%95%EC%8A%A4%22,%22display%22:%22standalone%22,%22start_url%22:%22./%22}">
<title>포켓몬고 박스 의사결정 도우미</title>
<style>
  * { box-sizing: border-box; }
  :root {
    --bg: #f5f5f7; --card: #fff; --text: #1d1d1f; --muted: #6e6e73;
    --line: #e0e0e6; --accent: #2e7cf6; --raid: #ff6b35;
    --pri1: #d70015; --pri2: #ff9500; --pri3: #007aff; --pri4: #8e8e93;
  }
  body { font-family: 'Segoe UI', 'Apple SD Gothic Neo', 'Malgun Gothic', system-ui, sans-serif;
         margin: 0; background: var(--bg); color: var(--text); line-height: 1.45;
         -webkit-font-smoothing: antialiased; }
  header { background: #fff; border-bottom: 1px solid var(--line);
           position: sticky; top: 0; z-index: 100;
           box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
  .head-inner { max-width: 1400px; margin: 0 auto; padding: 10px 16px; }
  .head-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .head-row + .head-row { margin-top: 8px; }
  h1 { font-size: 15px; margin: 0; font-weight: 600; flex-shrink: 0;
       white-space: nowrap; }
  h1 .sub { color: var(--muted); font-weight: 400; font-size: 12px; margin-left: 6px; }
  .ctrl { padding: 6px 10px; font-size: 13px; border: 1px solid #d0d0d6;
          border-radius: 6px; background: #fff; }
  #search { flex: 1 1 200px; min-width: 140px; max-width: 360px; }
  .tabs { display: flex; gap: 2px; background: #e8e8ec;
          padding: 3px; border-radius: 8px; flex-wrap: wrap; }
  .tab { padding: 5px 12px; font-size: 12px; cursor: pointer; border-radius: 5px;
         user-select: none; transition: background 0.15s; white-space: nowrap; }
  .tab:hover { background: rgba(255,255,255,0.5); }
  .tab.active { background: #fff; font-weight: 600; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .tab .cnt { color: var(--muted); font-weight: 400; font-size: 11px; margin-left: 3px; }
  main { padding: 14px 16px 80px; max-width: 1400px; margin: 0 auto; }
  .stat { color: var(--muted); font-size: 12px; margin-bottom: 10px; }

  .card { background: var(--card); border-radius: 10px; padding: 12px 14px;
          margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
  .card h2 { font-size: 15px; margin: 0 0 6px 0; display: flex;
             align-items: baseline; gap: 6px; flex-wrap: wrap; }
  .card h3 { font-size: 14px; margin: 10px 0 5px 0; color: var(--muted);
             font-weight: 600; text-transform: none; }
  .dex { color: var(--muted); font-size: 12px; font-weight: 400; }
  .en { color: var(--muted); font-size: 12px; font-weight: 400; }

  .badge { display: inline-block; padding: 1px 7px; border-radius: 4px;
           font-size: 11px; color: #fff; font-weight: 600;
           text-shadow: 0 1px 1px rgba(0,0,0,0.2); white-space: nowrap; }
  .row { font-size: 13px; margin: 3px 0; }
  .row .lbl { color: var(--muted); min-width: 50px; display: inline-block;
              font-weight: 600; font-size: 11px; text-transform: uppercase;
              letter-spacing: 0.04em; }
  .multipliers .badge { margin-right: 3px; margin-bottom: 2px; }
  .role { background: #f5f5f7; padding: 5px 8px; border-radius: 5px;
          margin: 3px 0; font-size: 12px; }
  .role .en-mv { color: var(--muted); font-size: 11px; }
  .role.pvp { border-left: 3px solid var(--accent); }
  .role.raid { border-left: 3px solid var(--raid); }

  /* 투자 가이드 */
  .verdict { display: inline-flex; align-items: center; gap: 6px;
             padding: 3px 8px; border-radius: 5px; font-size: 12px;
             font-weight: 600; margin-bottom: 6px; }
  .pri-1 { background: #ffe8eb; color: var(--pri1); }
  .pri-2 { background: #fff3d9; color: var(--pri2); }
  .pri-3 { background: #e0eaff; color: var(--pri3); }
  .pri-4 { background: #f0f0f3; color: var(--pri4); }
  .stages { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
  .stage { padding: 2px 6px; border-radius: 4px; font-size: 11px;
           border: 1px solid; }
  .stage.pri-1 { border-color: var(--pri1); }
  .stage.pri-2 { border-color: var(--pri2); }
  .stage.pri-3 { border-color: var(--pri3); }
  .stage.pri-4 { border-color: var(--pri4); }
  .stage .reason { color: var(--muted); margin-left: 4px; font-weight: 400; }

  table { width: 100%; border-collapse: collapse; background: #fff;
          border-radius: 8px; overflow: hidden;
          box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 10px; }
  th, td { padding: 6px 8px; font-size: 12px; text-align: left;
           border-bottom: 1px solid #f0f0f3; vertical-align: top; }
  th { background: #fafafa; font-weight: 600; color: var(--muted); }
  tr:last-child td { border-bottom: none; }
  tr:hover { background: #fafafa; }
  td.num { color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
  td.rank { font-weight: 600; color: var(--accent); }
  .moves-ko { font-weight: 500; }
  .moves-en { color: var(--muted); font-size: 11px; }
  .ml { color: var(--muted); font-size: 10px; font-weight: 600; text-transform: uppercase; }
  .rk-list { display: flex; flex-direction: column; gap: 2px; }
  .rk { font-size: 11px; padding: 1px 6px; border-radius: 3px; white-space: nowrap; }
  .rk small { font-size: 10px; opacity: 0.7; margin-left: 3px; }
  .rk-major { background: #ffe8eb; color: var(--pri1); font-weight: 600; }
  .rk-cup { background: #f0f0f3; color: var(--muted); }
  .chain { color: #8e8e93; font-size: 11px; font-weight: 400; }
  .iv-cell { display: inline-block; line-height: 1.2; }
  .iv-cell b { color: var(--accent); font-size: 13px; }
  .iv-vals { font-family: 'Consolas', 'Menlo', monospace; font-size: 12px;
             color: var(--text); }
  .iv-note { background: #e0eaff; color: var(--pri3); padding: 6px 10px;
             border-radius: 6px; font-size: 12px; margin-bottom: 10px; }
  .ovl-list { display: flex; flex-direction: column; gap: 2px; }
  .ovl { font-size: 11px; padding: 1px 6px; border-radius: 3px;
         font-weight: 600; white-space: nowrap; }
  .ovl-gl { background: #d6f5d6; color: #186118; }
  .ovl-ul { background: #d6e6f5; color: #1b4d80; }
  .ovl-ml { background: #f5e6d6; color: #804a1b; }
  .ovl-lc { background: #f5d6e6; color: #80286c; }
  .ovl-raid { background: #ffe8eb; color: var(--pri1); }
  .ovl-cup { background: #f0f0f3; color: var(--muted); }
  small.muted { color: var(--muted); font-size: 10px; font-weight: 400; }

  .section-h { font-size: 13px; font-weight: 700; color: var(--text);
               margin: 16px 0 6px 0; padding-bottom: 4px;
               border-bottom: 2px solid var(--line); }
  .boss-head { display: flex; align-items: baseline; gap: 8px;
               flex-wrap: wrap; margin: 12px 0 4px 0; }
  .boss-head h3 { margin: 0; font-size: 14px; color: var(--text); font-weight: 600; }
  .boss-head .weak { font-size: 11px; color: var(--muted); }

  .t-normal{background:#a8a77a}.t-fire{background:#ee8130}.t-water{background:#6390f0}
  .t-electric{background:#f7d02c;color:#1d1d1f;text-shadow:none}.t-grass{background:#7ac74c}
  .t-ice{background:#96d9d6;color:#1d1d1f;text-shadow:none}.t-fighting{background:#c22e28}
  .t-poison{background:#a33ea1}.t-ground{background:#e2bf65;color:#1d1d1f;text-shadow:none}
  .t-flying{background:#a98ff3}.t-psychic{background:#f95587}.t-bug{background:#a6b91a}
  .t-rock{background:#b6a136}.t-ghost{background:#735797}.t-dragon{background:#6f35fc}
  .t-dark{background:#705746}.t-steel{background:#b7b7ce;color:#1d1d1f;text-shadow:none}
  .t-fairy{background:#d685ad}

  .empty { color: var(--muted); font-style: italic; padding: 40px 20px;
           text-align: center; }
  .more { padding: 8px; text-align: center; cursor: pointer; color: var(--accent);
          font-size: 12px; user-select: none; }
  .more:hover { background: #fafafa; border-radius: 6px; }

  /* 속성 그리드 */
  .type-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
               gap: 10px; }
  .type-card { background: #fff; border-radius: 10px; padding: 12px;
               box-shadow: 0 1px 3px rgba(0,0,0,0.05); cursor: pointer;
               border-top: 4px solid; transition: transform 0.1s; }
  .type-card:hover { transform: translateY(-1px); box-shadow: 0 3px 8px rgba(0,0,0,0.08); }
  .type-card .type-h { display: flex; align-items: center; justify-content: space-between;
                       margin-bottom: 6px; }
  .type-card .name-ko { font-size: 16px; font-weight: 700; }
  .type-card .name-en { color: var(--muted); font-size: 11px; }
  .type-card .nums { display: flex; gap: 8px; font-size: 11px; color: var(--muted); }
  .type-card .top-mons { display: flex; gap: 3px; flex-wrap: wrap; margin-top: 6px; }
  .type-card .mon { font-size: 11px; padding: 2px 6px; background: #f5f5f7;
                    border-radius: 4px; }
  .type-card .mon.essential { background: #ffe8eb; color: var(--pri1); font-weight: 600; }

  /* 좁은 화면 */
  @media (max-width: 600px) {
    .head-inner { padding: 8px 12px; }
    h1 { font-size: 14px; }
    h1 .sub { display: none; }
    main { padding: 10px 12px 60px; }
    .tab { padding: 4px 8px; font-size: 11px; }
    .tab .cnt { display: none; }
    th, td { padding: 5px 6px; font-size: 11px; }
    .moves-en { display: none; }
    .role { font-size: 11px; }
    .badge { font-size: 10px; padding: 1px 5px; }
  }
</style>
</head>
<body>
<header>
  <div class="head-inner">
    <div class="head-row">
      <h1>포켓몬고 박스 의사결정<span class="sub">살릴지 · 보낼지 · IV 등급 · 최종 업데이트 __BUILD_TIME__</span></h1>
      <div class="tabs">
        <div class="tab active" data-tab="types">속성별</div>
        <div class="tab" data-tab="gl">슈퍼리그</div>
        <div class="tab" data-tab="ul">하이퍼리그</div>
        <div class="tab" data-tab="ml">마스터리그</div>
        <div class="tab" data-tab="raids">레이드</div>
        <div class="tab" data-tab="lc">리틀컵</div>
        <div class="tab" data-tab="cups">컵 시즌</div>
        <div class="tab" data-tab="search">검색</div>
      </div>
    </div>
    <div class="head-row">
      <input id="search" class="ctrl" placeholder="포켓몬·기술·보스 검색 (한글·영어)">
      <select id="type-filter" class="ctrl">
        <option value="">속성 필터 (전체)</option>
      </select>
      <select id="sort" class="ctrl">
        <option value="rank">정렬: 우선순위 ↑</option>
        <option value="keep">정렬: 살릴 가치 ↓</option>
        <option value="dex">정렬: 도감번호</option>
        <option value="ko">정렬: 한글 가나다</option>
      </select>
    </div>
  </div>
</header>
<main id="main"></main>

<script id="data" type="application/json">__DATA_JSON__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const TYPES_KO = DATA.types_ko;
const ALL_TYPES = ['normal','fighting','flying','poison','ground','rock','bug','ghost',
  'steel','fire','water','grass','electric','psychic','ice','dragon','dark','fairy'];

// 검색 인덱스 미리 만들기 (성능) — 진화 사슬 이름 포함
for (const sp of Object.values(DATA.species)) {
  sp._search = (sp.ko + ' ' + sp.en + ' ' + sp.id + ' ' +
    (sp.chain_ko||[]).join(' ') + ' ' + (sp.chain_en||[]).join(' ') + ' ' +
    sp.pvp.map(p => [p.fast_ko, p.fast_en, p.charged_ko, p.charged_en, p.league_ko].join(' ')).join(' ') + ' ' +
    sp.raid.map(r => [r.fast_ko, r.fast_en, r.charged_ko, r.charged_en, r.boss_ko, r.boss_en].join(' ')).join(' ')
  ).toLowerCase();
}
for (const b of Object.values(DATA.bosses)) {
  b._search = (b.boss_ko + ' ' + b.boss_en + ' ' +
    b.counters.map(c => c.ko + ' ' + c.en + ' ' + c.fast_ko + ' ' + c.fast_en + ' ' + c.charged_ko + ' ' + c.charged_en).join(' ')
  ).toLowerCase();
}

// 카운트는 각 탭 라벨 옆에 자동 표시 (별도 cnt 엘리먼트 사용 X)

const sel = document.getElementById('type-filter');
ALL_TYPES.forEach(t => {
  const o = document.createElement('option');
  o.value = t; o.textContent = `${TYPES_KO[t]||t} (${t})`;
  sel.appendChild(o);
});

let state = { tab: 'types', q: '', typeFilter: '', sort: 'rank', selectedType: null };
let renderTimer = null;

function debouncedRender() {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(render, 80);
}

document.querySelectorAll('.tab').forEach(el => {
  el.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    state.tab = el.dataset.tab;
    state.selectedType = null;
    render();
  });
});
document.getElementById('search').addEventListener('input', e => {
  state.q = e.target.value.toLowerCase().trim(); debouncedRender();
});
document.getElementById('type-filter').addEventListener('change', e => {
  state.typeFilter = e.target.value; render();
});
document.getElementById('sort').addEventListener('change', e => {
  state.sort = e.target.value; render();
});

function badge(t) { return `<span class="badge t-${t}">${TYPES_KO[t]||t}</span>`; }
function nameKo(sp) {
  // 진화 사슬 — 기초 이름 같이 표시
  const ck = sp.chain_ko || [sp.ko];
  if (ck.length <= 1) return `<b>${sp.ko}</b>`;
  // 현재가 마지막. 기초 + (중간) → 현재 형태로
  const base = ck[0];
  if (ck.length === 2) return `<b>${sp.ko}</b> <span class="chain">← ${base}</span>`;
  return `<b>${sp.ko}</b> <span class="chain">← ${ck.slice(0, -1).join(' → ')}</span>`;
}
function fmtMult(m) {
  if (Math.abs(m - Math.round(m)) < 0.01) return '×' + Math.round(m);
  return '×' + m.toFixed(2).replace(/\.?0+$/, '');
}
function multBadges(obj) {
  return Object.entries(obj).sort((a,b) => b[1]-a[1])
    .map(([t,m]) => `<span class="badge t-${t}">${TYPES_KO[t]||t} ${fmtMult(m)}</span>`).join(' ');
}
function speciesPasses(sp) {
  if (state.q && !sp._search.includes(state.q)) return false;
  if (state.typeFilter && !sp.types.includes(state.typeFilter)) return false;
  return true;
}
// rankCtxFn 은 정렬용 rank (낮은 것이 우선) — 컨텍스트마다 다름
function sortSpecies(arr, rankCtxFn) {
  if (state.sort === 'rank' && rankCtxFn) {
    return arr.sort((a,b) => rankCtxFn(a) - rankCtxFn(b) || a.dex - b.dex);
  }
  if (state.sort === 'keep') return arr.sort((a,b) => b.invest.keep_score - a.invest.keep_score || a.dex - b.dex);
  if (state.sort === 'ko') return arr.sort((a,b) => a.ko.localeCompare(b.ko, 'ko'));
  if (state.sort === 'dex') return arr.sort((a,b) => a.dex - b.dex || a.id.localeCompare(b.id));
  // rank 인데 ctx 없으면 keep 으로 fallback
  return arr.sort((a,b) => b.invest.keep_score - a.invest.keep_score || a.dex - b.dex);
}

// ━━━━━━ 속성별 뷰 ━━━━━━
function renderTypes() {
  if (state.selectedType) return renderTypeDetail(state.selectedType);
  const cards = ALL_TYPES.map(t => {
    const td = DATA.types[t];
    if (!td) return '';
    const top3 = td.core_species.slice(0, 5).map(s =>
      `<span class="mon ${s.essential?'essential':''}">${s.ko}</span>`
    ).join('');
    return `<div class="type-card t-${t}" style="border-color:var(--xx)" data-type="${t}">
      <div class="type-h">
        <div>
          <div class="name-ko">${td.ko}</div>
          <div class="name-en">${t}</div>
        </div>
        ${badge(t)}
      </div>
      <div class="nums">
        <span>약점 보스: <b>${td.boss_count}</b></span>
        <span>핵심 종: <b>${td.core_count}</b></span>
      </div>
      <div class="top-mons">${top3}</div>
    </div>`;
  }).join('');
  setTimeout(() => {
    document.querySelectorAll('.type-card').forEach(el => {
      el.addEventListener('click', () => {
        state.selectedType = el.dataset.type; render();
      });
    });
  }, 0);
  return `<div class="stat">속성을 클릭하면 그 속성으로 강하게 때릴 수 있는 보스 + 핵심 종 목록이 나옵니다.</div>
          <div class="type-grid">${cards}</div>`;
}

function renderTypeDetail(t) {
  const td = DATA.types[t];
  if (!td) return '<div class="empty">데이터 없음</div>';
  let html = `<div style="margin-bottom:10px"><span class="more" onclick="state.selectedType=null;render()">← 속성 목록으로</span></div>`;
  html += `<div class="card">
    <h2>${badge(t)} ${td.ko} <span class="en">/ ${t}</span></h2>
    <div class="stat">이 속성으로 공격하면 효과적인 곳, 그리고 키울 가치 있는 종.</div>
  </div>`;

  // 1. 약점 보스
  if (td.weak_bosses.length) {
    html += `<div class="section-h">이 속성으로 공격 — 약점인 보스 (${td.weak_bosses.length})</div>`;
    const grouped = {};
    for (const b of td.weak_bosses) {
      if (!grouped[b.tier_en]) grouped[b.tier_en] = [];
      grouped[b.tier_en].push(b);
    }
    const tierOrder = ['T5','T5sh','Mega','MegaT5','UB','Elite','T3','T1',
                       'T5*','T5sh*','Mega*','MegaT5*','UB*'];
    for (const tier of tierOrder) {
      const list = grouped[tier];
      if (!list) continue;
      html += `<h3>${list[0].tier_ko} (${list.length})</h3>`;
      html += `<table><tbody>` + list.map(b => {
        const dex = b.boss_dex && b.boss_dex < 9999 ? `#${String(b.boss_dex).padStart(3,'0')}` : '';
        return `<tr>
          <td class="num">${dex}</td>
          <td><b>${b.boss_ko}</b></td>
          <td class="en">${b.boss_en}</td>
          <td><span class="badge t-${t}">${fmtMult(b.mult)}</span></td>
        </tr>`;
      }).join('') + `</tbody></table>`;
    }
  }

  // 2. PvP 활약 리그
  if (td.league_uses.length) {
    html += `<div class="section-h">${td.ko} 타입이 자주 등장하는 리그/컵</div>`;
    html += `<table><thead><tr><th>리그/컵</th><th>등장 종 수</th></tr></thead><tbody>` +
      td.league_uses.slice(0, 15).map(l =>
        `<tr><td><b>${l.league_ko}</b> <span class="en">${l.league_en}</span></td>
             <td class="num">${l.count}종 ${l.is_major?'<span class="badge t-fire">메이저</span>':''}</td></tr>`
      ).join('') + `</tbody></table>`;
  }

  // 3. 핵심 종 — 분류별 컬럼 + IV (슈퍼/하이퍼만) + 노말/스페셜 분리
  const sortLabel = ({dex:'도감번호', ko:'가나다', keep:'살릴 가치', rank:'우선순위 (레이드)'})[state.sort] || '우선순위';
  html += `<div class="section-h">키울 가치 있는 ${td.ko} 타입 종 (정렬: ${sortLabel}) <span class="en">— ${td.core_count}종</span></div>`;

  const tweakBossKeys = new Set(td.weak_bosses.map(b => b.boss_key));
  const rankFn = sp => {
    let best = 9999;
    for (const r of sp.raid) {
      if (tweakBossKeys.has(r.boss_key) && r.rank < best) best = r.rank;
    }
    return best === 9999 ? (bestRaidRank(sp)?.rank || 999) + 100 : best;
  };
  let typeSpecies = td.core_species.map(s => DATA.species[s.sid]).filter(Boolean);
  typeSpecies = sortSpecies(typeSpecies, rankFn);

  html += `<table><thead><tr>
    <th>Dex</th><th>포켓몬</th><th>속성</th>
    <th>레이드 (vs ${td.ko}약점)</th><th>슈퍼 #</th><th>하이퍼 #</th><th>마스터 #</th>
    <th>슈퍼 IV</th><th>하이퍼 IV</th><th>추천 기술</th>
  </tr></thead><tbody>` + typeSpecies.slice(0, 50).map(sp => {
    let raidBest = null;
    for (const r of sp.raid) {
      if (tweakBossKeys.has(r.boss_key) && (!raidBest || r.rank < raidBest.rank)) raidBest = r;
    }
    const raidCell = raidBest
      ? `<span class="rk rk-major">vs ${raidBest.boss_ko} #${raidBest.rank}<small>${raidBest.tier_ko}</small></span>`
      : '<span class="muted">—</span>';
    const gl = bestRankIn(sp, GL_KEYS);
    const ul = bestRankIn(sp, UL_KEYS);
    const ml = bestRankIn(sp, ML_KEYS);
    const rkCell = (r) => (r && r.rank <= 15) ? `<span class="rk rk-major">#${r.rank}</span>` : '<span class="muted">—</span>';
    // 추천 기술: PvP 우선 (있으면 그쪽), 없으면 raid 무브셋
    let moveSrc = gl || ul || ml;
    if (!moveSrc && raidBest) moveSrc = raidBest;
    const moveCell = moveSrc ? moveSplitFromEntry(moveSrc) : '<span class="muted">—</span>';
    return `<tr>
      <td class="num">${String(sp.dex).padStart(3,'0')}</td>
      <td>${nameKo(sp)}<br><span class="en">${sp.en}</span></td>
      <td>${sp.types.map(badge).join(' ')}</td>
      <td>${raidCell}</td>
      <td>${rkCell(gl)}</td>
      <td>${rkCell(ul)}</td>
      <td>${rkCell(ml)}</td>
      <td>${ivCellGL(sp)}</td>
      <td>${ivCellUL(sp)}</td>
      <td>${moveCell}</td>
    </tr>`;
  }).join('') + `</tbody></table>`;
  return html;
}

// 헬퍼 — 리그 우선순위 (메이저 먼저, 컵 다음, 각 #랭크 + rank1 IV)
function ivForLeagueKey(sp, key) {
  const rk = sp.rank1_iv || {};
  if (key.includes('1500') && rk.GL) return rk.GL;
  if (key.includes('2500') && rk.UL) return rk.UL;
  if (key.includes('500') && !key.includes('1500') && !key.includes('2500') && rk.Little) return rk.Little;
  if (key.includes('10000')) return {lv: 50, atk: 15, def: 15, sta: 15};
  return null;
}
function pvpRanksHtml(sp) {
  if (!sp.pvp.length) return '<span style="color:var(--muted)">—</span>';
  const major = sp.pvp.filter(p => p.is_major).sort((a,b) => a.rank - b.rank);
  const others = sp.pvp.filter(p => !p.is_major).sort((a,b) => a.rank - b.rank);
  const fmt = (p, cls) => {
    const iv = ivForLeagueKey(sp, p.league_key);
    const ivStr = iv ? `<small>Lv${iv.lv} ${iv.atk}/${iv.def}/${iv.sta}</small>` : '';
    return `<span class="rk ${cls}">${p.league_ko} #${p.rank} ${ivStr}</span>`;
  };
  const parts = [];
  major.slice(0, 3).forEach(p => parts.push(fmt(p, 'rk-major')));
  others.slice(0, 3).forEach(p => parts.push(fmt(p, 'rk-cup')));
  return `<div class="rk-list">${parts.join('')}</div>`;
}
function raidRanksHtml(sp) {
  if (!sp.raid.length) return '<span style="color:var(--muted)">—</span>';
  const ranked = [...sp.raid].sort((a,b) => a.rank - b.rank);
  const seen = new Set();
  const parts = [];
  for (const r of ranked) {
    if (seen.has(r.boss_ko)) continue;
    seen.add(r.boss_ko);
    const cls = r.is_essential_tier ? 'rk-major' : 'rk-cup';
    parts.push(`<span class="rk ${cls}">vs ${r.boss_ko} #${r.rank}<small>${r.tier_ko}</small></span>`);
    if (parts.length >= 4) break;
  }
  // 마지막 줄에 IV: 100%
  parts.push(`<span class="rk rk-major">권장 IV: <small>100% (Lv50 15/15/15)</small></span>`);
  return `<div class="rk-list">${parts.join('')}</div>`;
}
function movesetsHtml(sp) {
  // PvP top moveset + raid top moveset
  const out = [];
  if (sp.pvp.length) {
    const top = [...sp.pvp].sort((a,b) => a.rank - b.rank)[0];
    out.push(`<div><span class="ml">PvP:</span> <b>${top.moves_ko}</b><br><span class="moves-en">${top.moves_en}</span></div>`);
  }
  if (sp.raid.length) {
    const top = [...sp.raid].sort((a,b) => a.rank - b.rank)[0];
    if (out.length === 0 || top.moves_ko !== sp.pvp[0]?.moves_ko) {
      out.push(`<div><span class="ml">Raid:</span> <b>${top.moves_ko}</b><br><span class="moves-en">${top.moves_en}</span></div>`);
    }
  }
  return out.join('') || '<span style="color:var(--muted)">—</span>';
}

// ━━━━━━ 박스 의사결정 ━━━━━━
function verdictHtml(inv) {
  const pri = Math.min(...inv.stages.map(s => s.priority));
  return `<span class="verdict pri-${pri}">${inv.verdict_ko}</span>`;
}
function stagesHtml(inv) {
  return `<div class="stages">` + inv.stages.map(s =>
    `<span class="stage pri-${s.priority}"><b>${s.ko}</b><span class="reason">${s.reason}</span></span>`
  ).join('') + `</div>`;
}

// rank 1 IV 추천 — 등장 리그에 맞춰 표시
function ivAdvice(sp) {
  const items = [];
  const stageLabels = sp.invest.stages.map(s => s.ko);
  const rk = sp.rank1_iv || {};
  const fmtIV = iv => `<b>Lv ${iv.lv}</b> · ${iv.atk}/${iv.def}/${iv.sta}`;
  if (stageLabels.includes('마스터/레이드')) {
    items.push(`<span class="iv-row pri-1"><b>마스터/레이드</b>: 100% (15/15/15) · Lv 50</span>`);
  } else if (stageLabels.includes('레이드 보조')) {
    items.push(`<span class="iv-row pri-2"><b>레이드</b>: 100% 우선 · Lv 50</span>`);
  }
  if (stageLabels.includes('하이퍼리그') && rk.UL) {
    items.push(`<span class="iv-row pri-2"><b>하이퍼리그</b>: ${fmtIV(rk.UL)}</span>`);
  }
  if (stageLabels.includes('슈퍼리그') && rk.GL) {
    items.push(`<span class="iv-row pri-2"><b>슈퍼리그</b>: ${fmtIV(rk.GL)}</span>`);
  }
  if (stageLabels.includes('리틀컵') && rk.Little) {
    items.push(`<span class="iv-row pri-3"><b>리틀컵</b>: ${fmtIV(rk.Little)}</span>`);
  }
  return items.length ? `<div class="iv-advice">${items.join('')}</div>` : '';
}
function renderTriage() {
  if (!state.q && !state.typeFilter) {
    return `<div class="empty">상단 검색창에 가진 포켓몬 이름을 한글/영어로 입력하세요.<br>(진화 전 이름·기술명도 검색 가능)</div>`;
  }
  const rankFn = sp => {
    const ranks = [bestRankIn(sp, GL_KEYS), bestRankIn(sp, UL_KEYS),
                   bestRankIn(sp, ML_KEYS), bestRaidRank(sp)];
    return Math.min(...ranks.map(r => r?.rank || 999));
  };
  let list = Object.values(DATA.species).filter(speciesPasses);
  list = sortSpecies(list, rankFn);
  if (!list.length) return `<div class="empty">결과 없음</div>`;

  let html = `<div class="stat">${list.length}종</div>`;
  for (const sp of list.slice(0, 30)) html += renderSpeciesDetailCard(sp);
  if (list.length > 30) html += `<div class="more">+ ${list.length - 30}종 더 (검색어 좁히세요)</div>`;
  return html;
}

function renderSpeciesDetailCard(sp) {
  const gl = bestRankIn(sp, GL_KEYS);
  const ul = bestRankIn(sp, UL_KEYS);
  const ml = bestRankIn(sp, ML_KEYS);
  const lc = bestRankIn(sp, LC_KEYS);
  const raid = bestRaidRank(sp);
  const cups = sp.pvp.filter(p =>
    !GL_KEYS.has(p.league_key) && !UL_KEYS.has(p.league_key) &&
    !ML_KEYS.has(p.league_key) && !LC_KEYS.has(p.league_key)
  ).sort((a,b) => a.rank - b.rank);

  const sectionRows = [];
  const addRow = (label, entry, ivHtml) => {
    if (!entry) return;
    sectionRows.push(`<tr>
      <td><b>${label}</b></td>
      <td class="rank">#${entry.rank}</td>
      <td>${ivHtml}</td>
      <td>${moveSplitFromEntry(entry)}</td>
    </tr>`);
  };
  addRow('슈퍼리그', gl, ivCellGL(sp));
  addRow('하이퍼리그', ul, ivCellUL(sp));
  addRow('마스터리그', ml, '<span class="muted">100%</span>');
  addRow('리틀컵', lc, ivCellLC(sp));
  if (raid) {
    sectionRows.push(`<tr>
      <td><b>레이드</b></td>
      <td class="rank">#${raid.rank}</td>
      <td><span class="muted">100%</span></td>
      <td><small class="muted">vs ${raid.boss_ko} (${raid.tier_ko})</small><br>${moveSplitFromEntry(raid)}</td>
    </tr>`);
  }
  for (const c of cups.slice(0, 5)) addRow(c.league_ko, c, ivCellGL(sp));

  return `<div class="card">
    <h2><span class="dex">#${String(sp.dex).padStart(3,'0')}</span>
        ${nameKo(sp)} <span class="en">/ ${sp.en}</span> ${sp.types.map(badge).join(' ')}</h2>
    ${verdictHtml(sp.invest)}
    ${sectionRows.length
      ? `<table><thead><tr><th>분류</th><th>#</th><th>추천 IV</th><th>추천 기술</th></tr></thead><tbody>${sectionRows.join('')}</tbody></table>`
      : '<div class="muted">랭킹 외 — 보내도 OK</div>'}
  </div>`;
}

// ━━━━━━ 핵심/전체 카드 뷰 ━━━━━━
function renderCard(sp) {
  const pvpHtml = sp.pvp.length ? sp.pvp.map(p =>
    `<div class="role pvp"><b>${p.league_ko}</b> <span class="en">(${p.league_en})</span> #${p.rank} —
      <span class="moves-ko">${p.moves_ko}</span> <span class="en-mv">${p.moves_en}</span></div>`
  ).join('') : '';
  const raidHtml = sp.raid.length ? sp.raid.map(r =>
    `<div class="role raid">vs <b>${r.boss_ko}</b> <span class="en">(${r.boss_en})</span>
      [${r.tier_ko}] #${r.rank} —
      <span class="moves-ko">${r.moves_ko}</span> <span class="en-mv">${r.moves_en}</span></div>`
  ).join('') : '';
  return `<div class="card">
    <h2><span class="dex">#${String(sp.dex).padStart(3,'0')}</span>
        ${sp.ko} <span class="en">/ ${sp.en}</span> ${sp.types.map(badge).join(' ')}</h2>
    ${verdictHtml(sp.invest)}
    ${stagesHtml(sp.invest)}
    <div class="row multipliers"><span class="lbl">약점</span> ${multBadges(sp.weak)||'<i>없음</i>'}</div>
    <div class="row multipliers"><span class="lbl">저항</span> ${multBadges(sp.resist)||'<i>없음</i>'}</div>
    ${pvpHtml ? `<div class="row"><span class="lbl">PvP</span></div>${pvpHtml}` : ''}
    ${raidHtml ? `<div class="row"><span class="lbl">레이드</span></div>${raidHtml}` : ''}
  </div>`;
}
function renderSpeciesList(filterFn) {
  const list = sortSpecies(Object.values(DATA.species).filter(filterFn).filter(speciesPasses));
  if (!list.length) return `<div class="empty">결과 없음</div>`;
  // 페이지네이션 — 첫 50개만, 더 보기 버튼
  return paginate(list, renderCard, 50);
}

let _pageState = {};
function paginate(list, renderFn, perPage) {
  const key = list.length + '_' + state.tab + '_' + state.q + '_' + state.typeFilter + '_' + state.sort;
  if (!_pageState[key]) _pageState[key] = perPage;
  const shown = Math.min(_pageState[key], list.length);
  let html = `<div class="stat">${list.length}종 (${shown} 표시)</div>`;
  html += list.slice(0, shown).map(renderFn).join('');
  if (shown < list.length) {
    html += `<div class="more" id="more-btn">더 보기 (${list.length - shown} 더)</div>`;
    setTimeout(() => {
      const btn = document.getElementById('more-btn');
      if (btn) btn.addEventListener('click', () => {
        _pageState[key] += perPage; render();
      });
    }, 0);
  }
  return html;
}

// ━━━━━━ 레이드 ━━━━━━
function renderRaids() {
  const tierOrder = ['T5','T5sh','Mega','MegaT5','UB','Elite',
                     'T5*','T5sh*','Mega*','MegaT5*','UB*'];
  const titles = {
    T5:'현재 5성', T5sh:'현재 쉐도우 5성', Mega:'현재 메가', MegaT5:'메가 5성',
    UB:'울트라비스트', Elite:'엘리트', T3:'현재 3성', T1:'현재 1성',
    'T5*':'예정 5성', 'T5sh*':'예정 쉐도우 5성', 'Mega*':'예정 메가',
    'MegaT5*':'예정 메가 5성', 'UB*':'예정 울트라비스트',
  };
  const grouped = {};
  for (const b of Object.values(DATA.bosses)) {
    if (state.typeFilter && !b.boss_types.includes(state.typeFilter)) continue;
    if (state.q && !b._search.includes(state.q)) continue;
    if (!grouped[b.tier_en]) grouped[b.tier_en] = [];
    grouped[b.tier_en].push(b);
  }
  let html = ''; let total = 0;
  for (const tier of tierOrder) {
    const list = grouped[tier];
    if (!list || !list.length) continue;
    list.sort((a,b) => (a.boss_dex||9999) - (b.boss_dex||9999));
    total += list.length;
    html += `<div class="section-h">${titles[tier]||tier} (${list.length})</div>`;
    for (const b of list) {
      const dex = b.boss_dex && b.boss_dex < 9999 ?
                  `<span class="dex">#${String(b.boss_dex).padStart(3,'0')}</span> ` : '';
      html += `<div class="boss-head">
        <h3>${dex}${b.boss_ko} <span class="en">/ ${b.boss_en}</span></h3>
        <span>${b.boss_types.map(badge).join(' ')}</span>
        <span class="weak">약점: ${multBadges(b.boss_weak)||'없음'}</span>
      </div>
      <table><thead><tr><th>#</th><th>한글</th><th>영어</th><th>기술</th></tr></thead>
        <tbody>${b.counters.map(c =>
          `<tr><td class="rank">${c.rank}</td><td><b>${c.ko}</b></td>
               <td class="en">${c.en}</td>
               <td><span class="moves-ko">${c.fast_ko} / ${c.charged_ko}</span><br>
                   <span class="moves-en">${c.fast_en} / ${c.charged_en}</span></td></tr>`
        ).join('')}</tbody></table>`;
    }
  }
  if (!total) return `<div class="empty">결과 없음</div>`;
  return `<div class="stat">${total} 보스</div>` + html;
}

// ━━━━━━ 리그/컵 ━━━━━━
function renderLeagues() {
  const order = ['all_1500','all_2500','all_10000','all_500',
                 'premier_1500','premier_2500','premier_10000','premier_500',
                 'classic_1500','classic_2500','classic_10000','classic_500',
                 'little_500'];
  const others = Object.keys(DATA.leagues).filter(k => !order.includes(k)).sort();
  const all = [...order, ...others].filter(k => DATA.leagues[k]);
  let html = '';
  for (const key of all) {
    const lg = DATA.leagues[key];
    const entries = lg.entries.filter(e => {
      const sp = DATA.species[e.sid];
      if (!sp) return false;
      return speciesPasses(sp);
    });
    if (!entries.length) continue;
    html += `<div class="section-h">${lg.ko} <span class="en">(${lg.en})</span></div>
      <table><thead><tr><th>#</th><th>Dex</th><th>한글</th><th>영어</th><th>속성</th><th>판단</th><th>기술</th></tr></thead>
        <tbody>${entries.map(e => {
          const sp = DATA.species[e.sid];
          return `<tr>
            <td class="rank">${e.rank}</td>
            <td class="num">${String(sp.dex).padStart(3,'0')}</td>
            <td>${nameKo(sp)}</td>
            <td class="en">${sp.en}</td>
            <td>${sp.types.map(badge).join(' ')}</td>
            <td>${verdictHtml(sp.invest)}</td>
            <td><span class="moves-ko">${e.moves_ko}</span><br>
                <span class="moves-en">${e.moves_en}</span></td>
          </tr>`;
        }).join('')}</tbody></table>`;
  }
  if (!html) return `<div class="empty">결과 없음</div>`;
  return html;
}

// 등장 리그 그룹 (겹침 표시용)
const GL_KEYS = new Set(['all_1500','premier_1500','classic_1500']);
const UL_KEYS = new Set(['all_2500','premier_2500','classic_2500']);
const ML_KEYS = new Set(['all_10000','premier_10000','classic_10000']);
const LC_KEYS = new Set(['all_500','little_500','premier_500','classic_500']);

function bestRankIn(sp, keys) {
  let best = null;
  for (const p of sp.pvp) {
    if (!keys.has(p.league_key)) continue;
    if (!best || p.rank < best.rank) best = p;
  }
  return best;
}
function bestRaidRank(sp) {
  if (!sp.raid.length) return null;
  return [...sp.raid].sort((a,b) => a.rank - b.rank)[0];
}

// 다른 곳에도 등장하면 배지 — 현재 컨텍스트 제외
function overlapBadges(sp, exceptCtx) {
  const out = [];
  if (exceptCtx !== 'GL') {
    const r = bestRankIn(sp, GL_KEYS);
    if (r && r.rank <= 15) out.push(`<span class="ovl ovl-gl">슈퍼 #${r.rank}</span>`);
  }
  if (exceptCtx !== 'UL') {
    const r = bestRankIn(sp, UL_KEYS);
    if (r && r.rank <= 15) out.push(`<span class="ovl ovl-ul">하이퍼 #${r.rank}</span>`);
  }
  if (exceptCtx !== 'ML') {
    const r = bestRankIn(sp, ML_KEYS);
    if (r && r.rank <= 15) out.push(`<span class="ovl ovl-ml">마스터 #${r.rank}</span>`);
  }
  if (exceptCtx !== 'LC') {
    const r = bestRankIn(sp, LC_KEYS);
    if (r && r.rank <= 10) out.push(`<span class="ovl ovl-lc">리틀 #${r.rank}</span>`);
  }
  if (exceptCtx !== 'Raid') {
    const r = bestRaidRank(sp);
    if (r && r.is_essential_tier && r.rank <= 5)
      out.push(`<span class="ovl ovl-raid">레이드 vs ${r.boss_ko} #${r.rank}</span>`);
  }
  // 컵 한정 등장
  if (exceptCtx !== 'Cup') {
    const cups = sp.pvp.filter(p =>
      !GL_KEYS.has(p.league_key) && !UL_KEYS.has(p.league_key) &&
      !ML_KEYS.has(p.league_key) && !LC_KEYS.has(p.league_key) &&
      p.rank <= 10
    );
    if (cups.length) {
      const top = cups.sort((a,b) => a.rank - b.rank)[0];
      out.push(`<span class="ovl ovl-cup">${top.league_ko} #${top.rank}${cups.length > 1 ? ` +${cups.length - 1}` : ''}</span>`);
    }
  }
  return out.length ? `<div class="ovl-list">${out.join('')}</div>` : '<span style="color:var(--muted)">—</span>';
}

function _ivOk(iv) {
  if (!iv) return false;
  // Lv 50 + 15/15/15 = 사실상 ML 전용 (해당 리그 무의미) — 표기 X
  if (iv.lv >= 50 && iv.atk === 15 && iv.def === 15 && iv.sta === 15) return false;
  return true;
}
function _ivStr(iv) {
  return `<span class="iv-cell"><b>Lv ${iv.lv}</b> <span class="iv-vals">${iv.atk}/${iv.def}/${iv.sta}</span></span>`;
}
function ivCellGL(sp) {
  const iv = sp.rank1_iv?.GL;
  return _ivOk(iv) ? _ivStr(iv) : '<span class="muted">—</span>';
}
function ivCellUL(sp) {
  const iv = sp.rank1_iv?.UL;
  return _ivOk(iv) ? _ivStr(iv) : '<span class="muted">—</span>';
}
function ivCellLC(sp) {
  const iv = sp.rank1_iv?.Little;
  return _ivOk(iv) ? _ivStr(iv) : '<span class="muted">—</span>';
}

// 기술 셀 — 노말 / 스페셜 분리
function moveSplitHtml(fk, fe, ck, ce) {
  const fast = fk ? `<div><span class="ml">노말</span> <b>${fk}</b> <span class="moves-en">${fe}</span></div>` : '';
  const charged = ck ? `<div><span class="ml">스페셜</span> <b>${ck}</b> <span class="moves-en">${ce}</span></div>` : '';
  return fast + charged || '<span class="muted">—</span>';
}
function moveSplitFromEntry(e) {
  return moveSplitHtml(e.fast_ko, e.fast_en, e.charged_ko, e.charged_en);
}

function renderLeagueTab(ctxKey, ctxLabel, ctxKeys, opts) {
  const cap = opts?.cap || 30;
  const isRaid = ctxKey === 'Raid';

  let list;
  if (isRaid) {
    list = Object.values(DATA.species).filter(sp => {
      if (!sp.raid.length) return false;
      const r = bestRaidRank(sp);
      return r && r.is_essential_tier && r.rank <= cap;
    });
  } else {
    list = Object.values(DATA.species).filter(sp => {
      const r = bestRankIn(sp, ctxKeys);
      return r && r.rank <= cap;
    });
  }
  list = list.filter(speciesPasses);

  const rankFn = isRaid
    ? (sp => bestRaidRank(sp)?.rank || 999)
    : (sp => bestRankIn(sp, ctxKeys)?.rank || 999);
  list = sortSpecies(list, rankFn);

  if (!list.length) return `<div class="empty">결과 없음</div>`;

  let html = `<div class="stat">${ctxLabel} — ${list.length}종 (Top ${cap})</div>`;

  let ivNote = '';
  if (ctxKey === 'GL') ivNote = '슈퍼리그 IV: CP 1500 cap 에서 stat product 최대화 (저공·고방·고체) — 1500 컵들 모두 동일';
  else if (ctxKey === 'UL') ivNote = '하이퍼리그 IV: CP 2500 cap 기준 — 2500 컵들 모두 동일';
  else if (ctxKey === 'ML' || ctxKey === 'Raid') ivNote = '마스터/레이드는 100% (15/15/15) 자명 — IV 컬럼 생략';
  else if (ctxKey === 'LC') ivNote = '리틀컵 IV: CP 500 cap 기준';
  if (ivNote) html += `<div class="iv-note">${ivNote}</div>`;

  const showIVs = !(ctxKey === 'ML' || ctxKey === 'Raid');
  html += `<table><thead><tr>
    <th>#</th><th>Dex</th><th>포켓몬</th><th>속성</th>
    ${showIVs ? '<th>슈퍼 IV</th><th>하이퍼 IV</th>' : ''}
    <th>추천 기술</th><th>비고</th>
  </tr></thead><tbody>`;
  for (const sp of list) {
    const r = isRaid ? bestRaidRank(sp) : bestRankIn(sp, ctxKeys);
    const rank = r?.rank ?? '—';
    let moveEntry;
    if (isRaid) {
      moveEntry = sp.raid.find(x => x.boss_ko === r.boss_ko && x.rank === r.rank);
    } else {
      moveEntry = r;
    }
    const moveStr = moveEntry ? moveSplitFromEntry(moveEntry) : '<span class="muted">—</span>';
    const tag = isRaid && r ? `<br><small class="muted">vs ${r.boss_ko} (${r.tier_ko})</small>` : '';
    const ivCells = showIVs ? `<td>${ivCellGL(sp)}</td><td>${ivCellUL(sp)}</td>` : '';
    html += `<tr>
      <td class="rank">${rank}</td>
      <td class="num">${String(sp.dex).padStart(3,'0')}</td>
      <td>${nameKo(sp)}<br><span class="en">${sp.en}</span>${tag}</td>
      <td>${sp.types.map(badge).join(' ')}</td>
      ${ivCells}
      <td>${moveStr}</td>
      <td>${extraInfoBadges(sp, ctxKey)}</td>
    </tr>`;
  }
  html += `</tbody></table>`;
  return html;
}

// 레이드 — 보스별 그룹 + 보스 약점 + 카운터 Top 8
function renderRaidsView() {
  const tierOrder = ['T5','T5sh','Mega','MegaT5','UB','Elite',
                     'T5*','T5sh*','Mega*','MegaT5*','UB*'];
  const titles = {
    T5:'현재 5성', T5sh:'현재 쉐도우 5성', Mega:'현재 메가', MegaT5:'메가 5성',
    UB:'울트라비스트', Elite:'엘리트', T3:'현재 3성', T1:'현재 1성',
    'T5*':'예정 5성', 'T5sh*':'예정 쉐도우 5성', 'Mega*':'예정 메가',
    'MegaT5*':'예정 메가 5성', 'UB*':'예정 울트라비스트',
  };
  const grouped = {};
  for (const b of Object.values(DATA.bosses)) {
    if (state.typeFilter && !b.boss_types.includes(state.typeFilter)) continue;
    if (state.q && !b._search.includes(state.q)) continue;
    if (!grouped[b.tier_en]) grouped[b.tier_en] = [];
    grouped[b.tier_en].push(b);
  }
  let total = 0;
  let html = `<div class="iv-note">레이드 — 모든 카운터는 100% IV (Lv50 15/15/15) 우선. 보스 약점 클릭하면 그 속성으로 강하게 때릴 수 있는 곳들.</div>`;
  for (const tier of tierOrder) {
    const list = grouped[tier];
    if (!list || !list.length) continue;
    list.sort((a,b) => (a.boss_dex||9999) - (b.boss_dex||9999));
    total += list.length;
    html += `<div class="section-h">${titles[tier]||tier} (${list.length})</div>`;
    for (const b of list) {
      const dex = b.boss_dex && b.boss_dex < 9999 ?
                  `<span class="dex">#${String(b.boss_dex).padStart(3,'0')}</span> ` : '';
      html += `<div class="boss-head">
        <h3>${dex}${b.boss_ko} <span class="en">/ ${b.boss_en}</span></h3>
        <span>${b.boss_types.map(badge).join(' ')}</span>
        <span class="weak">약점: ${multBadges(b.boss_weak)||'없음'}</span>
      </div>
      <table><thead><tr><th>#</th><th>Dex</th><th>카운터</th><th>속성</th><th>추천 기술</th><th>비고</th></tr></thead>
        <tbody>${b.counters.map(c => {
          const sp = DATA.species[c.sid];
          const types = sp ? sp.types.map(badge).join(' ') : '';
          const note = sp ? extraInfoBadges(sp, 'Raid') : '';
          return `<tr>
            <td class="rank">${c.rank}</td>
            <td class="num">${sp ? String(sp.dex).padStart(3,'0') : ''}</td>
            <td>${sp ? nameKo(sp) : c.ko}<br><span class="en">${c.en}</span></td>
            <td>${types}</td>
            <td>${moveSplitHtml(c.fast_ko, c.fast_en, c.charged_ko, c.charged_en)}</td>
            <td>${note}</td>
          </tr>`;
        }).join('')}</tbody></table>`;
    }
  }
  if (!total) return `<div class="empty">결과 없음</div>`;
  return `<div class="stat">${total} 보스</div>` + html;
}

// "비고" 컬럼 — 다른 등장처 모두 (컵 포함, 풀로 표시)
function extraInfoBadges(sp, exceptCtx) {
  const out = [];
  if (exceptCtx !== 'GL') {
    const r = bestRankIn(sp, GL_KEYS);
    if (r && r.rank <= 15) out.push(`<span class="ovl ovl-gl">슈퍼 #${r.rank}</span>`);
  }
  if (exceptCtx !== 'UL') {
    const r = bestRankIn(sp, UL_KEYS);
    if (r && r.rank <= 15) out.push(`<span class="ovl ovl-ul">하이퍼 #${r.rank}</span>`);
  }
  if (exceptCtx !== 'ML') {
    const r = bestRankIn(sp, ML_KEYS);
    if (r && r.rank <= 15) out.push(`<span class="ovl ovl-ml">마스터 #${r.rank}</span>`);
  }
  if (exceptCtx !== 'LC') {
    const r = bestRankIn(sp, LC_KEYS);
    if (r && r.rank <= 10) out.push(`<span class="ovl ovl-lc">리틀 #${r.rank}</span>`);
  }
  if (exceptCtx !== 'Raid') {
    const r = bestRaidRank(sp);
    if (r && r.is_essential_tier && r.rank <= 5)
      out.push(`<span class="ovl ovl-raid">vs ${r.boss_ko} #${r.rank}(${r.tier_ko})</span>`);
  }
  // 컵들 — 모두 나열
  if (exceptCtx !== 'Cup') {
    const cups = sp.pvp.filter(p =>
      !GL_KEYS.has(p.league_key) && !UL_KEYS.has(p.league_key) &&
      !ML_KEYS.has(p.league_key) && !LC_KEYS.has(p.league_key) &&
      p.rank <= 15
    ).sort((a,b) => a.rank - b.rank);
    cups.forEach(c => {
      out.push(`<span class="ovl ovl-cup">${c.league_ko} #${c.rank}</span>`);
    });
  }
  return out.length ? `<div class="ovl-list">${out.join('')}</div>` : '<span class="muted">—</span>';
}

function renderCups() {
  const cupKeys = Object.keys(DATA.leagues).filter(k =>
    !GL_KEYS.has(k) && !UL_KEYS.has(k) && !ML_KEYS.has(k) && !LC_KEYS.has(k)
  );
  let html = `<div class="iv-note">컵 시즌 한정 픽 — CP cap 에 맞는 IV (1500 컵 → 슈퍼 IV / 2500 컵 → 하이퍼 IV)</div>`;
  let total = 0;
  for (const key of cupKeys.sort()) {
    const lg = DATA.leagues[key];
    const cap = parseInt(key.split('_').pop()) || 1500;
    const entries = lg.entries.filter(e => {
      const sp = DATA.species[e.sid];
      return sp && speciesPasses(sp);
    });
    if (!entries.length) continue;
    total += entries.length;
    html += `<div class="section-h">${lg.ko} <span class="en">(${lg.en}, CP ${cap})</span></div>`;
    html += `<table><thead><tr>
      <th>#</th><th>Dex</th><th>포켓몬</th><th>속성</th>
      <th>슈퍼 IV</th><th>하이퍼 IV</th><th>추천 기술</th><th>비고</th>
    </tr></thead><tbody>`;
    for (const e of entries) {
      const sp = DATA.species[e.sid];
      html += `<tr>
        <td class="rank">${e.rank}</td>
        <td class="num">${String(sp.dex).padStart(3,'0')}</td>
        <td>${nameKo(sp)}<br><span class="en">${sp.en}</span></td>
        <td>${sp.types.map(badge).join(' ')}</td>
        <td>${ivCellGL(sp)}</td>
        <td>${ivCellUL(sp)}</td>
        <td>${moveSplitFromEntry(e)}</td>
        <td>${extraInfoBadges(sp, 'Cup')}</td>
      </tr>`;
    }
    html += `</tbody></table>`;
  }
  if (!total) return `<div class="empty">결과 없음</div>`;
  return `<div class="stat">${cupKeys.length} 컵</div>` + html;
}

function render() {
  const main = document.getElementById('main');
  let html = '';
  if (state.tab === 'types') html = renderTypes();
  else if (state.tab === 'gl') html = renderLeagueTab('GL', '슈퍼리그 (Great League)', GL_KEYS, {cap:30});
  else if (state.tab === 'ul') html = renderLeagueTab('UL', '하이퍼리그 (Ultra League)', UL_KEYS, {cap:30});
  else if (state.tab === 'ml') html = renderLeagueTab('ML', '마스터리그 (Master League)', ML_KEYS, {cap:30});
  else if (state.tab === 'raids') html = renderRaidsView();
  else if (state.tab === 'lc') html = renderLeagueTab('LC', '리틀컵 (Little)', LC_KEYS, {cap:25});
  else if (state.tab === 'cups') html = renderCups();
  else if (state.tab === 'search') html = renderTriage();
  main.innerHTML = html;
  window.scrollTo(0, 0);
}
window.state = state;
render();
</script>
</body>
</html>
"""


def main() -> None:
    trans = load_translations()
    species, moves = load_gamemaster()
    bundle = collect_all(species, moves, trans)

    # 임베드 — '</script>' 가 데이터 안에 들어가면 깨지니 escape
    json_text = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    json_text = json_text.replace("</", "<\\/")

    build_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    html = HTML_TEMPLATE.replace("__DATA_JSON__", json_text).replace("__BUILD_TIME__", build_time)
    out_path = OUT / "index.html"
    out_path.write_text(html, encoding="utf-8")
    size_kb = out_path.stat().st_size // 1024
    print(f"[html] {out_path} ({size_kb} KB)")
    print(f"  종 {len(bundle['species'])} / 보스 {len(bundle['bosses'])} / "
          f"리그 {len(bundle['leagues'])} / 핵심 {bundle['essentials_count']}")


if __name__ == "__main__":
    main()
