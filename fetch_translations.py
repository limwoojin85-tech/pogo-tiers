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

    # 종 -- pokemon_species (id, identifier) + pokemon_species_names (ko name)
    species_meta = fetch_csv("pokemon_species.csv")
    species_names = fetch_csv("pokemon_species_names.csv")

    # id → identifier 매핑 (id 가 곧 dex 번호)
    sp_by_id = {row["id"]: row["identifier"] for row in species_meta}
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
        "species": species,           # by dex (id 가 곧 dex)
        "moves": moves,               # by pvpoke move_id
        "types_ko": types_ko,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[translations] 완료: 종 {len(species)} / 기술 {len(moves)} → {OUT}")


if __name__ == "__main__":
    main()
