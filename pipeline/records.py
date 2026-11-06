"""《泰拉记事》：官方微博发的剧中文件（简报、档案、信件之类），PRTS「泰拉记事」页汇总并存了原图。

    python -X utf8 -m pipeline.records index      抓页面源码，列出篇目，写 Raw Data/泰拉记事/index.json
    python -X utf8 -m pipeline.records download   下载原图，可以续传，已下完的不再请求
    python -X utf8 -m pipeline.records list       列出篇目

原图放在 Raw Data/泰拉记事/<编号> <日期> <篇名>/NN.jpg，同目录的 说明.txt 是微博配文。
版权属于鹰角网络，只留在本地，不上传，不进公开站。
PRTS 对连续请求比较敏感：请求之间留间隔，遇到 403/429 就停下，不换身份重试。
"""
import json
import re
import subprocess
import sys
import time
import urllib.parse

from . import config, prts

OUT = config.ROOT / "Raw Data" / "泰拉记事"
INDEX = OUT / "index.json"
PAGE = "泰拉记事"
GAP = 3.0  # 秒，两次请求之间
IMAGE = re.compile(r"\|\s*([^|\n<>{}\[\]]+\.(?:jpe?g|png|gif|webp))", re.I)
HEAD = re.compile(r"^(={2,3})\s*(.*?)\s*\1\s*$", re.M)
BLOCK = re.compile(r"\{\{微博\|\[(\S+)\s+(\d{4}-\d{2}-\d{2})\s*(.*?)\]\s*(.*?)\n?\}\}", re.S)


def safe_name(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', " ", text).strip()[:60].strip(". ")


def parse(source: str) -> list[dict]:
    """页面源码 -> 篇目表。分组取最近的二级、三级标题。"""
    marks = [(m.start(), len(m.group(1)), m.group(2)) for m in HEAD.finditer(source)]
    docs = []
    for m in BLOCK.finditer(source):
        group = sub = ""
        for pos, level, name in marks:
            if pos > m.start():
                break
            if level == 2:
                group, sub = name, ""
            else:
                sub = name
        url, date, title, rest = m.groups()
        poem = re.search(r"<poem>(.*?)</poem>", rest, re.S)
        note = poem.group(1).strip() if poem else ""
        names = [n.strip() for n in IMAGE.findall(re.sub(r"<poem>.*?</poem>", "", rest, flags=re.S))]
        docs.append({"no": len(docs) + 1, "group": group, "sub": sub, "date": date,
                     "title": title.strip() or sub or date, "weibo": url, "note": note,
                     "images": [{"name": n} for n in names]})
    return docs


def folder(doc: dict):
    return OUT / safe_name(f"{doc['no']:02d} {doc['date']} {doc['title']}")


def api_get(params: dict) -> dict:
    url = f"{prts.API}?{urllib.parse.urlencode(params)}"
    out = subprocess.run(["curl", "-s", "-f", "-m", "60", "-A", prts.USER_AGENT, url], capture_output=True, check=True)
    return json.loads(out.stdout)


def resolve(docs: list[dict]) -> None:
    """用 imageinfo 查每张图的地址和大小，每次最多 50 个。"""
    images = [im for d in docs for im in d["images"]]
    for start in range(0, len(images), 50):
        batch = images[start:start + 50]
        data = api_get({"action": "query", "prop": "imageinfo", "iiprop": "url|size", "format": "json",
                        "titles": "|".join(f"File:{im['name']}" for im in batch)})["query"]
        renamed = {n["from"]: n["to"] for n in data.get("normalized", [])}
        pages = {p["title"]: p for p in data["pages"].values()}
        for im in batch:
            page = pages.get(renamed.get(f"File:{im['name']}", f"File:{im['name']}"), {})
            info = (page.get("imageinfo") or [{}])[0]
            im.update(url=info.get("url", ""), size=info.get("size", 0), width=info.get("width", 0), height=info.get("height", 0))
        time.sleep(GAP)


def index() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page = prts.fetch_page(PAGE)
    time.sleep(GAP)
    docs = parse(page["content"])
    resolve(docs)
    INDEX.write_text(json.dumps({"revid": page["revid"], "timestamp": page["timestamp"], "docs": docs},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    images = [im for d in docs for im in d["images"]]
    print(f"{len(docs)} 篇，{len(images)} 张图，共 {sum(im['size'] for im in images) / 1e6:.0f} MB，"
          f"查不到地址的 {sum(1 for im in images if not im['url'])} 张")


def fetch(url: str, target) -> int:
    """下载到 target，返回 HTTP 状态码。curl 不用 -f，好拿到状态码。"""
    tmp = target.with_name(target.name + ".part")
    out = subprocess.run(["curl", "-s", "-m", "240", "-A", prts.USER_AGENT, "-o", str(tmp), "-w", "%{http_code}", url],
                         capture_output=True, text=True)
    code = int(out.stdout or 0)
    if code == 200:
        tmp.replace(target)
    else:
        tmp.unlink(missing_ok=True)
    return code


def download() -> None:
    docs = json.loads(INDEX.read_text(encoding="utf-8"))["docs"]
    got = failed = skipped = 0
    for doc in docs:
        where = folder(doc)
        where.mkdir(exist_ok=True)
        (where / "说明.txt").write_text(f"{doc['date']} {doc['title']}\n分组：{doc['group']} / {doc['sub']}\n"
                                        f"微博：{doc['weibo']}\n\n{doc['note']}\n", encoding="utf-8")
        for i, im in enumerate(doc["images"], 1):
            suffix = im["name"].rsplit(".", 1)[-1].lower()
            target = where / f"{i:02d}.{suffix}"
            im["file"] = f"{where.name}/{target.name}"
            if target.exists() and target.stat().st_size == im["size"]:
                skipped += 1
                continue
            if not im["url"]:
                print("没有地址", doc["no"], im["name"], flush=True)
                failed += 1
                continue
            for attempt in range(3):
                code = fetch(im["url"], target)
                time.sleep(GAP)
                if code == 200 or code in (403, 429):
                    break
                time.sleep(10 * (attempt + 1))
            if code in (403, 429):
                sys.exit(f"PRTS 返回 {code}，停下。已下 {got} 张，稍后再续。")
            if code != 200 or target.stat().st_size != im["size"]:
                print("失败", code, doc["no"], im["name"], flush=True)
                failed += 1
                continue
            got += 1
        print(f"{doc['no']:02d} {doc['date']} {doc['title']}（{len(doc['images'])} 张）", flush=True)
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    data["docs"] = docs
    INDEX.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"新下 {got} 张，跳过 {skipped} 张，失败 {failed} 张")


def show() -> None:
    for d in json.loads(INDEX.read_text(encoding="utf-8"))["docs"]:
        print(f"{d['no']:02d} {d['date']} [{d['group']}/{d['sub']}] {d['title']}（{len(d['images'])} 张）")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "index":
        index()
    elif command == "download":
        download()
    elif command == "list":
        show()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
