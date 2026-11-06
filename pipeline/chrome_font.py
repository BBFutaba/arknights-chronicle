"""把网页界面文字用到的汉字从 Noto Sans SC 可变字体里切出来，写到 site/fonts/。

完整字体 17 MB，网页只带界面上写死的字（标签名、站名、字幕），正文仍用系统字体。
界面文字改了就重跑一次，否则新字会退回系统字体。

需要 fonttools 和 brotli，这两个不是网页和流水线的依赖，只有这个脚本用：
    python -X utf8 -m pipeline.chrome_font <NotoSansSC 可变字体路径>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "site/index.html", ROOT / "site/js/station.js"]
OUT = ROOT / "site/fonts/NotoSansSC-chrome.woff2"


def chrome_chars() -> str:
    text = ""
    for path in SOURCES:
        src = path.read_text(encoding="utf-8")
        # 注释不上屏，别把注释里的字也切进去
        src = re.sub(r"<!--.*?-->|/\*.*?\*/", "", src, flags=re.S)
        text += re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return "".join(sorted({c for c in text if ord(c) > 0x2E7F}))


def make(font_path: str, chars: str, out: Path) -> int:
    font = TTFont(font_path)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "vert", "locl", "ccmp"]
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]
    opts.notdef_outline = True
    s = subset.Subsetter(opts)
    s.populate(text=chars)
    s.subset(font)
    font.flavor = "woff2"
    out.parent.mkdir(parents=True, exist_ok=True)
    font.save(out)
    return out.stat().st_size


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    chars = chrome_chars()
    size = make(sys.argv[1], chars, OUT)
    print(f"{OUT.name}：{len(chars)} 字，{size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
