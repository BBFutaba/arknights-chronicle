"""下载或更新数据：
- 游戏数据：只稀疏检出 zh_CN 的 story 和 excel 两个目录（约 230MB）；
- PRTS：泰拉年表页面源码（已缓存则跳过）。

用法：python -m pipeline.fetch [--refresh-prts]
"""
import argparse
import subprocess

from . import config, prts


def git(*args: str):
    subprocess.run(["git", *args], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-prts", action="store_true", help="重新抓取已缓存的 PRTS 页面")
    args = ap.parse_args()

    repo = str(config.RAW_REPO)
    if (config.RAW_REPO / ".git").exists():
        git("-C", repo, "fetch", "--depth", "1", "origin")
        git("-C", repo, "reset", "--hard", "FETCH_HEAD")
    else:
        config.RAW_REPO.parent.mkdir(parents=True, exist_ok=True)
        git("clone", "--depth", "1", "--filter=blob:none", "--sparse", config.DATA_REPO_URL, repo)
        git("-C", repo, "sparse-checkout", "set", *config.SPARSE_PATHS)
    git("-C", repo, "log", "-1", "--format=游戏数据版本：%cd %h", "--date=short")
    prts.fetch_all(refresh=args.refresh_prts)


if __name__ == "__main__":
    main()
