"""把当前提交发布出去：推送 main，更新 GitHub Pages，重打两个单文件版，更新 GitHub Release。

这个脚本不提交。先自己 commit，工作区不干净就不往下走，免得把没看过的改动带上线。

    python -m pipeline.deploy                       # 全做，等 Pages 生效后再退出（最多 10 分钟，建议放后台跑）
    python -m pipeline.deploy --dry-run             # 只做检查和构建，不推送
    python -m pipeline.deploy --no-release          # 不动 Release
    python -m pipeline.deploy --no-wait             # 不等 Pages 生效
    python -m pipeline.deploy --note "剧情写到……"   # 写进 Release 说明的一句话

Release 的版本号是当天日期。同一天再发，原地更新：移动 tag，换文件，改说明。
换了日期就新建一个，旧的不动，结束时打印删除旧版本的命令，由人决定要不要删。

gh-pages 每次都是强制覆盖，只有一个提交。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request

from .config import ROOT

REPO = "BBFutaba/arknights-chronicle"
PAGES = "https://bbfutaba.github.io/arknights-chronicle/"
DIST = ROOT / "dist"
PUBLIC_HTML = ROOT / "刻舟录-公开版.html"
ASSET_LABEL = "刻舟录 公开版（单文件网页）"


def run(*cmd: str, cwd=ROOT, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit(f"失败：{' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r


def out(*cmd: str, cwd=ROOT) -> str:
    return run(*cmd, cwd=cwd).stdout.strip()


def python(*args: str) -> subprocess.CompletedProcess:
    return run(sys.executable, "-X", "utf8", "-m", *args)


def require_clean(when: str):
    dirty = out("git", "-c", "core.quotepath=off", "status", "--short")
    if dirty:
        raise SystemExit(f"{when}工作区不干净，先提交或处理这些文件：\n{dirty}")


def build():
    print("构建……", flush=True)
    log = python("pipeline.build").stdout
    problems = [l for l in log.splitlines() if l.lstrip().startswith("!")]
    if problems:
        raise SystemExit("构建有问题，不发布：\n" + "\n".join(problems[:30]))
    require_clean("构建之后")
    for args in (["--public"], []):
        print(python("pipeline.bundle", *args).stdout.strip().splitlines()[-1], flush=True)


def remove_git_dir(path):
    """Windows 上 git 对象是只读的，shutil.rmtree 要先改权限。"""
    def retry(func, name, _):
        os.chmod(name, stat.S_IWRITE)
        func(name)
    if path.exists():
        shutil.rmtree(path, onerror=retry)


def push_pages():
    print("更新 gh-pages……", flush=True)
    url = out("git", "remote", "get-url", "origin")
    name, email = out("git", "config", "user.name"), out("git", "config", "user.email")
    git_dir = DIST / ".git"
    remove_git_dir(git_dir)
    try:
        run("git", "init", "-q", "-b", "gh-pages", cwd=DIST)
        run("git", "-c", "core.autocrlf=false", "add", "-A", cwd=DIST)
        run("git", "-c", f"user.name={name}", "-c", f"user.email={email}",
            "commit", "-q", "-m", "Publish 刻舟录 public edition", cwd=DIST)
        run("git", "push", "-q", "-f", url, "gh-pages", cwd=DIST)
    finally:
        remove_git_dir(git_dir)


def release_notes(version: str, note: str) -> str:
    data = ROOT / "site" / "data"
    annals = json.loads((data / "annals.json").read_text(encoding="utf-8"))
    bowu = json.loads((data / "bowu.json").read_text(encoding="utf-8"))
    entries = sum(v["stats"]["entries"] for v in annals["volumes"])
    extra = f"{note}\n\n" if note else ""
    return f"""《刻舟录》，明日方舟编年史。同人整理，非官方作品。

## 下载

`kezhoulu-{version}.html` 是一个单独的网页文件，下载后用浏览器打开就能看，不需要联网。内容和[网页版]({PAGES})相同。

## 内容

- 编年史：{len(annals["volumes"])} 卷 {entries} 条
- 列传：{len(annals["liezhuan"])} 篇
- 纪事本末：{len(annals["benmo"])} 件
- 博物志：{len(bowu["entries"])} 条

另有时间轴、剧情目录、人物页和关系图。

{extra}文件里不含剧本全文和干员档案正文，只有书中引用的原文片段。所以剧情页只显示官方简介、出场人物和相关事件。

## 协议

转载和再创作的约定见网页的「凡例」页。书的文字按 CC BY-NC-SA 4.0 发布，代码按 MIT 发布。剧本、干员档案、设定集、影片、漫画和《泰拉记事》的版权归鹰角网络。
"""


def update_release(note: str):
    version = datetime.date.today().strftime("%Y.%m.%d")
    head = out("git", "rev-parse", "HEAD")
    asset_name = f"kezhoulu-{version}.html"
    with tempfile.TemporaryDirectory() as tmp:
        asset = os.path.join(tmp, asset_name)
        shutil.copyfile(PUBLIC_HTML, asset)
        notes = os.path.join(tmp, "notes.md")
        with open(notes, "w", encoding="utf-8", newline="\n") as f:
            f.write(release_notes(version, note))
        spec = f"{asset}#{ASSET_LABEL}"
        title = f"刻舟录 {version}"
        exists = run("gh", "release", "view", version, "--repo", REPO, check=False).returncode == 0
        if exists:
            print(f"Release {version} 已有，原地更新……", flush=True)
            run("git", "tag", "-f", version, head)
            run("git", "push", "-q", "-f", "origin", f"refs/tags/{version}")
            run("gh", "release", "upload", version, spec, "--repo", REPO, "--clobber")
            run("gh", "release", "edit", version, "--repo", REPO, "--title", title,
                "--notes-file", notes, "--target", head, "--latest")
        else:
            print(f"新建 Release {version}……", flush=True)
            run("gh", "release", "create", version, spec, "--repo", REPO, "--target", head,
                "--title", title, "--notes-file", notes, "--latest")
    url = f"https://github.com/{REPO}/releases/download/{version}/{asset_name}"
    with urllib.request.urlopen(url, timeout=120) as r:
        online = r.read()
    if online != PUBLIC_HTML.read_bytes():
        raise SystemExit(f"Release 上的文件和本地不一致：{url}")
    print(f"Release 文件已核对：{url}", flush=True)
    listed = json.loads(out("gh", "release", "list", "--repo", REPO, "--json", "tagName"))
    for old in (x["tagName"] for x in listed if x["tagName"] != version):
        print(f"旧版本 {old} 还在。要删的话，由你自己运行：gh release delete {old} --repo {REPO} --cleanup-tag")


def fetch(path: str, n: int) -> bytes:
    req = urllib.request.Request(f"{PAGES}{path}?nc={n}", headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def wait_for_pages():
    print("等 Pages 生效……", flush=True)
    paths = ["index.html", "js/main.js", "data/annals.json"]
    want = {p: hashlib.md5((DIST / p).read_bytes()).hexdigest() for p in paths}
    for i in range(1, 58):
        try:
            if all(hashlib.md5(fetch(p, i)).hexdigest() == want[p] for p in paths):
                print(f"Pages 已生效，用时约 {i * 10} 秒。之前打开过网站的浏览器，最多 10 分钟内可能看到旧脚本。", flush=True)
                return
        except OSError:
            pass
        time.sleep(10)
    raise SystemExit("等了将近 10 分钟 Pages 还没更新：看一下仓库的 Pages 构建状态。")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="推送并发布《刻舟录》")
    ap.add_argument("--dry-run", action="store_true", help="只检查和构建，不推送")
    ap.add_argument("--no-release", action="store_true", help="不更新 Release")
    ap.add_argument("--no-wait", action="store_true", help="不等 Pages 生效")
    ap.add_argument("--note", default="", help="写进 Release 说明的一句话")
    a = ap.parse_args()
    require_clean("发布之前")
    branch = out("git", "branch", "--show-current")
    if branch != "main":
        raise SystemExit(f"当前在 {branch}，只从 main 发布。")
    build()
    if a.dry_run:
        print("--dry-run：检查和构建都通过，没有推送。")
        return 0
    print("推送 main……", flush=True)
    run("git", "push", "-q", "origin", "main")
    push_pages()
    if not a.no_release:
        update_release(a.note)
    if not a.no_wait:
        wait_for_pages()
    print(f"完成：{out('git', 'log', '--oneline', '-1')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
