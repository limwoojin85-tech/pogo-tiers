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
    prettify_name,
    species_ko_name,
)
from type_chart import weaknesses_resistances, ALL_TYPES, SE


# 특수 진화 — 교환·버디·아이템·지역 한정
# kind: trade(교환), buddy(버디 미션), item(진화 아이템), walk(걷기), region(지역 한정)
SPECIAL_EVO: dict[str, tuple[str, str]] = {
    # 교환 진화 — 친구 교환 시 사탕 0
    "alakazam":      ("trade", "교환 시 사탕 0 (Kadabra→)"),
    "machamp":       ("trade", "교환 시 사탕 0 (Machoke→)"),
    "gengar":        ("trade", "교환 시 사탕 0 (Haunter→)"),
    "golem":         ("trade", "교환 시 사탕 0 (Graveler→)"),
    "golem_alolan":  ("trade", "교환 시 사탕 0"),
    "kingdra":       ("trade", "교환 시 사탕 0 + 드래곤스케일"),
    "scizor":        ("trade", "교환 시 사탕 0 + 메탈코트"),
    "porygon2":      ("trade", "교환 시 사탕 0 + 업그레이드"),
    "porygon_z":     ("trade", "교환 시 사탕 0 + 더비어스디스크"),
    "slowking":      ("trade", "교환 시 사탕 0 + 왕의징표석"),
    "politoed":      ("trade", "교환 시 사탕 0 + 왕의징표석"),
    "steelix":       ("trade", "교환 시 사탕 0 + 메탈코트"),
    "huntail":       ("trade", "교환 시 사탕 0 + 딥씨톱니"),
    "gorebyss":      ("trade", "교환 시 사탕 0 + 딥씨비늘"),
    "rhyperior":     ("trade", "교환 시 사탕 0 + 별의조각"),
    "magnezone":     ("trade", "교환 시 사탕 0 + 마그네틱 모듈"),
    "electivire":    ("trade", "교환 시 사탕 0 + 엘렉트로이저"),
    "magmortar":     ("trade", "교환 시 사탕 0 + 매그마라이저"),
    "dusknoir":      ("trade", "교환 시 사탕 0 + 저주의갑옷"),
    "annihilape":    ("buddy", "성난원숭이 + 라이지컬 30회 + 사탕 100"),
    # 버디 / 워크 진화
    "milotic":       ("walk",  "버디로 20km 걷기 + 사탕 100"),
    "leafeon":       ("item",  "이끼 루어 모듈 + 사탕 25 (이브이)"),
    "glaceon":       ("item",  "얼음 루어 모듈 + 사탕 25 (이브이)"),
    "sylveon":       ("buddy", "버디 하트 70 + 사탕 25 (이브이)"),
    "espeon":        ("buddy", "낮 + 버디 10km + 사탕 25 (이브이)"),
    "umbreon":       ("buddy", "밤 + 버디 10km + 사탕 25 (이브이)"),
    # 지역 한정
    "mr_mime":       ("region", "유럽 지역 한정"),
    "kangaskhan":    ("region", "호주 지역 한정"),
    "tauros":        ("region", "북미 지역 한정"),
    "farfetchd":     ("region", "한국·일본 지역 한정"),
    "heracross":     ("region", "남미·중미 지역 한정"),
    "corsola":       ("region", "적도 지역 한정"),
    "relicanth":     ("region", "뉴질랜드 한정"),
    "torkoal":       ("region", "인도·남아시아 한정"),
    "lunatone":      ("region", "북반구 한정"),
    "solrock":       ("region", "남반구 한정"),
    "tropius":       ("region", "아프리카 한정"),
    "pachirisu":     ("region", "북부 한정"),
    "carnivine":     ("region", "미국 동남부 한정"),
    "chatot":        ("region", "남반구 한정"),
}


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

    # archive 컵 — fetch_pvpoke 의 manifest 에서
    archive_set: set[str] = set()
    manifest_path = PVPOKE / "_manifest.json"
    if manifest_path.exists():
        try:
            mf = json.loads(manifest_path.read_text(encoding="utf-8"))
            for fname in mf.get("archived_only", []):
                archive_set.add(fname.removesuffix(".json"))
        except Exception:
            pass

    # 진화 부모 맵 + rank 1 IV (pvpoke gamemaster 에서)
    gm = json.loads((PVPOKE / "_gamemaster.json").read_text(encoding="utf-8"))
    parent_map: dict[str, str] = {}
    rank1_iv_map: dict[str, dict] = {}
    all_sids: set[str] = set()
    for p in gm["pokemon"]:
        all_sids.add(p["speciesId"])
        fam = p.get("family") or {}
        parent = fam.get("parent")
        if parent:
            parent_map[p["speciesId"]] = parent
        rank1_iv_map[p["speciesId"]] = p.get("defaultIVs") or {}

    def has_mega_form(sid: str) -> list[str]:
        """이 종이 메가/원시 진화 가능한지 — 가능한 폼 sid 리스트."""
        candidates = [f"{sid}_mega", f"{sid}_mega_x", f"{sid}_mega_y",
                      f"{sid}_mega_z", f"{sid}_primal"]
        return [c for c in candidates if c in all_sids]

    # 필드 포획 가능 여부 — 레이드/대회 한정 X
    # 1) tags: legendary/mythical/ultrabeast/wildlegendary → 제외
    # 2) sid 에 _mega/_primal → 메가는 베이스만 잡고 변신
    # 3) tag 누락된 raid-exclusive (paradox 등) — boss 셋으로 보강 (별도 단계)
    NON_FIELD_TAGS = {"legendary", "mythical", "ultrabeast", "wildlegendary"}
    pokemon_by_sid = {p["speciesId"]: p for p in gm["pokemon"]}

    # 베이비 포켓몬 — 알 부화로만 획득
    BABY_POKEMON = {
        "pichu", "cleffa", "igglybuff", "togepi", "tyrogue",
        "smoochum", "elekid", "magby", "azurill", "wynaut",
        "budew", "chingling", "bonsly", "mime_jr", "happiny",
        "munchlax", "riolu", "mantyke", "toxel",
    }

    # 획득처 분류
    def acquisition_methods(sid: str) -> list[str]:
        p = pokemon_by_sid.get(sid)
        if not p:
            return ["?"]
        tags = set(p.get("tags", []))
        methods: list[str] = []

        if sid.endswith("_shadow"):
            return ["로켓 그런츠/리더"]
        if "_mega" in sid or "_primal" in sid:
            return ["메가 에너지로 진화"]

        if "wildlegendary" in tags:
            return ["야생 (희귀)", "5성 레이드"]
        if "legendary" in tags:
            base = sid.replace("_galarian", "").replace("_hisuian", "").replace("_alolan", "")
            if base in raid_boss_sids or sid in raid_boss_sids:
                return ["5성/메가/UB 레이드"]
            return ["레이드"]
        if "mythical" in tags:
            return ["스페셜 리서치"]
        if "ultrabeast" in tags:
            return ["UB 레이드"]
        if sid in raid_boss_sids:
            # paradox 등
            methods.append("레이드 한정")
        if "regional" in tags:
            methods.append("지역 한정")
        if sid in BABY_POKEMON:
            return ["알 부화 (Baby)"]
        if "alolan" in tags:
            methods.append("알/이벤트 (알로라)")
        elif "galarian" in tags:
            methods.append("알/이벤트 (가라르)")
        elif "hisuian" in tags:
            methods.append("리서치/이벤트 (히스이)")
        elif "paldean" in tags:
            methods.append("리서치/이벤트 (팔데아)")
        if not methods:
            # parent 가 야생/baby 면 진화로
            parent = parent_map.get(sid)
            if parent in BABY_POKEMON:
                methods.append("진화 (베이비 부화)")
            elif parent:
                methods.append("진화")
            else:
                methods.append("야생/알/리서치")
        return methods

    def is_field_catchable(sid: str, raid_boss_sids: set) -> bool:
        if "_mega" in sid or "_primal" in sid:
            return False
        p = pokemon_by_sid.get(sid)
        if not p:
            return False
        tags = set(p.get("tags", []))
        if tags & NON_FIELD_TAGS:
            return False
        # paradox 등 태그 누락 — T5+/Mega/UB 보스로 등장하면 사실상 레이드 한정
        # 단 _shadow 는 로켓에서 잡으니 field 인정
        base_sid = sid.replace("_shadow", "")
        if base_sid in raid_boss_sids:
            return False
        return True

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
        # 특수 진화 — 자기 자신 또는 이 가족의 최종 진화에 적용된 메서드
        evo_kind = None
        evo_note = None
        if sid in SPECIAL_EVO:
            evo_kind, evo_note = SPECIAL_EVO[sid]
        else:
            # 진화 후 형태가 special evo 라면 표시 (에를들면 kadabra 의 진화는 alakazam 이고 alakazam 이 trade)
            for child_sid, child_evo in SPECIAL_EVO.items():
                # parent_map[child_sid] 가 sid 이거나, 자손
                cur = child_sid
                depth = 0
                while cur in parent_map and depth < 5:
                    if parent_map[cur] == sid:
                        evo_kind, evo_note = child_evo
                        break
                    cur = parent_map[cur]
                    depth += 1
                if evo_kind:
                    break

        mega_forms = has_mega_form(sid)

        # 베이스 스탯 (DPS 비교용)
        gm_p = pokemon_by_sid.get(sid)
        base_stats = (gm_p or {}).get("baseStats") or {"atk": 0, "def": 0, "hp": 0}

        # 100% IV Lv50 stat product + CP (raid 비교 + 만렙 표시용)
        # 공식: CP = max(10, floor(Atk × √Def × √HP / 10)), 각 스탯 = (Base+IV) × CPM (raw, no floor)
        # Stat product 는 displayed HP 사용 (floor)
        cpm50 = 0.84029999
        a_raw = (base_stats.get("atk", 0) + 15) * cpm50
        d_raw = (base_stats.get("def", 0) + 15) * cpm50
        h_raw = (base_stats.get("hp", 0) + 15) * cpm50
        max_sp = round(a_raw * d_raw * int(h_raw))
        max_cp = max(10, int(a_raw * (d_raw ** 0.5) * (h_raw ** 0.5) / 10))

        # 최종 진화형 여부 — pvpoke family.evolutions 비어있으면 최종
        gm_fam = (gm_p or {}).get("family") or {}
        is_final = not gm_fam.get("evolutions")

        species_out[sid] = {
            "id": sid,
            "dex": info["dex"],
            "ko": species_ko_name(info["dex"], info["name_en"], trans),
            "en": info["name_en"],
            "types": types,
            "base_stats": {"atk": base_stats.get("atk", 0),
                           "def": base_stats.get("def", 0),
                           "hp": base_stats.get("hp", 0)},
            "max_sp": max_sp,    # 100% IV Lv50 stat product
            "max_cp": max_cp,    # 100% IV Lv50 CP
            "is_final": is_final,
            "weak": {t: round(m, 4) for t, m in weak.items()},
            "resist": {t: round(m, 4) for t, m in resist.items()},
            "chain_ko": chain_kos,
            "chain_en": chain_ens,
            "rank1_iv": rank1,
            "evo_kind": evo_kind,
            "evo_note": evo_note,
            "mega_forms": mega_forms,
            "acquisition": [],  # 보스 셋 완성 후 채움
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
        is_major = league_key in MAJOR_LEAGUES_KEYS
        cup_only = "_" in league_key and league_key not in {
            "all_500", "all_1500", "all_2500", "all_10000",
            "premier_500", "premier_1500", "premier_2500", "premier_10000",
            "little_500",
        }
        is_archive = league_key in archive_set
        league_out = {
            "key": league_key, "ko": ko, "en": en,
            "is_major": is_major, "is_cup": cup_only,
            "is_archive": is_archive,
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
                "is_archive": is_archive,
                "rank": rank,
                "fast_ko": fast_ko, "fast_en": fast_en,
                "charged_ko": charged_ko, "charged_en": charged_en,
            })
        leagues_out[league_key] = league_out

    # 레이드 데이터 + 필드 포획 판단용 보스 sid 셋
    raid_boss_sids: set[str] = set()
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
        raid_boss_sids.add(boss_sid)
        # 베이스도 — _shadow_form 의 베이스
        raid_boss_sids.add(boss_sid.replace("_shadow", ""))
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

    # 필드 포획 가능 여부 + 획득처 — 보스 셋 완성 후 마킹
    for sid, sdata in species_out.items():
        sdata["is_field"] = is_field_catchable(sid, raid_boss_sids)
        sdata["acquisition"] = acquisition_methods(sid)

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

    # 박사 송출 / 메가 보관 후보 분류
    ranked_sids = {sid for sid, s in species_out.items() if s["pvp"] or s["raid"]}
    family_of: dict[str, str] = {}
    # 1차: pvpoke gamemaster 의 family.id (있는 것만)
    for p in gm["pokemon"]:
        fid = (p.get("family") or {}).get("id")
        if fid:
            family_of[p["speciesId"]] = fid

    # 2차: evolutions propagate — 부모가 family 알고 있으면 자식도 같은 family
    # (gastrodon 처럼 본인 family=None 인 경우 shellos.evolutions 로부터 백필)
    changed = True
    while changed:
        changed = False
        for p in gm["pokemon"]:
            sid = p["speciesId"]
            if sid not in family_of:
                continue
            for child in (p.get("family") or {}).get("evolutions") or []:
                if child not in family_of:
                    family_of[child] = family_of[sid]
                    changed = True

    # 3차: mega/primal/_shadow suffix 백필 — 베이스 sid 의 family 로
    for p in gm["pokemon"]:
        sid = p["speciesId"]
        if sid in family_of:
            continue
        base = re.sub(r"_(mega(_[xyz])?|primal|shadow)$", "", sid)
        if base != sid and base in family_of:
            family_of[sid] = family_of[base]
        else:
            family_of[sid] = sid

    family_members: dict[str, list[str]] = defaultdict(list)
    for sid, fid in family_of.items():
        family_members[fid].append(sid)

    # 각 가족마다 분류:
    #   "transfer": 어디에도 안 쓰임 — 송출 OK (가족당 1마리만 보관 권장)
    #   "mega_keep": 메가/원시만 쓰이고 베이스/일반은 안 쓰임 — 메가 변신 위해 보관 필수
    #   "ranked":   일반 형태가 ranked — 별도 처리 X (다른 탭에 이미 나옴)
    def is_special_form(s: str) -> bool:
        return "_mega" in s or "_primal" in s

    transfer_groups = []
    mega_keep_groups = []          # 메가가 ranked — 무조건 베이스 보관
    mega_possible_groups = []      # 메가 폼 존재하지만 ranked 는 아님 — 추후 대비 보관

    for fid, mids in family_members.items():
        ranked_in_family = [s for s in mids if s in ranked_sids]
        ranked_normal = [s for s in ranked_in_family if not is_special_form(s)]
        ranked_mega = [s for s in ranked_in_family if is_special_form(s)]

        # 멤버 메타 (쉐도우 + 일반 + 메가 모두 포함)
        member_dicts = []
        for mid in mids:
            mp = next((x for x in gm["pokemon"] if x["speciesId"] == mid), None)
            if not mp or not mp.get("released", True):
                continue
            ko = species_ko_name(mp["dex"], prettify_name(mp["speciesName"]), trans)
            member_dicts.append({
                "sid": mid, "dex": mp["dex"],
                "ko": ko, "en": prettify_name(mp["speciesName"]),
                "types": [t for t in mp.get("types", []) if t and t != "none"],
                "is_shadow": "_shadow" in mid,
                "is_mega": is_special_form(mid),
            })
        if not member_dicts:
            continue
        member_dicts.sort(key=lambda x: (x["is_mega"], x["is_shadow"], x["dex"], x["sid"]))

        # 가족의 최종 진화 (최고 dex 의 일반형)
        normal_members = [m for m in member_dicts if not m["is_mega"] and not m["is_shadow"]]
        keep_member = normal_members[-1] if normal_members else member_dicts[-1]

        if not ranked_in_family:
            # 어디에도 안 쓰임. 메가 폼 존재 여부로 분류.
            base_sid = keep_member["sid"]
            base_evo = SPECIAL_EVO.get(base_sid)
            mega_avail_sids: list[str] = []
            for m in member_dicts:
                if not m["is_mega"]:
                    mega_avail_sids.extend(has_mega_form(m["sid"]))
            group_data = {
                "family_id": fid,
                "keep_sid": keep_member["sid"],
                "keep_ko": keep_member["ko"],
                "keep_en": keep_member["en"],
                "keep_dex": keep_member["dex"],
                "members": [m for m in member_dicts if not m["is_mega"]],
                "evo_kind": base_evo[0] if base_evo else None,
                "evo_note": base_evo[1] if base_evo else None,
            }
            if mega_avail_sids:
                # 메가 폼 존재 — 박사송출 X, 보관 권장
                mega_kos = [species_ko_name(
                    pokemon_by_sid[ms]["dex"],
                    prettify_name(pokemon_by_sid[ms]["speciesName"]),
                    trans
                ) for ms in mega_avail_sids if ms in pokemon_by_sid]
                group_data["mega_avail_kos"] = mega_kos
                group_data["mega_avail_sids"] = mega_avail_sids
                mega_possible_groups.append(group_data)
            else:
                transfer_groups.append(group_data)
        elif ranked_mega and not ranked_normal:
            # 메가/원시만 쓰임 — 베이스 보관 필수 (메가 변신 재료)
            mega_member = next((m for m in member_dicts if m["is_mega"]), None)
            mega_keep_groups.append({
                "family_id": fid,
                "keep_sid": keep_member["sid"],
                "keep_ko": keep_member["ko"],
                "keep_en": keep_member["en"],
                "keep_dex": keep_member["dex"],
                "mega_ko": mega_member["ko"] if mega_member else "",
                "mega_en": mega_member["en"] if mega_member else "",
                "mega_types": mega_member["types"] if mega_member else [],
                "members": [m for m in member_dicts if not m["is_mega"]],
                "evo_kind": (SPECIAL_EVO.get(keep_member["sid"]) or (None,))[0],
                "evo_note": (SPECIAL_EVO.get(keep_member["sid"]) or (None, None))[1],
            })
        # else: 일반 형태가 ranked — 다른 탭에 이미 노출

    transfer_groups.sort(key=lambda g: g["keep_dex"])
    mega_keep_groups.sort(key=lambda g: g["keep_dex"])
    mega_possible_groups.sort(key=lambda g: g["keep_dex"])

    # 등장한 종만 남김 — 단 쉐도우/메가 가 ranked 면 일반(베이스) 도 같이 남김
    # (검색 시 일반 폼도 찾을 수 있게 + 어느 쪽이 더 강한지 비교 가능)
    ranked_initial = {sid for sid, s in species_out.items() if s["pvp"] or s["raid"]}
    keep_sids = set(ranked_initial)
    stronger_form_of: dict[str, list[str]] = defaultdict(list)
    for sid in ranked_initial:
        # 쉐도우 → 일반
        if sid.endswith("_shadow"):
            base = sid[: -len("_shadow")]
            if base in species_out and base not in ranked_initial:
                keep_sids.add(base)
                stronger_form_of[base].append(sid)
        # 메가/원시 → 일반
        base = re.sub(r"_(mega(_[xyz])?|primal)$", "", sid)
        if base != sid and base in species_out and base not in ranked_initial:
            keep_sids.add(base)
            stronger_form_of[base].append(sid)
    species_out = {sid: s for sid, s in species_out.items() if sid in keep_sids}
    # 더 강한 폼 정보 부착 + 판단 메시지 갱신
    for sid, stronger_sids in stronger_form_of.items():
        if sid not in species_out:
            continue
        sp_data = species_out[sid]
        sp_data["stronger_forms"] = stronger_sids
        # 일반 폼이 랭킹 외이지만 더 강한 폼이 있으면 보내지 말라고 표시
        if sp_data["invest"]["verdict_ko"] == "보내도 OK":
            sp_data["invest"]["verdict_ko"] = "더 강한 폼 우선 — 베이스 보관"
            sp_data["invest"]["keep_score"] = 35
            sp_data["invest"]["stages"] = [{
                "ko": "베이스 보관",
                "en": "Keep base",
                "priority": 2,
                "reason": "쉐도우/메가 폼이 랭킹에 있어 베이스 1마리 필요",
            }]

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

        # 2.5 ★ 필드 추천 — 레이드에서 쓸 수 있는 비전설/비메가 (Top 6)
        # 최종 진화형만 (근육몬 X, 괴력몬 O)
        tweak_keys = {b["boss_key"] for b in weak_bosses}
        field_candidates = []
        for sp in species_out.values():
            if t not in sp["types"]:
                continue
            if not sp.get("is_field"):
                continue
            if not sp.get("is_final"):
                continue  # 최종 진화형만
            if not sp["raid"]:
                continue  # 레이드 카운터 역할 있어야 함
            # T 약점 보스 vs 일반 보스 둘 다 가능. T-약점 매칭이 우선.
            best_t = 9999
            best_any = 9999
            best_entry = None
            for r in sp["raid"]:
                if r["boss_key"] in tweak_keys and r["rank"] < best_t:
                    best_t = r["rank"]
                    best_entry = r
                if r["rank"] < best_any:
                    best_any = r["rank"]
                    if best_t == 9999:
                        best_entry = r
            score = best_t if best_t < 9999 else (best_any + 100)
            field_candidates.append({
                "sid": sp["id"], "dex": sp["dex"], "ko": sp["ko"], "en": sp["en"],
                "types": sp["types"],
                "max_cp": sp["max_cp"],
                "rank_in_t": best_t if best_t < 9999 else None,
                "rank_any": best_any,
                "best_boss_ko": best_entry["boss_ko"] if best_entry else "",
                "best_boss_en": best_entry["boss_en"] if best_entry else "",
                "best_tier_ko": best_entry["tier_ko"] if best_entry else "",
                "fast_ko": best_entry["fast_ko"] if best_entry else "",
                "fast_en": best_entry["fast_en"] if best_entry else "",
                "charged_ko": best_entry["charged_ko"] if best_entry else "",
                "charged_en": best_entry["charged_en"] if best_entry else "",
                "score": score,
            })
        field_candidates.sort(key=lambda x: (x["score"], x["dex"]))
        field_top6 = field_candidates[:6]

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
            "field_top6": field_top6,
            "league_uses": league_uses,
            "boss_count": len(weak_bosses),
            "core_count": len(type_species),
            "field_count": len(field_candidates),
        }

    # 박스 매칭용 — gamemaster 의 unranked 종 (분류 안 된 종) 슬림 정보
    unranked: dict[str, dict] = {}
    for p in gm["pokemon"]:
        sid = p["speciesId"]
        if sid in species_out:
            continue
        if not p.get("released", True):
            continue
        cko = species_ko_name(p["dex"], prettify_name(p["speciesName"]), trans)
        unranked[sid] = {
            "id": sid, "dex": p["dex"], "ko": cko,
            "en": prettify_name(p["speciesName"]),
            "types": [t for t in p.get("types", []) if t and t != "none"],
        }

    # CPM 테이블 — Pokemon GO 공식 값. Lv 1.0 → 50.0 (0.5 간격)
    # 인덱스: (lv - 1) * 2 → 0 = Lv1, 98 = Lv50
    cpm_table = [
        0.094, 0.135137432, 0.16639787, 0.192650919, 0.21573247,
        0.236572661, 0.25572005, 0.273530381, 0.29024988, 0.306057377,
        0.3210876, 0.335445036, 0.34921268, 0.362457751, 0.37523559,
        0.387592406, 0.39956728, 0.411193551, 0.42250001, 0.432926419,
        0.44310755, 0.453059958, 0.46279839, 0.472336083, 0.48168495,
        0.4908558, 0.49985844, 0.508701765, 0.51739395, 0.525942511,
        0.53435433, 0.542635767, 0.55079269, 0.558830576, 0.56675452,
        0.574569153, 0.58227891, 0.589887917, 0.59740001, 0.604818814,
        0.61215729, 0.619399365, 0.62656713, 0.633644533, 0.64065295,
        0.647576426, 0.65443563, 0.661214806, 0.667934, 0.674577537,
        0.68116492, 0.687680648, 0.69414365, 0.700538673, 0.70688421,
        0.713164996, 0.71939909, 0.725571552, 0.7317, 0.734741009,
        0.73776948, 0.740785574, 0.74378943, 0.746781211, 0.74976104,
        0.752729087, 0.75568551, 0.758630378, 0.76156384, 0.764486065,
        0.76739717, 0.770297266, 0.7731865, 0.776064962, 0.77893275,
        0.781790055, 0.78463697, 0.787473578, 0.79030001, 0.792803968,
        0.79530001, 0.797803921, 0.8003, 0.802803968, 0.8053,
        0.807803921, 0.81029999, 0.812803968, 0.81529999, 0.817803921,
        0.82029999, 0.822803895, 0.82529999, 0.827803895, 0.82999998,
        0.832803905, 0.83529997, 0.837803885, 0.84029999, 0.842803895, 0.84529999,
    ]

    return {
        "species": species_out,
        "bosses": bosses_out,
        "leagues": leagues_out,
        "types": types_out,
        "types_ko": types_ko,
        "cpm": cpm_table,
        "essentials_count": len(essential_ids),
        "transfer_groups": transfer_groups,
        "mega_keep_groups": mega_keep_groups,
        "mega_possible_groups": mega_possible_groups,
        "unranked": unranked,
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
  .ivcalc { background: #fafafa; border-radius: 6px; padding: 8px 10px;
            margin-top: 8px; }
  .ivcalc input[type="number"] { padding: 3px 5px; font-size: 12px;
            border: 1px solid #d0d0d6; border-radius: 4px; }
  .ivcalc table { margin: 0; }
  .ivcalc .pri-1 { color: var(--pri1); font-weight: 600; }
  .ivcalc .pri-3 { color: var(--pri3); font-weight: 600; }
  button.ctrl { padding: 6px 14px; background: var(--accent); color: #fff;
                border: none; border-radius: 6px; font-size: 13px; cursor: pointer;
                font-weight: 600; }
  button.ctrl:hover { background: #1d6bd6; }
  textarea { font-family: 'Consolas', 'Menlo', monospace; }
  .bucket-bar { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }
  .bucket-btn { padding: 6px 12px; font-size: 13px; border: 1px solid #d0d0d6;
                background: #fff; color: var(--text); border-radius: 6px;
                cursor: pointer; font-weight: 600; }
  .bucket-btn:hover { background: #f0f0f3; }
  .bucket-btn.on { background: #1d1d1f; color: #fff; border-color: #1d1d1f; }
  .bucket-btn.export-btn { margin-left: auto; background: var(--accent); color: #fff; }
  .bucket-btn.export-btn:hover { background: #1d6bd6; }

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
        <div class="tab" data-tab="fieldtop">한눈에</div>
        <div class="tab" data-tab="field">⭐ 필드 추천</div>
        <div class="tab" data-tab="raids">레이드</div>
        <div class="tab" data-tab="gl">슈퍼리그</div>
        <div class="tab" data-tab="ul">하이퍼리그</div>
        <div class="tab" data-tab="ml">마스터리그</div>
        <div class="tab" data-tab="lc">리틀컵</div>
        <div class="tab" data-tab="cups">컵 시즌</div>
        <div class="tab" data-tab="transfer">박사 송출</div>
        <div class="tab" data-tab="calcy">📥 Calcy 분석</div>
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

  // ★ 필드 추천 — 레이드에서 쓸 수 있는 비전설/비메가 Top 6
  if (td.field_top6 && td.field_top6.length) {
    html += `<div class="section-h">⭐ 필드 추천 — 레이드에서 쓸 수 있는 ${td.ko} 어태커 Top 6 <span class="en">(전설/메가 제외, ${td.field_count}종 중)</span></div>`;
    html += `<div class="iv-note" style="background:#e8f5e9;color:#186118">
      전설은 모두가 못 잡으니 <b>야생/알/리서치/로켓에서 얻을 수 있는 종</b>만. 100% IV 우선, Lv 50 강화 권장.
    </div>`;
    html += `<table><thead><tr>
      <th>#</th><th>Dex</th><th>포켓몬</th><th>속성</th><th>만렙 CP<br><small>(100% Lv50)</small></th><th>획득처</th><th>최강 매치업</th><th>추천 기술</th>
    </tr></thead><tbody>`;
    td.field_top6.forEach((f, i) => {
      const sp = DATA.species[f.sid];
      const types = sp ? sp.types.map(badge).join(' ') : f.types.map(badge).join(' ');
      const acq = sp ? (sp.acquisition || []).map(a => `<span class="ovl ovl-cup">${a}</span>`).join(' ') : '';
      const cp = f.max_cp || sp?.max_cp || '—';
      const matchup = f.best_boss_ko
        ? `<b>vs ${f.best_boss_ko}</b><br><small class="muted">${f.best_boss_en} (${f.best_tier_ko}) #${f.rank_in_t || f.rank_any}</small>`
        : '<span class="muted">—</span>';
      const moves = moveSplitHtml(f.fast_ko, f.fast_en, f.charged_ko, f.charged_en);
      html += `<tr>
        <td class="rank">${i + 1}</td>
        <td class="num">${String(f.dex).padStart(3,'0')}</td>
        <td>${sp ? nameKo(sp) : '<b>'+f.ko+'</b>'}<br><span class="en">${f.en}</span></td>
        <td>${types}</td>
        <td class="num"><b>${cp.toLocaleString ? cp.toLocaleString() : cp}</b></td>
        <td>${acq}</td>
        <td>${matchup}</td>
        <td>${moves}</td>
      </tr>`;
    });
    html += `</tbody></table>`;
  }

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

// 비교 — 100% IV Lv50 기준 stat product 백분율 vs 최강 필드 같은 속성
function statProductAt(sp, atk_iv, def_iv, sta_iv, level) {
  const idx = Math.round((level - 1) * 2);
  const cpm = DATA.cpm[idx];
  if (!cpm || !sp.base_stats) return 0;
  const a = (sp.base_stats.atk + atk_iv) * cpm;
  const d = (sp.base_stats.def + def_iv) * cpm;
  const h = Math.floor((sp.base_stats.hp + sta_iv) * cpm); // displayed HP
  return Math.round(a * d * h);
}

function bestFieldOfType(t, exceptSid) {
  let best = null;
  for (const sp of Object.values(DATA.species)) {
    if (!sp.is_field) continue;
    if (!sp.types.includes(t)) continue;
    if (sp.id === exceptSid) continue;
    if (!best || sp.max_sp > best.max_sp) best = sp;
  }
  return best;
}

function comparisonBlock(sp) {
  // sp 의 각 속성에 대해 최강 필드 비교 + IV 입력 기능
  if (!sp.max_sp || !sp.base_stats?.atk) return '';
  const cardId = 'cmp_' + sp.id;
  const initialSP = sp.max_sp;
  // 같은 속성 최강 필드 (자기 제외)
  const fieldRefs = sp.types.map(t => {
    const ref = bestFieldOfType(t, sp.id);
    return ref ? { type: t, ref } : null;
  }).filter(Boolean);

  const refsHtml = fieldRefs.map(r => {
    const pct = (sp.max_sp / r.ref.max_sp * 100).toFixed(0);
    const cls = sp.max_sp >= r.ref.max_sp ? 'pri-1' : 'pri-3';
    return `<tr>
      <td>${badge(r.type)} 최강 필드</td>
      <td><b>${r.ref.ko}</b><br><span class="en">${r.ref.en}</span></td>
      <td class="num">${(r.ref.max_cp||0).toLocaleString()}</td>
      <td class="num">${r.ref.max_sp.toLocaleString()}</td>
      <td class="num"><b class="${cls}">${pct}%</b></td>
    </tr>`;
  }).join('');

  return `<div class="iv-note" style="background:#f0f8ff;color:var(--pri3)">
    <b>성능 비교 (Lv50 100% IV 기준 stat product)</b> — 풀강할 가치 판단용
  </div>
  <div class="ivcalc" id="${cardId}">
    <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12px">
      <span><b>내 IV</b></span>
      공 <input type="number" min="0" max="15" value="15" data-iv="atk" style="width:50px">
      방 <input type="number" min="0" max="15" value="15" data-iv="def" style="width:50px">
      체 <input type="number" min="0" max="15" value="15" data-iv="sta" style="width:50px">
      Lv <input type="number" min="1" max="51" step="0.5" value="50" data-iv="lv" style="width:60px">
      <button data-act="calc">계산</button>
      <span class="result" style="margin-left:auto;font-weight:600"></span>
    </div>
    <table style="margin-top:8px"><thead><tr>
      <th>비교</th><th>대상</th><th>만렙 CP</th><th>SP (100% Lv50)</th><th>이 종 대비</th>
    </tr></thead><tbody>
      <tr style="background:#fffbe6">
        <td>이 포켓몬 (100%)</td>
        <td><b>${sp.ko}</b></td>
        <td class="num">${(sp.max_cp||0).toLocaleString()}</td>
        <td class="num">${sp.max_sp.toLocaleString()}</td>
        <td class="num"><b>100%</b> (기준)</td>
      </tr>
      ${refsHtml || '<tr><td colspan="5" class="muted">같은 속성 필드 비교 대상 없음</td></tr>'}
    </tbody></table>
  </div>`;
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

  // 획득처
  const acqStr = (sp.acquisition || []).map(a => `<span class="ovl ovl-cup">${a}</span>`).join(' ');
  // 더 강한 폼 (쉐도우/메가) 안내
  let strongerHint = '';
  if (sp.stronger_forms && sp.stronger_forms.length) {
    const formNames = sp.stronger_forms.map(s => {
      const f = DATA.species[s];
      return f ? f.ko : s;
    }).join(', ');
    strongerHint = `<div class="iv-note" style="background:#fff3d9;color:var(--pri2)">
      ⚠️ <b>${formNames}</b> 가 랭킹에 등장 — 이 일반 폼은 직접 랭킹에 없음.
      쉐도우는 공격 +20%, 메가는 변신 시 큰 폭 강해짐. <b>기본적으로 더 강한 폼 추천</b>.
    </div>`;
  }

  return `<div class="card" data-sid="${sp.id}">
    <h2><span class="dex">#${String(sp.dex).padStart(3,'0')}</span>
        ${nameKo(sp)} <span class="en">/ ${sp.en}</span> ${sp.types.map(badge).join(' ')}</h2>
    ${verdictHtml(sp.invest)}
    ${strongerHint}
    <div class="row"><span class="lbl">획득처</span> ${acqStr || '<span class="muted">—</span>'}</div>
    <div class="row"><span class="lbl">베이스 스탯</span> 공 ${sp.base_stats.atk} · 방 ${sp.base_stats.def} · 체 ${sp.base_stats.hp}</div>
    <div class="row"><span class="lbl">만렙 CP</span> <b>${(sp.max_cp||0).toLocaleString()}</b> <small class="muted">(100% IV Lv50)</small> ${sp.is_final ? '' : '<span class="ovl ovl-cup">진화 가능 — 최종 진화 후 더 높음</span>'}</div>
    ${sectionRows.length
      ? `<table><thead><tr><th>분류</th><th>#</th><th>추천 IV</th><th>추천 기술</th></tr></thead><tbody>${sectionRows.join('')}</tbody></table>`
      : '<div class="muted">랭킹 외 — 보내도 OK</div>'}
    ${comparisonBlock(sp)}
  </div>`;
}

// IV 계산기 인터랙션 — 검색 탭에서 input 수정 시 결과 갱신
document.addEventListener('input', e => {
  if (!e.target.matches('.ivcalc input')) return;
  const card = e.target.closest('.ivcalc');
  if (!card) return;
  const sid = card.id.replace('cmp_', '');
  const sp = DATA.species[sid];
  if (!sp) return;
  const ivs = {atk:15, def:15, sta:15, lv:50};
  card.querySelectorAll('input[data-iv]').forEach(inp => {
    ivs[inp.dataset.iv] = parseFloat(inp.value) || 0;
  });
  const sp_now = statProductAt(sp, ivs.atk, ivs.def, ivs.sta, ivs.lv);
  const pct = (sp_now / sp.max_sp * 100).toFixed(1);
  // CP at IV/Lv — raw stats (no floor inside), floor only at end
  const cpmIdx = Math.round((ivs.lv - 1) * 2);
  const cpm = DATA.cpm[cpmIdx] || 0;
  const aN = (sp.base_stats.atk + ivs.atk) * cpm;
  const dN = (sp.base_stats.def + ivs.def) * cpm;
  const hN = (sp.base_stats.hp + ivs.sta) * cpm;
  const cp_now = Math.max(10, Math.floor(aN * Math.sqrt(dN) * Math.sqrt(hN) / 10));
  // 같은 속성 최강 필드 비교
  const fields = sp.types.map(t => bestFieldOfType(t, sp.id)).filter(Boolean);
  const verdict = fields.length
    ? (() => {
        const fieldMax = Math.max(...fields.map(f => f.max_sp));
        const ratio = sp_now / fieldMax * 100;
        return ratio >= 100
          ? `<span class="pri-1">필드 최강(${fieldMax.toLocaleString()}) 보다 강함 — 풀강 가치</span>`
          : `<span class="pri-3">필드 최강의 ${ratio.toFixed(0)}% — 풀강 보다 필드 100% 가 나을 수 있음</span>`;
      })()
    : '';
  card.querySelector('.result').innerHTML =
    `CP <b>${cp_now.toLocaleString()}</b> · SP <b>${sp_now.toLocaleString()}</b> (${pct}%) ${verdict}`;
});

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
                     'Gmax','GmaxX','Dmax5','Dmax4','Dmax3','Dmax2','Dmax1',
                     'T5*','T5sh*','Mega*','MegaT5*','UB*',
                     'Gmax*','GmaxX*','Dmax5*','Dmax4*','Dmax3*'];
  const titles = {
    T5:'현재 5성', T5sh:'현재 쉐도우 5성', Mega:'현재 메가', MegaT5:'메가 5성',
    UB:'울트라비스트', Elite:'엘리트',
    Gmax:'거다이맥스', GmaxX:'거다이맥스 특수',
    Dmax5:'다이맥스 5성', Dmax4:'다이맥스 4성', Dmax3:'다이맥스 3성',
    Dmax2:'다이맥스 2성', Dmax1:'다이맥스 1성',
    'T5*':'예정 5성', 'T5sh*':'예정 쉐도우 5성', 'Mega*':'예정 메가',
    'MegaT5*':'예정 메가 5성', 'UB*':'예정 울트라비스트',
    'Gmax*':'예정 거다이맥스', 'GmaxX*':'예정 거다이맥스 특수',
    'Dmax5*':'예정 다이맥스 5성', 'Dmax4*':'예정 다이맥스 4성', 'Dmax3*':'예정 다이맥스 3성',
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

// 진화 방식 배지
const EVO_BADGE = {
  trade:  ['ovl-gl',   '교환 진화'],
  buddy:  ['ovl-ml',   '버디 미션'],
  walk:   ['ovl-ml',   '걷기 필요'],
  item:   ['ovl-ul',   '아이템 진화'],
  region: ['ovl-cup',  '지역 한정'],
};
function evoBadge(kind, note) {
  if (!kind) return '';
  const [cls, label] = EVO_BADGE[kind] || ['ovl-cup', kind];
  return `<span class="ovl ${cls}" title="${note||''}">${label}${note ? ': ' + note : ''}</span>`;
}

// 한눈에 — 18 속성 × 최강 필드 어태커 Top 3 (압축 표 1개)
function renderFieldTopGlance() {
  let html = `<div class="iv-note" style="background:#e8f5e9;color:#186118">
    <b>전속성 필드 최강 한눈에</b> — 보스 약점 본 뒤 즉시 매칭. 6마리 파티용 Top 3.<br>
    전설/메가/UB 제외. 모두 야생/진화/로켓에서 획득. 100% IV Lv50 풀강 권장.
  </div>`;
  html += `<table><thead><tr>
    <th>속성</th><th>1위</th><th>2위</th><th>3위</th>
  </tr></thead><tbody>`;
  for (const t of ALL_TYPES) {
    const td = DATA.types[t];
    if (!td) continue;
    const top3 = (td.field_top6 || []).slice(0, 3);
    if (!top3.length) continue;
    if (state.typeFilter && state.typeFilter !== t) continue;

    const cellHtml = (f) => {
      if (!f) return '<span class="muted">—</span>';
      const sp = DATA.species[f.sid];
      const cp = f.max_cp || sp?.max_cp || 0;
      const moves = `<small class="moves-en">${f.fast_ko} / ${f.charged_ko}</small>`;
      return `<b>${f.ko}</b><br>
              <span class="en">${f.en}</span><br>
              <span class="rk rk-major">CP ${cp.toLocaleString()}</span> ${moves}`;
    };
    html += `<tr>
      <td style="font-size:14px"><b>${badge(t)} ${td.ko}</b></td>
      <td>${cellHtml(top3[0])}</td>
      <td>${cellHtml(top3[1])}</td>
      <td>${cellHtml(top3[2])}</td>
    </tr>`;
  }
  html += `</tbody></table>`;
  return html;
}

// ━━━━━━ 📥 Calcy IV CSV 일괄 분석 ━━━━━━
const NAME_INDEX = (() => {
  const idx = {};
  const add = (key, sid) => {
    if (!key) return;
    const k = String(key).toLowerCase().trim();
    if (k && !idx[k]) idx[k] = sid;
    // 괄호 제거
    const base = k.replace(/\s*\([^)]*\)/g, '').trim();
    if (base && !idx[base]) idx[base] = sid;
    // 괄호 → 공백 (form 텍스트 유지: "깝질무 (동쪽바다)" → "깝질무 동쪽바다")
    const np = k.replace(/[()]/g, ' ').replace(/\s+/g, ' ').trim();
    if (np && !idx[np]) idx[np] = sid;
  };
  // 1) species_out 모든 종
  for (const sp of Object.values(DATA.species)) {
    add(sp.ko, sp.id);
    add(sp.en, sp.id);
    add(sp.id, sp.id);
    for (const k of (sp.chain_ko || [])) add(k, sp.id);
    for (const e of (sp.chain_en || [])) add(e, sp.id);
  }
  // 2) 가족 그룹 멤버
  for (const groupKey of ['transfer_groups', 'mega_keep_groups', 'mega_possible_groups']) {
    for (const g of (DATA[groupKey] || [])) {
      for (const m of (g.members || [])) {
        add(m.ko, m.sid); add(m.en, m.sid); add(m.sid, m.sid);
      }
    }
  }
  // 3) unranked (gamemaster 폴백)
  for (const u of Object.values(DATA.unranked || {})) {
    add(u.ko, u.id); add(u.en, u.id); add(u.id, u.id);
  }
  return idx;
})();

const FORM_SUFFIX = {
  shadow: '_shadow', mega: '_mega', 'mega x': '_mega_x', 'mega y': '_mega_y',
  alolan: '_alolan', galarian: '_galarian', hisuian: '_hisuian', paldean: '_paldean',
  origin: '_origin', altered: '_altered', therian: '_therian', incarnate: '_incarnate',
  primal: '_primal', '쉐도우': '_shadow', '메가': '_mega', '메가 x': '_mega_x',
  '메가 y': '_mega_y', '알로라': '_alolan', '가라르': '_galarian',
};

// 한글 폼 키워드 → suffix
const KO_FORM_KEYWORDS = {
  '동쪽바다': '_east_sea', '서쪽바다': '_west_sea',
  '알로라': '_alolan', '갈라르': '_galarian',
  '히스이': '_hisuian', '팔데아': '_paldean',
  '오리진': '_origin', '어나더': '_altered',
  '영물': '_therian', '화신': '_incarnate',
  '원시': '_primal',
  '메가 x': '_mega_x', '메가 y': '_mega_y', '메가': '_mega',
  '쉐도우': '_shadow',
  '초목도롱': '_plant', '모래도롱': '_sandy', '쓰레기도롱': '_trash',
  '여름의': '_summer', '가을의': '_autumn', '겨울의': '_winter', '봄의': '_spring',
};

// Calcy IV 가 이름에 붙이는 마크 제거 (성별·사이즈 등)
function stripCalcyDecorations(name) {
  if (!name) return '';
  let n = name;
  n = n.replace(/\s*[♀♂]\s*/g, ' ');
  n = n.replace(/\s+(XXL|XXS|XL|XS|M|S|L)\s*$/i, '');
  n = n.replace(/[★☆"']/g, '');
  return n.replace(/\s+/g, ' ').trim();
}

function matchSpecies(name, form, isShadow) {
  if (!name) return null;
  name = stripCalcyDecorations(name);
  const cleanName = name.replace(/\s*\([^)]*\)/g, '').trim();
  // 1: 그대로 / 괄호 제거 버전 매칭
  let baseId = NAME_INDEX[name.toLowerCase().trim()]
            || NAME_INDEX[cleanName.toLowerCase()];

  // 2: 한글 폼 키워드 추출 (이름에 폼이 합쳐서 들어온 경우)
  if (!baseId) {
    const keys = Object.keys(KO_FORM_KEYWORDS).sort((a, b) => b.length - a.length);
    for (const kw of keys) {
      if (name.toLowerCase().includes(kw)) {
        const pure = name.toLowerCase().replace(kw, '').replace(/\s+/g, ' ').trim();
        const bid = NAME_INDEX[pure];
        if (bid) {
          const base = bid.replace(/_(mega(_[xyz])?|primal|shadow|alolan|galarian|hisuian|paldean|origin|altered|therian|incarnate|east_sea|west_sea|plant|sandy|trash|summer|autumn|winter|spring)$/, '');
          const variant = base + KO_FORM_KEYWORDS[kw];
          if (DATA.species[variant] || (DATA.unranked && DATA.unranked[variant])) return variant;
          return bid;
        }
      }
    }
  }
  if (!baseId) return null;

  // 3: form 컬럼 적용
  const formKey = (form || '').toLowerCase().trim();
  let suffix = FORM_SUFFIX[formKey] || '';
  if (isShadow && !suffix) suffix = '_shadow';
  if (suffix) {
    const base = baseId.replace(/_(mega(_[xyz])?|primal|shadow|alolan|galarian|hisuian|paldean|origin|altered|therian|incarnate)$/, '');
    const variant = base + suffix;
    if (DATA.species[variant]) return variant;
  }
  return baseId;
}

// 종 정보 lookup — species_out 우선, 없으면 transfer/mega/unranked
function lookupSpecies(sid) {
  if (DATA.species[sid]) return { sp: DATA.species[sid], category: 'species' };
  for (const g of (DATA.transfer_groups || [])) {
    const m = g.members.find(x => x.sid === sid);
    if (m) return { sp: m, category: 'transfer', group: g };
  }
  for (const g of (DATA.mega_keep_groups || [])) {
    const m = g.members.find(x => x.sid === sid);
    if (m) return { sp: m, category: 'mega_keep', group: g };
  }
  for (const g of (DATA.mega_possible_groups || [])) {
    const m = g.members.find(x => x.sid === sid);
    if (m) return { sp: m, category: 'mega_possible', group: g };
  }
  if (DATA.unranked && DATA.unranked[sid]) return { sp: DATA.unranked[sid], category: 'unranked' };
  return null;
}

function maxLevelForCP(sp, ivA, ivD, ivS, cpCap) {
  if (!sp.base_stats) return null;
  for (let i = DATA.cpm.length - 1; i >= 0; i--) {
    const cpm = DATA.cpm[i];
    const a = (sp.base_stats.atk + ivA) * cpm;
    const d = (sp.base_stats.def + ivD) * cpm;
    const s = (sp.base_stats.hp + ivS) * cpm;
    const cp = Math.max(10, Math.floor(a * Math.sqrt(d) * Math.sqrt(s) / 10));
    if (cp <= cpCap) {
      return { level: 1 + i * 0.5, cp, sp: a * d * Math.floor(s) };
    }
  }
  return null;
}

function leagueScore(sp, leagueIV, ivA, ivD, ivS, cpCap) {
  // 사용자 IV 의 SP / 그 종의 rank-1 IV SP × 100
  if (!leagueIV) return null;
  const userMax = maxLevelForCP(sp, ivA, ivD, ivS, cpCap);
  const r1Max = maxLevelForCP(sp, leagueIV.atk, leagueIV.def, leagueIV.sta, cpCap);
  if (!userMax || !r1Max || !r1Max.sp) return null;
  return {
    pct: (userMax.sp / r1Max.sp * 100),
    cp: userMax.cp,
    level: userMax.level,
  };
}

function analyzeOne(sp, ivA, ivD, ivS, level, isLucky) {
  if (!sp) return null;
  // 1) 풀강 SP / 100% Lv50 SP
  const userSP = statProductAt(sp, ivA, ivD, ivS, level);
  const userPct = sp.max_sp ? userSP / sp.max_sp * 100 : 0;

  // 2) 리그별 점수 (SP 기준 rank-1 대비 %)
  const glScore = sp.rank1_iv?.GL ? leagueScore(sp, sp.rank1_iv.GL, ivA, ivD, ivS, 1500) : null;
  const ulScore = sp.rank1_iv?.UL ? leagueScore(sp, sp.rank1_iv.UL, ivA, ivD, ivS, 2500) : null;
  const lcScore = sp.rank1_iv?.Little ? leagueScore(sp, sp.rank1_iv.Little, ivA, ivD, ivS, 500) : null;

  // 3) 역할
  const ml = bestRankIn(sp, ML_KEYS);
  const gl = bestRankIn(sp, GL_KEYS);
  const ul = bestRankIn(sp, UL_KEYS);
  const lc = bestRankIn(sp, LC_KEYS);
  const raid = bestRaidRank(sp);
  const cups = sp.pvp.filter(p =>
    !GL_KEYS.has(p.league_key) && !UL_KEYS.has(p.league_key) &&
    !ML_KEYS.has(p.league_key) && !LC_KEYS.has(p.league_key)
  ).sort((a,b) => a.rank - b.rank);

  // 4) 판단 — 우선순위 높은 것부터
  const decisions = [];
  const isHundo = ivA === 15 && ivD === 15 && ivS === 15;
  const ivSum = ivA + ivD + ivS;

  // 백개체 — 항상 최상위 라벨. ML/레이드 종 여부와 무관 (메가/마스터/컬렉션 가치)
  if (isHundo) {
    const ctx = (ml && ml.rank <= 15) ? `ML#${ml.rank}` :
                (raid && raid.rank <= 8 && raid.is_essential_tier) ? `vs ${raid.boss_ko}#${raid.rank}` :
                (gl && gl.rank <= 20) ? `슈퍼리그 #${gl.rank} (캡 손해 있음)` :
                '메가 변신 / 마스터리그 / 콜렉션';
    decisions.push({pri:1, text:`🏆 백개체 (15/15/15) — ML / 레이드 종결`, why: ctx});
  }

  // 마스터/레이드 — ATK IV 가 핵심 (DEF/HP 는 부활 가능해서 영향 적음)
  if (!isHundo && ((ml && ml.rank <= 15) || (raid && raid.is_essential_tier && raid.rank <= 8))) {
    const isML = ml && ml.rank <= 15;
    const ctxBoss = raid ? `vs ${raid.boss_ko}#${raid.rank}` : '';
    if (false) {
      // hundo 위에서 처리됨 — 분기 살리기 위해 dummy
    } else if (ivA === 15 && ivSum >= 38) {
      // ATK 15 + 합 38+ — 레이드 최적 (ML 도 거의 풀강 가치)
      decisions.push({pri:1, text:`🔴 레이드 최적 (ATK 15, ${ivSum}/45)`,
                      why:`공격력 풀 → DPS 손실 X · ${ctxBoss}`});
    } else if (ivA >= 14 && ivSum >= 38) {
      decisions.push({pri:2, text:`🟡 레이드 강 (ATK ${ivA}, ${ivSum}/45)`,
                      why:`공격력 거의 풀 · 100% 잡으면 교체${isML?' (ML 은 100% 우선)':''}`});
    } else if (ivA === 15 && ivSum >= 30) {
      decisions.push({pri:2, text:`🟡 레이드 가능 (ATK 15, 약방어)`,
                      why:'레이드용은 OK, ML 은 100% 우선'});
    } else if (ivSum >= 42) {
      // 100%에 가깝지만 ATK 가 낮음
      decisions.push({pri:2, text:`🟡 마스터 후보 (IV ${ivSum}/45 · ATK ${ivA})`,
                      why:'ML 강함, 레이드는 ATK 낮아 약함'});
    } else if (ivA >= 13 && ivSum >= 36) {
      decisions.push({pri:3, text:`🔵 레이드 보조 (ATK ${ivA})`,
                      why:'더 좋은 거 잡으면 송출'});
    } else if (ivSum >= 36) {
      decisions.push({pri:3, text:`🔵 IV 부족 — 송출 후보`,
                      why:'ATK 낮아 레이드 비효율'});
    }
  }

  // 슈퍼리그
  if (gl && gl.rank <= 20 && glScore) {
    if (glScore.pct >= 99) decisions.push({pri:1, text:`🔴 슈퍼리그 #${gl.rank} 거의 완벽 (${glScore.pct.toFixed(1)}%)`, why:`Lv${glScore.level} CP${glScore.cp}`});
    else if (glScore.pct >= 96) decisions.push({pri:2, text:`🟡 슈퍼리그 #${gl.rank} 쓸만 (${glScore.pct.toFixed(1)}%)`, why:`Lv${glScore.level} CP${glScore.cp}`});
    else if (glScore.pct >= 90) decisions.push({pri:3, text:`🔵 슈퍼리그 #${gl.rank} 부족 (${glScore.pct.toFixed(1)}%)`, why:'rank-1 IV 보다 약함'});
  }

  // 하이퍼리그
  if (ul && ul.rank <= 20 && ulScore) {
    if (ulScore.pct >= 99) decisions.push({pri:1, text:`🔴 하이퍼리그 #${ul.rank} 거의 완벽 (${ulScore.pct.toFixed(1)}%)`, why:`Lv${ulScore.level} CP${ulScore.cp}`});
    else if (ulScore.pct >= 96) decisions.push({pri:2, text:`🟡 하이퍼리그 #${ul.rank} 쓸만 (${ulScore.pct.toFixed(1)}%)`, why:`Lv${ulScore.level} CP${ulScore.cp}`});
  }

  // 리틀컵
  if (lc && lc.rank <= 15 && lcScore && lcScore.pct >= 96) {
    decisions.push({pri:2, text:`🟡 리틀컵 #${lc.rank} (${lcScore.pct.toFixed(1)}%)`, why:`Lv${lcScore.level} CP${lcScore.cp}`});
  }

  // 컵 한정 — 1500 CP 컵이라 GL 종결 IV 가 컵에도 종결. glScore.pct 로 검증
  if (cups.length && !decisions.length) {
    const top = cups[0];
    if (glScore && glScore.pct >= 99) {
      decisions.push({pri:1, text:`🥇 컵 종결 — ${top.league_ko}#${top.rank} (${glScore.pct.toFixed(1)}%)`,
                      why:`Lv${glScore.level} CP${glScore.cp} · 1500 캡 거의 완벽`});
    } else if (glScore && glScore.pct >= 96) {
      decisions.push({pri:2, text:`🟡 컵 한정 — ${top.league_ko}#${top.rank} (${glScore.pct.toFixed(1)}%)`,
                      why:`Lv${glScore.level} CP${glScore.cp} · 컵 풀강 가능`});
    } else if (glScore && glScore.pct >= 90) {
      decisions.push({pri:3, text:`🔵 컵 후보 — ${top.league_ko}#${top.rank} (${glScore.pct.toFixed(1)}%)`,
                      why:'IV 부족 — 더 좋은 거 잡으면 송출'});
    } else if (glScore) {
      // ATK 높아 1500 캡에 못 맞춤 — 컵에서 무용
      decisions.push({pri:4, text:`📦 컵 못 씀 — ${top.league_ko}#${top.rank} (${glScore.pct.toFixed(1)}%)`,
                      why:`IV ${ivA}/${ivD}/${ivS} — 공격 너무 높아 1500 캡 풀강 불가`});
    } else {
      // rank1_iv.GL 없음 (베이비/너무 약함) — 컵 의미 없음
      decisions.push({pri:3, text:`🔵 컵 한정 — ${top.league_ko}#${top.rank}`, why:'시즌 한정, 보관 권장'});
    }
  }

  // 가족이 박사송출 / 메가 보관 그룹인지
  const inMegaKeep = (DATA.mega_keep_groups||[]).some(g => g.members.some(m => m.sid === sp.id));
  const inMegaPossible = (DATA.mega_possible_groups||[]).some(g => g.members.some(m => m.sid === sp.id));
  const inTransfer = (DATA.transfer_groups||[]).some(g => g.members.some(m => m.sid === sp.id));

  if (!decisions.length) {
    if (sp.stronger_forms && sp.stronger_forms.length) {
      decisions.push({pri:3, text:`🔵 더 강한 폼 우선`, why:'쉐도우/메가 가 핵심 — 베이스 1마리만 보관'});
    } else if (inMegaKeep) {
      decisions.push({pri:1, text:`🔴 메가 변신 베이스 — 100% IV 보관 필수`, why:'메가가 ranked'});
    } else if (inMegaPossible) {
      decisions.push({pri:2, text:`🟡 메가 가능 — 100% IV 1마리 보관`, why:'추후 메가 풀 추가 대비'});
    } else if (inTransfer) {
      decisions.push({pri:4, text:`⚪ 박사 송출 OK`, why:'어디에도 안 쓰임 (가족당 1마리만 보관)'});
    } else {
      decisions.push({pri:3, text:`🔵 랭킹 외 — 보관 OK`, why:'1마리만 보관 권장'});
    }
  }

  // 럭키면 우선순위 +1단계 보관 권장
  if (isLucky) {
    decisions.push({pri:0, text:'🍀 Lucky', why:'반값 강화 — 보관 가치 +1'});
  }

  decisions.sort((a, b) => a.pri - b.pri);
  return {
    sid: sp.id,
    ko: sp.ko, en: sp.en, dex: sp.dex, types: sp.types,
    iv: {a:ivA, d:ivD, s:ivS}, level, isLucky,
    sp_now: userSP, sp_pct: userPct,
    decisions,
    pri: decisions[0]?.pri || 99,
  };
}

function parseCSV(text) {
  const lines = text.replace(/﻿/g, '').trim().split(/\r?\n/);
  if (!lines.length) return {headers:[], rows:[]};
  const first = lines[0];
  const delim = first.includes('\t') ? '\t' : (first.split(';').length > first.split(',').length ? ';' : ',');
  const splitLine = (line) => {
    // 쉼표 인용 처리
    if (delim !== ',') return line.split(delim).map(c => c.trim());
    const out = []; let cur = ''; let inQ = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (c === '"') inQ = !inQ;
      else if (c === ',' && !inQ) { out.push(cur.trim()); cur = ''; }
      else cur += c;
    }
    out.push(cur.trim());
    return out;
  };
  const headers = splitLine(first).map(h => h.replace(/^"|"$/g, ''));
  const rows = lines.slice(1).filter(l => l.trim()).map(line =>
    splitLine(line).map(c => c.replace(/^"|"$/g, ''))
  );
  return {headers, rows};
}

function findCol(headers, aliases) {
  const lower = headers.map(h => h.toLowerCase().trim());
  for (const a of aliases) {
    const i = lower.indexOf(a.toLowerCase());
    if (i >= 0) return i;
  }
  // 부분 매칭
  for (let i = 0; i < lower.length; i++) {
    for (const a of aliases) {
      if (lower[i].includes(a.toLowerCase()) && lower[i].length < a.length + 4) return i;
    }
  }
  return -1;
}

function detectColumns(headers) {
  // 헤더 정규화 — Ø, Avg, 공백 통일
  const norm = headers.map(h => h.toLowerCase()
    .replace(/ø/g, 'avg ')
    .replace(/^avg(?=\S)/, 'avg ')      // "avgatt" → "avg att"
    .replace(/\s+/g, ' ').trim());
  // findCol 재구현 — 정규화된 버전에서 검색
  const find = (aliases) => {
    for (const a of aliases) {
      const i = norm.indexOf(a.toLowerCase());
      if (i >= 0) return i;
    }
    for (let i = 0; i < norm.length; i++) {
      for (const a of aliases) {
        const al = a.toLowerCase();
        if (norm[i] === al) return i;
        if (norm[i].includes(al) && norm[i].length < al.length + 8) return i;
      }
    }
    return -1;
  };
  return {
    name: find(['name', 'pokemon', 'species', '이름', '포켓몬', '몬스터']),
    form: find(['form', '폼']),
    cp: find(['cp']),
    atk: find(['avg att iv', 'avg att', 'att iv', 'atk', 'attack', '공격']),
    def: find(['avg def iv', 'avg def', 'def iv', 'def', 'defense', 'defence', '방어']),
    sta: find(['avg hp iv', 'avg hp', 'hp iv', 'sta iv', 'sta', 'stamina', '체력']),
    level: find(['lvl', 'level', 'lv', '레벨']),
    hp: find(['hp', 'health']),
    shadow: find(['shadowform', 'shadow', 'is shadow', '쉐도우']),
    lucky: find(['lucky?', 'lucky', 'is lucky', '럭키']),
  };
}

function renderCalcy() {
  let html = `<div class="iv-note" style="background:#e8f5e9;color:#186118">
    <b>📥 Calcy IV CSV 박스 정리</b><br>
    Calcy IV 의 "Scan all" → CSV → 업로드 → 박스 자동 분류:<br>
    🏆 종결 / ⚔️ 레이드용 / 🛡️ PvP용 / 🛡️ 메가 보관 / 🔄 컵 한정 / 📦 송출 / 🤔 고민
  </div>
  <div class="card">
    <input type="file" id="calcy-file" accept=".csv,.txt,.tsv" style="margin-bottom:8px">
    <textarea id="calcy-text" placeholder="또는 CSV 텍스트 붙여넣기"
      style="width:100%;height:100px;font-family:monospace;font-size:11px;padding:8px;border:1px solid #d0d0d6;border-radius:6px"></textarea>
    <div style="margin-top:8px;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
      <button id="calcy-go" class="ctrl">분석 실행</button>
      <span id="calcy-summary" class="muted" style="margin-left:auto"></span>
    </div>
  </div>
  <div id="calcy-buckets"></div>
  <div id="calcy-result"></div>`;
  return html;
}

let _calcyResults = null;
let _calcyBucket = 'transfer';  // 기본 표시 — 송출 후보

document.addEventListener('change', e => {
  if (e.target.id === 'calcy-file') {
    const f = e.target.files[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = ev => { document.getElementById('calcy-text').value = ev.target.result; };
    reader.readAsText(f, 'utf-8');
  }
});

document.addEventListener('click', e => {
  if (e.target.id === 'calcy-go') runCalcy();
  const bucketBtn = e.target.closest('[data-bucket]');
  if (bucketBtn) {
    _calcyBucket = bucketBtn.dataset.bucket;
    renderCalcyResults();
  }
  if (e.target.id === 'calcy-export') exportFilteredCSV();
});

function runCalcy() {
  const text = document.getElementById('calcy-text').value;
  if (!text.trim()) { alert('CSV 내용 없음'); return; }
  const {headers, rows} = parseCSV(text);
  const cols = detectColumns(headers);
  if (cols.name < 0 || cols.atk < 0 || cols.def < 0 || cols.sta < 0) {
    alert('필요 컬럼 못 찾음 — Name/Atk/Def/Sta 컬럼 헤더 확인');
    return;
  }
  const out = [];
  let unmatched = 0;
  for (const r of rows) {
    const name = r[cols.name];
    if (!name) continue;
    const form = cols.form >= 0 ? r[cols.form] : '';
    const isShadowCol = cols.shadow >= 0 ? r[cols.shadow] : '';
    const isShadow = /^(yes|true|1|y|쉐도우)$/i.test(isShadowCol);
    const sid = matchSpecies(name, form, isShadow);
    if (!sid) { unmatched++; continue; }
    const lookup = lookupSpecies(sid);
    if (!lookup) { unmatched++; continue; }
    const ivA = parseInt(r[cols.atk]);
    const ivD = parseInt(r[cols.def]);
    const ivS = parseInt(r[cols.sta]);
    const lv = parseFloat(r[cols.level]) || 30;
    const lucky = cols.lucky >= 0 && /^(yes|true|1|y|럭키)$/i.test(r[cols.lucky]);
    if (isNaN(ivA) || isNaN(ivD) || isNaN(ivS)) continue;

    let result;
    if (lookup.category === 'species') {
      result = analyzeOne(lookup.sp, ivA, ivD, ivS, lv, lucky);
    } else {
      // species_out 외 종 — 가족 분류로 직접 판단
      const m = lookup.sp;
      let pri = 4, text = '⚪ 박사 송출 OK', why = '';
      const isHundo = ivA === 15 && ivD === 15 && ivS === 15;
      if (lookup.category === 'mega_keep') {
        pri = isHundo ? 1 : 2;
        text = isHundo ? '🔴 메가 변신 베이스 — 100% 보관' : '🟡 메가 보관 — 100% 우선';
        why = '메가가 ranked';
      } else if (lookup.category === 'mega_possible') {
        pri = 2;
        text = '🟡 메가 가능 — 100% 1마리 보관';
        why = '추후 메가 풀 추가 대비';
      } else if (lookup.category === 'transfer') {
        const isKeep = lookup.group && m.sid === lookup.group.keep_sid;
        if (m.is_shadow) { pri = 4; text = '⚪ 박사 송출 OK (쉐도우)'; }
        else if (isKeep) { pri = 3; text = '🔵 가족 대표 — 1마리 보관'; why = '메타 변동 대비'; }
        else { pri = 4; text = '⚪ 박사 송출 OK'; why = '가족 송출 후보'; }
      } else {
        pri = 4; text = '⚪ 박사 송출 OK (분류 없음)'; why = '';
      }
      result = {
        sid, ko: m.ko, en: m.en || '', dex: m.dex || 9999,
        types: m.types || [],
        iv: {a: ivA, d: ivD, s: ivS}, level: lv, isLucky: lucky,
        sp_now: 0, sp_pct: 0,
        decisions: [{pri, text, why}],
        pri,
      };
    }
    if (result) out.push(result);
  }
  // 박스 기준 팀 빌드 — bucket 분류 가 팀 멤버십을 사용하므로 먼저
  buildUserTeams(out);
  // bucket 분류 — 팀에 든 애들은 team_*, 아니면 cand_*/hold/transfer
  for (const r of out) r.bucket = classifyBucket(r);
  // 후보군 dedup — 같은 종 여러 마리면 최고 1마리만 cand_*, 나머지 transfer
  dedupeCandidates(out);
  _calcyResults = out;
  document.getElementById('calcy-summary').textContent =
    `총 ${out.length}마리 분석 (매칭 실패 ${unmatched})`;
  renderCalcyResults();
}

// 후보군 dedup — 같은 종 여러 마리면 (sid × bucket) 별 최고 1마리만 keep, 나머지 transfer
// team_* 는 dedup 대상 아님 (이미 buildUserTeams 가 종당 1마리만 뽑음)
function dedupeCandidates(results) {
  const CAND_BUCKETS = new Set(['cand_raid', 'cand_gl', 'cand_ul', 'cand_cup', 'hold']);
  const bySid = {};
  for (const r of results) {
    if (!CAND_BUCKETS.has(r.bucket)) continue;
    if (!bySid[r.bucket]) bySid[r.bucket] = {};
    if (!bySid[r.bucket][r.sid]) bySid[r.bucket][r.sid] = [];
    bySid[r.bucket][r.sid].push(r);
  }
  for (const bucket of Object.keys(bySid)) {
    for (const sid of Object.keys(bySid[bucket])) {
      const list = bySid[bucket][sid];
      if (list.length <= 1) continue;
      // 정렬: ATK 가중치 + 합계
      list.sort((a, b) => {
        const sa = a.iv.a * 2 + a.iv.d + a.iv.s + (a.isLucky ? 5 : 0);
        const sb = b.iv.a * 2 + b.iv.d + b.iv.s + (b.isLucky ? 5 : 0);
        return sb - sa;
      });
      // 1번째 = 유지, 나머지는 송출 bucket 으로
      for (let i = 1; i < list.length; i++) {
        const r = list[i];
        r.bucket = 'transfer';
        r.decisions = [{
          pri: 4,
          text: `📦 중복 송출 — 같은 종 ${list.length}마리 중 ${i + 1}번째`,
          why: `최고: ${list[0].ko} IV ${list[0].iv.a}/${list[0].iv.d}/${list[0].iv.s}`,
        }];
        r.pri = 4;
      }
      // 1번째 keep 표시 보강
      const top = list[0];
      if (list.length > 1 && top.decisions[0]) {
        top.decisions[0].why = (top.decisions[0].why || '') + ` (이 종 ${list.length}마리 중 최고)`;
      }
    }
  }
}

// 박스 기준 팀 빌드 — 속성별·레이드별·리그별
let _myTeams = null;
function buildUserTeams(results) {
  // 1) 속성별 레이드 어태커 Top 6 (내 박스에서)
  const byType = {};  // type → list of {result, atkScore, raidRank}
  for (const r of results) {
    const sp = DATA.species[r.sid];
    if (!sp || !sp.raid?.length) continue;
    // ATK 가중치 점수
    const atkScore = r.iv.a * 2 + r.iv.d + r.iv.s;
    const bestRaid = [...sp.raid].sort((a,b) => a.rank - b.rank)[0];
    for (const t of sp.types) {
      // T 약점 보스에서 raid rank 가장 좋은 것
      let bestForT = null;
      for (const rd of sp.raid) {
        const boss = DATA.bosses[rd.boss_key];
        if (!boss) continue;
        if (!boss.boss_weak[t]) continue;
        if (!bestForT || rd.rank < bestForT.rank) bestForT = rd;
      }
      const score = (bestForT ? bestForT.rank : 99) - atkScore * 0.5;
      if (!byType[t]) byType[t] = [];
      byType[t].push({ r, atkScore, raidRank: bestForT?.rank || bestRaid.rank,
                       boss_ko: bestForT?.boss_ko, score });
    }
  }
  for (const t of Object.keys(byType)) {
    byType[t].sort((a, b) => a.score - b.score);
    byType[t] = byType[t].slice(0, 6);
  }

  // 2) 현재 활성 레이드 보스별 추천 팀
  const ESSENTIAL_TIERS = new Set(['T5','T5sh','Mega','MegaT5','UB','Elite']);
  const bossTeams = {};  // boss_key → list
  for (const [bossKey, b] of Object.entries(DATA.bosses)) {
    if (!ESSENTIAL_TIERS.has(b.tier_en)) continue;  // 현재만
    const candidates = [];
    for (const r of results) {
      const sp = DATA.species[r.sid];
      if (!sp) continue;
      const myMatch = sp.raid?.find(rd => rd.boss_key === bossKey);
      if (!myMatch) continue;
      const atkScore = r.iv.a * 2 + r.iv.d + r.iv.s;
      candidates.push({ r, raidRank: myMatch.rank, atkScore,
                        score: myMatch.rank - atkScore * 0.3 });
    }
    candidates.sort((a, b) => a.score - b.score);
    if (candidates.length) bossTeams[bossKey] = { boss: b, team: candidates.slice(0, 6) };
  }

  // 3) 슈퍼리그 / 하이퍼리그 박스 Top 6 (컵 IV 검증 포함)
  const leagueTeams = { GL: [], UL: [] };
  for (const r of results) {
    const sp = DATA.species[r.sid];
    if (!sp) continue;
    for (const [code, keys, cap] of [['GL', GL_KEYS, 1500], ['UL', UL_KEYS, 2500]]) {
      const best = bestRankIn(sp, keys);
      if (!best || best.rank > 30) continue;
      const r1 = sp.rank1_iv?.[code];
      const score = r1 ? leagueScore(sp, r1, r.iv.a, r.iv.d, r.iv.s, cap) : null;
      const pct = score?.pct || 0;
      if (pct < 90) continue;  // 풀강 못하는 IV 제외
      leagueTeams[code].push({ r, leagueRank: best.rank, pct });
    }
  }
  for (const k of Object.keys(leagueTeams)) {
    leagueTeams[k].sort((a, b) => (a.leagueRank - b.leagueRank) || (b.pct - a.pct));
    const seen = new Set();
    leagueTeams[k] = leagueTeams[k].filter(x => {
      if (seen.has(x.r.sid)) return false;
      seen.add(x.r.sid);
      return true;
    }).slice(0, 6);
  }

  // 4) 컵별 Top 6 (1500 캡 → glScore 로 IV 검증)
  // sp.pvp 에서 GL/UL/ML/Little 외 모든 league_key
  const cupAccum = {};
  for (const r of results) {
    const sp = DATA.species[r.sid];
    if (!sp) continue;
    for (const p of (sp.pvp || [])) {
      if (GL_KEYS.has(p.league_key) || UL_KEYS.has(p.league_key)
       || ML_KEYS.has(p.league_key) || LC_KEYS.has(p.league_key)) continue;
      if (p.rank > 30) continue;
      // 1500 컵 — glScore 검증 (rank1_iv.GL 사용)
      const r1 = sp.rank1_iv?.GL;
      const score = r1 ? leagueScore(sp, r1, r.iv.a, r.iv.d, r.iv.s, 1500) : null;
      const pct = score?.pct || 0;
      if (pct < 90) continue;
      if (!cupAccum[p.league_key]) cupAccum[p.league_key] = { league_ko: p.league_ko, league_en: p.league_en, list: [] };
      cupAccum[p.league_key].list.push({ r, cupRank: p.rank, pct });
    }
  }
  const cupTeams = {};
  for (const k of Object.keys(cupAccum)) {
    const ct = cupAccum[k];
    ct.list.sort((a,b) => (a.cupRank - b.cupRank) || (b.pct - a.pct));
    const seen = new Set();
    ct.list = ct.list.filter(x => {
      if (seen.has(x.r.sid)) return false;
      seen.add(x.r.sid); return true;
    }).slice(0, 6);
    if (ct.list.length >= 3) cupTeams[k] = ct;  // 박스에서 3마리 이상 모이는 컵만
  }

  _myTeams = { byType, bossTeams, leagueTeams, cupTeams };
}

// 가용한 leagueScore (analyze 가 쓰던 거) — 클로저 외부에 있어야 함
function bestRankInBox(sp, keys) {
  let best = null;
  for (const p of (sp.pvp || [])) {
    if (!keys.has(p.league_key)) continue;
    if (!best || p.rank < best.rank) best = p;
  }
  return best;
}

// 박스 정리 bucket 분류 — 팀 멤버십 우선, 그 다음 후보군 / 보류 / 송출
// _myTeams 가 buildUserTeams 호출 후 채워져 있어야 함.
function classifyBucket(r) {
  // ─── 1순위: 베스트 6 팀에 들어간 경우
  if (_myTeams) {
    for (const bt of Object.values(_myTeams.bossTeams || {})) {
      if (bt.team.some(m => m.r === r)) return 'team_raid_current';
    }
    if ((_myTeams.leagueTeams.GL || []).some(m => m.r === r)) return 'team_gl';
    if ((_myTeams.leagueTeams.UL || []).some(m => m.r === r)) return 'team_ul';
    for (const ct of Object.values(_myTeams.cupTeams || {})) {
      if (ct.list.some(m => m.r === r)) return 'team_cups';
    }
    for (const arr of Object.values(_myTeams.byType || {})) {
      if (arr.some(m => m.r === r)) return 'team_raid_type';
    }
  }

  // ─── 2순위: 후보군 — decision 별로 검사 (전체 allTxt 합치면 .* 가 다른 decision 까지 매칭함)
  const decTexts = r.decisions.map(d => d.text || '');
  const anyDec = (re) => decTexts.some(t => re.test(t));

  // 컵 못 씀 (1500 캡 풀강 불가) → 송출
  if (anyDec(/컵 못 씀/)) return 'transfer';

  // 백개체 / ATK 15 강자 → 레이드 후보군
  if (r.iv.a === 15 && r.iv.d === 15 && r.iv.s === 15) return 'cand_raid';
  if (anyDec(/마스터\/레이드 풀강|레이드 최적|레이드 강|레이드 가능|메가 변신 베이스/)) return 'cand_raid';

  // 리그 후보군 — decision 안에서 (긍정 신호 AND 부족 아님)
  if (anyDec(/슈퍼리그.*(거의 완벽|쓸만)/)) return 'cand_gl';
  if (anyDec(/하이퍼리그.*(거의 완벽|쓸만)/)) return 'cand_ul';

  // 컵 후보군 — 컵 종결/한정/후보 (90%+)
  if (anyDec(/컵 종결|컵 한정|컵 후보/)) return 'cand_cup';

  // ─── 3순위: 보류 — 메가 / 가족 대표
  if (anyDec(/메가 가능|메가 보관|가족 대표/)) return 'hold';

  // ─── 4순위: 송출 (그 외 모두 — IV 부족, 랭킹 외, 송출 OK 등)
  return 'transfer';
}

const BUCKET_INFO = {
  // ─── 베스트 6 — 키울 6마리 (자동 선발)
  team_raid_current: { label: '🏟️ 현재 레이드 베스트 6', desc: '활성 레이드 보스별로 박스에서 자동 선발' },
  team_raid_type:    { label: '🌈 속성별 레이드 Top 6',  desc: '18 속성별 박스 기준 어태커 Top 6' },
  team_gl:           { label: '⚔️ 슈퍼리그 베스트 6',    desc: '1500 캡 — 박스 Top 6 (종 중복 제거)' },
  team_ul:           { label: '🛡️ 하이퍼리그 베스트 6', desc: '2500 캡 — 박스 Top 6 (종 중복 제거)' },
  team_cups:         { label: '🥊 각종 컵 베스트 6',     desc: '컵별 박스 Top 6 (3마리 이상 모이는 컵만)' },
  // ─── 후보군 — 베스트 못 들었지만 버리기 아까운 백업
  cand_raid: { label: '⚔️ 레이드용 후보군', desc: '백개체 / ATK 15 강자 / 메가 베이스 — 백업' },
  cand_gl:   { label: '🛡️ 슈퍼리그 후보군', desc: 'GL Top 30 + IV 적합 — 베스트 6 외 백업' },
  cand_ul:   { label: '🛡️ 하이퍼리그 후보군', desc: 'UL Top 30 + IV 적합 — 베스트 6 외 백업' },
  cand_cup:  { label: '🥊 컵 후보군',         desc: '컵 종결 / 컵 한정 — 컵 베스트 외 백업' },
  // ─── 결정
  hold:     { label: '🤔 보류',     desc: '가족 대표 / 메가 변신 대비' },
  transfer: { label: '📦 박사 송출', desc: '바로 보내도 OK' },
};
const BUCKET_ORDER = [
  'team_raid_current', 'team_raid_type', 'team_gl', 'team_ul', 'team_cups',
  'cand_raid', 'cand_gl', 'cand_ul', 'cand_cup',
  'hold', 'transfer',
];

function exportFilteredCSV() {
  if (!_calcyResults) return;
  const list = _calcyBucket === 'all' ? _calcyResults
             : _calcyResults.filter(r => r.bucket === _calcyBucket);
  const rows = [['Dex','한글','영어','속성','IV','Lv','분류','판단','이유']];
  list.sort((a,b) => a.ko.localeCompare(b.ko, 'ko') || a.dex - b.dex);
  for (const r of list) {
    const top = r.decisions[0];
    rows.push([
      String(r.dex).padStart(3,'0'),
      r.ko, r.en, (r.types||[]).join('/'),
      `${r.iv.a}/${r.iv.d}/${r.iv.s}`,
      r.level,
      BUCKET_INFO[r.bucket]?.label || r.bucket,
      top.text, top.why,
    ]);
  }
  const csv = '﻿' + rows.map(r => r.map(c =>
    /[,"\n]/.test(String(c)) ? '"' + String(c).replace(/"/g,'""') + '"' : c
  ).join(',')).join('\n');
  const blob = new Blob([csv], {type: 'text/csv;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `pogo_${_calcyBucket}_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
}

function renderCalcyResults() {
  if (!_calcyResults) return;
  const counts = {};
  for (const r of _calcyResults) counts[r.bucket] = (counts[r.bucket] || 0) + 1;

  let bh = '<div class="bucket-bar">';
  bh += `<button class="bucket-btn ${_calcyBucket === 'all' ? 'on' : ''}" data-bucket="all">전부 ${_calcyResults.length}</button>`;
  for (const b of BUCKET_ORDER) {
    if (!counts[b]) continue;
    const cls = _calcyBucket === b ? 'on' : '';
    bh += `<button class="bucket-btn ${cls}" data-bucket="${b}">${BUCKET_INFO[b].label} ${counts[b]}</button>`;
  }
  bh += `<button id="calcy-export" class="bucket-btn export-btn" title="현재 보기 CSV 저장">⬇ CSV 저장</button>`;
  bh += '</div>';
  document.getElementById('calcy-buckets').innerHTML = bh;

  // ─── team_* bucket 들은 각자 팀 화면 (테이블 X)
  const TEAM_RENDERERS = {
    team_raid_current: renderTeamRaidCurrent,
    team_raid_type:    renderTeamRaidType,
    team_gl:           () => renderTeamLeague('GL'),
    team_ul:           () => renderTeamLeague('UL'),
    team_cups:         renderTeamCups,
  };
  if (TEAM_RENDERERS[_calcyBucket]) {
    document.getElementById('calcy-result').innerHTML = TEAM_RENDERERS[_calcyBucket]();
    return;
  }

  let list = _calcyBucket === 'all' ? _calcyResults
           : _calcyResults.filter(r => r.bucket === _calcyBucket);
  // 같은 종 묶이게 ko 이름 정렬, 그 안에서 IV 합 높은 순
  list = [...list].sort((a, b) => {
    const c = a.ko.localeCompare(b.ko, 'ko');
    if (c) return c;
    return (b.iv.a + b.iv.d + b.iv.s) - (a.iv.a + a.iv.d + a.iv.s);
  });

  const info = BUCKET_INFO[_calcyBucket];
  const head = info
    ? `<div class="iv-note">${info.label} — ${info.desc}. ${list.length}마리.</div>`
    : `<div class="stat">${list.length}마리</div>`;

  let html = head;
  html += `<table><thead><tr>
    <th>Dex</th><th>포켓몬</th><th>속성</th><th>IV</th><th>합계</th><th>Lv</th><th>CP</th><th>판단</th>
  </tr></thead><tbody>`;

  let prevKo = null, sameKoCount = 0;
  for (const r of list.slice(0, 800)) {
    const sp = DATA.species[r.sid];
    const ivSum = r.iv.a + r.iv.d + r.iv.s;
    const ivPct = (ivSum / 45 * 100).toFixed(0);
    const top = r.decisions[0];
    // 같은 종 그룹 표시 (라인 사이 구분)
    const sameSpecies = (r.ko === prevKo);
    if (!sameSpecies) {
      sameKoCount = list.filter(x => x.ko === r.ko).length;
      prevKo = r.ko;
    }
    const dupTag = sameKoCount > 1 ? `<small class="muted">×${sameKoCount}</small>` : '';
    const cpEst = sp?.max_cp ? sp.max_cp : 0;
    html += `<tr ${sameSpecies ? 'style="background:#fafafa"' : ''}>
      <td class="num">${String(r.dex).padStart(3,'0')}</td>
      <td>${sp ? nameKo(sp) : '<b>'+r.ko+'</b>'}${!sameSpecies?dupTag:''}<br><span class="en">${r.en}</span>${r.isLucky?' 🍀':''}</td>
      <td>${(r.types||[]).map(badge).join(' ')}</td>
      <td class="num"><b>${r.iv.a}/${r.iv.d}/${r.iv.s}</b></td>
      <td class="num">${ivSum}<small class="muted">/45 (${ivPct}%)</small></td>
      <td class="num">${r.level}</td>
      <td class="num"><small class="muted">~${cpEst.toLocaleString()}</small></td>
      <td><b>${top.text}</b><br><small class="muted">${top.why || ''}</small></td>
    </tr>`;
  }
  html += `</tbody></table>`;
  if (list.length > 800) html += `<div class="muted">+ ${list.length - 800} 더 있음</div>`;
  document.getElementById('calcy-result').innerHTML = html;
}

// ─── 팀 렌더 헬퍼 — 한 마리 row
function _teamRow(m, i, extraCols) {
  const r = m.r;
  const sp = DATA.species[r.sid];
  const lucky = r.isLucky ? ' 🍀' : '';
  return `<tr>
    <td class="rank">${i+1}</td>
    <td>${sp ? nameKo(sp) : r.ko}<br><span class="en">${r.en}</span>${lucky}</td>
    <td>${(r.types||[]).map(badge).join(' ')}</td>
    <td class="num"><b>${r.iv.a}/${r.iv.d}/${r.iv.s}</b></td>
    ${extraCols(m)}
  </tr>`;
}

// 🏟️ 현재 레이드 베스트 6 — 보스별
function renderTeamRaidCurrent() {
  if (!_myTeams || !Object.keys(_myTeams.bossTeams).length) {
    return '<div class="empty">박스에 현재 레이드 보스 카운터가 없음</div>';
  }
  let html = `<div class="iv-note">${BUCKET_INFO.team_raid_current.label} — ${BUCKET_INFO.team_raid_current.desc}</div>`;
  for (const bt of Object.values(_myTeams.bossTeams)) {
    const b = bt.boss;
    html += `<div class="boss-head">
      <h3>${b.boss_ko} <span class="en">/ ${b.boss_en}</span></h3>
      <span>${(b.boss_types||[]).map(badge).join(' ')}</span>
      <span class="weak">약점: ${multBadges(b.boss_weak||{})||'없음'}</span>
      <span class="muted">[${b.tier_ko}]</span>
    </div>`;
    html += `<table><thead><tr><th>#</th><th>포켓몬</th><th>속성</th><th>IV</th><th>랭크</th></tr></thead><tbody>`;
    bt.team.forEach((m, i) => {
      html += _teamRow(m, i, mm => `<td class="num">#${mm.raidRank}</td>`);
    });
    html += `</tbody></table>`;
  }
  return html;
}

// 🌈 속성별 레이드 Top 6 — 18 속성 매트릭스
function renderTeamRaidType() {
  if (!_myTeams) return '<div class="empty">데이터 없음</div>';
  const TYPES = ['fire','water','grass','electric','ice','fighting','poison','ground',
                 'flying','psychic','bug','rock','ghost','dragon','dark','steel','fairy','normal'];
  let html = `<div class="iv-note">${BUCKET_INFO.team_raid_type.label} — ${BUCKET_INFO.team_raid_type.desc}</div>`;
  html += `<table><thead><tr><th>속성</th><th>1위</th><th>2위</th><th>3위</th><th>4위</th><th>5위</th><th>6위</th></tr></thead><tbody>`;
  for (const t of TYPES) {
    const list = _myTeams.byType[t];
    if (!list || !list.length) continue;
    html += `<tr><td><b>${badge(t)} ${TYPES_KO[t]||t}</b></td>`;
    for (let i = 0; i < 6; i++) {
      const m = list[i];
      if (!m) { html += '<td class="muted">—</td>'; continue; }
      html += `<td><b>${m.r.ko}</b><br>
        <small><span class="muted">${m.r.iv.a}/${m.r.iv.d}/${m.r.iv.s}</span>
        ${m.boss_ko ? `<br>vs ${m.boss_ko} #${m.raidRank}` : ''}</small></td>`;
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

// ⚔️ / 🛡️ 슈퍼/하이퍼 베스트 6
function renderTeamLeague(code) {
  if (!_myTeams) return '<div class="empty">데이터 없음</div>';
  const list = _myTeams.leagueTeams[code] || [];
  const lbl = code === 'GL' ? '슈퍼리그 (CP1500)' : '하이퍼리그 (CP2500)';
  const info = BUCKET_INFO[code === 'GL' ? 'team_gl' : 'team_ul'];
  let html = `<div class="iv-note">${info.label} — ${info.desc}</div>`;
  if (!list.length) return html + '<div class="empty">박스에 ' + lbl + ' 후보가 없음</div>';
  html += `<h3 style="margin:10px 0 4px">${lbl}</h3>`;
  html += `<table><thead><tr><th>#</th><th>포켓몬</th><th>속성</th><th>IV</th><th>리그 #</th><th>매칭 %</th></tr></thead><tbody>`;
  list.forEach((m, i) => {
    html += _teamRow(m, i, mm => `<td class="num">#${mm.leagueRank}</td><td class="num">${mm.pct.toFixed(1)}%</td>`);
  });
  html += `</tbody></table>`;
  return html;
}

// 🥊 각종 컵 베스트 6 — 컵별로 펼침
function renderTeamCups() {
  if (!_myTeams) return '<div class="empty">데이터 없음</div>';
  const cups = _myTeams.cupTeams || {};
  const keys = Object.keys(cups).sort((a,b) =>
    (cups[b].list.length - cups[a].list.length) || cups[a].league_ko.localeCompare(cups[b].league_ko, 'ko'));
  let html = `<div class="iv-note">${BUCKET_INFO.team_cups.label} — ${BUCKET_INFO.team_cups.desc}</div>`;
  if (!keys.length) return html + '<div class="empty">박스에 어느 컵도 3마리 이상 모이지 않음</div>';
  for (const k of keys) {
    const ct = cups[k];
    html += `<h3 style="margin:14px 0 4px">🥊 ${ct.league_ko} <span class="en">(${ct.league_en})</span> <span class="muted">— ${ct.list.length}마리</span></h3>`;
    html += `<table><thead><tr><th>#</th><th>포켓몬</th><th>속성</th><th>IV</th><th>컵 #</th><th>매칭 %</th></tr></thead><tbody>`;
    ct.list.forEach((m, i) => {
      html += _teamRow(m, i, mm => `<td class="num">#${mm.cupRank}</td><td class="num">${mm.pct.toFixed(1)}%</td>`);
    });
    html += `</tbody></table>`;
  }
  return html;
}

// 🎯 내 박스 팀빌더 렌더 (예전 단일 화면 — 호환용 유지)
function renderMyTeams() {
  if (!_myTeams) return '<div class="empty">팀 데이터 없음 — 분석 다시 실행</div>';
  const tt = _myTeams;

  let html = `<div class="iv-note" style="background:#e0eaff;color:var(--pri3)">
    <b>🎯 내 박스 기준 베스트 팀</b> — 풀강 가정 시 어떤 6마리 팀 / PvP 픽이 되는지.
    원 박스에서 IV·랭크 기준으로 자동 선발.
  </div>`;

  // 1) 현재 레이드 보스별 추천 팀
  if (Object.keys(tt.bossTeams).length) {
    html += `<div class="section-h">⚔️ 현재 레이드 — 보스별 내 박스 추천 6마리</div>`;
    for (const bt of Object.values(tt.bossTeams)) {
      const b = bt.boss;
      html += `<div class="boss-head">
        <h3>${b.boss_ko} <span class="en">/ ${b.boss_en}</span></h3>
        <span>${(b.boss_types||[]).map(badge).join(' ')}</span>
        <span class="weak">약점: ${multBadges(b.boss_weak||{})||'없음'}</span>
        <span class="muted">[${b.tier_ko}]</span>
      </div>`;
      html += `<table><thead><tr><th>#</th><th>포켓몬</th><th>속성</th><th>IV</th><th>랭크</th></tr></thead><tbody>`;
      bt.team.forEach((m, i) => {
        const sp = DATA.species[m.r.sid];
        html += `<tr>
          <td class="rank">${i+1}</td>
          <td>${sp ? nameKo(sp) : m.r.ko}<br><span class="en">${m.r.en}</span>${m.r.isLucky?' 🍀':''}</td>
          <td>${(m.r.types||[]).map(badge).join(' ')}</td>
          <td class="num"><b>${m.r.iv.a}/${m.r.iv.d}/${m.r.iv.s}</b></td>
          <td class="num">#${m.raidRank}</td>
        </tr>`;
      });
      html += `</tbody></table>`;
    }
  }

  // 2) 리그별 박스 Top 6
  html += `<div class="section-h">🛡️ 메이저 리그 — 내 박스 Top 6 (종 중복 제거)</div>`;
  const LEAGUE_LBL = {GL: '슈퍼리그 (CP1500)', UL: '하이퍼리그 (CP2500)', ML: '마스터리그'};
  for (const code of ['GL', 'UL', 'ML']) {
    const list = tt.leagueTeams[code];
    if (!list || !list.length) continue;
    html += `<h3 style="margin:10px 0 4px">${LEAGUE_LBL[code]}</h3>`;
    html += `<table><thead><tr><th>#</th><th>포켓몬</th><th>속성</th><th>IV</th><th>리그 #</th><th>매칭 %</th></tr></thead><tbody>`;
    list.forEach((m, i) => {
      const sp = DATA.species[m.r.sid];
      html += `<tr>
        <td class="rank">${i+1}</td>
        <td>${sp ? nameKo(sp) : m.r.ko}<br><span class="en">${m.r.en}</span>${m.r.isLucky?' 🍀':''}</td>
        <td>${(m.r.types||[]).map(badge).join(' ')}</td>
        <td class="num"><b>${m.r.iv.a}/${m.r.iv.d}/${m.r.iv.s}</b></td>
        <td class="num">#${m.leagueRank}</td>
        <td class="num">${m.pct.toFixed(1)}%</td>
      </tr>`;
    });
    html += `</tbody></table>`;
  }

  // 3) 속성별 내 박스 Top 6
  html += `<div class="section-h">🌈 속성별 — 내 박스 레이드 어태커 Top 6</div>`;
  const TYPES = ['fire','water','grass','electric','ice','fighting','poison','ground',
                 'flying','psychic','bug','rock','ghost','dragon','dark','steel','fairy','normal'];
  html += `<table><thead><tr><th>속성</th><th>1위</th><th>2위</th><th>3위</th><th>4위</th><th>5위</th><th>6위</th></tr></thead><tbody>`;
  for (const t of TYPES) {
    const list = tt.byType[t];
    if (!list || !list.length) continue;
    html += `<tr><td><b>${badge(t)} ${TYPES_KO[t]||t}</b></td>`;
    for (let i = 0; i < 6; i++) {
      const m = list[i];
      if (!m) { html += '<td class="muted">—</td>'; continue; }
      html += `<td><b>${m.r.ko}</b><br>
        <small><span class="muted">${m.r.iv.a}/${m.r.iv.d}/${m.r.iv.s}</span>
        ${m.boss_ko ? `<br>vs ${m.boss_ko} #${m.raidRank}` : ''}</small></td>`;
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

// ⭐ 필드 추천 — 18 속성 전부 한 화면에
function renderFieldAll() {
  let html = `<div class="iv-note" style="background:#e8f5e9;color:#186118">
    <b>전설 없이 잡을 수 있는 레이드 어태커</b> — 야생/알/리서치/로켓에서 얻을 수 있는 종.
    100% IV Lv50 풀강 권장. 속성별 Top 6 + 매치업 + 추천 기술.
  </div>`;
  html += `<div class="stat">18 속성 전체 — 검색·속성 필터로 좁힐 수 있음</div>`;
  for (const t of ALL_TYPES) {
    const td = DATA.types[t];
    if (!td || !td.field_top6.length) continue;
    if (state.typeFilter && state.typeFilter !== t) continue;
    // 검색 매치 — 어떤 필드 픽이라도 hit 하면 표시
    if (state.q) {
      const hay = td.field_top6.map(f =>
        f.ko + ' ' + f.en + ' ' + (f.fast_ko||'') + ' ' + (f.fast_en||'') +
        ' ' + (f.charged_ko||'') + ' ' + (f.charged_en||'')).join(' ').toLowerCase();
      if (!hay.includes(state.q)) continue;
    }
    html += `<div class="section-h">${badge(t)} <b>${td.ko}</b> <span class="en">(${t}) — ${td.field_count}종 중 Top 6</span></div>`;
    html += `<table><thead><tr>
      <th>#</th><th>Dex</th><th>포켓몬</th><th>속성</th><th>만렙 CP<br><small>(100% Lv50)</small></th><th>획득처</th><th>최강 매치업</th><th>추천 기술</th>
    </tr></thead><tbody>`;
    td.field_top6.forEach((f, i) => {
      const sp = DATA.species[f.sid];
      const types = sp ? sp.types.map(badge).join(' ') : f.types.map(badge).join(' ');
      const acq = sp ? (sp.acquisition || []).map(a => `<span class="ovl ovl-cup">${a}</span>`).join(' ') : '';
      const cp = f.max_cp || sp?.max_cp || '—';
      const matchup = f.best_boss_ko
        ? `<b>vs ${f.best_boss_ko}</b><br><small class="muted">${f.best_boss_en} (${f.best_tier_ko}) #${f.rank_in_t || f.rank_any}</small>`
        : '<span class="muted">—</span>';
      const moves = moveSplitHtml(f.fast_ko, f.fast_en, f.charged_ko, f.charged_en);
      html += `<tr>
        <td class="rank">${i + 1}</td>
        <td class="num">${String(f.dex).padStart(3,'0')}</td>
        <td>${sp ? nameKo(sp) : '<b>'+f.ko+'</b>'}<br><span class="en">${f.en}</span></td>
        <td>${types}</td>
        <td class="num"><b>${cp.toLocaleString ? cp.toLocaleString() : cp}</b></td>
        <td>${acq}</td>
        <td>${matchup}</td>
        <td>${moves}</td>
      </tr>`;
    });
    html += `</tbody></table>`;
  }
  return html;
}

// 박사 송출 — 두 섹션 (송출 가능 / 메가 보관)
function renderTransfer() {
  const passes = (g) => {
    if (state.q) {
      const hay = (g.keep_ko + ' ' + g.keep_en + ' ' + (g.mega_ko||'') + ' ' + (g.mega_en||'') + ' ' +
                   g.members.map(m => m.ko + ' ' + m.en).join(' ')).toLowerCase();
      if (!hay.includes(state.q)) return false;
    }
    if (state.typeFilter) {
      return g.members.some(m => m.types.includes(state.typeFilter)) ||
             (g.mega_types || []).includes(state.typeFilter);
    }
    return true;
  };

  const xfer = (DATA.transfer_groups || []).filter(passes);
  const megaKeep = (DATA.mega_keep_groups || []).filter(passes);
  const megaPossible = (DATA.mega_possible_groups || []).filter(passes);

  let html = '';

  // ─── 섹션 1: 메가 진화 보관 ───
  if (megaKeep.length) {
    html += `<div class="iv-note" style="background:#fff3d9;color:var(--pri2)">
      <b>메가 진화 대비 보관</b> — 일반 형태는 안 쓰이지만 <b>메가/원시 형태가 핵심</b>이라
      베이스를 보관해야 메가 에너지로 변신 가능. 가족당 1마리 (가능하면 100% IV).
    </div>`;
    html += `<div class="section-h">메가 진화 대비 보관 — ${megaKeep.length} 가족</div>`;
    html += `<table><thead><tr>
      <th>Dex</th><th>보관할 베이스</th><th>활약하는 메가/원시</th><th>진화 메모</th>
    </tr></thead><tbody>`;
    for (const g of megaKeep) {
      html += `<tr>
        <td class="num">#${String(g.keep_dex).padStart(3,'0')}</td>
        <td>
          <b>${g.keep_ko}</b> <span class="en">/ ${g.keep_en}</span><br>
          <div class="muted" style="font-size:11px">100% IV 1마리 우선 보관</div>
        </td>
        <td>
          <b>${g.mega_ko || '—'}</b> <span class="en">/ ${g.mega_en || ''}</span><br>
          ${(g.mega_types || []).map(badge).join(' ')}
        </td>
        <td>${evoBadge(g.evo_kind, g.evo_note) || '<span class="muted">—</span>'}</td>
      </tr>`;
    }
    html += `</tbody></table>`;
  }

  // ─── 섹션 1.5: 메가 가능 — 추후 대비 보관 ───
  if (megaPossible.length) {
    html += `<div class="iv-note" style="background:#fff3d9;color:var(--pri2)">
      <b>메가 진화 가능 — 추후 대비 보관</b><br>
      현재 메가도 핵심은 아니지만 <b>메가 폼이 존재</b>. Niantic 이 언제든 메가 풀에 추가할 수 있어 베이스 1마리 보관 권장.
    </div>`;
    html += `<div class="section-h">메가 진화 가능 (대비 보관) — ${megaPossible.length} 가족</div>`;
    html += `<table><thead><tr>
      <th>Dex</th><th>보관할 베이스</th><th>가능한 메가 폼</th><th>진화 메모</th>
    </tr></thead><tbody>`;
    for (const g of megaPossible) {
      const keepMember = g.members.find(m => m.sid === g.keep_sid) || g.members[g.members.length - 1];
      const megaList = (g.mega_avail_kos || []).map(k => `<span class="ovl ovl-raid">${k}</span>`).join(' ');
      html += `<tr>
        <td class="num">#${String(g.keep_dex).padStart(3,'0')}</td>
        <td>
          <b>${g.keep_ko}</b> <span class="en">/ ${g.keep_en}</span><br>
          ${keepMember.types.map(badge).join(' ')}
          <div class="muted" style="font-size:11px">100% IV 1마리 보관</div>
        </td>
        <td>${megaList || '<span class="muted">—</span>'}</td>
        <td>${evoBadge(g.evo_kind, g.evo_note) || '<span class="muted">—</span>'}</td>
      </tr>`;
    }
    html += `</tbody></table>`;
  }

  // ─── 섹션 2: 박사 송출 가능 ───
  html += `<div class="iv-note">
    <b>박사 송출 가능</b> — 어떤 리그·컵·레이드·메가에도 안 쓰이는 가족.<br>
    메타 변동 대비 가족당 1마리 (최종 진화·100%·Lucky 우선) 보관 권장. 나머지는 송출 → 사탕.<br>
    교환 진화·버디·지역 한정 표시된 건 진화 자체가 어렵거나 가치가 있을 수 있으니 참고.
  </div>`;
  html += `<div class="section-h">박사 송출 가능 — ${xfer.length} 가족</div>`;
  html += `<table><thead><tr>
    <th>Dex</th><th>보관 (1마리)</th><th>송출 OK</th><th>진화 메모</th>
  </tr></thead><tbody>`;
  for (const g of xfer) {
    const keepMember = g.members.find(m => m.sid === g.keep_sid) || g.members[g.members.length - 1];
    const otherMembers = g.members.filter(m => m.sid !== g.keep_sid);
    const notes = [];
    if (g.evo_kind) notes.push(evoBadge(g.evo_kind, g.evo_note));
    html += `<tr>
      <td class="num">#${String(g.keep_dex).padStart(3,'0')}</td>
      <td>
        <b>${g.keep_ko}</b> <span class="en">/ ${g.keep_en}</span><br>
        ${keepMember.types.map(badge).join(' ')}
      </td>
      <td>
        ${otherMembers.length === 0
          ? '<span class="muted">진화 없음</span>'
          : otherMembers.map(m => {
              const cls = m.is_shadow ? 'ovl ovl-raid' : 'ovl ovl-cup';
              return `<span class="${cls}">${m.ko}${m.is_shadow?' (쉐)':''}</span>`;
            }).join(' ')
        }
      </td>
      <td>${notes.length ? notes.join(' ') : '<span class="muted">—</span>'}</td>
    </tr>`;
  }
  html += `</tbody></table>`;
  return html;
}

// 레이드 — 보스별 그룹 + 보스 약점 + 카운터 Top 8
function renderRaidsView() {
  const tierOrder = ['T5','T5sh','Mega','MegaT5','UB','Elite',
                     'Gmax','GmaxX','Dmax5','Dmax4','Dmax3','Dmax2','Dmax1',
                     'T5*','T5sh*','Mega*','MegaT5*','UB*',
                     'Gmax*','GmaxX*','Dmax5*','Dmax4*','Dmax3*'];
  const titles = {
    T5:'현재 5성', T5sh:'현재 쉐도우 5성', Mega:'현재 메가', MegaT5:'메가 5성',
    UB:'울트라비스트', Elite:'엘리트',
    Gmax:'거다이맥스', GmaxX:'거다이맥스 특수',
    Dmax5:'다이맥스 5성', Dmax4:'다이맥스 4성', Dmax3:'다이맥스 3성',
    Dmax2:'다이맥스 2성', Dmax1:'다이맥스 1성',
    'T5*':'예정 5성', 'T5sh*':'예정 쉐도우 5성', 'Mega*':'예정 메가',
    'MegaT5*':'예정 메가 5성', 'UB*':'예정 울트라비스트',
    'Gmax*':'예정 거다이맥스', 'GmaxX*':'예정 거다이맥스 특수',
    'Dmax5*':'예정 다이맥스 5성', 'Dmax4*':'예정 다이맥스 4성', 'Dmax3*':'예정 다이맥스 3성',
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
  // 활성 vs 과거 분리
  const activeCups = cupKeys.filter(k => !DATA.leagues[k].is_archive).sort();
  const archiveCups = cupKeys.filter(k => DATA.leagues[k].is_archive).sort();

  let html = `<div class="iv-note">
    컵 시즌 — CP cap 에 맞는 IV (1500 컵 → 슈퍼 IV).
    <b>과거 시즌 (archive)</b> 는 다시 열릴 수 있어 데이터 유지. 가족당 1마리는 보관 권장.
  </div>`;
  const renderBlock = (key) => {
    const lg = DATA.leagues[key];
    const cap = parseInt(key.split('_').pop()) || 1500;
    const entries = lg.entries.filter(e => {
      const sp = DATA.species[e.sid];
      return sp && speciesPasses(sp);
    });
    if (!entries.length) return '';
    const archiveTag = lg.is_archive ? ` <span class="ovl ovl-cup">과거 시즌</span>` : '';
    let h = `<div class="section-h">${lg.ko} <span class="en">(${lg.en}, CP ${cap})</span>${archiveTag}</div>`;
    h += `<table><thead><tr>
      <th>#</th><th>Dex</th><th>포켓몬</th><th>속성</th>
      <th>슈퍼 IV</th><th>하이퍼 IV</th><th>추천 기술</th><th>비고</th>
    </tr></thead><tbody>`;
    for (const e of entries) {
      const sp = DATA.species[e.sid];
      h += `<tr>
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
    h += `</tbody></table>`;
    return h;
  };

  let total = 0;
  if (activeCups.length) {
    html += `<h2 style="font-size:15px;margin:14px 0 6px">현재 시즌 컵 (${activeCups.length})</h2>`;
    for (const k of activeCups) { html += renderBlock(k); total++; }
  }
  if (archiveCups.length) {
    html += `<h2 style="font-size:15px;margin:20px 0 6px;color:var(--muted)">과거 시즌 컵 — archive (${archiveCups.length}, 다시 열릴 수 있음)</h2>`;
    for (const k of archiveCups) { html += renderBlock(k); total++; }
  }
  if (!total) return `<div class="empty">결과 없음</div>`;
  return html;
}

function render() {
  const main = document.getElementById('main');
  let html = '';
  if (state.tab === 'types') html = renderTypes();
  else if (state.tab === 'fieldtop') html = renderFieldTopGlance();
  else if (state.tab === 'field') html = renderFieldAll();
  else if (state.tab === 'gl') html = renderLeagueTab('GL', '슈퍼리그 (Great League)', GL_KEYS, {cap:30});
  else if (state.tab === 'ul') html = renderLeagueTab('UL', '하이퍼리그 (Ultra League)', UL_KEYS, {cap:30});
  else if (state.tab === 'ml') html = renderLeagueTab('ML', '마스터리그 (Master League)', ML_KEYS, {cap:30});
  else if (state.tab === 'raids') html = renderRaidsView();
  else if (state.tab === 'lc') html = renderLeagueTab('LC', '리틀컵 (Little)', LC_KEYS, {cap:25});
  else if (state.tab === 'cups') html = renderCups();
  else if (state.tab === 'transfer') html = renderTransfer();
  else if (state.tab === 'calcy') html = renderCalcy();
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
