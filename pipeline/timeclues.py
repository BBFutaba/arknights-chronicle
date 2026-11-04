"""从剧本里提取时间线索，整理成不依赖 PRTS 的时间线，作为编年史的对照。

线索分三类：
    stamp  场景抬头：剧本里的地点·时间标记，或「5:57 a.m. \\ 多云 \\ 能见度…」「营救行动 结束后4天」这样的短旁白
    date   明写的日期：1097年、12月23日、结晶纪元……
    ago    相对时间：三年前、去年、半年前、那年冬天……

    python -m pipeline.timeclues build              提取全部线索，写 data/structured/timeclues.json
    python -m pipeline.timeclues show <组id>        列出一个剧情组每集的时间线索
    python -m pipeline.timeclues gaps <年份>        列出系于这一年的剧情组里，年表和编年史都没碰到的分集
    python -m pipeline.timeclues years              各剧情组：原文明写的年份 与 PRTS 系年 对照

时间线索只是素材：哪一集发生在哪一天，要结合上下文判断，写进 data/annals/丛目/<年份>.md。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict

from . import annals as A
from .config import ROOT, SITE_DATA, STRUCTURED

OUT = STRUCTURED / "timeclues.json"

CN_NUM = "一二三四五六七八九十两半几数百千"
CLOCK = re.compile(r"(?<![\d:])\d{1,2}\s*[:：]\s*\d{2}(?:\s*[:：]\s*\d{2})?\s*(?:[ap]\.?\s?m\.?|[AP]\.?M\.?)?", re.I)
WEATHER = re.compile(r"天气|能见度|多云|晴|阴|雨|雪|雾|风")
STAMP_HINT = re.compile(r"(之前|之后|以前|以后|结束后|开始后|前|后)\s*(\d+|[" + CN_NUM + r"]+)\s*(个)?(小时|天|日|周|星期|月|年)")
YEAR = re.compile(r"(?<!\d)(1[01]\d{2})\s*年")
MONTH_DAY = re.compile(r"(?<!\d)(1[0-2]|0?[1-9])\s*月\s*(3[01]|[12]\d|0?[1-9])\s*日")
CN_MONTH_DAY = re.compile(r"([正一二三四五六七八九十]{1,3})月([一二三四五六七八九十]{1,3})日")
ERA = re.compile(r"结晶纪元")
AGO = re.compile(r"(\d+|[" + CN_NUM + r"]+)\s*(个)?(多)?(年|月|周|星期|天)(多)?\s*(前|之前|以前|后|之后|以后)")
REL = re.compile(r"去年|前年|今年|明年|上个月|上半年|下半年|那年(春|夏|秋|冬)天?|那个(春|夏|秋|冬)天")


def clues_of(lines: list[list]) -> list[dict]:
    out = []
    for no, ln in enumerate(lines, 1):
        kind, speaker, _ = ln
        if kind == "b":
            continue
        text = A.line_text(ln)
        short = len(text) <= 60
        if kind == "s" or (kind == "n" and short and (CLOCK.search(text) and (WEATHER.search(text) or "\\" in text)
                                                         or STAMP_HINT.search(text))):
            out.append({"line": no, "kind": "stamp", "text": text})
            continue
        found = []
        for m in YEAR.finditer(text):
            found.append(("date", m[0]))
        for m in MONTH_DAY.finditer(text):
            found.append(("date", m[0]))
        for m in CN_MONTH_DAY.finditer(text):
            found.append(("date", m[0]))
        if ERA.search(text):
            found.append(("date", "结晶纪元"))
        for m in AGO.finditer(text):
            found.append(("ago", m[0]))
        for m in REL.finditer(text):
            found.append(("ago", m[0]))
        if found:
            who = f"{speaker}：" if speaker else ""
            out.append({"line": no, "kind": found[0][0], "hits": sorted({h for _, h in found}),
                        "text": (who + text)[:120]})
    return out


def prts_index() -> tuple[dict, dict, dict]:
    """PRTS 年表：组 → 故事线本身的事件年份（这一组「现在」发生在哪年）；组 → 出处引到它的事件年份（含回忆往事）；
    分集 → 引到它的事件编号。"""
    own: dict[str, Counter] = defaultdict(Counter)
    refs: dict[str, Counter] = defaultdict(Counter)
    by_ep: dict[str, list[str]] = defaultdict(list)
    for eid, e in A.events().items():
        y = e["year"]
        if y and e["thread"] in A.groups():
            own[e["thread"]][y] += 1
        for s in e["sources"]:
            for g in s["groups"]:
                if y:
                    refs[g][y] += 1
            for sid in s["stories"]:
                by_ep[sid].append(eid)
    return own, refs, by_ep


def quoted_episodes() -> set[str]:
    """编年史里引用过的分集。"""
    path = SITE_DATA / "annals.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    out = set()
    for v in data["volumes"]:
        for s in v["sections"]:
            for d in s["days"]:
                for e in d["entries"]:
                    for g in e["groups"]:
                        out |= {q["sid"] for q in g["quotes"] if q["type"] == "story"}
    return out


def build() -> int:
    own, refs, by_ep = prts_index()
    out = {}
    n_clues = 0
    for gid, g in A.groups().items():
        eps = []
        for ep in g["episodes"]:
            cl = clues_of(A.lines_of(ep["id"]))
            n_clues += len(cl)
            eps.append({"id": ep["id"], "label": A.episode_label(ep["id"]), "clues": cl, "prts": by_ep.get(ep["id"], [])})
        years = Counter(int(m) for e in eps for c in e["clues"] if c["kind"] == "date"
                        for h in c.get("hits", []) for m in YEAR.findall(h))
        out[gid] = {"name": g["name"], "category": g["category"], "text_years": dict(years),
                    "prts_years": dict(own.get(gid, {})), "prts_refs": dict(refs.get(gid, {})), "episodes": eps}
    STRUCTURED.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"{len(out)} 个剧情组，{sum(len(g['episodes']) for g in out.values())} 集，时间线索 {n_clues} 条 → {OUT.relative_to(ROOT)}")
    return 0


def load() -> dict:
    if not OUT.exists():
        build()
    return json.loads(OUT.read_text(encoding="utf-8"))


def show(gid: str):
    g, quoted = load()[gid], quoted_episodes()
    print(f"# {gid} {g['name']}（{g['category']}）  原文年份 {g['text_years'] or '无'}  "
          f"PRTS 本线系年 {g['prts_years'] or '无'}  引到本组的事件年份 {g.get('prts_refs') or '无'}")
    for ep in g["episodes"]:
        flag = (f"  [年表 {','.join(ep['prts'])}]" if ep["prts"] else "") + ("  [编年已引]" if ep["id"] in quoted else "")
        print(f"\n## {ep['id']}  {ep['label']}{flag}")
        syn = A.episode_index()[ep["id"]][1].get("synopsis", "").replace("\n", " ")
        if syn:
            print(f"  简介：{syn}")
        for c in ep["clues"]:
            print(f"  {c['line']:4d} {c['kind']:5s} {c['text']}")


def years():
    for gid, g in load().items():
        if g["category"] == "干员密录" and not g["text_years"]:
            continue
        ty = ",".join(f"{y}×{n}" for y, n in sorted(g["text_years"].items()))
        py = ",".join(f"{y}×{n}" for y, n in sorted(g["prts_years"].items()))
        print(f"{gid:16s} {g['name'][:12]:12s}  原文 {ty or '—':30s} PRTS 本线 {py or '—'}")


def gaps(year: int):
    """系于这一年的剧情组（故事线本身有这一年的年表事件）里，年表没引到、编年史也没引用过的分集。"""
    data, quoted = load(), quoted_episodes()
    total = 0
    for gid, g in data.items():
        if year not in {int(y) for y in g["prts_years"]}:
            continue
        miss = [ep for ep in g["episodes"] if not ep["prts"] and ep["id"] not in quoted]
        if not miss:
            continue
        total += len(miss)
        print(f"\n# {gid} {g['name']}：{len(miss)}/{len(g['episodes'])} 集未覆盖")
        for ep in miss:
            syn = A.episode_index()[ep["id"]][1].get("synopsis", "").replace("\n", " ")
            stamps = "；".join(c["text"] for c in ep["clues"] if c["kind"] == "stamp")[:60]
            print(f"  {ep['id']}  {ep['label']}  {syn[:60]}{('  ⏱ ' + stamps) if stamps else ''}")
    print(f"\n共 {total} 集未覆盖。")


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cmd, *rest = argv or ["help"]
    if cmd == "build":
        return build()
    if cmd == "show":
        show(rest[0])
    elif cmd == "gaps":
        gaps(int(rest[0]))
    elif cmd == "years":
        years()
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
