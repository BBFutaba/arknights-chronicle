"""读 PRTS（prts.wiki）页面的本地缓存（data/raw/prts/，git 忽略）。

PRTS 内容采用 CC BY-NC-SA 4.0 协议，仅供个人整理使用，页面上要注明出处。
缓存要先在本机准备好；构建只读缓存，不联网。
"""
import json

from . import config

CACHE = config.ROOT / "data" / "raw" / "prts"
PAGES = ["泰拉年表"]


def cache_path(title: str):
    return CACHE / f"{title.replace('/', '__')}.json"


def load_page(title: str) -> dict:
    p = cache_path(title)
    if not p.exists():
        raise FileNotFoundError(f"没有缓存的 PRTS 页面「{title}」：data/raw/prts/ 里要先有它")
    return json.loads(p.read_text(encoding="utf-8"))
