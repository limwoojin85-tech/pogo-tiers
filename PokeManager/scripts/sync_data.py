"""
PokeManager 앱 데이터 동기화 — pogo_tiers 의 must_have.json + gamemaster + 한글 번역을
앱 assets 로 변환.

출력:
  app/src/main/assets/pokemon_stats.json     모든 종 (1100+) — base stats + 한글
  app/src/main/assets/species_meta.json      메타 (must_have.json 의 사이트 분석 데이터)
  app/src/main/assets/groups.json            transfer/mega/pre_evolution 그룹
"""
from __future__ import annotations
import json, sys, io, re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).parent.parent.parent  # PokeManager/scripts/ 의 상위 두 단계 = pogo_tiers
ASSETS = Path(__file__).parent.parent / "app" / "src" / "main" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

# 1. 데이터 로드
gm = json.loads((ROOT / "data" / "pvpoke" / "_gamemaster.json").read_text(encoding="utf-8"))
trans = json.loads((ROOT / "data" / "translations.json").read_text(encoding="utf-8"))
must_have = json.loads((ROOT / "out" / "must_have.json").read_text(encoding="utf-8"))

# 2. embedded data — out/index.html 에서 species 섹션 + 그룹 추출
import re as _re
html = (ROOT / "out" / "index.html").read_text(encoding="utf-8")
m = _re.search(r'<script id="data" type="application/json">(.+?)</script>', html, _re.DOTALL)
DATA = json.loads(m.group(1).replace("<\\/", "</"))

# 3. 한글 이름 — translations
ko_by_dex = {int(k): v.get("ko", "") for k, v in trans.get("species", {}).items()}

# 4. pokemon_stats — 1100+ 종, 모든 폼 포함
def form_label(sid: str) -> str:
    """ko 이름에 폼 라벨 부여."""
    suffix_map = {
        "_alolan": " (알로라)", "_galarian": " (갈라르)", "_hisuian": " (히스이)",
        "_paldean": " (팔데아)", "_origin": " (오리진)", "_altered": " (어나더)",
        "_therian": " (영물)", "_incarnate": " (화신)", "_primal": " (원시)",
        "_mega_x": " (메가 X)", "_mega_y": " (메가 Y)", "_mega": " (메가)",
        "_shadow": " (쉐도우)", "_east_sea": " (동쪽바다)", "_west_sea": " (서쪽바다)",
        "_attack": " (어택)", "_defense": " (디펜스)", "_speed": " (스피드)",
        "_sky": " (스카이)", "_aria": " (보이스)", "_pirouette": " (스텝)",
        "_dawn_wings": " (새벽날개)", "_dusk_mane": " (황혼갈기)", "_ultra": " (울트라)",
    }
    for suf, lbl in suffix_map.items():
        if sid.endswith(suf):
            return lbl
    return ""

stats = []
for p in gm["pokemon"]:
    if not p.get("released", True):
        continue
    sid = p["speciesId"]
    dex = p.get("dex", 0)
    base_ko = ko_by_dex.get(dex, "")
    label = form_label(sid)
    name_ko = base_ko + label if base_ko else sid
    base = p.get("baseStats") or {}
    types = [t.upper() for t in (p.get("types") or []) if t and t != "none"]
    stats.append({
        "id": sid,
        "name": p.get("speciesName", sid),
        "nameKo": name_ko,
        "dex": dex,
        "atk": base.get("atk", 0),
        "def": base.get("def", 0),
        "sta": base.get("hp", 0),
        "types": types,
    })

print(f"pokemon_stats: {len(stats)} 종")
(ASSETS / "pokemon_stats.json").write_text(
    json.dumps(stats, ensure_ascii=False, separators=(",", ":")) + "\n",
    encoding="utf-8"
)

# 5. species_meta — 사이트 분석용 (랭킹, pvp, raid)
species_meta = {}
for sid, sp in DATA["species"].items():
    species_meta[sid] = {
        "ko": sp.get("ko", ""),
        "en": sp.get("en", ""),
        "dex": sp.get("dex", 0),
        "types": sp.get("types", []),
        "pvp": sp.get("pvp", []),       # 리그/컵 랭킹
        "raid": sp.get("raid", []),     # 보스별 카운터 랭크
        "rank1_iv": sp.get("rank1_iv"), # GL/UL 종결 IV
        "is_final": sp.get("is_final", True),
        "max_cp": sp.get("max_cp", 0),
        "max_sp": sp.get("max_sp", 0),
    }
print(f"species_meta: {len(species_meta)} 랭킹된 종")
(ASSETS / "species_meta.json").write_text(
    json.dumps(species_meta, ensure_ascii=False, separators=(",", ":")) + "\n",
    encoding="utf-8"
)

# 6. groups — transfer/mega/pre_evolution 분류
groups = {
    "transfer_groups": DATA.get("transfer_groups") or [],
    "mega_keep_groups": DATA.get("mega_keep_groups") or [],
    "mega_possible_groups": DATA.get("mega_possible_groups") or [],
    "pre_evolution_groups": DATA.get("pre_evolution_groups") or [],
}
print(f"groups: transfer {len(groups['transfer_groups'])}, "
      f"mega_keep {len(groups['mega_keep_groups'])}, "
      f"mega_possible {len(groups['mega_possible_groups'])}, "
      f"pre_evolution {len(groups['pre_evolution_groups'])}")
(ASSETS / "groups.json").write_text(
    json.dumps(groups, ensure_ascii=False, separators=(",", ":")) + "\n",
    encoding="utf-8"
)

# 7. CPM 테이블 (사이트와 동일)
cpm_data = {"cpm": DATA.get("cpm") or []}
(ASSETS / "cpm.json").write_text(
    json.dumps(cpm_data, ensure_ascii=False, separators=(",", ":")) + "\n",
    encoding="utf-8"
)
print(f"cpm: {len(cpm_data['cpm'])} 레벨")

# 출력 사이즈 통계
for f in ["pokemon_stats.json", "species_meta.json", "groups.json", "cpm.json"]:
    p = ASSETS / f
    print(f"  {f}: {p.stat().st_size / 1024:.1f} KB")

print("\n✅ assets 동기화 완료")
print(f"   {ASSETS}")
