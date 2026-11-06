"""从泰拉记事社（官方漫画站，公开、免登录）取漫画，只留在本地 Raw Data/漫画/。

    python -m pipeline.comics catalog                 取目录，写 catalog.json
    python -m pipeline.comics download 3114 0694      按 cid 下载整部，可续传
    python -m pipeline.comics sheets 3114             把页面按两页一张拼图，便于读图
    python -m pipeline.comics sample 2864 --pages 6   每部均匀抽几页拼成一张，用来判断值不值得下

图片版权归鹰角网络，目录 Raw Data/ 不进 git，这里只有代码。
每次请求之间留间隔，一次只跑一部的一页，不并发。
"""
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import config

API = "https://comic.hypergryph.com/api/comic"
USER_AGENT = "ArknightsChronicle/0.1 (personal, non-commercial)"
ROOT = config.ROOT / "Raw Data" / "漫画"
GAP = 0.6  # 秒，每次请求之前
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _fetch(url: str, retries: int = 3) -> bytes:
    for attempt in range(retries):
        time.sleep(GAP)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with _opener.open(request, timeout=60) as response:
                return response.read()
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def _api(path: str) -> dict:
    payload = json.loads(_fetch(API + path))
    if payload.get("code") != 0:
        raise RuntimeError(f"{path}: {payload}")
    return payload["data"]


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def _comic_dir(detail: dict) -> Path:
    return ROOT / f"{detail['cid']} {_safe(detail['title'])}"


def _episodes(detail: dict) -> list:
    """接口把最新的一话排在前面，这里按发布顺序排回来。"""
    return list(reversed(detail["episodes"]))


def catalog():
    ROOT.mkdir(parents=True, exist_ok=True)
    details = [_api(f"/{item['cid']}") for item in _api("")]
    (ROOT / "catalog.json").write_text(json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")
    for d in details:
        print(d["cid"], d["title"], len(d["episodes"]), "话")


def download(cid: str):
    detail = _api(f"/{cid}")
    folder = _comic_dir(detail)
    folder.mkdir(parents=True, exist_ok=True)
    index = {"cid": cid, "title": detail["title"], "introduction": detail.get("introduction"),
             "keywords": detail.get("keywords"), "episodes": []}
    fetched = 0
    for order, episode in enumerate(_episodes(detail), 1):
        info = _api(f"/{cid}/episode/{episode['cid']}")
        pages = info.get("pageInfos") or []
        ep_dir = folder / f"{order:02d} {_safe(episode.get('shortTitle') or '')} {_safe(episode['title'])}".replace("  ", " ")
        ep_dir.mkdir(exist_ok=True)
        for number in range(1, len(pages) + 1):
            target = ep_dir / f"p{number:03d}.jpg"
            if target.exists():
                continue
            # 图片地址带时效，只能现取现用
            url = _api(f"/{cid}/episode/{episode['cid']}/page?pageNum={number}")["url"]
            data = _fetch(url)
            temp = target.with_suffix(".part")
            temp.write_bytes(data)
            temp.replace(target)
            fetched += 1
        index["episodes"].append({"eid": episode["cid"], "title": episode["title"], "short": episode.get("shortTitle"),
                                  "time": episode.get("displayTime"), "pages": len(pages), "folder": ep_dir.name})
        print(f"  {ep_dir.name}: {len(pages)} 页", flush=True)
    (folder / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{detail['title']}: 新下 {fetched} 页", flush=True)


def _montage(images: list, target: Path, height: int):
    """把几张页面按同一高度横排拼起来。跨页图更宽，不会被裁。"""
    inputs, chains, tags = [], [], []
    for i, image in enumerate(images):
        inputs += ["-i", str(image)]
        chains.append(f"[{i}:v]scale=-2:{height}[v{i}]")
        tags.append(f"[v{i}]")
    stack = "".join(tags) + (f"hstack=inputs={len(tags)}" if len(tags) > 1 else "null")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + inputs +
                   ["-filter_complex", ";".join(chains) + ";" + stack, "-frames:v", "1", "-q:v", "3", str(target)], check=True)


def sheets(cid: str, per: int = 2, height: int = 1100):
    folders = [p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith(f"{cid} ")]
    if not folders:
        sys.exit(f"还没有下载 {cid}")
    count = 0
    for ep_dir in sorted(p for p in folders[0].iterdir() if p.is_dir()):
        pages = sorted(ep_dir.glob("p*.jpg"))
        out = ep_dir / "sheets"
        out.mkdir(exist_ok=True)
        for n, start in enumerate(range(0, len(pages), per), 1):
            _montage(pages[start:start + per], out / f"s{n:03d}.jpg", height)
            count += 1
    print(f"{folders[0].name}: {count} 张")


def sample(cids: list, pages: int, out: Path):
    """不下整部，只从全部页里均匀抽几页，用来判断这部漫画跟项目有没有关系。"""
    out.mkdir(parents=True, exist_ok=True)
    for cid in cids:
        detail = _api(f"/{cid}")
        spots = []
        for episode in _episodes(detail):
            info = _api(f"/{cid}/episode/{episode['cid']}")
            spots += [(episode["cid"], n) for n in range(1, len(info.get("pageInfos") or []) + 1)]
        # 第一页多是封面，从靠后一点开始取
        step = max(1, len(spots) // (pages + 1))
        chosen = spots[step::step][:pages]
        files = []
        for i, (eid, number) in enumerate(chosen):
            url = _api(f"/{cid}/episode/{eid}/page?pageNum={number}")["url"]
            path = out / f"{cid}_{i}.jpg"
            path.write_bytes(_fetch(url))
            files.append(path)
        _montage(files[:len(files) // 2 or 1], out / f"{cid}_a.jpg", 760)
        if len(files) > 1:
            _montage(files[len(files) // 2:], out / f"{cid}_b.jpg", 760)
        for path in files:
            path.unlink()
        print(f"{cid} {detail['title']}: 抽 {len(chosen)} 页 / 共 {len(spots)} 页", flush=True)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog")
    p = sub.add_parser("download")
    p.add_argument("cids", nargs="+")
    p = sub.add_parser("sheets")
    p.add_argument("cids", nargs="+")
    p.add_argument("--per", type=int, default=2)
    p = sub.add_parser("sample")
    p.add_argument("cids", nargs="+")
    p.add_argument("--pages", type=int, default=4)
    p.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.command == "catalog":
        catalog()
    elif args.command == "download":
        for cid in args.cids:
            download(cid)
    elif args.command == "sheets":
        for cid in args.cids:
            sheets(cid, args.per)
    else:
        sample(args.cids, args.pages, Path(args.out))


if __name__ == "__main__":
    main()
