"""构建入口：解析全部剧本和 PRTS 年表 → data/structured/episodes.jsonl 和 site/data/。

用法（在项目根目录运行）：
    python -m pipeline.build          构建全部主线、活动（含隐藏剧情）、故事集和干员密录
    python -m pipeline.build --list   列出所有剧情组 id
构建完用 python -m pipeline.serve 在浏览器里打开。
"""
import argparse
import json
import subprocess
import sys

from . import chronicle, config, gamedata
from .analyze import analyze_episode, to_record
from .entities import Registry
from .site import SiteExporter


def data_version() -> str:
    try:
        out = subprocess.run(["git", "-C", str(config.RAW_REPO), "log", "-1", "--format=%cd %h", "--date=short"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "未知"


def main():
    ap = argparse.ArgumentParser(description="生成明日方舟剧情浏览器的数据")
    ap.add_argument("--list", action="store_true", help="列出所有剧情组 id")
    args = ap.parse_args()

    if not config.STORY.exists():
        sys.exit("还没有游戏数据，请先运行：python -m pipeline.fetch")
    groups = gamedata.load_groups()
    if args.list:
        for g in sorted(groups.values(), key=gamedata.sort_key):
            print(f"{g.id:16s} {g.category}  {g.label:8s} {g.name}（{len(g.episodes)} 集）")
        return

    reg = Registry()
    built = {gid: [analyze_episode(e, reg) for e in g.episodes] for gid, g in groups.items()}
    events, prts_meta = chronicle.load_events(groups)

    config.STRUCTURED.mkdir(parents=True, exist_ok=True)
    with open(config.STRUCTURED / "episodes.jsonl", "w", encoding="utf-8") as f:
        for eps in built.values():
            for d in eps:
                f.write(json.dumps(to_record(d, reg), ensure_ascii=False) + "\n")

    stats = SiteExporter(reg, groups, built, events, prts_meta, data_version()).export()
    for cat, n_groups, n_eps, n_chars in stats["by_category"]:
        print(f"  {cat}：{n_groups} 组 {n_eps} 集 {n_chars:,} 字")
    print(f"构建完成：{stats['groups']} 组 {stats['episodes']} 集，年表事件 {stats['events']} 条，"
          f"人物 {stats['characters']}，地区与势力 {stats['powers']} → {config.SITE_DATA}")
    # 编年史的引文按行号取自刚导出的剧本，所以放在最后；有问题只提示，不影响网页数据
    from . import annals
    print("编年史：")
    annals.build()
    print("在浏览器中查看：python -m pipeline.serve")


if __name__ == "__main__":
    main()
