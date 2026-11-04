"""编年史：查剧本、取引文、把卷稿导出成网页数据。

卷稿在 data/annals/<年份>/，每个文件由若干条目组成，每条以一行 @条 开头：

    @条 ev0536                几件事合写一条：@条 ev0549,ev0550；只知年份：@条 ev0516 是岁:乌萨斯
    【纲】**……**
    【目】……
    【人物】[[陈]] · [[诗怀雅]]
    【原文】
    @引 <分集id> <行号范围> 「锚点」
    【考异】……

引文只写出处指令，不写原文：
    @引 <分集id> <行号范围> 「锚点」...
        行号是 show 列出的编号，范围可写 12-18 或 12-18,25-27（中间补省略号）。
        锚点是引文里必须出现的原文片段，用来防止行号写错。
        剧本选项默认署名博士；玩家扮演别人时在行末写「选项=Scout」。
    @档 <人物> <档案栏目> 「开头」…「结尾」
        引干员档案里从「开头」到「结尾」的一段。

月、日标题按 PRTS 年表的日期生成，条目按事件编号排序。纪事本末在 data/annals/纪事本末.md，
凡例在 data/annals/凡例.md。build 把原文从 site/data 里取出，导出 site/data/annals.json
（网页「编年」页用）和 annals/<年份>.md（含原文，不提交）。

    python -m pipeline.annals show <分集id> [起 止]   带行号列出剧本
    python -m pipeline.annals find <正则> [组id]      在剧本里搜索
    python -m pipeline.annals check <稿件路径>        检查一个稿件文件
    python -m pipeline.annals build                   检查并导出全部卷和纪事本末
"""
from __future__ import annotations

import json
import re
import sys
from functools import cache
from pathlib import Path

from .config import ROOT, SITE_DATA

SRC_DIR = ROOT / "data" / "annals"
OUT_DIR = ROOT / "annals"

MAX_LINES = 15
MAX_CHARS = 450


# ---------------------------------------------------------------- 游戏数据


@cache
def groups() -> dict[str, dict]:
    data = json.loads((SITE_DATA / "groups.json").read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("groups", list(data.values()))
    return {g["id"]: g for g in items}


@cache
def episode_index() -> dict[str, tuple[dict, dict]]:
    """分集id → (所属组, 分集信息)。"""
    out = {}
    for g in groups().values():
        for ep in g["episodes"]:
            out[ep["id"]] = (g, ep)
    return out


@cache
def stories(group_id: str) -> dict[str, dict]:
    return json.loads((SITE_DATA / "stories" / f"{group_id}.json").read_text(encoding="utf-8"))


def lines_of(story_id: str) -> list[list]:
    if story_id not in episode_index():
        raise KeyError(f"没有这个分集：{story_id}")
    g, _ = episode_index()[story_id]
    return stories(g["id"])[story_id]["lines"]


@cache
def characters() -> dict[str, dict]:
    return json.loads((SITE_DATA / "characters.json").read_text(encoding="utf-8"))


@cache
def events() -> dict[str, dict]:
    data = json.loads((SITE_DATA / "events.json").read_text(encoding="utf-8"))
    return {e["id"]: e for e in data["events"]}


def year_events(year: int) -> list[str]:
    return [i for i, e in events().items() if e["year"] == year or str(year) in e["era"]]


def line_text(line: list) -> str:
    kind, speaker, body = line
    if kind == "c":
        body = "／".join(body)
    return body.replace("{@Nickname}", "博士")


def plain(line: list) -> str:
    """查锚点用：说话人 + 正文。"""
    kind, speaker, _ = line
    return f"{speaker}：{line_text(line)}" if speaker else line_text(line)


def episode_label(story_id: str) -> str:
    g, ep = episode_index()[story_id]
    parts = [p for p in (ep.get("code"), ep.get("avg"), ep.get("title")) if p]
    return f"《{g['name']}》{' · '.join(parts)}"


class Problems(list):
    def add(self, where: str, msg: str):
        self.append(f"{where}：{msg}")


# ---------------------------------------------------------------- 引文

ANCHOR = re.compile(r"「(.+?)」")


def parse_ranges(spec: str) -> list[tuple[int, int]]:
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.append((int(a), int(b or a)))
    return out


def story_quote(args: str, where: str, probs: Problems) -> dict | None:
    """@引 → {type, sid, label, ranges, blocks}；blocks 是每个行号范围的 [类型, 说话人, 正文] 列表。"""
    m = re.match(r"(\S+)\s+([\d,\-]+)\s*(.*)$", args)
    if not m:
        probs.add(where, f"@引 格式不对：{args}")
        return None
    sid, spec, rest = m.groups()
    chooser = re.search(r"选项=(\S+)", rest)
    chooser = chooser.group(1) if chooser else "博士"
    try:
        lines = lines_of(sid)
    except KeyError as e:
        probs.add(where, str(e))
        return None
    ranges, blocks, picked = parse_ranges(spec), [], []
    for a, b in ranges:
        if not (1 <= a <= b <= len(lines)):
            probs.add(where, f"{sid} 行号 {a}-{b} 超出范围（共 {len(lines)} 行）")
            return None
        block = []
        for ln in lines[a - 1 : b]:
            picked.append(ln)
            kind, speaker, _ = ln
            if kind == "b":
                continue  # 分支标记不显示
            block.append([kind, chooser if kind == "c" else (speaker or ""), line_text(ln)])
        blocks.append(block)
    joined = "\n".join(plain(ln) for ln in picked)
    anchors = ANCHOR.findall(rest)
    if not anchors:
        probs.add(where, f"{sid} {spec} 没写锚点")
    for anchor in anchors:
        if anchor not in joined:
            probs.add(where, f"{sid} {spec} 里找不到锚点「{anchor}」")
    chars = sum(len(line_text(ln)) for ln in picked)
    if len(picked) > MAX_LINES or chars > MAX_CHARS:
        probs.add(where, f"{sid} {spec} 引文偏长（{len(picked)} 行 / {chars} 字）")
    return {"type": "story", "sid": sid, "label": episode_label(sid), "ranges": ranges, "blocks": blocks, "chars": chars}


def profile_quote(args: str, where: str, probs: Problems) -> dict | None:
    """@档 → {type, name, section, label, paras}。"""
    m = re.match(r"(\S+)\s+(\S+)\s+(.*)$", args)
    if not m:
        probs.add(where, f"@档 格式不对：{args}")
        return None
    name, section, rest = m.groups()
    ch = characters().get(name)
    secs = {s["title"]: s["text"] for s in (ch or {}).get("profile", {}).get("sections", [])} if ch else {}
    if section not in secs:
        probs.add(where, f"{name} 没有档案栏目「{section}」")
        return None
    text = secs[section]
    anchors = ANCHOR.findall(rest)
    if len(anchors) not in (1, 2):
        probs.add(where, f"@档 要写一个或两个「」：{args}")
        return None
    start, end = anchors[0], anchors[-1]
    a = text.find(start)
    b = text.find(end, a if a >= 0 else 0)
    if a < 0 or b < 0:
        probs.add(where, f"{name}「{section}」里找不到「{start if a < 0 else end}」")
        return None
    excerpt = text[a : b + len(end)]
    if len(excerpt) > MAX_CHARS:
        probs.add(where, f"{name}「{section}」引文偏长（{len(excerpt)} 字）")
    paras = [p for p in excerpt.split("\n") if p.strip()]
    return {"type": "profile", "name": name, "section": section, "label": f"{name}干员档案 · {section}",
            "paras": paras, "chars": len(excerpt)}


# ---------------------------------------------------------------- 日期

CN = "〇一二三四五六七八九"


def cn_num(n: int) -> str:
    if n < 10:
        return CN[n]
    tens, ones = divmod(n, 10)
    return ("" if tens == 1 else CN[tens]) + "十" + (CN[ones] if ones else "")


def cn_year(y: int) -> str:
    return "".join(CN[int(c)] for c in str(y))


def cn_month(m: int) -> str:
    return "正月" if m == 1 else f"{cn_num(m)}月"


def placement(when: str) -> tuple[str, str | None]:
    """PRTS 的时间写法 → (月份标题, 日标题)。只知年份的归入「是岁」。"""
    rest = re.sub(r"^\s*\d+\s*年", "", when).strip()
    if not rest or "未知" in rest:
        return "是岁", None
    if m := re.fullmatch(r"(\d+)\s*[~～\-]\s*(\d+)\s*月", rest):
        return f"{cn_month(int(m[1]))}至{cn_month(int(m[2]))}", None
    if m := re.fullmatch(r"(\d+)\s*月\s*(\d+)\s*日.*", rest):
        return cn_month(int(m[1])), f"{cn_num(int(m[2]))}日"
    if m := re.fullmatch(r"(\d+)\s*月", rest):
        return cn_month(int(m[1])), "是月"
    if m := re.fullmatch(r"(春|夏|秋|冬)季?", rest):
        return m[1], None
    return rest, None


# ---------------------------------------------------------------- 条目

ENTRY = re.compile(r"@条\s+(ev\d+(?:\s*,\s*ev\d+)*)\s*(?:是岁[:：](\S+))?\s*$")
num = lambda i: int(i[2:])


class Entry:
    def __init__(self, ids: list[str], region: str | None, where: str):
        self.ids, self.region, self.where = ids, region, where
        self.lines: list[tuple[str, str]] = []
        self.groups: list[dict] = []
        self.year = 0
        self.section: str | None = None
        self.day: str | None = None

    @property
    def anchor(self) -> str:
        """定位用的事件：有日期的优先，取编号最小的。"""
        known = [i for i in self.ids if i in events()]
        dated = [i for i in known if placement(events()[i]["when"])[0] != "是岁"]
        return min(dated or known or self.ids, key=num)

    def place(self):
        if self.region:
            self.section, self.day = "是岁", self.region
        elif self.anchor in events():
            self.section, self.day = placement(events()[self.anchor]["when"])
        else:
            self.section, self.day = "？", None

    def when(self, short: bool = False) -> str:
        y = f"{cn_year(self.year)}年"
        if self.section == "是岁":
            return y if short else f"{y}（月日不详）"
        if self.day == "是月":
            return f"{y}{self.section}"
        return f"{y}{self.section}{self.day or ''}"


def parse_entries(path: Path, probs: Problems) -> list[Entry]:
    out: list[Entry] = []
    for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        where = f"{path.name}:{no}"
        if raw.startswith("@条"):
            m = ENTRY.match(raw)
            if not m:
                probs.add(where, f"@条 格式不对：{raw}")
                continue
            ids = [i.strip() for i in m[1].split(",")]
            out.append(Entry(ids, m[2], where))
            unknown = [i for i in ids if i not in events()]
            for i in unknown:
                probs.add(where, f"没有这个事件：{i}")
            yearly = [i for i in ids if i in events() and placement(events()[i]["when"])[0] == "是岁"]
            if not m[2] and yearly and len(yearly) == len(ids) - len(unknown):
                probs.add(where, f"{ids[0]} 只知年份，要写成 @条 {ids[0]} 是岁:地区")
        elif out:
            out[-1].lines.append((where, raw))
        elif raw.strip() and not raw.startswith("<!--"):
            probs.add(where, "第一条 @条 之前不能有正文")
    for e in out:
        e.groups = parse_groups(e, probs)
        e.place()
    return out


FIELD = re.compile(r"^【(纲|目|人物|原文|考异)】\s*(.*)$")


def parse_groups(e: Entry, probs: Problems) -> list[dict]:
    """把一条拆成若干组 {纲, 目, 人物, 原文, 考异}。一条里可以有几组纲目。"""
    out: list[dict] = []
    g, field = None, None
    for where, raw in e.lines:
        s = raw.strip()
        if not s:
            continue
        m = FIELD.match(s)
        if m and m[1] == "纲":
            g = {"gang": m[2], "mu": [], "people": [], "quotes": [], "kaoyi": []}
            out.append(g)
            field = "纲"
            continue
        if g is None:
            probs.add(where, "【纲】之前不能有正文")
            continue
        if m:
            field, rest = m[1], m[2]
            if field == "目" and rest:
                g["mu"].append(rest)
            elif field == "人物":
                g["people"] = [t for t in re.split(r"\s+·\s+", rest) if t]
            elif field == "考异" and rest:
                g["kaoyi"].append({"li": False, "text": rest})
            continue
        if s.startswith("@引 ") or s.startswith("@档 "):
            q = (story_quote if s.startswith("@引") else profile_quote)(s[3:].strip(), where, probs)
            if q:
                g["quotes"].append(q)
        elif field == "考异":
            li = s.startswith("- ")
            g["kaoyi"].append({"li": li, "text": s[2:].strip() if li else s})
        elif field == "目":
            g["mu"].append(s)
        else:
            probs.add(where, f"不知道该归入哪个字段：{s[:20]}")
    if not out:
        probs.add(e.where, f"{','.join(e.ids)} 缺少【纲】")
    for g in out:
        if not g["quotes"] and not g["kaoyi"]:
            probs.add(e.where, f"{','.join(e.ids)} 有一组没有原文，要在【考异】里交代出处")
    return out


def volume_years() -> list[int]:
    return sorted(int(p.name) for p in SRC_DIR.iterdir() if p.is_dir() and p.name.isdigit())


def load_volume(year: int, probs: Problems) -> list[Entry]:
    """读一卷的全部条目，检查漏写和重复，按卷中顺序排好。"""
    entries: list[Entry] = []
    for part in sorted((SRC_DIR / str(year)).glob("*.md")):
        entries += parse_entries(part, probs)
    seen: dict[str, str] = {}
    for e in entries:
        e.year = year
        for i in e.ids:
            if i in seen:
                probs.add(e.where, f"{i} 重复，已见于 {seen[i]}")
            seen[i] = e.where
            if i in events() and i not in year_events(year):
                probs.add(e.where, f"{i} 不属于 {year} 年")
    missing = [i for i in year_events(year) if i not in seen]
    if missing:
        probs.add(str(year), f"还没写的事件 {len(missing)} 条：{'、'.join(missing)}")
    return order_entries(entries)


def order_entries(entries: list[Entry]) -> list[Entry]:
    """有日期的按事件编号排；只知年份的放到卷末，按地区分组，地区按首次出现排。"""
    dated = sorted((e for e in entries if not e.region), key=lambda e: num(e.anchor))
    yearly = sorted((e for e in entries if e.region), key=lambda e: num(e.anchor))
    regions = list(dict.fromkeys(e.region for e in yearly))
    return dated + sorted(yearly, key=lambda e: regions.index(e.region))


def sections(entries: list[Entry]) -> list[dict]:
    """[{label, days: [{label, entries}]}]，是岁的 days 是各地区。"""
    out: list[dict] = []
    for e in entries:
        if not out or out[-1]["label"] != e.section:
            out.append({"label": e.section, "days": []})
        days = out[-1]["days"]
        if not days or days[-1]["label"] != e.day:
            days.append({"label": e.day, "entries": []})
        days[-1]["entries"].append(e)
    return out


# ---------------------------------------------------------------- 纪事本末


def load_benmo(probs: Problems) -> list[dict]:
    """纪事本末.md：@事 名称 / @线 剧情组… / @加 事件… / @减 事件…，其后是本末概述。"""
    path = SRC_DIR / "纪事本末.md"
    if not path.exists():
        return []
    out: list[dict] = []
    for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = raw.strip()
        if s.startswith("@事 "):
            out.append({"title": s[3:].strip(), "threads": set(), "add": set(), "drop": set(), "summary": []})
        elif not out:
            continue  # 文件开头的说明
        elif s.startswith("@线 "):
            out[-1]["threads"] |= set(s[3:].split())
        elif s.startswith("@加 "):
            out[-1]["add"] |= set(s[3:].split())
        elif s.startswith("@减 "):
            out[-1]["drop"] |= set(s[3:].split())
        elif s.startswith("@"):
            probs.add(f"纪事本末.md:{no}", f"不认识的指令：{s[:10]}")
        elif s:
            out[-1]["summary"].append(s)
    for b in out:
        for i in b["add"] | b["drop"]:
            if i not in events():
                probs.add("纪事本末.md", f"{b['title']}：没有这个事件 {i}")
        for t in b["threads"]:
            if t not in groups():
                probs.add("纪事本末.md", f"{b['title']}：没有这个剧情组 {t}")
    return out


def benmo_members(b: dict, entries: list[Entry]) -> list[Entry]:
    def hit(e: Entry) -> bool:
        if any(i in b["drop"] for i in e.ids):
            return False
        return any(i in b["add"] or events().get(i, {}).get("thread") in b["threads"] for i in e.ids)

    # 与卷中一致：逐年排列，只知年份的放在当年末尾
    return sorted((e for e in entries if hit(e)), key=lambda e: (e.year, bool(e.region), num(e.anchor)))


# ---------------------------------------------------------------- 导出


def entry_json(e: Entry, benmo_titles: list[str]) -> dict:
    return {
        "id": e.anchor, "ids": e.ids, "year": e.year, "when": e.when(),
        "threads": sorted({events()[i]["thread"] for i in e.ids if i in events()}),
        "benmo": benmo_titles, "groups": e.groups,
    }


def fanli_lines() -> list[str]:
    path = SRC_DIR / "凡例.md"
    if not path.exists():
        return []
    return [l[2:].strip() for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("- ")]


MD_LINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")


def md_text(s: str) -> str:
    return MD_LINK.sub(r"\1", s)


def entry_md(e: Entry) -> list[str]:
    out = []
    for g in e.groups:
        out += [f"【纲】{g['gang']}", ""]
        out += [f"【目】{p}" if i == 0 else p for i, p in enumerate(g["mu"])] + ([""] if g["mu"] else [])
        if g["people"]:
            out += [f"【人物】{' · '.join(md_text(p) for p in g['people'])}", ""]
        for q in g["quotes"]:
            if q["type"] == "story":
                body = []
                for bi, block in enumerate(q["blocks"]):
                    if bi:
                        body.append("……")
                    for kind, sp, t in block:
                        body.append({"d": f"{sp}：{t}" if sp else t, "n": f"*{t}*", "c": f"{sp}（选项）：{t}",
                                     "s": f"〔{t}〕"}[kind])
            else:
                body = q["paras"]
            out += [x for t in body for x in (f"> {t}", ">")] + [f"> ——{q['label']}", ""]
        if g["kaoyi"]:
            out += ["【考异】"] + [f"- {k['text']}" if k["li"] else k["text"] for k in g["kaoyi"]] + [""]
    return out


def build(quiet: bool = False) -> int:
    probs = Problems()
    benmo = load_benmo(probs)
    volumes, all_entries = [], []
    for year in volume_years():
        vprobs = Problems()
        entries = load_volume(year, vprobs)
        probs += vprobs
        all_entries += entries
        volumes.append((year, entries))
    members = {b["title"]: benmo_members(b, all_entries) for b in benmo}
    belongs: dict[int, list[str]] = {}
    for title, es in members.items():
        for e in es:
            belongs.setdefault(id(e), []).append(title)

    data = {"fanli": fanli_lines(), "volumes": [], "benmo": []}
    OUT_DIR.mkdir(exist_ok=True)
    for year, entries in volumes:
        secs = sections(entries)
        n_quotes = sum(len(g["quotes"]) for e in entries for g in e.groups)
        q_chars = sum(q["chars"] for e in entries for g in e.groups for q in g["quotes"])
        prose = sum(len(re.sub(r"\s|\*|\[\[|\]\]", "", g["gang"] + "".join(g["mu"]) + "".join(g["people"])
                                + "".join(k["text"] for k in g["kaoyi"]))) for e in entries for g in e.groups)
        n_gang = sum(len(e.groups) for e in entries)
        data["volumes"].append({
            "year": year, "title": f"结晶纪元{cn_year(year)}年",
            "stats": {"entries": len(entries), "gang": n_gang, "quotes": n_quotes, "prose": prose, "quote_chars": q_chars},
            "sections": [{"label": s["label"], "days": [
                {"label": d["label"], "entries": [entry_json(e, belongs.get(id(e), [])) for e in d["entries"]]}
                for d in s["days"]]} for s in secs],
        })
        md = [f"# 泰拉编年史 · 结晶纪元{cn_year(year)}年", ""]
        for s in secs:
            md += [f"## {s['label']}", ""]
            for d in s["days"]:
                if d["label"]:
                    md += [f"### {d['label']}", ""]
                for e in d["entries"]:
                    md += entry_md(e)
        (OUT_DIR / f"{year}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        if not quiet:
            print(f"{year} 年：{len(entries)} 条、{n_gang} 组纲目、{n_quotes} 段引文；撰文 {prose:,} 字，引文 {q_chars:,} 字")
    for b in benmo:
        es = members[b["title"]]
        if not es:
            probs.add("纪事本末.md", f"{b['title']}：一条也没有")
            continue
        data["benmo"].append({
            "title": b["title"], "summary": b["summary"], "span": [es[0].when(True), es[-1].when(True)],
            "entries": [{"year": e.year, "id": e.anchor} for e in es],
        })
        if not quiet:
            print(f"纪事本末「{b['title']}」：{len(es)} 条，{es[0].when(True)} 至 {es[-1].when(True)}")
    (SITE_DATA / "annals.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if not quiet:
        print(f"已写出 {(SITE_DATA / 'annals.json').relative_to(ROOT)} 和 {OUT_DIR.relative_to(ROOT)}/")
    for p in probs:
        print("  !", p)
    return 1 if probs else 0


def check(path: str) -> int:
    """检查一个稿件文件：格式、事件编号、引文。"""
    probs = Problems()
    entries = parse_entries(Path(path).resolve(), probs)
    for e in order_entries(entries):
        prose = sum(len(re.sub(r"\s", "", g["gang"] + "".join(g["mu"]) + "".join(k["text"] for k in g["kaoyi"])))
                    for g in e.groups)
        quotes = sum(len(g["quotes"]) for g in e.groups)
        tag = f" 是岁:{e.region}" if e.region else ""
        print(f"  {','.join(e.ids)}{tag}  {e.section}{e.day or ''}  {len(e.groups)} 组，撰文 {prose} 字，引文 {quotes} 段")
    print(f"{len(entries)} 条")
    for p in probs:
        print("  !", p)
    return 1 if probs else 0


# ---------------------------------------------------------------- 查剧本


def show_line(line: list) -> str | None:
    kind, speaker, _ = line
    text = line_text(line)
    return {"d": f"{speaker}：{text}" if speaker else text, "n": f"*{text}*", "c": f"博士（选项）：{text}",
            "s": f"〔{text}〕"}.get(kind)


def show(sid: str, a: int | None = None, b: int | None = None):
    g, ep = episode_index()[sid]
    print(f"# {sid}  {episode_label(sid)}")
    if ep.get("synopsis"):
        print("简介：" + ep["synopsis"].replace("\n", " "))
    for i, ln in enumerate(lines_of(sid), 1):
        if (a and i < a) or (b and i > b):
            continue
        if (t := show_line(ln)) is not None:
            print(f"{i:4d} {t}")


def find(pattern: str, group: str | None = None, limit: int = 80):
    rx = re.compile(pattern)
    n = 0
    for gid in [group] if group else groups():
        for sid, st in stories(gid).items():
            for i, ln in enumerate(st["lines"], 1):
                if ln[0] in "dnsc" and rx.search(plain(ln)):
                    print(f"{sid} {i:4d}  {plain(ln)[:120]}")
                    n += 1
                    if n >= limit:
                        print("……（只列前", limit, "条）")
                        return


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 0
    cmd, *rest = argv
    if cmd == "show":
        show(rest[0], *(int(x) for x in rest[1:3]))
    elif cmd == "find":
        find(rest[0], rest[1] if len(rest) > 1 else None)
    elif cmd == "check":
        return check(rest[0])
    elif cmd in ("build", "render"):
        return build()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
