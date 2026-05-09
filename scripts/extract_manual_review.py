"""
Calcy 가 인식 못한 ?? / 빈 이름 row 만 추출.
사용자가 수기로 이름 채워넣을 수 있게 review_template.csv 생성.

사용법:
  python extract_manual_review.py path/to/history.csv

출력:
  review_template_<날짜>.csv  ← 채워넣을 빈 칸 + 식별 정보 (CP, HP, Lv, 무게, 키, 잡은 날짜·장소)
"""
from __future__ import annotations
import csv
import sys
import io
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

if len(sys.argv) < 2:
    print("사용법: python extract_manual_review.py path/to/history.csv")
    sys.exit(1)

src = Path(sys.argv[1])
if not src.exists():
    print(f"파일 없음: {src}")
    sys.exit(1)

with src.open(encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

print(f"전체 row: {len(rows)}")

# "??" / 빈 이름 / 빈 IV 행 추출
needs_review = []
for r in rows:
    name = (r.get("Name") or "").strip()
    iv = (r.get("ØIV%") or r.get("avg IV%") or "").strip()
    # ?? 표기 또는 IV 가 빈/?
    if not name or "?" in name or not iv or iv in ("?", "-", "??"):
        needs_review.append(r)
    elif name in ("???", "??") or "??" in name:
        needs_review.append(r)

print(f"수기 review 필요: {len(needs_review)} 행 ({len(needs_review)/max(len(rows),1)*100:.1f}%)")

if not needs_review:
    print("\n✅ 다 정상 인식됨 — 수기 작업 불필요")
    sys.exit(0)

# 출력
today = datetime.now().strftime("%Y%m%d_%H%M")
out = src.parent / f"review_template_{today}.csv"

# 사용자가 채우기 쉽게 핵심 컬럼만 + 빈 "수기 이름" 컬럼
key_cols = ["Scan date", "Nr", "Name", "Nickname", "Level", "CP", "HP",
            "ØIV%", "ØATT IV", "ØDEF IV", "ØHP IV",
            "Height (cm)", "Weight (g)", "Catch Date"]

with out.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["수기 이름", "수기 IV (a/d/s)"] + key_cols)
    for r in needs_review:
        w.writerow([
            "",  # ← 사용자가 폰 보고 채워넣음
            "",  # ← IV 도 폰에서 직접 확인
            *[r.get(c, "") for c in key_cols]
        ])

print(f"\n저장: {out}")
print(f"\n사용 흐름:")
print(f"  1. 폰에서 Calcy IV → History 또는 Pokemon GO 박스 해당 마리 확인")
print(f"  2. {out.name} 의 '수기 이름' / '수기 IV' 칸 채우기")
print(f"  3. 사이트 Calcy 분석에 별도 업로드 (또는 원본 CSV 와 합쳐서)")

# 식별 단서로 분류
from collections import Counter
print(f"\n=== 인식 실패 패턴 분석 ===")
empty_name = sum(1 for r in needs_review if not (r.get("Name") or "").strip())
qq_name = sum(1 for r in needs_review if "??" in (r.get("Name") or "") or (r.get("Name") or "").strip() == "?")
no_iv = sum(1 for r in needs_review if not (r.get("ØIV%") or "").strip() or (r.get("ØIV%") or "").strip() in ("?", "-", "??"))
print(f"  이름 빈 행: {empty_name}")
print(f"  ?? 표기 행: {qq_name}")
print(f"  IV 빈 행:   {no_iv}")
