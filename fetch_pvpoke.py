"""
pvpoke 랭킹 일괄 다운로더.

src/data/rankings/{league}/overall/rankings-{cp}.json 전체를 받아
data/pvpoke/{league}_{cp}.json 로 저장.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "data" / "pvpoke"
OUT_DIR.mkdir(parents=True, exist_ok=True)

GH_API = "https://api.github.com/repos/pvpoke/pvpoke/contents/src/data/rankings"
RAW = "https://raw.githubusercontent.com/pvpoke/pvpoke/master/src/data/rankings"

UA = {"User-Agent": "pogo-tiers-fetcher/1.0"}


def gh_json(url: str) -> list | dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def list_leagues() -> list[str]:
    items = gh_json(GH_API)
    return [i["name"] for i in items if i["type"] == "dir"]


def list_overall_files(league: str) -> list[str]:
    try:
        items = gh_json(f"{GH_API}/{league}/overall")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    return [i["name"] for i in items if i["name"].startswith("rankings-") and i["name"].endswith(".json")]


def download(league: str, fname: str) -> Path:
    cp = fname.removeprefix("rankings-").removesuffix(".json")
    out = OUT_DIR / f"{league}_{cp}.json"
    url = f"{RAW}/{league}/overall/{fname}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        out.write_bytes(r.read())
    return out


def fetch_gamemaster() -> None:
    """gamemaster.json — 종 메타 + rank1 IV 등 핵심 메타데이터."""
    url = "https://raw.githubusercontent.com/pvpoke/pvpoke/master/src/data/gamemaster.json"
    out = OUT_DIR / "_gamemaster.json"
    print("[pvpoke] gamemaster.json 다운로드")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        out.write_bytes(r.read())


def main() -> None:
    fetch_gamemaster()
    leagues = list_leagues()
    print(f"[pvpoke] {len(leagues)} 리그/컵 발견")

    manifest: dict[str, list[str]] = {}
    total = 0

    for lg in leagues:
        files = list_overall_files(lg)
        if not files:
            continue
        manifest[lg] = []
        for f in files:
            try:
                p = download(lg, f)
                manifest[lg].append(p.name)
                total += 1
                print(f"  {p.name}")
            except Exception as e:
                print(f"  ! {lg}/{f}: {e}", file=sys.stderr)
            time.sleep(0.05)

    (OUT_DIR / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[pvpoke] 완료: {total} 파일 → {OUT_DIR}")


if __name__ == "__main__":
    main()
