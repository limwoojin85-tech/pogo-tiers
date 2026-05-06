"""
1번/2번 계정 Calcy CSV 통합.

입력:
  scripts/calcy_adb/history.csv          (1번 계정 — 5/6 22:47 ~ 5/7 00:13, 1063건)
  G:/내 드라이브/history_20260507_014523.csv  (2번 계정 — 5/7 00:13 ~ 01:32, 638건)

출력:
  scripts/calcy_adb/history_merged.csv   (모든 행 + Account 컬럼 추가)

같은 닉네임이 두 계정에 동시 존재할 일은 거의 없지만, account 라벨로 구분 보존.
타임스탬프로 스캔이 어디서 끝났는지도 살릴 수 있음.
"""
from __future__ import annotations
import csv
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).parent.parent
ACC1 = ROOT / "scripts" / "calcy_adb" / "history.csv"
ACC2 = Path("G:/내 드라이브/history_20260507_014523.csv")
OUT = ROOT / "scripts" / "calcy_adb" / "history_merged.csv"


def read(path: Path):
    with path.open(encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r), r.fieldnames


a1, h1 = read(ACC1)
a2, h2 = read(ACC2)

print(f"1번 계정: {len(a1)}건")
print(f"2번 계정: {len(a2)}건")

# 모든 row 에 Account 컬럼 붙이기
for r in a1: r["Account"] = "1"
for r in a2: r["Account"] = "2"

merged = a1 + a2
fieldnames = list(h1) + ["Account"]

with OUT.open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(merged)

print(f"\n저장: {OUT}")
print(f"통합 총 {len(merged)}건")

# 종 단위 분포 빠르게
from collections import Counter
nr = Counter(r["Nr"] for r in merged)
print(f"유니크 Nr (종/폼): {len(nr)}")
nick = Counter(r["Nickname"] for r in merged if r.get("Nickname"))
print(f"유니크 닉네임: {len(nick)}")
print(f"중복 닉네임 (같은 마리 여러 번 스캔): {sum(1 for v in nick.values() if v>1)}마리")
