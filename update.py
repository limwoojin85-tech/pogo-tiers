"""
모든 데이터 자동 업데이트 + HTML 재생성.

기본 동작:
  - 데이터 파일이 24시간 이상 오래되면 다시 받음
  - 항상 HTML 은 다시 빌드

옵션:
  --force      : 무조건 모든 fetcher 재실행
  --no-fetch   : fetcher 스킵, HTML 만 재빌드 (디버깅)
  --max-age=H  : 오래됨 기준 (기본 24시간)

Windows Task Scheduler 자동 실행 등록 예시 (관리자 PowerShell):
  schtasks /Create /SC DAILY /TN "pogo_tiers update" /TR "python C:\\Users\\limwo\\새 폴더\\pogo_tiers\\update.py" /ST 06:00
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"


def is_fresh(path: Path, max_age_h: float) -> bool:
    if not path.exists():
        return False
    age_h = (time.time() - path.stat().st_mtime) / 3600
    return age_h < max_age_h


def run(script: str) -> None:
    print(f"\n=== {script} ===")
    r = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT)
    if r.returncode != 0:
        print(f"!! {script} 실패 (exit {r.returncode})", file=sys.stderr)
        sys.exit(r.returncode)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--max-age", type=float, default=24)
    args = ap.parse_args()

    do_pvpoke = args.force or not is_fresh(DATA / "pvpoke" / "_gamemaster.json", args.max_age)
    do_pb = args.force or not is_fresh(DATA / "pokebattler" / "tiers.json", args.max_age)
    do_trans = args.force or not is_fresh(DATA / "translations.json", args.max_age * 7)
    do_egg = args.force or not is_fresh(DATA / "egg_pool.json", args.max_age * 3)
    # 번역은 거의 안 바뀜 → 일주일
    # 알 풀은 시즌 단위 갱신 (~3일 주기로 충분)

    if args.no_fetch:
        do_pvpoke = do_pb = do_trans = do_egg = False

    print(f"[update] pvpoke={do_pvpoke}, pokebattler={do_pb}, "
          f"translations={do_trans}, egg_pool={do_egg}")

    if do_pvpoke:
        run("fetch_pvpoke.py")
    if do_pb:
        run("fetch_pokebattler.py")
    if do_trans:
        run("fetch_translations.py")
    if do_egg:
        run("fetch_egg_pool.py")

    run("must_have.py")
    run("build_html.py")
    print("\n[update] 완료 ✓")


if __name__ == "__main__":
    main()
