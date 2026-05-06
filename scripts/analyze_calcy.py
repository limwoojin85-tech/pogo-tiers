"""
Calcy IV CSV 일괄 분석 — 로컬 Python 으로 사이트의 Calcy 분석 탭 로직 그대로 실행.
출력: out/box_analysis.html (사이트와 같은 형태)
      out/box_analysis.csv (스프레드시트용 결정 리스트)
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
CSV_PATH = ROOT / "scripts" / "calcy_adb" / "history.csv"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)

# 사이트 빌드 데이터에서 species 메타 + rank 정보 가져오기
import re as _re
_html = (ROOT / "out" / "index.html").read_text(encoding="utf-8")
_m = _re.search(
    r'<script id="data" type="application/json">(.+?)</script>',
    _html, _re.DOTALL
)
DATA = json.loads(_m.group(1).replace("<\\/", "</"))

# CPM 테이블
CPM = DATA["cpm"]

# 그룹 키들
GL_KEYS = {"all_1500", "premier_1500", "classic_1500"}
UL_KEYS = {"all_2500", "premier_2500", "classic_2500"}
ML_KEYS = {"all_10000", "premier_10000", "classic_10000"}
LC_KEYS = {"all_500", "little_500", "premier_500", "classic_500"}


# ───── 이름 → species_id 매칭 ─────
# species_out + transfer_groups + mega_keep + mega_possible 의 모든 멤버 포함
NAME_INDEX: dict[str, str] = {}

def _add(name: str, sid: str):
    if not name:
        return
    n = name.lower().strip()
    NAME_INDEX.setdefault(n, sid)
    # 괄호 안 제거 — 베이스만
    base = re.sub(r"\s*\([^)]*\)", "", name).strip().lower()
    if base and base != n:
        NAME_INDEX.setdefault(base, sid)
    # 괄호 만 제거 — form 텍스트 유지 ("깝질무 (동쪽바다)" → "깝질무 동쪽바다")
    no_p = re.sub(r"[()]", " ", name)
    no_p = re.sub(r"\s+", " ", no_p).strip().lower()
    if no_p != n and no_p != base:
        NAME_INDEX.setdefault(no_p, sid)

# 1) species_out 모든 종
for sp in DATA["species"].values():
    _add(sp.get("ko", ""), sp["id"])
    _add(sp.get("en", ""), sp["id"])
    _add(sp.get("id", ""), sp["id"])
    for k in (sp.get("chain_ko") or []) + (sp.get("chain_en") or []):
        _add(k, sp["id"])

# 2) 가족 그룹 멤버들 (송출/메가 보관/메가 가능) — species_out 에 없는 종 포함
for group_key in ("transfer_groups", "mega_keep_groups", "mega_possible_groups"):
    for g in DATA.get(group_key) or []:
        for m in g.get("members", []):
            _add(m.get("ko", ""), m["sid"])
            _add(m.get("en", ""), m["sid"])
            _add(m["sid"], m["sid"])

# 3) pvpoke gamemaster + PokeAPI 한글 번역 — fallback (분류 없는 종)
_gm = json.loads((ROOT / "data" / "pvpoke" / "_gamemaster.json").read_text(encoding="utf-8"))
_trans_path = ROOT / "data" / "translations.json"
if _trans_path.exists():
    _trans = json.loads(_trans_path.read_text(encoding="utf-8"))
    _ko_by_dex = {int(k): v.get("ko", "") for k, v in _trans.get("species", {}).items()}
else:
    _ko_by_dex = {}

for p in _gm["pokemon"]:
    sid = p["speciesId"]
    if sid in DATA["species"]:
        continue
    _add(sid, sid)
    _add(p.get("speciesName", ""), sid)
    ko = _ko_by_dex.get(p["dex"], "")
    if ko:
        _add(ko, sid)
        # 폼 모디파이어 한글 — 베이스 ko 에 폼 텍스트 붙이기 (간단히 영어 form 그대로)


def _strip_calcy_decorations(name: str) -> str:
    """Calcy IV 가 이름에 붙이는 성별/사이즈/특수 마크 제거."""
    n = name
    # 성별 ♀ ♂
    n = re.sub(r"\s*[♀♂]\s*", " ", n)
    # 사이즈 (M, XS, XL, XXL — 단어 끝에 단독으로)
    n = re.sub(r"\s+(XXL|XXS|XL|XS|M|S|L)\s*$", "", n)
    # 따옴표/별표
    n = re.sub(r"[★☆\"']", "", n)
    return n.strip()


# 한글 폼 키워드 → species_id suffix
KOREAN_FORM_MAP = {
    "동쪽바다": "_east_sea", "서쪽바다": "_west_sea",
    "알로라": "_alolan", "갈라르": "_galarian",
    "히스이": "_hisuian", "팔데아": "_paldean",
    "오리진": "_origin", "어나더": "_altered",
    "영물": "_therian", "화신": "_incarnate",
    "원시": "_primal",
    "메가 x": "_mega_x", "메가 y": "_mega_y", "메가": "_mega",
    "쉐도우": "_shadow",
    "초목도롱": "_plant", "모래도롱": "_sandy", "쓰레기도롱": "_trash",
    "여름의": "_summer", "가을의": "_autumn", "겨울의": "_winter", "봄의": "_spring",
    "햇빛모습": "_sunny", "비모습": "_rainy", "눈모습": "_snowy",
    "공격형": "_attack", "방어형": "_defense", "스피드형": "_speed",
}


def match_species(name: str, is_shadow: bool, form: str = "") -> str | None:
    if not name:
        return None
    name = _strip_calcy_decorations(name)
    cleaned = re.sub(r"\s*\([^)]*\)", "", name).strip().lower()

    # 1) 그대로 매칭
    base_id = NAME_INDEX.get(name.lower().strip()) or NAME_INDEX.get(cleaned)

    # 2) 폼 키워드 추출 매칭
    if not base_id:
        for keyword, suffix in sorted(KOREAN_FORM_MAP.items(), key=lambda x: -len(x[0])):
            if keyword in name.lower():
                pure_name = re.sub(re.escape(keyword), "", name, flags=re.IGNORECASE)
                pure_name = re.sub(r"\s+", " ", pure_name).strip().lower()
                bid = NAME_INDEX.get(pure_name)
                if bid:
                    base = re.sub(
                        r"_(mega(_[xyz])?|primal|shadow|alolan|galarian|hisuian|paldean|origin|altered|therian|incarnate|east_sea|west_sea|plant|sandy|trash|summer|autumn|winter|spring|sunny|rainy|snowy|attack|defense|speed)$",
                        "", bid)
                    variant = base + suffix
                    if variant in DATA["species"]:
                        return variant
                    return bid  # 베이스라도 반환

    if not base_id:
        return None
    suffix = ""
    if is_shadow:
        suffix = "_shadow"
    elif form:
        f = form.lower().strip()
        FORM_MAP = {
            "shadow": "_shadow", "mega": "_mega", "mega x": "_mega_x",
            "mega y": "_mega_y", "alolan": "_alolan", "galarian": "_galarian",
            "hisuian": "_hisuian", "paldean": "_paldean",
            "origin": "_origin", "altered": "_altered",
            "therian": "_therian", "incarnate": "_incarnate",
            "primal": "_primal",
        }
        suffix = FORM_MAP.get(f, "")
    if suffix:
        base = re.sub(r"_(mega(_[xyz])?|primal|shadow|alolan|galarian|hisuian|paldean|origin|altered|therian|incarnate)$", "", base_id)
        variant = base + suffix
        if variant in DATA["species"]:
            return variant
    return base_id


def best_rank_in(sp: dict, keys: set) -> dict | None:
    best = None
    for p in sp.get("pvp", []):
        if p["league_key"] not in keys:
            continue
        if best is None or p["rank"] < best["rank"]:
            best = p
    return best


def best_raid(sp: dict) -> dict | None:
    if not sp.get("raid"):
        return None
    return min(sp["raid"], key=lambda r: r["rank"])


# ───── 리그 SP 비율 계산 ─────
def max_level_for_cp(sp: dict, ivA: int, ivD: int, ivS: int, cp_cap: int) -> dict | None:
    base = sp.get("base_stats")
    if not base or not base.get("atk"):
        return None
    for i in range(len(CPM) - 1, -1, -1):
        cpm = CPM[i]
        a = (base["atk"] + ivA) * cpm
        d = (base["def"] + ivD) * cpm
        h = (base["hp"] + ivS) * cpm
        cp = max(10, int(a * (d ** 0.5) * (h ** 0.5) / 10))
        if cp <= cp_cap:
            return {
                "level": 1 + i * 0.5,
                "cp": cp,
                "sp": a * d * int(h),
            }
    return None


def league_score(sp: dict, league_iv: dict, ivA: int, ivD: int, ivS: int, cp_cap: int) -> dict | None:
    if not league_iv:
        return None
    user = max_level_for_cp(sp, ivA, ivD, ivS, cp_cap)
    r1 = max_level_for_cp(sp, league_iv["atk"], league_iv["def"], league_iv["sta"], cp_cap)
    if not user or not r1 or not r1.get("sp"):
        return None
    return {
        "pct": user["sp"] / r1["sp"] * 100,
        "cp": user["cp"],
        "level": user["level"],
    }


# ───── 1마리 분석 ─────
def analyze_one(sp: dict, ivA: int, ivD: int, ivS: int, level: float, is_lucky: bool):
    iv_sum = ivA + ivD + ivS
    is_hundo = ivA == 15 and ivD == 15 and ivS == 15

    ml = best_rank_in(sp, ML_KEYS)
    gl = best_rank_in(sp, GL_KEYS)
    ul = best_rank_in(sp, UL_KEYS)
    lc = best_rank_in(sp, LC_KEYS)
    raid = best_raid(sp)

    cups = sorted(
        [p for p in sp.get("pvp", [])
         if p["league_key"] not in GL_KEYS | UL_KEYS | ML_KEYS | LC_KEYS],
        key=lambda x: x["rank"],
    )

    rk = sp.get("rank1_iv") or {}
    gl_score = league_score(sp, rk.get("GL"), ivA, ivD, ivS, 1500) if rk.get("GL") else None
    ul_score = league_score(sp, rk.get("UL"), ivA, ivD, ivS, 2500) if rk.get("UL") else None

    decisions = []

    # 마스터/레이드
    if (ml and ml["rank"] <= 15) or (raid and raid["is_essential_tier"] and raid["rank"] <= 8):
        if is_hundo:
            decisions.append((1, "🔴 마스터/레이드 풀강 (100%)",
                              f"ML#{ml['rank']}" if ml else f"vs {raid['boss_ko']}#{raid['rank']}"))
        elif iv_sum >= 42:
            decisions.append((2, f"🟡 마스터/레이드 후보 (IV {iv_sum}/45)",
                              "100% 잡으면 교체"))
        elif iv_sum >= 36:
            decisions.append((3, f"🔵 마스터/레이드 IV 부족 ({iv_sum}/45)",
                              "더 좋은 거 잡으면 송출"))

    # 슈퍼리그
    if gl and gl["rank"] <= 20 and gl_score:
        if gl_score["pct"] >= 99:
            decisions.append((1, f"🔴 슈퍼리그 #{gl['rank']} 거의 완벽 ({gl_score['pct']:.1f}%)",
                              f"Lv{gl_score['level']} CP{gl_score['cp']}"))
        elif gl_score["pct"] >= 96:
            decisions.append((2, f"🟡 슈퍼리그 #{gl['rank']} 쓸만 ({gl_score['pct']:.1f}%)",
                              f"Lv{gl_score['level']} CP{gl_score['cp']}"))
        elif gl_score["pct"] >= 90:
            decisions.append((3, f"🔵 슈퍼리그 #{gl['rank']} 부족 ({gl_score['pct']:.1f}%)",
                              "rank-1 IV 보다 약함"))

    # 하이퍼리그
    if ul and ul["rank"] <= 20 and ul_score:
        if ul_score["pct"] >= 99:
            decisions.append((1, f"🔴 하이퍼리그 #{ul['rank']} 거의 완벽 ({ul_score['pct']:.1f}%)",
                              f"Lv{ul_score['level']} CP{ul_score['cp']}"))
        elif ul_score["pct"] >= 96:
            decisions.append((2, f"🟡 하이퍼리그 #{ul['rank']} 쓸만 ({ul_score['pct']:.1f}%)",
                              f"Lv{ul_score['level']} CP{ul_score['cp']}"))

    if cups and not decisions:
        top = cups[0]
        decisions.append((3, f"🔵 컵 한정 — {top['league_ko']}#{top['rank']}", "시즌 한정"))

    # 가족 그룹 분류
    sid = sp["id"]
    in_mega_keep = any(any(m["sid"] == sid for m in g["members"]) for g in DATA.get("mega_keep_groups") or [])
    in_mega_possible = any(any(m["sid"] == sid for m in g["members"]) for g in DATA.get("mega_possible_groups") or [])
    in_transfer = any(any(m["sid"] == sid for m in g["members"]) for g in DATA.get("transfer_groups") or [])

    if not decisions:
        if sp.get("stronger_forms"):
            decisions.append((3, "🔵 더 강한 폼 우선", "쉐도우/메가 핵심 — 베이스 1마리만"))
        elif in_mega_keep:
            decisions.append((1, "🔴 메가 변신 베이스 — 100% IV 보관 필수", "메가가 ranked"))
        elif in_mega_possible:
            decisions.append((2, "🟡 메가 가능 — 100% IV 1마리 보관", "추후 메가 풀 추가 대비"))
        elif in_transfer:
            decisions.append((4, "⚪ 박사 송출 OK", "어디에도 안 쓰임"))
        else:
            decisions.append((3, "🔵 랭킹 외 — 1마리 보관", ""))

    if is_lucky:
        decisions.insert(0, (0, "🍀 Lucky", "반값 강화 — 보관 가치 +1"))

    return {
        "sid": sid, "ko": sp["ko"], "en": sp["en"], "dex": sp["dex"], "types": sp["types"],
        "iv": (ivA, ivD, ivS), "level": level, "lucky": is_lucky,
        "decisions": decisions,
        "pri": min(d[0] for d in decisions if d[0] > 0) if any(d[0] > 0 for d in decisions) else 99,
    }


# ───── CSV 파싱 ─────
def normalize_header(h: str) -> str:
    h = h.replace("Ø", "avg ").replace("ø", "avg ")
    h = re.sub(r"\s+", " ", h).strip().lower()
    return h


def find_col(headers_norm: list[str], aliases: list[str]) -> int:
    for a in aliases:
        if a in headers_norm:
            return headers_norm.index(a)
    for i, h in enumerate(headers_norm):
        for a in aliases:
            if h == a or (a in h and len(h) < len(a) + 8):
                return i
    return -1


def main() -> None:
    print(f"[CSV] {CSV_PATH}")
    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.reader(f))

    print(f"[CSV] {len(rows)} 행 (헤더 + {len(rows) - 1} entries)")

    headers = rows[0]
    headers_norm = [normalize_header(h) for h in headers]
    print(f"[CSV] 헤더: {headers}")

    cols = {
        "name": find_col(headers_norm, ["name", "pokemon", "species", "이름"]),
        "form": find_col(headers_norm, ["form", "폼"]),
        "cp": find_col(headers_norm, ["cp"]),
        "atk": find_col(headers_norm, ["avg att iv", "avg att", "att iv", "atk", "attack", "공격"]),
        "def": find_col(headers_norm, ["avg def iv", "avg def", "def iv", "defense", "방어"]),
        "sta": find_col(headers_norm, ["avg hp iv", "avg hp", "hp iv", "sta iv", "stamina", "체력"]),
        "level": find_col(headers_norm, ["lvl", "level", "lv", "레벨"]),
        "shadow": find_col(headers_norm, ["shadowform", "shadow"]),
        "lucky": find_col(headers_norm, ["lucky?", "lucky"]),
    }
    print(f"[cols] {cols}")
    if cols["name"] < 0 or cols["atk"] < 0 or cols["def"] < 0 or cols["sta"] < 0:
        print("!! 컬럼 매칭 실패")
        return

    results = []
    unmatched_names: Counter = Counter()
    for r in rows[1:]:
        if len(r) <= max(cols.values()):
            continue
        name = r[cols["name"]].strip()
        if not name:
            continue
        form = r[cols["form"]] if cols["form"] >= 0 else ""
        is_shadow_str = r[cols["shadow"]] if cols["shadow"] >= 0 else ""
        is_shadow = is_shadow_str.lower() in ("yes", "true", "1", "y", "쉐도우", "shadow")
        sid = match_species(name, is_shadow, form)
        if not sid:
            unmatched_names[name] += 1
            continue

        try:
            ivA = int(float(r[cols["atk"]]))
            ivD = int(float(r[cols["def"]]))
            ivS = int(float(r[cols["sta"]]))
            lv = float(r[cols["level"]]) if cols["level"] >= 0 else 30
        except (ValueError, IndexError):
            continue
        is_lucky = cols["lucky"] >= 0 and r[cols["lucky"]].lower() in ("yes", "true", "1", "y")

        if sid in DATA["species"]:
            sp = DATA["species"][sid]
            results.append(analyze_one(sp, ivA, ivD, ivS, lv, is_lucky))
        else:
            # species_out 에 없는 종 = 송출 가족. 가족 정보로 직접 처리.
            transfer_member = None
            for g in DATA.get("transfer_groups") or []:
                for m in g["members"]:
                    if m["sid"] == sid:
                        transfer_member = (g, m)
                        break
                if transfer_member:
                    break
            mega_member = None
            if not transfer_member:
                for grp_key in ("mega_keep_groups", "mega_possible_groups"):
                    for g in DATA.get(grp_key) or []:
                        for m in g["members"]:
                            if m["sid"] == sid:
                                mega_member = (grp_key, g, m)
                                break
                        if mega_member:
                            break
                    if mega_member:
                        break

            if transfer_member:
                g, m = transfer_member
                is_keep = (m["sid"] == g["keep_sid"])
                pri = 4
                if m.get("is_shadow"):
                    decision = (4, "⚪ 박사 송출 OK (쉐도우 1마리만 보관)", "")
                elif is_keep:
                    decision = (3, "🔵 가족 대표 — 1마리 보관", "메타 변동 대비")
                else:
                    decision = (4, "⚪ 박사 송출 OK", "가족 송출 후보")
                results.append({
                    "sid": sid, "ko": m["ko"], "en": m["en"], "dex": m["dex"],
                    "types": m["types"], "iv": (ivA, ivD, ivS), "level": lv,
                    "lucky": is_lucky, "decisions": [decision], "pri": decision[0],
                })
            elif mega_member:
                grp_key, g, m = mega_member
                is_hundo = ivA == 15 and ivD == 15 and ivS == 15
                if grp_key == "mega_keep_groups":
                    text = "🔴 메가 변신 베이스 — 100% 보관" if is_hundo else "🟡 메가 보관 — 100% 우선"
                    pri = 1 if is_hundo else 2
                else:
                    text = "🟡 메가 가능 — 100% 1마리 보관"
                    pri = 2
                results.append({
                    "sid": sid, "ko": m["ko"], "en": m["en"], "dex": m["dex"],
                    "types": m["types"], "iv": (ivA, ivD, ivS), "level": lv,
                    "lucky": is_lucky,
                    "decisions": [(pri, text, "")], "pri": pri,
                })
            else:
                # gamemaster 에 있지만 어디에도 분류 안 됨 — 베이비/짧은 사슬
                results.append({
                    "sid": sid, "ko": name, "en": "", "dex": 9999, "types": [],
                    "iv": (ivA, ivD, ivS), "level": lv, "lucky": is_lucky,
                    "decisions": [(4, "⚪ 박사 송출 OK (분류 없음)", "")], "pri": 4,
                })

    print(f"\n[match] {len(results)} / {len(rows) - 1} 분석 완료")
    if unmatched_names:
        print(f"[unmatched] {sum(unmatched_names.values())} entries / {len(unmatched_names)} unique names")
        print("  Top unmatched names:")
        for n, c in unmatched_names.most_common(15):
            print(f"    {c:>3}× {n!r}")

    # 카운트
    counts = Counter(r["pri"] for r in results)
    print(f"\n=== 판단 분포 ===")
    print(f"  🔴 풀강:       {counts.get(1, 0)}")
    print(f"  🟡 권장:       {counts.get(2, 0)}")
    print(f"  🔵 부족·컵한정: {counts.get(3, 0)}")
    print(f"  ⚪ 송출 OK:    {counts.get(4, 0)}")
    print(f"  기타:          {counts.get(99, 0)}")

    # CSV 출력
    out_csv = OUT_DIR / "box_analysis.csv"
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["우선순위", "Dex", "한글", "영어", "속성", "IV", "Lv", "판단", "이유"])
        results.sort(key=lambda r: (r["pri"], r["dex"]))
        for r in results:
            top = r["decisions"][0]
            iv_str = f"{r['iv'][0]}/{r['iv'][1]}/{r['iv'][2]}"
            w.writerow([
                {1: "풀강", 2: "권장", 3: "부족/컵", 4: "송출OK"}.get(r["pri"], "기타"),
                f"{r['dex']:03d}",
                r["ko"], r["en"],
                "/".join(r["types"]),
                iv_str, r["level"],
                top[1].split("(")[0].strip(),
                top[2],
            ])

    print(f"\n[out] {out_csv}")
    print(f"[out] {len(results)} 행 (우선순위 순 정렬)")


if __name__ == "__main__":
    main()
