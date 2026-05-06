"""
스캔 결과 진단:
- 시간 갭 (조사하기 꺼진 구간)
- 시간당 스캔률
- 중복 스캔 (같은 포켓몬 여러 번)
- 누락 가능성 추정
"""
from __future__ import annotations
import csv
import sys
import io
from datetime import datetime
from pathlib import Path
from collections import Counter

# Windows cp949 콘솔 회피 — UTF-8 강제
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CSV = Path(__file__).parent / "calcy_adb" / "history.csv"

def parse_dt(s: str) -> datetime:
    # "5/7/26 0:13:44"
    return datetime.strptime(s.strip(), "%m/%d/%y %H:%M:%S")

rows = []
with CSV.open(encoding="utf-8") as f:
    r = csv.DictReader(f)
    for row in r:
        try:
            ts = parse_dt(row["Scan date"])
            rows.append((ts, row))
        except Exception:
            pass

# 오름차순 (오래된 → 최신)
rows.sort(key=lambda x: x[0])
n = len(rows)
print(f"총 스캔: {n}")
print(f"시작: {rows[0][0]}")
print(f"종료: {rows[-1][0]}")
total_sec = (rows[-1][0] - rows[0][0]).total_seconds()
print(f"총 시간: {total_sec/60:.1f}분")
print(f"평균 간격: {total_sec/(n-1):.2f}초/스캔")
print()

# 1) 가장 최근 단일 세션만 추리기 — 30분 이상 끊기면 다른 세션
sessions = [[rows[0]]]
for i in range(1, n):
    gap = (rows[i][0] - rows[i-1][0]).total_seconds()
    if gap > 1800:  # 30분
        sessions.append([])
    sessions[-1].append(rows[i])

print(f"세션 수 (30분 이상 끊김 기준): {len(sessions)}")
for i, sess in enumerate(sessions):
    s, e = sess[0][0], sess[-1][0]
    dur = (e - s).total_seconds() / 60
    print(f"  세션 {i+1}: {len(sess):4d}개  {s} → {e}  ({dur:.1f}분)")

# 마지막 세션 = 오늘 자동스캔
print()
print("=== 가장 최근 세션 분석 ===")
sess = sessions[-1]
gaps = []
for i in range(1, len(sess)):
    g = (sess[i][0] - sess[i-1][0]).total_seconds()
    gaps.append((g, sess[i-1][1].get("Name",""), sess[i][1].get("Name",""), sess[i-1][0], sess[i][0]))

# 간격 통계
gs = [g[0] for g in gaps]
gs_sorted = sorted(gs)
print(f"중간값 간격: {gs_sorted[len(gs)//2]:.2f}초")
print(f"95%: {gs_sorted[int(len(gs)*0.95)]:.2f}초")
print(f"최대: {max(gs):.2f}초")

# 갭 분류:
#  5~120초    → Calcy 조사하기 드롭아웃 가능성 (진짜 문제)
#  120~600초  → 알림/짧은 자리비움 (보통 사용자가 끼어든 것)
#  >600초     → 명백한 일시정지 (스캔 자체 멈춤)
dropout = [g for g in gaps if 5 <= g[0] < 120]
medium  = [g for g in gaps if 120 <= g[0] < 600]
pause   = [g for g in gaps if g[0] >= 600]

print(f"\n갭 분류:")
print(f"  Calcy 드롭아웃 의심 (5~120s): {len(dropout)}건")
print(f"  중간 끊김 (2~10min):          {len(medium)}건")
print(f"  명백한 일시정지 (>10min):      {len(pause)}건")

print(f"\n=== Calcy 드롭아웃 의심 구간 (top 20) ===")
for g in sorted(dropout, key=lambda x: -x[0])[:20]:
    print(f"  {g[0]:6.1f}s  {g[3].strftime('%H:%M:%S')}  {g[1]:>12} -> {g[2]}")

print(f"\n=== 중간 끊김 (사용자 자리비움?) ===")
for g in medium:
    print(f"  {g[0]:6.1f}s ({g[0]/60:5.1f}min)  {g[3].strftime('%H:%M:%S')} -> {g[4].strftime('%H:%M:%S')}")

print(f"\n=== 명백한 일시정지 ===")
for g in pause:
    print(f"  {g[0]/60:5.1f}min  {g[3].strftime('%H:%M:%S')} -> {g[4].strftime('%H:%M:%S')}")

# 빈 스와이프 추정 — 드롭아웃 구간만 카운트
swipe_interval = 1.3
lost_swipes = sum(int((g[0] - 1.3) / swipe_interval) for g in dropout)
print(f"\nCalcy 드롭아웃 동안 헛스와이프 추정: ~{lost_swipes}회")
print(f"  = 그동안 박스에서 ~{lost_swipes}마리 그냥 넘어간 셈 (다시 스캔 필요할 수도)")

# 2) 중복 (같은 포켓몬 닉네임) — 같은 마리를 두 번 찍은 것
print(f"\n=== 같은 마리 중복 스캔 ===")
nickname_cnt = Counter(r[1].get("Nickname","") for r in sess)
dup = [(k,v) for k,v in nickname_cnt.items() if v > 1 and k]
dup.sort(key=lambda x: -x[1])
total_dup = sum(v-1 for _,v in dup)
print(f"유니크 닉네임: {sum(1 for k,v in nickname_cnt.items() if k)}")
print(f"중복 row: {total_dup}건 ({len(dup)}마리가 2회+ 찍힘)")
print(f"가장 많이 중복:")
for nm, cnt in dup[:10]:
    print(f"  {cnt}회  {nm}")

# 3) 종(Nr) 분포 — IV 가 같은 마리는 닉네임이 같아 위에서 잡힘
# 박스에 같은 종 여러 마리 있는 건 정상

# 4) 데이터 품질 — IV "?" 또는 빈 값
bad_iv = sum(1 for r in sess if r[1].get("ØIV%","") in ("","?","-"))
print(f"\nIV 미인식 row: {bad_iv}/{len(sess)}")
