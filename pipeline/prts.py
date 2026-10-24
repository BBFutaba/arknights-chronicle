"""从 PRTS（prts.wiki）抓取少量页面的源码并缓存到 data/raw/prts/。

PRTS 内容采用 CC BY-NC-SA 4.0 协议，仅供个人整理使用，页面上要注明出处。
PRTS 对连续请求比较敏感，这里每次只抓需要的几页，请求之间留间隔，结果缓存后不再重复请求。
用 curl 而不是 urllib：Python 自带的证书校验认不了 prts.wiki 的证书链。
"""
import json
import subprocess
import time
import urllib.parse

from . import config

API = "https://prts.wiki/api.php"
USER_AGENT = "ArknightsStoryTeller/0.1 (personal, non-commercial)"
CACHE = config.ROOT / "data" / "raw" / "prts"
PAGES = ["泰拉年表"]


def cache_path(title: str):
    return CACHE / f"{title.replace('/', '__')}.json"


def fetch_page(title: str) -> dict:
    params = {
        "action": "query", "titles": title, "prop": "revisions", "rvprop": "content|timestamp|ids",
        "rvslots": "main", "redirects": "1", "format": "json",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    out = subprocess.run(["curl", "-s", "-f", "-m", "60", "-A", USER_AGENT, url],
                         capture_output=True, check=True)
    page = next(iter(json.loads(out.stdout)["query"]["pages"].values()))
    if "missing" in page:
        raise RuntimeError(f"PRTS 上没有页面：{title}")
    rev = page["revisions"][0]
    return {"title": page["title"], "revid": rev["revid"], "timestamp": rev["timestamp"],
            "content": rev["slots"]["main"]["*"]}


def load_page(title: str) -> dict:
    p = cache_path(title)
    if not p.exists():
        raise FileNotFoundError(f"没有缓存的 PRTS 页面「{title}」，请先运行：python -m pipeline.fetch")
    return json.loads(p.read_text(encoding="utf-8"))


def fetch_all(refresh: bool = False):
    CACHE.mkdir(parents=True, exist_ok=True)
    for i, title in enumerate(PAGES):
        p = cache_path(title)
        if p.exists() and not refresh:
            print(f"PRTS「{title}」已缓存，跳过（--refresh 可强制更新）")
            continue
        if i:
            time.sleep(3)
        page = fetch_page(title)
        p.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
        print(f"PRTS「{title}」：修订 {page['revid']}（{page['timestamp']}），{len(page['content'])} 字")
