"""
한글 + 영어 + 속성 상성 + 추천 기술 포함한 상세 마스터 리스트 생성.

출력:
  out/must_have.md            전체 (덱스 순 표)
  out/must_have_essentials.md 진짜 핵심 (덱스 순 상세 카드)
  out/raids_by_boss.md        보스별 카운터 (한글)
  out/by_league.md            리그/컵별 Top
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from type_chart import effectiveness, weaknesses_resistances, fmt_mult

ROOT = Path(__file__).parent
PVPOKE = ROOT / "data" / "pvpoke"
PB = ROOT / "data" / "pokebattler" / "counters"
TRANS_FILE = ROOT / "data" / "translations.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

PVP_TOP_N = 20        # 원래 15 → 20 (살짝만 넓힘)
RAID_TOP_N = 10       # 원래 8 → 10
ESSENTIAL_PVP_RANK = 5
ESSENTIAL_RAID_RANK = 5
MAJOR_LEAGUES_KEYS = {"all_1500", "all_2500", "all_10000"}
ESSENTIAL_RAID_TIERS = {"T5", "T5sh", "Mega", "MegaT5", "UB", "Elite"}

LEAGUE_KO = {
    "all_500":   ("리틀리그",        "Little"),
    "all_1500":  ("슈퍼리그",        "Great League"),
    "all_2500":  ("하이퍼리그",      "Ultra League"),
    "all_10000": ("마스터리그",      "Master League"),
    "premier_500":   ("프리미어 리틀",  "Premier Little"),
    "premier_1500":  ("프리미어 슈퍼",  "Premier Great"),
    "premier_2500":  ("프리미어 하이퍼", "Premier Ultra"),
    "premier_10000": ("프리미어 마스터", "Premier Master"),
    "little_500":    ("리틀컵",         "Little Cup"),
    "classic_500":   ("클래식 리틀",     "Classic Little"),
    "classic_1500":  ("클래식 슈퍼",     "Classic Great"),
    "classic_2500":  ("클래식 하이퍼",   "Classic Ultra"),
    "classic_10000": ("클래식 마스터",   "Classic Master"),
    "retro_1500":    ("레트로컵",       "Retro Cup"),
    "remix_1500":    ("리믹스컵",       "Remix Cup"),
    "fantasy_1500":  ("판타지컵",       "Fantasy Cup"),
    "jungle_1500":   ("정글컵",         "Jungle Cup"),
    "spring_1500":   ("스프링컵",       "Spring Cup"),
    "electric_1500": ("일렉트릭컵",     "Electric Cup"),
    "cosy_1500":     ("코지컵",         "Cosy Cup"),
    "spellcraft_1500": ("스펠크래프트컵", "Spellcraft Cup"),
    "equinox_1500":  ("이쿼녹스컵",     "Equinox Cup"),
    "maelstrom_1500": ("메일스트롬컵",  "Maelstrom Cup"),
    "naic2026_1500":   ("NAIC 2026",   "NAIC 2026"),
    "laic2025remix_1500": ("LAIC 2025", "LAIC 2025 Remix"),
    "bayou_1500":    ("베이유컵",       "Bayou Cup"),
    "bfretro_1500":  ("BF 레트로",      "BF Retro"),
    "bfretro_2500":  ("BF 레트로 하이퍼", "BF Retro Ultra"),
    "battlefrontiermaster_10000": ("BF 마스터", "Battle Frontier Master"),
    "catch_1500":    ("캐치컵",         "Catch Cup"),
    "chrono_1500":   ("크로노컵",       "Chrono Cup"),
    # ─── 과거 시즌 archive ───
    "kanto_1500":    ("관동컵",         "Kanto Cup"),
    "johto_1500":    ("성도컵",         "Johto Cup"),
    "hoenn_1500":    ("호연컵",         "Hoenn Cup"),
    "sinnoh_1500":   ("신오컵",         "Sinnoh Cup"),
    "unova_1500":    ("하나컵",         "Unova Cup"),
    "kalos_1500":    ("칼로스컵",       "Kalos Cup"),
    "alola_1500":    ("알로라컵",       "Alola Cup"),
    "galar_1500":    ("가라르컵",       "Galar Cup"),
    "paldea_1500":   ("팔데아컵",       "Paldea Cup"),
    "halloween_1500":("할로윈컵",       "Halloween Cup"),
    "holiday_1500":  ("홀리데이컵",     "Holiday Cup"),
    "summer_1500":   ("여름컵",         "Summer Cup"),
    "love_1500":     ("러브컵",         "Love Cup"),
    "valentine_1500":("발렌타인컵",     "Valentine Cup"),
    "evolution_1500":("진화컵",         "Evolution Cup"),
    "color_1500":    ("컬러컵",         "Color Cup"),
    "fossil_1500":   ("화석컵",         "Fossil Cup"),
    "psychic_1500":  ("에스퍼컵",       "Psychic Cup"),
    "mountain_1500": ("마운틴컵",       "Mountain Cup"),
    "sunshine_1500": ("선샤인컵",       "Sunshine Cup"),
    "willpower_1500":("의지컵",         "Willpower Cup"),
    "ferocity_1500": ("야성컵",         "Ferocity Cup"),
    "tinkerer_1500": ("팅커러컵",       "Tinkerer Cup"),
    "twilight_1500": ("황혼컵",         "Twilight Cup"),
    "kingdom_1500":  ("킹덤컵",         "Kingdom Cup"),
    "shore_1500":    ("쇼어컵",         "Shore Cup"),
    "frostlight_1500":("서리빛컵",      "Frostlight Cup"),
    "festival_1500": ("페스티벌컵",     "Festival Cup"),
    "vintage_1500":  ("빈티지컵",       "Vintage Cup"),
    "throwback_1500":("스로우백컵",     "Throwback Cup"),
    "championshipseries_1500": ("챔피언십 시리즈", "Championship Series"),
    # 단일 타입 컵
    "single-type-bug_1500":     ("벌레 단일컵",   "Single-Type Bug"),
    "single-type-dark_1500":    ("악 단일컵",     "Single-Type Dark"),
    "single-type-dragon_1500":  ("드래곤 단일컵", "Single-Type Dragon"),
    "single-type-electric_1500":("전기 단일컵",   "Single-Type Electric"),
    "single-type-fairy_1500":   ("페어리 단일컵", "Single-Type Fairy"),
    "single-type-fighting_1500":("격투 단일컵",   "Single-Type Fighting"),
    "single-type-fire_1500":    ("불꽃 단일컵",   "Single-Type Fire"),
    "single-type-flying_1500":  ("비행 단일컵",   "Single-Type Flying"),
    "single-type-ghost_1500":   ("고스트 단일컵", "Single-Type Ghost"),
    "single-type-grass_1500":   ("풀 단일컵",     "Single-Type Grass"),
    "single-type-ground_1500":  ("땅 단일컵",     "Single-Type Ground"),
    "single-type-ice_1500":     ("얼음 단일컵",   "Single-Type Ice"),
    "single-type-normal_1500":  ("노말 단일컵",   "Single-Type Normal"),
    "single-type-poison_1500":  ("독 단일컵",     "Single-Type Poison"),
    "single-type-psychic_1500": ("에스퍼 단일컵", "Single-Type Psychic"),
    "single-type-rock_1500":    ("바위 단일컵",   "Single-Type Rock"),
    "single-type-steel_1500":   ("강철 단일컵",   "Single-Type Steel"),
    "single-type-water_1500":   ("물 단일컵",     "Single-Type Water"),
    # 대회
    "naic2024_1500": ("NAIC24",     "NAIC 2024"),
    "naic2025_1500": ("NAIC25",     "NAIC 2025"),
    "laic2024_1500": ("LAIC24",     "LAIC 2024"),
    "laic2025_1500": ("LAIC25",     "LAIC 2025"),
    "laic2026_1500": ("LAIC26",     "LAIC 2026"),
    "euic2024_1500": ("EUIC24",     "EUIC 2024"),
    "euic2025_1500": ("EUIC25",     "EUIC 2025"),
    "euic2026_1500": ("EUIC26",     "EUIC 2026"),
    "ocic2024_1500": ("OCIC24",     "OCIC 2024"),
    "ocic2025_1500": ("OCIC25",     "OCIC 2025"),
    "ocic2026_1500": ("OCIC26",     "OCIC 2026"),
    "worlds2024_1500": ("월드24",    "Worlds 2024"),
    "worlds2025_1500": ("월드25",    "Worlds 2025"),
    "worlds2026_1500": ("월드26",    "Worlds 2026"),
}

TIER_LABEL = {
    "RAID_LEVEL_5": ("5성", "T5"),
    "RAID_LEVEL_5_FUTURE": ("5성 (예정)", "T5*"),
    "RAID_LEVEL_5_SHADOW": ("쉐도우 5성", "T5sh"),
    "RAID_LEVEL_5_SHADOW_FUTURE": ("쉐도우 5성 (예정)", "T5sh*"),
    "RAID_LEVEL_MEGA": ("메가", "Mega"),
    "RAID_LEVEL_MEGA_FUTURE": ("메가 (예정)", "Mega*"),
    "RAID_LEVEL_MEGA_5": ("메가 5성", "MegaT5"),
    "RAID_LEVEL_MEGA_5_FUTURE": ("메가 5성 (예정)", "MegaT5*"),
    "RAID_LEVEL_ULTRA_BEAST": ("울트라비스트", "UB"),
    "RAID_LEVEL_ULTRA_BEAST_FUTURE": ("울트라비스트 (예정)", "UB*"),
    "RAID_LEVEL_ELITE": ("엘리트", "Elite"),
    # 다이맥스
    "RAID_LEVEL_1_MAX": ("다이맥스 1성", "Dmax1"),
    "RAID_LEVEL_2_MAX": ("다이맥스 2성", "Dmax2"),
    "RAID_LEVEL_3_MAX": ("다이맥스 3성", "Dmax3"),
    "RAID_LEVEL_3_MAX_FUTURE": ("다이맥스 3성 (예정)", "Dmax3*"),
    "RAID_LEVEL_4_MAX": ("다이맥스 4성", "Dmax4"),
    "RAID_LEVEL_4_MAX_FUTURE": ("다이맥스 4성 (예정)", "Dmax4*"),
    "RAID_LEVEL_5_MAX": ("다이맥스 5성", "Dmax5"),
    "RAID_LEVEL_5_MAX_FUTURE": ("다이맥스 5성 (예정)", "Dmax5*"),
    # 거다이맥스 (T6_MAX)
    "RAID_LEVEL_6_MAX": ("거다이맥스", "Gmax"),
    "RAID_LEVEL_6_MAX_FUTURE": ("거다이맥스 (예정)", "Gmax*"),
    "RAID_LEVEL_6_5_MAX": ("거다이맥스 (특수)", "GmaxX"),
    "RAID_LEVEL_6_5_MAX_FUTURE": ("거다이맥스 (예정·특수)", "GmaxX*"),
}

# 폼 모디파이어 영→한
FORM_KO = {
    "Mega": "메가", "Mega X": "메가 X", "Mega Y": "메가 Y",
    "Mega Z": "메가 Z",
    "Shadow": "쉐도우",
    "Alolan": "알로라", "Galarian": "가라르",
    "Hisuian": "히스이", "Paldean": "팔데아",
    "Origin": "오리진", "Altered": "어나더",
    "Therian": "영물", "Incarnate": "화신",
    "Primal": "원시",
    "Crowned Sword": "검의 왕", "Crowned Shield": "방패의 왕", "Hero": "용사",
    "Black": "블랙", "White": "화이트",
    "Sky": "스카이", "Land": "랜드",
    "Ultimate": "얼티밋", "Apex": "아펙스",
    "Single Strike": "일격의 일족", "Rapid Strike": "연격의 일족",
    "Ice Rider": "백마 라이더", "Shadow Rider": "흑마 라이더",
    "Ice": "아이스", "Eternal": "영원",
    "Dawn Wings": "새벽날개", "Dusk Mane": "황혼갈기",
    "Aria": "보이스", "Pirouette": "스텝",
    "Confined": "굴레씌움", "Unbound": "굴레풀림",
    "Ordinary": "평상시", "Resolute": "각오",
    "Standard": "보통", "Zen": "달마",
    "Plant": "초목", "Sandy": "모래", "Trash": "쓰레기",
    "Midday": "한낮", "Midnight": "한밤", "Dusk": "황혼",
    "Defense": "디펜스", "Speed": "스피드", "Attack": "어택",
    "Complete": "퍼펙트", "C": "10%",
    "Bug": "벌레", "Dark": "악", "Dragon": "드래곤", "Electric": "전기",
    "Fairy": "페어리", "Fighting": "격투", "Fire": "불꽃", "Flying": "비행",
    "Ghost": "고스트", "Grass": "풀", "Ground": "땅", "Ice (Type)": "얼음",
    "Normal": "노말", "Poison": "독", "Psychic": "에스퍼", "Rock": "바위",
    "Steel": "강철", "Water": "물",
    "Neutral": "중립",
}


def load_translations() -> dict:
    return json.loads(TRANS_FILE.read_text(encoding="utf-8"))


def load_gamemaster() -> tuple[dict[str, dict], dict[str, str]]:
    gm = json.loads((PVPOKE / "_gamemaster.json").read_text(encoding="utf-8"))
    species: dict[str, dict] = {}
    for p in gm["pokemon"]:
        species[p["speciesId"]] = {
            "dex": p["dex"],
            "name_en": prettify_name(p["speciesName"]),
            "types": [t for t in p.get("types", []) if t and t != "none"],
        }
    moves = {m["moveId"]: m["name"] for m in gm["moves"]}
    for mid, name in list(moves.items()):
        squashed = mid.replace("_", "")
        if squashed not in moves:
            moves[squashed] = name
    moves["HIDDEN_POWER_FAST"] = "Hidden Power"
    moves["HIDDEN_POWER"] = "Hidden Power"
    return species, moves


def prettify_name(raw: str) -> str:
    if "_" not in raw:
        return raw
    head, _, tail = raw.partition("_")
    return f"{head} ({tail.replace('_', ' ').title()})"


PB_ALIAS = {
    "giratina_shadow": "giratina_altered_shadow",
    "giratina": "giratina_altered",
    "shaymin": "shaymin_land",
    "deoxys": "deoxys_normal",
    "wormadam": "wormadam_plant",
    "burmy": "burmy_plant",
    "tornadus": "tornadus_incarnate",
    "thundurus": "thundurus_incarnate",
    "landorus": "landorus_incarnate",
    "enamorus": "enamorus_incarnate",
    "meloetta": "meloetta_aria",
    "keldeo": "keldeo_ordinary",
    "hoopa": "hoopa_confined",
    "lycanroc": "lycanroc_midday",
    "darmanitan": "darmanitan_standard",
    "darmanitan_shadow": "darmanitan_standard_shadow",
    "tornadus_shadow": "tornadus_incarnate_shadow",
    "thundurus_shadow": "thundurus_incarnate_shadow",
    "landorus_shadow": "landorus_incarnate_shadow",
    "enamorus_shadow": "enamorus_incarnate_shadow",
    "overqwil_shadow": "overqwil",
}


def pb_to_pvpoke_id(pb_id: str) -> str:
    s = pb_id.lower()
    s = re.sub(r"_form$", "", s)
    return PB_ALIAS.get(s, s)


def move_name_en(moves: dict[str, str], mid: str | None) -> str:
    if not mid:
        return ""
    if mid in moves:
        return moves[mid]
    if mid.endswith("_FAST"):
        return moves.get(mid[:-5], mid)
    return mid


def move_name_pair(moves_en: dict[str, str], moves_ko: dict[str, dict],
                   mid: str | None) -> tuple[str, str]:
    """(한글, 영어) 쌍."""
    if not mid:
        return "", ""
    en = move_name_en(moves_en, mid)
    # pvpoke move id 그대로, _FAST 제거 후 lookup
    key = mid[:-5] if mid.endswith("_FAST") else mid
    ko_entry = moves_ko.get(key) or {}
    ko = ko_entry.get("ko", "")
    return ko, en


def species_ko_name(dex: int, name_en: str, trans: dict) -> str:
    """한글 이름 (폼 모디파이어 한글로 변환). 없으면 영어 그대로."""
    sp = trans.get("species", {}).get(str(dex)) or {}
    base_ko = sp.get("ko", "")
    if not base_ko:
        return name_en

    # name_en 에서 폼 정보 추출. e.g. "Venusaur (Mega) (Shadow)" → ["Mega", "Shadow"]
    forms = re.findall(r"\(([^)]+)\)", name_en)
    if not forms:
        return base_ko
    forms_ko = [FORM_KO.get(f, f) for f in forms]
    return f"{base_ko} ({') ('.join(forms_ko)})"


def types_str(types: list[str], trans: dict) -> str:
    types_ko = trans.get("types_ko", {})
    parts = [f"{types_ko.get(t, t)} ({t})" for t in types]
    return " · ".join(parts)


def matchup_str(types: list[str], trans: dict) -> tuple[str, str]:
    """약점/저항 한글 문자열."""
    if not types:
        return "—", "—"
    types_ko = trans.get("types_ko", {})
    weak, resist = weaknesses_resistances(types)

    def fmt_dict(d: dict[str, float]) -> str:
        items = sorted(d.items(), key=lambda x: (-x[1], x[0]))
        return ", ".join(f"{types_ko.get(t, t)} {fmt_mult(m)}" for t, m in items)

    return fmt_dict(weak), fmt_dict(resist)


def collect_pvp(species: dict[str, dict], moves: dict[str, str],
                trans: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    moves_ko = trans["moves"]
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
        for rank, mon in enumerate(data[:PVP_TOP_N], 1):
            sid = mon.get("speciesId")
            if not sid:
                continue
            mset = mon.get("moveset") or []
            move_pairs = [move_name_pair(moves, moves_ko, m) for m in mset if m]
            move_str_ko = " / ".join(p[0] or p[1] for p in move_pairs)
            move_str_en = " / ".join(p[1] for p in move_pairs)
            out[sid].append({
                "league_key": league_key,
                "league_ko": ko, "league_en": en,
                "rank": rank,
                "score": mon.get("score") or mon.get("rating"),
                "moves_ko": move_str_ko,
                "moves_en": move_str_en,
            })
    return out


def collect_raid(species: dict[str, dict], moves: dict[str, str],
                 trans: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    moves_ko = trans["moves"]
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
                    fast_ko, fast_en = move_name_pair(moves, moves_ko, d_bm.get("move1"))
                    chg_ko,  chg_en  = move_name_pair(moves, moves_ko, d_bm.get("move2"))
                    movesets[pid_pv] = (fast_ko, fast_en, chg_ko, chg_en)

        PENALTY = 999
        avg: dict[str, float] = {}
        for pid_pv, rs in ranks.items():
            missing = n - len(rs)
            avg[pid_pv] = (sum(rs) + missing * PENALTY) / n
        ranked = sorted(avg.items(), key=lambda x: x[1])[:RAID_TOP_N]
        for new_rank, (pid_pv, _) in enumerate(ranked, 1):
            fk, fe, ck, ce = movesets[pid_pv]
            mv_ko = f"{fk or fe} / {ck or ce}".strip(" /")
            mv_en = f"{fe} / {ce}".strip(" /")
            out[pid_pv].append({
                "boss_ko": boss_ko, "boss_en": boss_en, "boss_dex": boss_dex,
                "tier_ko": tier_ko, "tier_en": tier_en,
                "rank": new_rank,
                "moves_ko": mv_ko, "moves_en": mv_en,
            })
    return out


# ────────── 출력 렌더러 ──────────

def render_master_table(species, pvp, raid, trans) -> str:
    all_ids = set(pvp) | set(raid)
    rows = []
    for sid in all_ids:
        info = species.get(sid)
        if not info:
            rows.append((9999, sid, sid, "", []))
            continue
        ko = species_ko_name(info["dex"], info["name_en"], trans)
        rows.append((info["dex"], sid, ko, info["name_en"], info["types"]))
    rows.sort(key=lambda x: (x[0], x[1]))

    lines = [
        "# 포켓몬고 마스터 리스트 (한글)",
        "",
        f"_PvP: 각 리그/컵 Top {PVP_TOP_N} / Raid: 보스별 카운터 Top {RAID_TOP_N}_  ",
        f"총 {len(rows)}종 (덱스 번호 순)",
        "",
        "| Dex | 한글 | 영어 | 속성 | PvP 활약 | 레이드 활약 | 추천 기술 |",
        "|---|---|---|---|---|---|---|",
    ]
    types_ko = trans.get("types_ko", {})
    for dex, sid, ko, en, types in rows:
        type_short = "/".join(types_ko.get(t, t) for t in types) or "?"
        type_en = "/".join(types) or "?"
        pvp_e = sorted(pvp.get(sid, []), key=lambda x: x["rank"])
        raid_e = sorted(raid.get(sid, []), key=lambda x: x["rank"])
        pvp_str = ", ".join(f"{e['league_ko']}#{e['rank']}" for e in pvp_e[:5])
        seen = set()
        raid_parts = []
        for e in raid_e:
            if e["boss_ko"] in seen:
                continue
            seen.add(e["boss_ko"])
            raid_parts.append(f"{e['boss_ko']}#{e['rank']}({e['tier_ko']})")
            if len(raid_parts) >= 5:
                break
        raid_str = ", ".join(raid_parts)
        moves = ""
        src = pvp_e[0] if pvp_e else (raid_e[0] if raid_e else None)
        if src:
            moves = f"{src['moves_ko']} ({src['moves_en']})"
        def esc(s): return s.replace("|", r"\|") if isinstance(s, str) else s
        lines.append(
            f"| {dex:03d} | {esc(ko)} | {esc(en)} | {type_short} ({type_en}) | "
            f"{esc(pvp_str)} | {esc(raid_str)} | {esc(moves)} |"
        )
    return "\n".join(lines) + "\n"


def render_essentials_cards(species, pvp, raid, trans) -> str:
    """덱스 순 상세 카드. 핵심만."""
    pvp_e: dict[str, list[dict]] = {}
    raid_e: dict[str, list[dict]] = {}
    for sid, ents in pvp.items():
        keep = [e for e in ents if e["league_key"] in MAJOR_LEAGUES_KEYS
                and e["rank"] <= ESSENTIAL_PVP_RANK]
        if keep:
            pvp_e[sid] = keep
    for sid, ents in raid.items():
        keep = [e for e in ents if e["tier_en"] in ESSENTIAL_RAID_TIERS
                and e["rank"] <= ESSENTIAL_RAID_RANK]
        if keep:
            raid_e[sid] = keep

    all_ids = set(pvp_e) | set(raid_e)
    rows = []
    for sid in all_ids:
        info = species.get(sid)
        if not info:
            continue
        rows.append((info["dex"], sid, info))
    rows.sort(key=lambda x: (x[0], x[1]))

    lines = [
        "# 포켓몬고 키워야 할 핵심 포켓몬 (한글 상세)",
        "",
        f"_PvP: 슈퍼/하이퍼/마스터 Top {ESSENTIAL_PVP_RANK} / "
        f"Raid: 현재 5성·메가·UB·엘리트 Top {ESSENTIAL_RAID_RANK}_  ",
        f"총 {len(rows)}종 (덱스 번호 순)",
        "",
    ]
    types_ko = trans.get("types_ko", {})
    for dex, sid, info in rows:
        ko = species_ko_name(dex, info["name_en"], trans)
        types = info["types"]
        type_str = " · ".join(f"{types_ko.get(t, t)} ({t})" for t in types)
        weak_str, resist_str = matchup_str(types, trans)

        lines.append(f"## #{dex:03d} {ko} / {info['name_en']}")
        lines.append("")
        lines.append(f"- **속성**: {type_str}")
        lines.append(f"- **약점**: {weak_str}")
        lines.append(f"- **저항**: {resist_str}")

        pvp_list = pvp_e.get(sid, [])
        raid_list = raid_e.get(sid, [])

        if pvp_list:
            lines.append("- **PvP 활약**:")
            for e in pvp_list:
                lines.append(
                    f"  - {e['league_ko']} ({e['league_en']}) "
                    f"#{e['rank']} — 추천기술: **{e['moves_ko']}** "
                    f"_({e['moves_en']})_"
                )

        if raid_list:
            lines.append("- **레이드 활약**:")
            for e in raid_list:
                lines.append(
                    f"  - vs **{e['boss_ko']}** _({e['boss_en']})_ "
                    f"[{e['tier_ko']}] #{e['rank']} — "
                    f"추천기술: **{e['moves_ko']}** _({e['moves_en']})_"
                )
        lines.append("")

    return "\n".join(lines) + "\n"


def render_per_boss(species, moves_en, trans) -> str:
    moves_ko = trans["moves"]
    by_boss: dict = {}
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
                    fk, fe = move_name_pair(moves_en, moves_ko, d_bm.get("move1"))
                    ck, ce = move_name_pair(moves_en, moves_ko, d_bm.get("move2"))
                    movesets[pid_pv] = (fk, fe, ck, ce)
        PENALTY = 999
        avg = {pid: (sum(rs) + (n - len(rs)) * PENALTY) / n for pid, rs in ranks.items()}
        ranked = sorted(avg.items(), key=lambda x: x[1])[:RAID_TOP_N]
        rows = []
        for new_rank, (pid, _) in enumerate(ranked, 1):
            cinfo = species.get(pid, {})
            cdex = cinfo.get("dex", 0)
            cen = cinfo.get("name_en", pid)
            cko = species_ko_name(cdex, cen, trans) if cdex else pid
            fk, fe, ck, ce = movesets[pid]
            rows.append((new_rank, cko, cen, fk or fe, fe, ck or ce, ce))
        by_boss[(tier_en, boss_dex, boss_ko, boss_en, tuple(boss_types))] = rows

    tier_order = ["T5", "T5sh", "Mega", "MegaT5", "UB", "Elite", "T3", "T1",
                  "T5*", "T5sh*", "Mega*", "MegaT5*", "UB*"]
    sec_titles = {
        "T5": "현재 5성 레이드", "T5sh": "현재 쉐도우 5성", "Mega": "현재 메가",
        "MegaT5": "메가 5성", "UB": "울트라비스트", "Elite": "엘리트",
        "T3": "현재 3성", "T1": "현재 1성",
        "T5*": "예정 5성", "T5sh*": "예정 쉐도우 5성", "Mega*": "예정 메가",
        "MegaT5*": "예정 메가 5성", "UB*": "예정 울트라비스트",
    }
    grouped: dict[str, list] = defaultdict(list)
    for k, v in by_boss.items():
        grouped[k[0]].append((k[1], k[2], k[3], k[4], v))

    types_ko = trans.get("types_ko", {})
    lines = [f"# 레이드 보스별 카운터 Top {RAID_TOP_N} (한글)", ""]
    for tier in tier_order:
        bosses = grouped.get(tier) or []
        if not bosses:
            continue
        bosses.sort(key=lambda x: (x[0] if isinstance(x[0], int) else 9999, x[1]))
        lines.append(f"\n## {sec_titles.get(tier, tier)}\n")
        for dex, ko, en, types, rows in bosses:
            type_str = " · ".join(types_ko.get(t, t) for t in types) or "?"
            type_en = "/".join(types) if types else "?"
            weak_str, _ = matchup_str(list(types), trans)
            lines.append(f"\n### #{dex:03d} {ko} / {en}" if isinstance(dex, int) and dex < 9999
                         else f"\n### {ko}")
            lines.append("")
            lines.append(f"- **속성**: {type_str} ({type_en})")
            lines.append(f"- **약점 노려서 공격**: {weak_str}")
            lines.append("")
            lines.append("| # | 카운터 (한글) | (영어) | 추천 기술 (한글) | (영어) |")
            lines.append("|---|---|---|---|---|")
            for rank, cko, cen, fk, fe, ck, ce in rows:
                lines.append(f"| {rank} | {cko} | {cen} | {fk} / {ck} | {fe} / {ce} |")
    return "\n".join(lines) + "\n"


def render_by_league(species, pvp, trans) -> str:
    """리그/컵별로 그룹핑한 Top 리스트."""
    types_ko = trans.get("types_ko", {})
    by_league: dict[str, list[tuple[int, str, dict]]] = defaultdict(list)
    for sid, ents in pvp.items():
        info = species.get(sid)
        if not info:
            continue
        for e in ents:
            by_league[e["league_key"]].append((e["rank"], sid, e, info))

    lines = [f"# 리그/컵별 Top {PVP_TOP_N} (한글)", ""]
    # 메이저 먼저
    order = ["all_1500", "all_2500", "all_10000", "all_500"]
    rest = sorted(k for k in by_league if k not in order)
    for key in order + rest:
        ents = by_league.get(key)
        if not ents:
            continue
        ko, en = LEAGUE_KO.get(key, (key, key))
        lines.append(f"\n## {ko} ({en})\n")
        lines.append("| # | Dex | 한글 | 영어 | 속성 | 추천 기술 (한글) | (영어) |")
        lines.append("|---|---|---|---|---|---|---|")
        ents.sort(key=lambda x: x[0])
        for rank, sid, e, info in ents:
            ko_name = species_ko_name(info["dex"], info["name_en"], trans)
            type_short = "/".join(types_ko.get(t, t) for t in info["types"]) or "?"
            lines.append(
                f"| {rank} | {info['dex']:03d} | {ko_name} | {info['name_en']} | "
                f"{type_short} | {e['moves_ko']} | {e['moves_en']} |"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    trans = load_translations()
    print(f"[trans] 종 {len(trans['species'])} / 기술 {len(trans['moves'])}")

    species, moves = load_gamemaster()
    print(f"[gm] {len(species)} 종, {len(moves)} 기술")

    pvp = collect_pvp(species, moves, trans)
    print(f"[pvp] {len(pvp)} 종이 PvP Top {PVP_TOP_N}")

    raid = collect_raid(species, moves, trans)
    print(f"[raid] {len(raid)} 종이 레이드 Top {RAID_TOP_N}")

    md = render_master_table(species, pvp, raid, trans)
    (OUT / "must_have.md").write_text(md, encoding="utf-8")
    print(f"[out] must_have.md ({len(md.splitlines())}줄)")

    md_e = render_essentials_cards(species, pvp, raid, trans)
    (OUT / "must_have_essentials.md").write_text(md_e, encoding="utf-8")
    print(f"[out] must_have_essentials.md ({len(md_e.splitlines())}줄)")

    md_b = render_per_boss(species, moves, trans)
    (OUT / "raids_by_boss.md").write_text(md_b, encoding="utf-8")
    print(f"[out] raids_by_boss.md ({len(md_b.splitlines())}줄)")

    md_l = render_by_league(species, pvp, trans)
    (OUT / "by_league.md").write_text(md_l, encoding="utf-8")
    print(f"[out] by_league.md ({len(md_l.splitlines())}줄)")


if __name__ == "__main__":
    main()
