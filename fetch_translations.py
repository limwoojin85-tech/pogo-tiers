"""
PokeAPI CSV 에서 한글 이름 데이터 받아서 캐시.

data/translations.json:
  species[dex] = {"ko": "이상해씨", "en": "bulbasaur"}
  moves["VINE_WHIP"] = {"ko": "덩굴채찍", "en": "Vine Whip"}
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "translations.json"

PA_RAW = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv"

# language_id = 3 -> 한국어 (PokeAPI 기준)
KO_LANG = "3"
EN_LANG = "9"


def fetch_csv(name: str) -> list[dict[str, str]]:
    url = f"{PA_RAW}/{name}"
    print(f"  [GET] {name}")
    req = urllib.request.Request(url, headers={"User-Agent": "pogo-tiers/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def main() -> None:
    print("[translations] PokeAPI CSV 다운로드")

    # 종 -- pokemon_species (id, identifier, evolves_from_species_id, evolution_chain_id) + names
    species_meta = fetch_csv("pokemon_species.csv")
    species_names = fetch_csv("pokemon_species_names.csv")

    # id → identifier (= dex 매핑)
    sp_by_id = {row["id"]: row["identifier"] for row in species_meta}
    # 진화 정보 — 부모/체인
    evolves_from: dict[int, int] = {}
    evolution_chain: dict[int, int] = {}  # dex → chain_id
    for row in species_meta:
        try:
            dex = int(row["id"])
            parent = row.get("evolves_from_species_id") or ""
            chain = row.get("evolution_chain_id") or ""
            if parent.isdigit():
                evolves_from[dex] = int(parent)
            if chain.isdigit():
                evolution_chain[dex] = int(chain)
        except Exception:
            continue

    species: dict[str, dict[str, str]] = {}
    for row in species_names:
        sid = row["pokemon_species_id"]
        if row["local_language_id"] != KO_LANG:
            continue
        if sid not in sp_by_id:
            continue
        species[sid] = {
            "ko": row["name"],
            "en": sp_by_id[sid].replace("-", " ").title(),
        }

    # 폼 한글 — pokemon_form_names (form_name = "메가", "원시" 등)
    pokemon_forms = fetch_csv("pokemon_forms.csv")
    pokemon_form_names = fetch_csv("pokemon_form_names.csv")
    # form_id → species dex 매핑 (pokemon_forms.pokemon_id 로 species 찾기)
    pokemon_csv = fetch_csv("pokemon.csv")
    poke_to_species = {row["id"]: row["species_id"] for row in pokemon_csv}
    form_to_species = {
        row["id"]: poke_to_species.get(row["pokemon_id"], "")
        for row in pokemon_forms
    }
    forms_ko: dict[str, str] = {}  # form_identifier → 한글 라벨 (예: "alolan" → "알로라")
    for row in pokemon_form_names:
        if row["local_language_id"] != KO_LANG:
            continue
        fid = row["pokemon_form_id"]
        form = next((f for f in pokemon_forms if f["id"] == fid), None)
        if not form:
            continue
        form_ident = form.get("form_identifier", "").strip()
        if not form_ident:
            continue
        # 폼 라벨만 뽑기 (예: "초목도롱" 그대로)
        if row["form_name"] and form_ident not in forms_ko:
            forms_ko[form_ident] = row["form_name"]

    # 진화 체인 — chain_id → [dex,...]
    chains_by_id: dict[int, list[int]] = {}
    for dex, cid in evolution_chain.items():
        chains_by_id.setdefault(cid, []).append(dex)
    for cid in chains_by_id:
        chains_by_id[cid].sort()

    # 기술 -- moves (id, identifier) + move_names
    moves_meta = fetch_csv("moves.csv")
    moves_names = fetch_csv("move_names.csv")
    mv_by_id = {row["id"]: row["identifier"] for row in moves_meta}
    move_id_to_ko: dict[str, str] = {}
    move_id_to_en: dict[str, str] = {}
    for row in moves_names:
        mid = row["move_id"]
        if mid not in mv_by_id:
            continue
        if row["local_language_id"] == KO_LANG:
            move_id_to_ko[mid] = row["name"]
        elif row["local_language_id"] == EN_LANG:
            move_id_to_en[mid] = row["name"]

    # PvPoke 의 move_id (VINE_WHIP) ↔ PokeAPI identifier (vine-whip) 매핑
    moves: dict[str, dict[str, str]] = {}
    for mid, ident in mv_by_id.items():
        pvpoke_id = ident.upper().replace("-", "_")
        ko = move_id_to_ko.get(mid, "")
        en = move_id_to_en.get(mid) or ident.replace("-", " ").title()
        moves[pvpoke_id] = {"ko": ko, "en": en}

    # 타입 한글
    types_ko = {
        "normal": "노말", "fighting": "격투", "flying": "비행",
        "poison": "독", "ground": "땅", "rock": "바위",
        "bug": "벌레", "ghost": "고스트", "steel": "강철",
        "fire": "불꽃", "water": "물", "grass": "풀",
        "electric": "전기", "psychic": "에스퍼", "ice": "얼음",
        "dragon": "드래곤", "dark": "악", "fairy": "페어리",
    }

    out = {
        "species": species,                       # by dex (id 가 곧 dex)
        "moves": moves,                           # by pvpoke move_id
        "types_ko": types_ko,
        "forms_ko": forms_ko,                     # form_identifier → 한글 (예: "alolan" → "알로라")
        "evolution_chain": evolution_chain,       # dex → chain_id
        "evolves_from": evolves_from,             # dex → 부모 dex (있으면)
        "chains_by_id": chains_by_id,             # chain_id → [dex,...] 체인 멤버
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[translations] 완료:")
    print(f"  종 {len(species)} / 기술 {len(moves)}")
    print(f"  폼 {len(forms_ko)} / 진화체인 {len(chains_by_id)} / 부모 정보 {len(evolves_from)}")
    print(f"  → {OUT}")


if __name__ == "__main__":
    main()
