"""
포켓몬고 속성 상성 표.

GO 배율: SE = 1.6 / NVE = 0.625 / 더블 NVE = 0.390625 / 무효 = 0.244 (이전엔 0.39).
매치업 자체는 본가와 동일.
"""
from __future__ import annotations

# (attacker, defender) → multiplier (mainline 기준; GO 는 별도 변환)
# 여기 등록 안 된 조합은 1.0 (보통).
SE: dict[str, set[str]] = {
    "normal": set(),
    "fighting": {"normal", "rock", "steel", "ice", "dark"},
    "flying":   {"fighting", "bug", "grass"},
    "poison":   {"grass", "fairy"},
    "ground":   {"poison", "rock", "steel", "fire", "electric"},
    "rock":     {"flying", "bug", "fire", "ice"},
    "bug":      {"grass", "psychic", "dark"},
    "ghost":    {"ghost", "psychic"},
    "steel":    {"rock", "ice", "fairy"},
    "fire":     {"bug", "steel", "grass", "ice"},
    "water":    {"ground", "rock", "fire"},
    "grass":    {"ground", "rock", "water"},
    "electric": {"flying", "water"},
    "psychic":  {"fighting", "poison"},
    "ice":      {"flying", "ground", "grass", "dragon"},
    "dragon":   {"dragon"},
    "dark":     {"ghost", "psychic"},
    "fairy":    {"fighting", "dragon", "dark"},
}

NVE: dict[str, set[str]] = {
    "normal":   {"rock", "steel"},
    "fighting": {"flying", "poison", "bug", "psychic", "fairy"},
    "flying":   {"rock", "steel", "electric"},
    "poison":   {"poison", "ground", "rock", "ghost"},
    "ground":   {"bug", "grass"},
    "rock":     {"fighting", "ground", "steel"},
    "bug":      {"fighting", "flying", "poison", "ghost", "steel", "fire", "fairy"},
    "ghost":    {"dark"},
    "steel":    {"steel", "fire", "water", "electric"},
    "fire":     {"rock", "fire", "water", "dragon"},
    "water":    {"water", "grass", "dragon"},
    "grass":    {"flying", "poison", "bug", "steel", "fire", "grass", "dragon"},
    "electric": {"grass", "electric", "dragon"},
    "psychic":  {"steel", "psychic"},
    "ice":      {"steel", "fire", "water", "ice"},
    "dragon":   {"steel"},
    "dark":     {"fighting", "dark", "fairy"},
    "fairy":    {"poison", "steel", "fire"},
}

IMMUNE: dict[str, set[str]] = {
    "normal":   {"ghost"},
    "fighting": {"ghost"},
    "poison":   {"steel"},
    "ground":   {"flying"},
    "ghost":    {"normal"},
    "electric": {"ground"},
    "psychic":  {"dark"},
    "dragon":   {"fairy"},
}

ALL_TYPES = list(SE.keys())

# GO 배율
GO_SE = 1.6
GO_NVE = 0.625
GO_DOUBLE_NVE = GO_NVE * GO_NVE          # 0.390625
GO_IMMUNE_SINGLE = 0.390625              # GO 의 무효도 NVE 와 같은 0.39 ~로 처리됨
GO_IMMUNE_NVE = GO_IMMUNE_SINGLE * GO_NVE


def effectiveness(attacker: str, defender_types: list[str]) -> float:
    """공격 타입이 방어자(1~2 타입) 에게 입히는 GO 배율."""
    mult = 1.0
    for d in defender_types:
        if not d or d == "none":
            continue
        if d in IMMUNE.get(attacker, set()):
            mult *= 0.390625
        elif d in SE.get(attacker, set()):
            mult *= GO_SE
        elif d in NVE.get(attacker, set()):
            mult *= GO_NVE
    return mult


def weaknesses_resistances(
    defender_types: list[str],
) -> tuple[dict[str, float], dict[str, float]]:
    """방어자 타입 조합의 약점/저항 — 배율 → {타입: 배율}."""
    weak: dict[str, float] = {}
    resist: dict[str, float] = {}
    for atk in ALL_TYPES:
        m = effectiveness(atk, defender_types)
        if m > 1.01:
            weak[atk] = m
        elif m < 0.99:
            resist[atk] = m
    return weak, resist


def fmt_mult(m: float) -> str:
    """1.6 → ×1.6 (소수 1자리, 정수면 정수)."""
    if abs(m - round(m)) < 0.01:
        return f"×{int(round(m))}"
    return f"×{m:.2f}".rstrip("0").rstrip(".")
