"""
진화 체인 데이터 검수.
1. 깝질무·트리토돈 같은 케이스가 species_out / transfer_groups / mega_keep_groups 어디에 있나?
2. 분류 없는 종 (gamemaster 에 있지만 어디에도 없음) 추출
"""
from __future__ import annotations
import json, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# index.html 의 embedded data 사용
html = open("out/index.html", encoding="utf-8").read()
m = re.search(r'<script id="data" type="application/json">(.+?)</script>', html, re.DOTALL)
DATA = json.loads(m.group(1).replace("<\\/", "</"))

print(f"species (랭킹된 종): {len(DATA['species'])}")
print(f"transfer_groups: {len(DATA.get('transfer_groups') or [])}")
print(f"mega_keep_groups: {len(DATA.get('mega_keep_groups') or [])}")
print(f"mega_possible_groups: {len(DATA.get('mega_possible_groups') or [])}")
print(f"pre_evolution_groups: {len(DATA.get('pre_evolution_groups') or [])}")

# 깝질무 = shellos / 트리토돈 = gastrodon
print("\n=== 깝질무 / 트리토돈 — 어디 분류됐는지 ===")
target_sids = {"shellos", "shellos_east_sea", "shellos_west_sea",
               "gastrodon", "gastrodon_east_sea", "gastrodon_west_sea"}
for sid in target_sids:
    sp = DATA["species"].get(sid)
    if sp:
        print(f"  ✅ species[{sid}] (ranked): ko={sp.get('ko')}")
        continue
    found = False
    for gk in ["transfer_groups","mega_keep_groups","mega_possible_groups","pre_evolution_groups"]:
        for g in (DATA.get(gk) or []):
            for m in g.get("members", []):
                if m.get("sid") == sid:
                    extra = ""
                    if gk == "pre_evolution_groups":
                        extra = f" → 진화 후: {g.get('evolves_to_ko')}"
                    print(f"  ✅ {gk}: {sid} ({m.get('ko')}){extra}")
                    found = True; break
            if found: break
        if found: break
    if not found:
        print(f"  ❌ {sid} 어디에도 없음")

# pvpoke gamemaster 에 있는 모든 species 와 우리 분류 비교
gm = json.load(open("data/pvpoke/_gamemaster.json", encoding="utf-8"))
gm_sids = set(p["speciesId"] for p in gm["pokemon"])
print(f"\n=== 분류 누락 종 (gamemaster 에 있지만 어디에도 안 들어감) ===")
species_sids = set(DATA["species"].keys())
group_sids = set()
for gk in ["transfer_groups", "mega_keep_groups", "mega_possible_groups", "pre_evolution_groups"]:
    for g in (DATA.get(gk) or []):
        for m in g.get("members", []):
            group_sids.add(m.get("sid",""))

missing = gm_sids - species_sids - group_sids
print(f"누락 총: {len(missing)} / {len(gm_sids)}")
print("샘플 30개:")
for sid in sorted(missing)[:30]:
    p = next((p for p in gm["pokemon"] if p["speciesId"] == sid), None)
    if p: print(f"  {sid} (dex {p['dex']}, {p.get('speciesName','')})")

# 샘플 — 진화 가능한 종인지 (familyId 가 있고 다른 멤버 있는 경우)
print("\n=== 누락 종 중 진화 체인 멤버 (다른 분류된 종과 같은 family) ===")
fams = {}
for p in gm["pokemon"]:
    fid = (p.get("family") or {}).get("id")
    if fid:
        fams.setdefault(fid, []).append(p["speciesId"])
cnt = 0
for sid in sorted(missing)[:200]:
    p = next((p for p in gm["pokemon"] if p["speciesId"] == sid), None)
    if not p: continue
    fid = (p.get("family") or {}).get("id")
    if not fid: continue
    sibs = [s for s in fams[fid] if s != sid]
    classified_sibs = [s for s in sibs if s in species_sids or s in group_sids]
    if classified_sibs:
        print(f"  {sid} → 같은 family ({fid}): {classified_sibs[:5]}")
        cnt += 1
        if cnt >= 20: break
