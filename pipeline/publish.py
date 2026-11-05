"""生成公开版网页，写到 dist/，用来挂 GitHub Pages。

公开版只放编年史和它引用的片段。两样东西留在本地（版权归鹰角网络）：
    data/stories/*.json          剧本全文
    characters.json 的档案正文   干员档案全文（基础档案和编年史里引用的片段还在）

    python -m pipeline.publish
"""
from __future__ import annotations

import json
import shutil
import sys

from .config import ROOT

SITE = ROOT / "site"
DIST = ROOT / "dist"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not (SITE / "data" / "annals.json").exists():
        print("site/data 还没有生成，先运行 python -m pipeline.build")
        return 1
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(SITE, DIST, ignore=shutil.ignore_patterns("stories"))
    path = DIST / "data" / "characters.json"
    chars = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for c in chars.values():
        prof = c.get("profile")
        if prof and prof.get("sections"):
            n += 1
            prof["sections"] = []
    path.write_text(json.dumps(chars, ensure_ascii=False), encoding="utf-8")
    path = DIST / "data" / "meta.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["public"] = True
    path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")
    size = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"公开版写到 {DIST.relative_to(ROOT)}/：{size / 1e6:.1f} MB，去掉了剧本全文和 {n} 位干员的档案正文")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
