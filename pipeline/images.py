"""干员立绘和头像：从社区公开的游戏资源仓库按需下载，缩成网页用的 webp，写到 site/img/。

    python -X utf8 -m pipeline.images           下载缺的原图，生成缺的缩图
    python -X utf8 -m pipeline.images --plan    只列出要下载多少、哪些干员没有图，不下载
    python -X utf8 -m pipeline.images --force   缩图全部重做（原图已下载的不重下）

来源（只取用到的文件，不克隆仓库；目录清单用 GitHub 的 trees 接口，缓存一天）：
    泰拉    yuanyan3060/ArknightsGameResource   avatar/<id>.png（头像）、skin/<id>_1b.png（立绘，初始形态）
    终末地  555me/EndfieldAssets                 .../sprites/charicon/icon_<id>.png（头像）、
                                                 .../sprites/characterportrait/<id>.png（立绘）
每个人物页取 char_ids 里第一个有图的 id（异格并入本体的用本体的图，终末地管理员用 chr_0002_endminm）。

原图存 data/raw/images/（git 忽略），按 git blob 的 SHA-1 校验，上游更新了才重下；
缩图写 site/img/avatar/<id>.webp（128×128）和 site/img/portrait/<id>.webp（高 720），也被 git 忽略：
游戏美术版权归鹰角网络，不进仓库，只随公开版网页（dist/）发布。

缩图要 Pillow（本机系统 Python 已装）。pipeline.build 不依赖它，只看 site/img/ 里有哪些图，
有的才在 characters.json 里写 avatar、portrait 字段。所以顺序是：先跑这个，再跑 pipeline.build。
遇到 403/429 就停，不换身份硬闯；环境变量 GITHUB_TOKEN 有值时目录清单请求带上它。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config, endfield
from .entities import Registry

RAW = config.ROOT / "data" / "raw" / "images"
OUT = config.SITE / "img"
UA = {"User-Agent": "image-fetch/1.0"}
PAUSE = 0.4  # 两次下载之间停一会儿
AVATAR_SIZE = 128
PORTRAIT_HEIGHT = 720
TREE_TTL = 24 * 3600

TERRA = "yuanyan3060/ArknightsGameResource"
ENDFIELD = "555me/EndfieldAssets"
EF_SPRITES = "assets/beyond/dynamicassets/gameplay/ui/sprites"
SOURCES = {  # (仓库, 分支, 目录) → 本地原图目录
    "terra/avatar": (TERRA, "main", "avatar"),
    "terra/skin": (TERRA, "main", "skin"),
    "endfield/charicon": (ENDFIELD, "main", f"{EF_SPRITES}/charicon"),
    "endfield/characterportrait": (ENDFIELD, "main", f"{EF_SPRITES}/characterportrait"),
}


class Blocked(Exception):
    """上游拒绝（403/429）：停下，不重试。"""


def get(url: str, headers=None) -> bytes:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise Blocked(f"{e.code} {url}") from e
        raise


def listing(key: str, refresh: bool) -> dict[str, dict]:
    """目录清单：文件名 → {sha, size}。缓存在 data/raw/images/trees/。"""
    repo, branch, path = SOURCES[key]
    cache = RAW / "trees" / (key.replace("/", "-") + ".json")
    if not refresh and cache.exists() and time.time() - cache.stat().st_mtime < TREE_TTL:
        return json.loads(cache.read_text(encoding="utf-8"))
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    ref = urllib.parse.quote(f"{branch}:{path}", safe=":/")
    tree = json.loads(get(f"https://api.github.com/repos/{repo}/git/trees/{ref}", headers))
    if tree.get("truncated"):
        print(f"  ! {repo}/{path} 的清单被截断，可能漏图")
    files = {e["path"]: {"sha": e["sha"], "size": e["size"]} for e in tree["tree"] if e["type"] == "blob"}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(files, ensure_ascii=False), encoding="utf-8")
    return files


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# ---------------------------------------------------------------------- 选图
def terra_ids() -> dict[str, list[str]]:
    reg = Registry()
    ops = {id(c): c for c in reg.chars.values() if c.kind == "operator"}
    return {c.name: list(c.char_ids) for c in ops.values()}


def endfield_ids() -> dict[str, list[str]]:
    if not (config.ENDFIELD / "TableCfg" / "CharacterTable.json").exists():
        print("终末地：未发现本机客户端数据，跳过。")
        return {}
    loader = endfield.Loader(config.ENDFIELD)
    loader.load_operators()
    return {endfield.PREFIX + name: op["ids"] for name, op in loader.operators.items()}


def terra_pick(cid: str, avatars: dict, skins: dict) -> tuple[str | None, str | None]:
    avatar = next((f for f in (f"{cid}.png", f"{cid}_2.png") if f in avatars), None)
    portrait = next((f for f in (f"{cid}_1b.png", f"{cid}_1+b.png", f"{cid}_2b.png") if f in skins), None)
    portrait = portrait or next((f for f in sorted(skins) if f.startswith(cid + "_") and f.endswith("b.png")), None)
    return avatar, portrait


def plan(refresh: bool):
    """[(人物, id, 种类, 本地原图目录, 文件名)]，以及缺图的人物。"""
    lists = {k: listing(k, refresh) for k in SOURCES}
    jobs, missing = [], {"avatar": [], "portrait": []}

    def choose(name, ids, pick, keys):
        got = {"avatar": None, "portrait": None}
        for cid in ids:  # 头像和立绘尽量取同一个 id
            a, p = pick(cid)
            if a and p:
                got = {"avatar": (cid, a), "portrait": (cid, p)}
                break
            got["avatar"] = got["avatar"] or (a and (cid, a))
            got["portrait"] = got["portrait"] or (p and (cid, p))
        for kind, key in zip(("avatar", "portrait"), keys):
            if got[kind]:
                cid, f = got[kind]
                jobs.append((name, cid, kind, key, f))
            else:
                missing[kind].append(name)

    for name, ids in sorted(terra_ids().items()):
        choose(name, ids, lambda cid: terra_pick(cid, lists["terra/avatar"], lists["terra/skin"]),
               ("terra/avatar", "terra/skin"))
    for name, ids in sorted(endfield_ids().items()):
        choose(name, ids, lambda cid: (f"icon_{cid}.png" if f"icon_{cid}.png" in lists["endfield/charicon"] else None,
                                       f"{cid}.png" if f"{cid}.png" in lists["endfield/characterportrait"] else None),
               ("endfield/charicon", "endfield/characterportrait"))
    return jobs, missing, lists


# ---------------------------------------------------------------------- 下载和缩图
def fetch(key: str, fname: str, meta: dict) -> bool:
    """原图不在或校验不符就下载；返回是否下载了。"""
    path = RAW / key / fname
    if path.exists() and path.stat().st_size == meta["size"] and blob_sha(path.read_bytes()) == meta["sha"]:
        return False
    repo, branch, folder = SOURCES[key]
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/" + urllib.parse.quote(f"{folder}/{fname}")
    data = get(url)
    if blob_sha(data) != meta["sha"]:
        raise RuntimeError(f"校验不符：{url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    time.sleep(PAUSE)
    return True


def make_avatar(src, dst):
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    if w != h:  # 终末地头像是竖的：取上偏中的正方形，脸在上半
        s = min(w, h)
        top = int((h - s) * 0.35)
        left = (w - s) // 2
        im = im.crop((left, top, left + s, top + s))
    im = im.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
    im.save(dst, "WEBP", quality=82, method=6)


def make_portrait(src, dst):
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    if box := im.getchannel("A").getbbox():
        im = im.crop(box)
    w, h = im.size
    scale = min(1.0, PORTRAIT_HEIGHT / h, 1000 / w)
    if scale < 1:
        im = im.resize((round(w * scale), round(h * scale)), Image.Resampling.LANCZOS)
    im.save(dst, "WEBP", quality=80, method=6)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="下载干员立绘和头像，缩成 site/img/ 下的 webp")
    ap.add_argument("--plan", action="store_true", help="只列出计划，不下载")
    ap.add_argument("--force", action="store_true", help="缩图全部重做")
    ap.add_argument("--refresh", action="store_true", help="不用缓存的目录清单")
    args = ap.parse_args()

    try:
        jobs, missing, lists = plan(args.refresh)
    except Blocked as e:
        print(f"GitHub 拒绝了目录清单请求（{e}），停下。过一会儿再试，或设置 GITHUB_TOKEN。")
        return 1
    files = {(key, f) for _, _, _, key, f in jobs}
    need = [(k, f) for k, f in sorted(files) if not (RAW / k / f).exists()]
    size = sum(lists[k][f]["size"] for k, f in need)
    terra = {n for n, cid, *_ in jobs if not n.startswith(endfield.PREFIX)}
    print(f"人物 {len({n for n, *_ in jobs})} 位有图（泰拉 {len(terra)}，终末地 {len({n for n, *_ in jobs}) - len(terra)}）；"
          f"原图 {len(files)} 个，还要下载 {len(need)} 个，约 {size / 1e6:.0f} MB")
    for kind, names in missing.items():
        if names:
            print(f"  没有{'头像' if kind == 'avatar' else '立绘'}：{'、'.join(names)}")
    if args.plan:
        return 0

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("缩图要 Pillow：python -m pip install Pillow")
        return 1
    done = 0
    try:
        for i, (k, f) in enumerate(sorted(files), 1):
            if fetch(k, f, lists[k][f]):
                done += 1
                if done % 25 == 0:
                    print(f"  已下载 {done}/{len(need)}", flush=True)
    except Blocked as e:
        print(f"上游拒绝（{e}），停下。已下载的留着，下次接着下。")
        return 1
    made = 0
    wanted = {"avatar": set(), "portrait": set()}
    for name, cid, kind, key, f in jobs:
        dst = OUT / kind / f"{cid}.webp"
        wanted[kind].add(dst.name)
        src = RAW / key / f
        if not src.exists():
            continue
        if args.force or not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            dst.parent.mkdir(parents=True, exist_ok=True)
            (make_avatar if kind == "avatar" else make_portrait)(src, dst)
            made += 1
    # 清掉不再用到的缩图（人物合并、改了选图规则）
    for kind, names in wanted.items():
        for p in (OUT / kind).glob("*.webp") if (OUT / kind).exists() else ():
            if p.name not in names:
                p.unlink()
    total = sum(p.stat().st_size for p in OUT.rglob("*.webp"))
    count = sum(1 for _ in OUT.rglob("*.webp"))
    print(f"下载 {done} 个，缩图 {made} 张；site/img/ 共 {count} 张 {total / 1e6:.1f} MB。"
          "接着运行 python -X utf8 -m pipeline.build 把图写进人物数据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
