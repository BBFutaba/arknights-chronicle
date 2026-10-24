"""检查与报告：
1. 年表事件的出处对应情况，列出对不上本地分集的剧情链接；
2. site/data/ 里的引用是否完整（事件指向的分集、人物、地区势力都存在）；
3. 需要人工处理的说话人：疑似干员的写法、台词最多的 NPC、被过滤的路人。

用法：python -m pipeline.check
"""
import json
from collections import Counter

from . import chronicle, config, gamedata
from .analyze import analyze_episode
from .entities import Registry


def check_site_data() -> list[str]:
    d = config.SITE_DATA
    if not (d / "meta.json").exists():
        return ["site/data 还没有生成，跳过（先运行 python -m pipeline.build）"]
    load = lambda name: json.loads((d / name).read_text(encoding="utf-8"))
    groups, chars, powers = load("groups.json"), load("characters.json"), load("powers.json")
    events = load("events.json")
    eps = {e["id"] for g in groups for e in g["episodes"]}
    gids = {g["id"] for g in groups}
    evids = {e["id"] for e in events["events"]}
    problems = []
    for e in events["events"]:
        for s in e["sources"]:
            problems += [f"{e['id']} 出处分集不存在：{x}" for x in s["stories"] if x not in eps]
            problems += [f"{e['id']} 出处剧情组不存在：{x}" for x in s["groups"] if x not in gids]
        problems += [f"{e['id']} 人物不存在：{x}" for x in e["chars"] if x not in chars]
        problems += [f"{e['id']} 地区势力不存在：{x}" for x in e["powers"] if x not in powers]
    for n, c in chars.items():
        problems += [f"人物 {n} 的事件不存在：{x}" for x in c["events"] if x not in evids]
        problems += [f"人物 {n} 的同场人物不存在：{x}" for x, _ in c["co"] if x not in chars]
    for g in groups:
        for e in g["episodes"]:
            problems += [f"分集 {e['id']} 的人物不存在：{x}" for x, _ in e["chars"] if x not in chars]
            if not (d / "stories" / f"{g['id']}.json").exists():
                problems.append(f"缺少剧本文件：stories/{g['id']}.json")
                break
    return problems


def main():
    groups = gamedata.load_groups()
    events, meta = chronicle.load_events(groups)
    with_group = sum(1 for e in events if e.group_ids)
    with_ep = sum(1 for e in events if e.story_ids)
    unmatched = [(e.id, t) for e in events for s in e.sources for t in s.unmatched]
    print(f"[年表] PRTS 修订 {meta['revid']}（{meta['timestamp'][:10]}），{len(events)} 条事件："
          f"对应到剧情组 {with_group}，精确到分集 {with_ep}，只有设定资料出处 {len(events) - with_group}")
    print(f"  对不上本地分集的剧情链接 {len(unmatched)} 个（肉鸽结局、愚人节等不在范围内的属正常）："
          + "".join(f"\n    {i} {t}" for i, t in unmatched))

    problems = check_site_data()
    print(f"\n[网页数据] 引用问题 {len(problems)} 个" + "".join(f"\n  {p}" for p in problems[:30]))

    reg = Registry()
    npc_lines, npc_eps, generic = Counter(), Counter(), Counter()
    for g in groups.values():
        for e in g.episodes:
            d = analyze_episode(e, reg)
            generic.update(d.unlinked)
            for n, c in d.lines.items():
                if reg.chars[n].kind == "npc":
                    npc_lines[n] += c
                    npc_eps[n] += 1
    ops = sorted((n for n in reg.op_by_name if len(n) >= 2), key=len, reverse=True)
    suspects = []
    for n in npc_lines:
        op = next((o for o in ops if o != n and (n.endswith(o) or n.startswith(o))), None)
        if op:
            suspects.append((n, op, npc_lines[n]))
    suspects.sort(key=lambda x: -x[2])
    print("\n[疑似干员的说话人]（确认后写进 entities.toml 的 [aliases]，其中有误报）")
    print("  " + "\n  ".join(f'"{n}" = "{op}"   # {c} 句' for n, op, c in suspects[:30]) if suspects else "  无")
    print("\n[台词最多的 NPC]")
    print("  " + "、".join(f"{n} {c}句/{npc_eps[n]}集" for n, c in npc_lines.most_common(40)))
    print("\n[被过滤的说话人]（如有具名人物，加进 entities.toml 的 keep）")
    print("  " + "、".join(f"{n} {c}" for n, c in generic.most_common(40)))


if __name__ == "__main__":
    main()
