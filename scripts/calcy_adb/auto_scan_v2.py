r"""
Calcy IV 자동 스캔 v2 — 이미지 인식으로 끝 감지 + 드롭아웃 감지

기능:
  1. 첫 마리 이미지 hash 저장 → 다시 등장하면 박스 한 바퀴 완료 → 자동 정지
  2. 매 10 swipe 마다 팀 리더 (블랜치/캔디라/스파크) 픽셀 체크
     → 안 보이면 = 조사하기 풀림 → 비프 + 콘솔 알림
  3. 같은 Pokemon 이미지가 swipe 후에도 안 바뀌면 → swipe 안 먹힘 알림

사용법 (Windows PowerShell):
  cd "C:\Users\limwo\새 폴더\pogo_tiers\scripts\calcy_adb"
  python auto_scan_v2.py [count]

  count 안 주면 박스 한 바퀴 다 돌면 자동 정지 (최대 2000)
"""
from __future__ import annotations
import sys
import io
import time
import subprocess
import hashlib
import argparse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

try:
    from PIL import Image
except ImportError:
    print("[!] Pillow 필요 — pip install pillow")
    sys.exit(1)

try:
    import imagehash
    HAVE_PHASH = True
except ImportError:
    HAVE_PHASH = False
    print("[warn] imagehash 없음 — pip install imagehash 권장 (perceptual hash 안정성↑)")

ROOT = Path(__file__).parent
ADB = str(ROOT / "platform-tools" / "adb.exe")
SHOT_DIR = ROOT / "_shots"
SHOT_DIR.mkdir(exist_ok=True)

# 갤럭시 Z Fold 4 커버 화면 (904×2316) 기준
DISPLAY_ID = "4630946213010294403"
SWIPE_X1, SWIPE_Y = 750, 300
SWIPE_X2 = 150
SWIPE_DUR = 600  # ms
DELAY_S = 2.5

# Pokemon 식별 영역 — 개체값 IV 바 (왼쪽 하단)
# 마리마다 IV 고유 → 바 고유 → hash 고유. 같은 종 다른 IV 도 구분됨.
# 904×2316 cover 화면 검증: 같은 마리 2회 캡처 phash distance=0
POKE_BOX = (100, 1860, 500, 2080)

# 조사하기 검출 — Mystic 리더 (블랜치) 얼굴이 화면에 있는지
# 조사하기 ON: 블랜치 앉아있음 (큰 파란 영역). OFF: 사라짐 (일반 detail 화면)
# 904×2316 cover 기준, Mystic 팀 (파란 유니폼). Valor=빨강 / Instinct=노랑이면 색 다름.
LEADER_BOX = (450, 1300, 900, 1700)
LEADER_TEAM = "mystic"  # mystic / valor / instinct


def adb(*args, capture=False):
    cmd = [ADB] + list(args)
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return subprocess.run(cmd, capture_output=False)


def screenshot() -> Image.Image | None:
    """Pull current display screenshot."""
    adb("shell", f"screencap -p -d {DISPLAY_ID} /sdcard/_p.png")
    path = SHOT_DIR / "_v2_current.png"
    res = adb("pull", "/sdcard/_p.png", str(path), capture=True)
    adb("shell", "rm /sdcard/_p.png")
    if not path.exists():
        return None
    try:
        return Image.open(path).copy()
    except Exception as e:
        print(f"[!] 이미지 열기 실패: {e}")
        return None


def hash_region(img: Image.Image, box: tuple):
    """이미지 영역 crop → perceptual hash (rendering noise 에 강함).
    imagehash 있으면 phash, 없으면 fallback 으로 grayscale MD5."""
    crop = img.crop(box)
    if HAVE_PHASH:
        return imagehash.phash(crop, hash_size=8)
    # fallback — grayscale + heavy downsample
    gray = crop.resize((16, 16), Image.LANCZOS).convert("L")
    return hashlib.md5(gray.tobytes()).hexdigest()[:12]


def hash_match(h1, h2, threshold=8):
    """두 hash 가 같은 Pokemon 인지. phash 면 hamming distance 비교, 아니면 정확 일치."""
    if HAVE_PHASH and hasattr(h1, '__sub__'):
        return (h1 - h2) <= threshold
    return h1 == h2


def detect_appraisal(img: Image.Image) -> bool:
    """조사하기 ON 여부 — 화면에 팀 리더 (Mystic=블랜치) 얼굴 있는지.
    리더가 보이면 조사하기 active. 사라졌으면 풀림."""
    crop = img.crop(LEADER_BOX).convert("RGB")
    pixels = list(crop.getdata())
    if not pixels:
        return False
    if LEADER_TEAM == "mystic":
        # 파란 유니폼 픽셀
        team_pixels = sum(1 for r, g, b in pixels if b > 130 and b > r + 30)
    elif LEADER_TEAM == "valor":
        # 빨간 유니폼
        team_pixels = sum(1 for r, g, b in pixels if r > 130 and r > b + 30 and r > g + 20)
    elif LEADER_TEAM == "instinct":
        # 노란 유니폼
        team_pixels = sum(1 for r, g, b in pixels if r > 180 and g > 150 and b < 100)
    else:
        team_pixels = 0
    pct = team_pixels / len(pixels) * 100
    # 큰 영역에 팀 색이 모이면 리더 등장 → 조사하기 ON
    return pct > 15


def swipe():
    adb("shell", f"input swipe {SWIPE_X1} {SWIPE_Y} {SWIPE_X2} {SWIPE_Y} {SWIPE_DUR}")


def beep():
    """Windows 비프 (PowerShell 호출)."""
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", "[console]::beep(1500, 300)"],
                       capture_output=True, timeout=2)
    except Exception:
        print("\a", end="", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("count", type=int, nargs="?", default=2000,
                    help="최대 스와이프 (기본 2000 — 한 바퀴 자동 감지로 보통 더 일찍 끝)")
    ap.add_argument("--check-every", type=int, default=10,
                    help="이미지 체크 주기 (기본 10 swipe 마다)")
    ap.add_argument("--no-stop-on-loop", action="store_true",
                    help="박스 한 바퀴 돌아도 안 멈춤")
    args = ap.parse_args()

    print("=" * 60)
    print(f"  자동 스캔 v2 — 이미지 인식")
    print(f"  최대 {args.count} 스와이프, {args.check_every} 회마다 체크")
    print("=" * 60)
    print()

    # 초기 스크린샷
    print("[init] 첫 마리 이미지 hash 저장...")
    img0 = screenshot()
    if img0 is None:
        print("[err] 초기 스크린샷 실패")
        return
    poke_hash_0 = hash_region(img0, POKE_BOX)
    print(f"  첫 마리 hash: {poke_hash_0}")
    if not detect_appraisal(img0):
        print("[!] 팀 리더 안 보임 — 시작 전 Pokemon GO 조사하기 ON 확인")

    seen = {str(poke_hash_0)}
    last_poke_hash = poke_hash_0
    appraisal_off_streak = 0
    same_pic_streak = 0
    start = time.time()

    for i in range(1, args.count + 1):
        swipe()
        time.sleep(DELAY_S)

        if i % args.check_every != 0:
            continue

        img = screenshot()
        if img is None:
            print(f"[{i}] 스크린샷 실패 — skip")
            continue

        poke_hash = hash_region(img, POKE_BOX)
        appraisal_on = detect_appraisal(img)

        # 끝 감지 — 첫 마리 다시 등장 (phash hamming distance ≤ 8)
        if i >= args.check_every * 2 and not args.no_stop_on_loop:
            if hash_match(poke_hash, poke_hash_0):
                elapsed = time.time() - start
                print()
                print("=" * 60)
                print(f"✅ 박스 한 바퀴 완료 — 첫 마리 다시 등장")
                print(f"  스와이프: {i} 회")
                print(f"  유니크 화면: {len(seen)} (= 박스 추정 마릿수)")
                print(f"  소요: {elapsed/60:.1f}분")
                print(f"  조사하기 풀림 감지: {appraisal_off_streak}회 (현재 streak)")
                print("=" * 60)
                return

        # 같은 화면 — swipe 안 먹힘?
        if hash_match(poke_hash, last_poke_hash, threshold=4):
            same_pic_streak += 1
            if same_pic_streak >= 2:
                print(f"[{i}] ⚠️ 화면 안 바뀜 ({same_pic_streak}회) — swipe 막힘? Pokemon GO 확인")
                beep()
        else:
            same_pic_streak = 0
            seen.add(str(poke_hash))

        # 조사하기 ON/OFF 체크 — 팀 리더 등장 여부
        if not appraisal_on:
            appraisal_off_streak += 1
            elapsed = time.time() - start
            print(f"[{i}] ⚠️ 팀 리더 안 보임 ({appraisal_off_streak}회) — 조사하기 풀림")
            if appraisal_off_streak >= 2:
                print(f"     🚨 {appraisal_off_streak}회 연속 — 폰에서 조사하기 다시 ON 필요")
                beep()
        else:
            if appraisal_off_streak > 0:
                print(f"[{i}] ✅ 조사하기 복귀")
            appraisal_off_streak = 0

        # 진행률
        elapsed = time.time() - start
        rate = i / elapsed * 60 if elapsed > 0 else 0
        print(f"[{i}/{args.count}] {len(seen)} 유니크 · {rate:.1f}/분 · "
              f"hash={poke_hash} · 조사하기 {'✅' if appraisal_on else '❌'}")
        last_poke_hash = poke_hash

    elapsed = time.time() - start
    print()
    print(f"=== 종료 (max count 도달) ===")
    print(f"  스와이프: {args.count}, 유니크: {len(seen)}, {elapsed/60:.1f}분")


if __name__ == "__main__":
    main()
