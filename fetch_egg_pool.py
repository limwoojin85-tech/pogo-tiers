"""
LeekDuck (leekduck.com/eggs) 에서 현재 알 풀 자동 수집.
출력: data/egg_pool.json
   { "2": ["dunsparce", ...], "5": [...], "7": [...], "10": [...], "12": [...],
     "_updated": "2026-05-08", "_source": "leekduck.com/eggs" }

build_html.py 가 species_out 의 acquisition 에 "🥚 12km" 같은 라벨 자동 추가.
"""
from __future__ import annotations
import json
import re
import sys
import io
import urllib.request
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "egg_pool.json"

# 영어 LeekDuck 표기 → pvpoke speciesId 매핑
NAME_FIXES = {
    "galarian meowth": "meowth_galarian",
    "galarian corsola": "corsola_galarian",
    "galarian zigzagoon": "zigzagoon_galarian",
    "galarian darumaka": "darumaka_galarian",
    "galarian stunfisk": "stunfisk_galarian",
    "galarian slowpoke": "slowpoke_galarian",
    "alolan geodude": "geodude_alolan",
    "alolan diglett": "diglett_alolan",
    "alolan vulpix": "vulpix_alolan",
    "alolan sandshrew": "sandshrew_alolan",
    "alolan rattata": "rattata_alolan",
    "alolan grimer": "grimer_alolan",
    "alolan exeggcute": "exeggcute",
    "hisuian sneasel": "sneasel_hisuian",
    "hisuian growlithe": "growlithe_hisuian",
    "hisuian voltorb": "voltorb_hisuian",
    "hisuian qwilfish": "qwilfish_hisuian",
    "indeedee (male)": "indeedee_male",
    "indeedee (female)": "indeedee_female",
    "basculin (white striped)": "basculin_white_striped",
    "type: null": "type_null",
}


def normalize_name(name: str) -> str:
    n = name.strip().lower()
    if n in NAME_FIXES:
        return NAME_FIXES[n]
    # 일반 변환: " " → "_", 특수문자 제거
    n = re.sub(r"[^a-z0-9_\s]", "", n)
    n = re.sub(r"\s+", "_", n.strip())
    return n


def fetch_leekduck_html() -> str:
    req = urllib.request.Request(
        "https://leekduck.com/eggs/",
        headers={"User-Agent": "Mozilla/5.0 (pogo-tiers fetcher)"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_egg_pool(html: str) -> dict[str, list[str]]:
    """HTML 에서 알 거리별 풀 추출. 거리는 텍스트로 등장."""
    pool: dict[str, list[str]] = {"2": [], "5": [], "7": [], "10": [], "12": []}
    # LeekDuck 의 알 페이지는 (2km, 5km, ...) 섹션 단위.
    # 단순 정규식 — section header + 다음 알 이름들 추출.
    # 알 이름은 보통 "name" 태그나 "data-name" 속성에 있음.
    # 우선 섹션 분리:
    sections = re.split(r"(\d+)\s*km\s+egg", html, flags=re.IGNORECASE)
    # sections = [pre, "2", "<2km section html>", "5", "<5km section html>", ...]
    current_km = None
    for i, part in enumerate(sections):
        if part in ("2", "5", "7", "10", "12"):
            current_km = part
            continue
        if current_km is None:
            continue
        # 알 이름 추출 — <span class="name">...</span> 또는 비슷한 패턴
        names = re.findall(r'<span class="name"[^>]*>([^<]+)</span>', part)
        if not names:
            # data-name 속성 시도
            names = re.findall(r'data-name="([^"]+)"', part)
        if not names:
            # alt 속성 시도 (이미지 alt)
            names = re.findall(r'alt="([^"]+)"', part)
        for n in names:
            n_clean = n.strip()
            if not n_clean or len(n_clean) < 2 or n_clean.lower() in ("sprite",):
                continue
            sid = normalize_name(n_clean)
            if sid and sid not in pool[current_km]:
                pool[current_km].append(sid)
        # 다음 km 으로 reset
        if "km" in part.lower() and any(k in part for k in ("2 km", "5 km", "7 km", "10 km", "12 km")):
            current_km = None
    return pool


def main() -> None:
    print("[egg_pool] LeekDuck fetch ...")
    try:
        html = fetch_leekduck_html()
        pool = parse_egg_pool(html)
        if not any(pool.values()):
            raise ValueError("파싱 결과 비어있음 — 페이지 구조 변경?")
    except Exception as e:
        print(f"[!] HTML fetch/parse 실패: {e}")
        print("    → 마지막 캐시 유지 또는 수동 업데이트 필요")
        return

    out = {
        **pool,
        "_updated": datetime.now().strftime("%Y-%m-%d"),
        "_source": "leekduck.com/eggs",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[egg_pool] 완료:")
    for km in ("2", "5", "7", "10", "12"):
        n = len(pool[km])
        print(f"  {km}km — {n}종: {', '.join(pool[km][:8])}{('...' if n>8 else '')}")
    print(f"  → {OUT}")


if __name__ == "__main__":
    main()
