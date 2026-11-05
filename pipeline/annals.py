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
    python -m pipeline.annals zhuan <人物>            列出某人列传收录的条目，供写概述
    python -m pipeline.annals benmo <事名>            列出某件纪事本末的概述和所收条目
    python -m pipeline.annals long <稿件路径>         列出目超过三百字的组，删定用
    python -m pipeline.annals rawfind <正则>          在全部原始游戏文本里搜索（含没收进剧本库的）
    python -m pipeline.annals quotes [输出文件]       核对纲目考异里的「」短引，列出全部游戏文本里都找不到的
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from functools import cache
from pathlib import Path

from . import config
from .config import ROOT, SITE_DATA

SRC_DIR = ROOT / "data" / "annals"
OUT_DIR = ROOT / "annals"

MAX_LINES = 15
MAX_CHARS = 450


# ---------------------------------------------------------------- 游戏数据


@cache
def aliases() -> dict[str, str]:
    """别名.md：同一个人的另一个名字，每行「别名=正名」。正名是列传和人物页用的名字。"""
    path = SRC_DIR / "别名.md"
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        if "=" in raw and not raw.startswith(("#", "<!--")):
            a, _, c = raw.partition("=")
            out[a.strip()] = c.strip()
    return out


def canon(name: str) -> str:
    return aliases().get(name, name)


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


def eff_year(e: dict) -> int | None:
    """PRTS 把「11 世纪 30 年代」记作 year=30，还原成 1030。"""
    y = e.get("year")
    if y is not None and 0 <= y < 100 and "11世纪" in e["era"]:
        return 1000 + y
    return y


# 前纪、外纪的事件散在一百多个年份，不能一年一卷：合成一卷（目录名即卷名），卷内按年表先后排，以年为大标题。
MERGED = {
    "外纪": ("外纪 · 结晶纪元之前", lambda e: e["era"] in ("结晶纪元之前", "可确认的大致时间点")),
    "前纪甲": ("前纪 · 十一世纪前", lambda e: "11 世纪前" in e["era"]),
    "前纪乙": ("前纪 · 一〇〇〇至一〇五九年", lambda e: "00 年代" in e["era"] and (eff_year(e) or 0) < 1060),
    "前纪丙": ("前纪 · 一〇六〇至一〇七九年", lambda e: "00 年代" in e["era"] and (eff_year(e) or 0) >= 1060),
    "不系年": ("不系年 · 原文与年表都无年份的剧情", lambda e: False),
}


def year_events(year) -> list[str]:
    if year in MERGED:
        return [i for i, e in events().items() if MERGED[year][1](e)]
    return [i for i, e in events().items() if eff_year(e) == year or (year == 1103 and "时间未知" in e["era"])]


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
    ch = characters().get(canon(name))
    secs = {s["title"]: s["text"] for s in (ch or {}).get("profile", {}).get("sections", [])} if ch else {}
    if section not in secs and f"{name}·{section}" in secs:  # 合并进来的另一身份，栏目名前加了名字
        section = f"{name}·{section}"
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


def cn_big(n: int) -> str:
    """一万、九千、四百、三十五……（前几千年的年份）。"""
    for unit, name in ((10000, "万"), (1000, "千"), (100, "百")):
        if n >= unit:
            head, rest = divmod(n, unit)
            return cn_num(head) + name + (cn_big(rest) if rest else "")
    return cn_num(n)


def era_label(when: str, y: int | None, vol: str) -> str:
    """合卷里的年份大标题。"""
    w = when.strip()
    if m := re.match(r"^(约?)前\s*(\d+)\s*年(?:\s*[~～\-]\s*前\s*(\d+)\s*年)?", w):
        tail = f"至前{cn_big(int(m[3]))}年" if m[3] else "年"
        return f"{m[1]}前{cn_big(int(m[2]))}{tail}"
    if m := re.match(r"^(\d+)\s*年?\s*[~～\-]\s*(\d+)\s*年", w):
        return f"{cn_year(int(m[1]))}至{cn_year(int(m[2]))}年"
    if m := re.match(r"^(\d+)\s*年前后", w):
        return f"{cn_year(int(m[1]))}年前后"
    if m := re.match(r"^(\d+)\s*世纪\s*(\d+)\s*年代", w):
        return f"{cn_year((int(m[1]) - 1) * 100 + int(m[2]))}年代"
    if m := re.match(r"^(\d+)\s*世纪", w):
        return f"{cn_num(int(m[1]))}世纪"
    if y is None:
        return w
    if vol == "外纪" and y > 0:
        return f"泰拉历{cn_big(y)}年"
    return f"{cn_year(y)}年"


def cn_month(m: int) -> str:
    return "正月" if m == 1 else f"{cn_num(m)}月"


def placement(when: str) -> tuple[str, str | None]:
    """PRTS 的时间写法 → (月份标题, 日标题)。只知年份的归入「是岁」。"""
    rest = re.sub(r"^\s*\d+\s*年", "", when).strip()
    if not rest or "未知" in rest:
        return "是岁", None
    if m := re.fullmatch(r"(\d+)\s*月?\s*[~～\-]\s*(\d+)\s*月", rest):
        return f"{cn_month(int(m[1]))}至{cn_month(int(m[2]))}", None
    if m := re.fullmatch(r"(\d+)\s*月\s*(\d+)\s*日.*", rest):
        return cn_month(int(m[1])), f"{cn_num(int(m[2]))}日"
    if m := re.fullmatch(r"(\d+)\s*月", rest):
        return cn_month(int(m[1])), "是月"
    if m := re.fullmatch(r"(春|夏|秋|冬)季?", rest):
        return m[1], None
    if m := re.fullmatch(r"\d+\s*世纪\s*(\d+)\s*年代", rest):
        return f"{cn_num(int(m[1]) // 10)}十年代", None
    return rest, None


# ---------------------------------------------------------------- 条目

ENTRY = re.compile(r"@条\s+(补[:：]\S+|ev\d+(?:\s*,\s*ev\d+)*)\s*(.*)$")
num = lambda i: int(i[2:])
# 季节排在这个月的各日之后，与 PRTS 年表的排法一致（夏在七月后，秋在八月后……）
SEASON_AFTER = {"春": 3, "夏": 7, "秋": 8, "冬": 11}


def date_key(when: str) -> tuple[int, int, int]:
    """系日 → 排序键 (月, 类, 日)：同一个月里「是月」和跨月的在前，具体日子居中，季节在后。"""
    rest = re.sub(r"^\s*\d+\s*年", "", when).strip()
    if m := re.fullmatch(r"(\d+)\s*月?\s*[~～\-]\s*(\d+)\s*月", rest):
        return int(m[1]), 0, 0
    if m := re.fullmatch(r"(\d+)\s*月\s*(\d+)\s*日.*", rest):
        return int(m[1]), 1, int(m[2])
    if m := re.fullmatch(r"(\d+)\s*月", rest):
        return int(m[1]), 0, 0
    if m := re.fullmatch(r"(春|夏|秋|冬)季?", rest):
        return SEASON_AFTER[m[1]], 2, 0
    if rest.startswith(("年初", "新春")):
        return 0, 0, 0
    return 13, 0, 0


def parse_override(value: str) -> tuple[int, str] | None:
    """系:1097-11-01 / 1097-01 / 1097-秋 / 1097-02~04 → (年, PRTS 式的时间写法)。"""
    m = re.fullmatch(r"(\d{3,4})(?:-(?:(春|夏|秋|冬)|(\d{1,2})~(\d{1,2})|(\d{1,2})(?:-(\d{1,2}))?))?", value)
    if not m:
        return None
    y = int(m[1])
    if not (m[2] or m[3] or m[5]):
        return y, f"{y} 年"  # 只知年份：补条配合「是岁:地区」用
    if m[2]:
        return y, f"{y} 年 {m[2]}季"
    if m[3]:
        return y, f"{y} 年 {int(m[3])} ~ {int(m[4])} 月"
    if m[6]:
        return y, f"{y} 年 {int(m[5])} 月 {int(m[6])} 日"
    return y, f"{y} 年 {int(m[5])} 月"


class Entry:
    def __init__(self, ids: list[str], where: str):
        self.ids, self.where = ids, where
        self.sup = ids[0].startswith("补")          # 补条：年表没有的事
        self.region: str | None = None             # 是岁:地区
        self.moved: tuple[int, str] | None = None  # 系:…（改系后的年份和时间写法）
        self.minor = False                         # 附：附记
        self.cunmu = False                         # 存目：不入正文
        self.shi: list[str] = []                   # 事:…（归属的纪事本末）
        self.zhuan: list[str] = []                 # 传:…（归属的列传）
        self.after: str | None = None              # 次:evXXXX（补条排在同日的这条之后）
        self.tail = False                          # 月末：只知月份，但在当月各日之后
        self.early = False                         # 季初：只知季节，但在这一季各月之前
        self.lines: list[tuple[str, str]] = []
        self.groups: list[dict] = []
        self.year: int | None = 0
        self.merged: str | None = None             # 合卷（外纪、前纪甲……）的卷名
        self.section: str | None = None
        self.day: str | None = None

    @property
    def anchor(self) -> str:
        """定位用的编号：补条用自己的名字；否则有日期的事件优先，取编号最小的。"""
        if self.sup:
            return self.ids[0]
        known = [i for i in self.ids if i in events()]
        dated = [i for i in known if placement(events()[i]["when"])[0] != "是岁"]
        return min(dated or known or self.ids, key=num)

    @property
    def order(self) -> int:
        """同日之内的先后：PRTS 事件按年表编号，补条排在同日的年表事件之后。"""
        if self.sup or (self.merged and self.after):  # 合卷里，改系的年表条目也靠 次: 排位
            return num(self.after) * 2 + 1 if self.after else 10**7
        return num(self.anchor) * 2

    @property
    def prts_when(self) -> str:
        return events().get(self.anchor, {}).get("when", "")

    @property
    def system_when(self) -> str:
        """实际系日：改系的用改后的，否则用 PRTS 的。"""
        return self.moved[1] if self.moved else self.prts_when

    @property
    def is_moved(self) -> bool:
        """改了 PRTS 的系日：用了 系:，或把有月日的事件放进了是岁。补条本来就没有年表日期，不算。"""
        if self.sup:
            return False
        if self.merged or "世纪" in self.prts_when:
            return bool(self.moved)
        return bool(self.moved) or (bool(self.region) and placement(self.prts_when)[0] != "是岁")

    @property
    def main(self) -> bool:
        """立条（纲目俱全的正文条目），不是附记也不是存目。"""
        return not self.minor and not self.cunmu

    def place(self):
        if self.region:
            self.section, self.day = "是岁", self.region
        elif self.system_when:
            self.section, self.day = placement(self.system_when)
        else:
            self.section, self.day = "？", None

    def place_merged(self):
        """合卷：年份作大标题，月日或地区作小标题。"""
        when = self.system_when or ""
        label = era_label(when, self.year, self.merged)
        if self.region:
            self.section, self.day = label, self.region
            return
        rest = re.sub(r"^\s*\d+\s*年", "", when).strip()
        if rest != when.strip() and rest and "年" not in rest and "未知" not in rest:
            sec, day = placement(when)
            self.section, self.day = label, sec + (day if day and day != "是月" else "")
        else:
            self.section, self.day = label, None

    @property
    def vol(self):
        """这条所在的卷：网页链接用。"""
        return self.merged or self.year

    def sort_key(self) -> tuple:
        key = date_key(self.system_when)
        if self.tail:
            key = (key[0], 1, 99)
        elif self.early:
            key = (key[0] - 1, 9, 0)
        return key, self.order

    def when(self, short: bool = False) -> str:
        if self.merged:
            return self.section if short else self.section + (self.day or "")
        y = f"{cn_year(self.year)}年"
        if self.section == "是岁":
            return y if short else f"{y}（月日不详）"
        if self.day == "是月":
            return f"{y}{self.section}"
        return f"{y}{self.section}{self.day or ''}"

    def people(self) -> set[str]:
        """【人物】里链接的名字。"""
        return {canon(n) for g in self.groups for t in g["people"] for n in re.findall(r"\[\[([^\]|]+)", t)}


def parse_entries(path: Path, probs: Problems) -> list[Entry]:
    out: list[Entry] = []
    for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        where = f"{path.name}:{no}"
        if raw.startswith("@条"):
            m = ENTRY.match(raw)
            if not m:
                probs.add(where, f"@条 格式不对：{raw}")
                continue
            ids = [m[1].replace("：", ":")] if m[1].startswith("补") else [i.strip() for i in m[1].split(",")]
            e = Entry(ids, where)
            out.append(e)
            for tok in m[2].split():
                key, _, val = tok.replace("：", ":").partition(":")
                if key == "是岁" and val:
                    e.region = val
                elif key == "系" and val:
                    e.moved = parse_override(val)
                    if not e.moved:
                        probs.add(where, f"系日写法不对：{tok}（例：系:1097-11-01、系:1097-01、系:1097-秋）")
                elif key == "事" and val:
                    e.shi += [v for v in val.split(",") if v]
                elif key == "传" and val:
                    e.zhuan += [canon(v) for v in val.split(",") if v]
                elif key == "次" and re.fullmatch(r"ev\d+", val):
                    e.after = val
                elif tok == "不系年":
                    e.moved = (None, "不系年")
                elif tok == "月末":
                    e.tail = True
                elif tok == "季初":
                    e.early = True
                elif tok == "附":
                    e.minor = True
                elif tok == "存目":
                    e.cunmu = True
                else:
                    probs.add(where, f"不认识的选项：{tok}")
            if e.sup:
                if not e.moved:
                    probs.add(where, f"{ids[0]} 是补条，要写系日：系:年-月-日")
                elif placement(e.moved[1])[0] == "是岁" and not e.region:
                    probs.add(where, f"{ids[0]} 只知年份，要同时写 是岁:地区")
                continue
            unknown = [i for i in e.ids if i not in events()]
            for i in unknown:
                probs.add(where, f"没有这个事件：{i}")
            yearly = [i for i in e.ids if i in events() and placement(events()[i]["when"])[0] == "是岁"]
            if not e.region and not e.moved and yearly and len(yearly) == len(e.ids) - len(unknown):
                probs.add(where, f"{e.ids[0]} 只知年份，要写成 @条 {e.ids[0]} 是岁:地区")
        elif out:
            out[-1].lines.append((where, raw))
        elif raw.strip() and not raw.startswith("<!--"):
            probs.add(where, "第一条 @条 之前不能有正文")
    for e in out:
        e.groups = parse_groups(e, probs)
        e.place()
        tag = ",".join(e.ids)
        has_kaoyi = any(g["kaoyi"] for g in e.groups)
        if e.minor and e.cunmu:
            probs.add(e.where, f"{tag} 附和存目只能选一个")
        if e.is_moved and not has_kaoyi:
            probs.add(e.where, f"{tag} 改了 PRTS 的系日，要在【考异】里写明依据")
        if not e.main and any(g["mu"] or g["quotes"] for g in e.groups):
            probs.add(e.where, f"{tag} 是{'存目' if e.cunmu else '附记'}，只写纲和考异，不写目和原文")
        if e.cunmu and not has_kaoyi:
            probs.add(e.where, f"{tag} 是存目，要在【考异】里写明不录的理由")
        if e.cunmu and (e.shi or e.zhuan):
            probs.add(e.where, f"{tag} 是存目，不能标归属")
        if e.sup and (not has_kaoyi or not any(g["quotes"] for g in e.groups)):
            probs.add(e.where, f"{tag} 是补条，要有原文和考异（写明年表不载与日期依据）")
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


# 书法：纲和目里不用的词（引号里的原话不算），见写作规范「书法」一节
SHUFA = ["牺牲", "阵亡", "殒命", "捐躯", "惨遭毒手", "被害", "处决", "自戕", "轻生", "病故", "病殁",
         "遇难", "罹难", "丧生", "身亡", "死去", "而死", "斩杀", "歼灭", "解放", "沦陷", "投敌", "背叛", "假死", "殒", "殁"]
SHUFA_RE = re.compile("|".join(sorted(SHUFA, key=len, reverse=True)))


def shufa_hits(e: Entry) -> list[str]:
    text = "\n".join(g["gang"] + "\n" + "\n".join(g["mu"]) for g in e.groups)
    return SHUFA_RE.findall(re.sub(r"「[^」]*」", "", text))


def volume_years() -> list:
    """全部卷，按年代先后：合卷在前，然后一年一卷。"""
    merged = [k for k in MERGED if (SRC_DIR / k).is_dir() and k != "不系年"]
    tail = ["不系年"] if (SRC_DIR / "不系年").is_dir() else []
    return merged + sorted(int(p.name) for p in SRC_DIR.iterdir() if p.is_dir() and p.name.isdigit()) + tail


def volume_title(year) -> str:
    return MERGED[year][0] if year in MERGED else f"结晶纪元{cn_year(year)}年"


def load_volume(year: int, probs: Problems) -> list[Entry]:
    """读一卷的全部条目，按卷中顺序排好。漏写和重复在 build 里跨卷检查。"""
    entries: list[Entry] = []
    for part in sorted((SRC_DIR / str(year)).glob("*.md")):
        entries += parse_entries(part, probs)
    for e in entries:
        if year in MERGED:
            e.merged = year
            first = next((events()[i] for i in e.ids if i in events()), None)
            e.year = e.moved[0] if e.moved else (eff_year(first) if first else None)
            e.place_merged()
            if e.sup and not e.after and year != "不系年":
                probs.add(e.where, f"{e.ids[0]} 在合卷里要写 次:ev编号，才排得进年表")
            if not e.moved and any(i in events() and not MERGED[year][1](events()[i]) for i in e.ids):
                probs.add(e.where, f"{','.join(e.ids)} 不属于「{year}」卷")
            continue
        e.year = year
        if e.moved:
            if e.moved[0] != year:
                probs.add(e.where, f"{','.join(e.ids)} 系于 {e.moved[0]} 年，条目要放到 data/annals/{e.moved[0]}/")
            continue
        for i in e.ids:
            if i in events() and i not in year_events(year):
                probs.add(e.where, f"{i} 不属于 {year} 年；若要改系，写 系:年-月-日")
    return order_entries(entries)


def order_entries(entries: list[Entry]) -> list[Entry]:
    """有日期的按系日排，同日按年表先后；只知年份的放到卷末，按地区分组，地区按首次出现排。"""
    if entries and entries[0].merged:
        return sorted(entries, key=lambda e: e.order)
    dated = sorted((e for e in entries if not e.region), key=Entry.sort_key)
    yearly = sorted((e for e in entries if e.region), key=lambda e: e.order)
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


def by_thread(b: dict, e: Entry) -> bool:
    """按 @线 / @加 / @减 判断：这条是否是这件事的候选。"""
    if any(i in b["drop"] for i in e.ids):
        return False
    return any(i in b["add"] or events().get(i, {}).get("thread") in b["threads"] for i in e.ids)


def chrono(e: Entry) -> tuple:
    """跨卷排序：逐年排列，只知年份的放在当年末尾。"""
    if e.merged:
        return (9999 if e.merged == "不系年" else list(MERGED).index(e.merged)), 0, e.order
    return 100 + e.year, bool(e.region), e.sort_key()


def benmo_members(b: dict, entries: list[Entry]) -> list[Entry]:
    """条目写了 事: 的，只算写明的那几件事；没写的按故事线自动归入（附记不自动归入）；存目一律不收。"""
    def hit(e: Entry) -> bool:
        if e.cunmu:
            return False
        if e.shi:
            return b["title"] in e.shi
        return e.main and not e.merged and by_thread(b, e)  # 合卷的远事不自动归入，要写明 事:

    return sorted((e for e in entries if hit(e)), key=chrono)


# ---------------------------------------------------------------- 列传


def load_renwu(probs: Problems) -> dict[str, str]:
    """人物志：data/annals/人物志/*.md，每行「名字：身份。」。程序把它放到每卷此人第一次出场的条目下。"""
    out: dict[str, str] = {}
    folder = SRC_DIR / "人物志"
    for path in sorted(folder.glob("*.md")) if folder.exists() else []:
        for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            s = raw.strip()
            if not s or s.startswith(("#", "<!--", ">")):
                continue
            m = re.match(r"^([^：:\s]+)[：:]\s*(.+)$", s)
            if not m:
                probs.add(f"人物志/{path.name}:{no}", f"格式应为「名字：身份。」：{s[:20]}")
            elif m[1] in out:
                probs.add(f"人物志/{path.name}:{no}", f"「{m[1]}」重复")
            else:
                out[m[1]] = m[2]
    return out


def add_intros(entries: list[Entry], renwu: dict[str, str]) -> list[str]:
    """按卷中顺序，给每人在本卷第一次出场的立条条目加上身份介绍；返回没有介绍的人名。"""
    seen, missing = set(), []
    for e in entries:
        for g in e.groups:
            g["intro"] = []
            if not e.main:
                continue
            for t in g["people"]:
                for n in re.findall(r"\[\[([^\]|]+)", t):
                    c = canon(n)
                    if c in seen:
                        continue
                    seen.add(c)
                    others = [a for a, x in aliases().items() if x == c]
                    if text := next((renwu[m] for m in [n, c, *others] if m in renwu), None):
                        g["intro"].append({"name": n, "text": text})
                    else:
                        missing.append(n)
    return missing


def load_liezhuan(probs: Problems) -> list[dict]:
    """列传.md：@传 人物，其后是概述。"""
    path = SRC_DIR / "列传.md"
    if not path.exists():
        return []
    out: list[dict] = []
    for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = raw.strip()
        if s.startswith("@传 "):
            out.append({"name": s[3:].strip(), "summary": []})
            if out[-1]["name"] not in characters():
                probs.add(f"列传.md:{no}", f"人物页里没有「{out[-1]['name']}」，名字要与网页人物页一致")
        elif not out:
            continue  # 文件开头的说明
        elif s.startswith("<!--"):
            continue
        elif s.startswith("@"):
            probs.add(f"列传.md:{no}", f"不认识的指令：{s[:10]}")
        elif s:
            out[-1]["summary"].append(s)
    return out


# ---------------------------------------------------------------- 导出


def entry_json(e: Entry, benmo_titles: list[str]) -> dict:
    return {
        "id": e.anchor, "ids": e.ids, "year": e.vol, "when": e.when(),
        "threads": sorted({events()[i]["thread"] for i in e.ids if i in events()}),
        "benmo": benmo_titles, "zhuan": e.zhuan, "groups": e.groups, "minor": e.minor, "sup": e.sup,
        "moved": e.prts_when if e.is_moved else None,
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
        out += [f"【纲】{'〔附〕' if e.minor else ''}{'〔补〕' if e.sup else ''}{g['gang']}", ""]
        out += [f"【目】{p}" if i == 0 else p for i, p in enumerate(g["mu"])] + ([""] if g["mu"] else [])
        if g["people"]:
            out += [f"【人物】{' · '.join(md_text(p) for p in g['people'])}", ""]
        for it in g.get("intro", []):
            out += [f"（初见）{it['name']}：{it['text']}", ""]
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
    # 漏写和重复跨卷检查：改系到别的年份的事件，在新的那一卷里算数
    seen: dict[str, str] = {}
    for e in all_entries:
        for i in e.ids:
            if i in seen:
                probs.add(e.where, f"{i} 重复，已见于 {seen[i]}")
            seen[i] = e.where
    for year, _ in volumes:
        missing = [i for i in year_events(year) if i not in seen]
        if missing:
            probs.add(str(year), f"还没写的事件 {len(missing)} 条：{'、'.join(missing)}")
    liezhuan = load_liezhuan(probs)
    renwu = load_renwu(probs)
    no_intro: list[str] = []
    titles, names = {b["title"] for b in benmo}, {z["name"] for z in liezhuan}
    for e in all_entries:
        for t in e.shi:
            if t not in titles:
                probs.add(e.where, f"纪事本末里没有「{t}」")
        for n in e.zhuan:
            if n not in names:
                probs.add(e.where, f"列传里没有「{n}」")
    members = {b["title"]: benmo_members(b, all_entries) for b in benmo}
    belongs: dict[int, list[str]] = {}
    for title, es in members.items():
        for e in es:
            belongs.setdefault(id(e), []).append(title)

    data = {"fanli": fanli_lines(), "aliases": aliases(), "volumes": [], "benmo": [], "liezhuan": []}
    # 归属：立条必须是某件事的一环或某个人的一笔；只靠故事线自动归入的，算「未确认」
    orphans = [e for e in all_entries if e.main and not e.zhuan and id(e) not in belongs and e.merged != "不系年"]
    implicit = [e for e in all_entries if e.main and not e.shi and not e.zhuan and id(e) in belongs]
    OUT_DIR.mkdir(exist_ok=True)
    for year, all_in_year in volumes:
        cunmu = [e for e in all_in_year if e.cunmu]
        entries = [e for e in all_in_year if not e.cunmu]
        no_intro += add_intros(entries, renwu)
        secs = sections(entries)
        n_quotes = sum(len(g["quotes"]) for e in entries for g in e.groups)
        q_chars = sum(q["chars"] for e in entries for g in e.groups for q in g["quotes"])
        prose = sum(len(re.sub(r"\s|\*|\[\[|\]\]", "", g["gang"] + "".join(g["mu"]) + "".join(g["people"])
                                + "".join(k["text"] for k in g["kaoyi"]))) for e in entries for g in e.groups)
        n_gang = sum(len(e.groups) for e in entries)
        data["volumes"].append({
            "year": year, "title": volume_title(year),
            "stats": {"entries": len(entries), "gang": n_gang, "quotes": n_quotes, "prose": prose, "quote_chars": q_chars},
            "sections": [{"label": s["label"], "days": [
                {"label": d["label"], "entries": [entry_json(e, belongs.get(id(e), [])) for e in d["entries"]]}
                for d in s["days"]]} for s in secs],
            "cunmu": [{"id": e.anchor, "ids": e.ids, "prts": e.prts_when, "gang": e.groups[0]["gang"] if e.groups else "",
                       "kaoyi": [k for g in e.groups for k in g["kaoyi"]]} for e in cunmu],
        })
        md = [f"# 明日方舟编年史 · {volume_title(year)}", ""]
        for s in secs:
            md += [f"## {s['label']}", ""]
            for d in s["days"]:
                if d["label"]:
                    md += [f"### {d['label']}", ""]
                for e in d["entries"]:
                    md += entry_md(e)
        if cunmu:
            md += ["## 存目", ""] + [f"- {e.groups[0]['gang'] if e.groups else e.anchor}（{e.prts_when}）："
                                    f"{' '.join(k['text'] for g in e.groups for k in g['kaoyi'])}" for e in cunmu] + [""]
        (OUT_DIR / f"{year}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        if not quiet:
            n_minor = sum(e.minor for e in entries)
            n_moved = sum(e.is_moved for e in entries)
            n_sup = sum(e.sup for e in entries)
            print(f"{year} 年：{len(entries)} 条（附记 {n_minor}，改系 {n_moved}，补条 {n_sup}），存目 {len(cunmu)}；"
                  f"{n_gang} 组纲目、{n_quotes} 段引文；撰文 {prose:,} 字，引文 {q_chars:,} 字")
            hits = Counter(w for e in entries for w in shufa_hits(e))
            if hits:
                print(f"  ~ 书法：纲目里有 {sum(hits.values())} 处不合用词（{'、'.join(f'{w}×{n}' for w, n in hits.most_common())}），"
                      f"用 check 看具体位置")
    for b in benmo:
        es = members[b["title"]]
        if not es:
            probs.add("纪事本末.md", f"{b['title']}：一条也没有")
            continue
        data["benmo"].append({
            "title": b["title"], "summary": b["summary"], "span": [es[0].when(True), es[-1].when(True)],
            "entries": [{"year": e.vol, "id": e.anchor} for e in es],
        })
        if not quiet:
            print(f"纪事本末「{b['title']}」：{len(es)} 条，{es[0].when(True)} 至 {es[-1].when(True)}")
    for z in liezhuan:
        es = sorted((e for e in all_entries if z["name"] in e.zhuan and not e.cunmu), key=chrono)
        others = sorted((e for e in all_entries if z["name"] in e.people() and z["name"] not in e.zhuan
                         and not e.cunmu), key=chrono)
        data["liezhuan"].append({
            "name": z["name"], "summary": z["summary"],
            "span": [es[0].when(True), es[-1].when(True)] if es else None,
            "entries": [{"year": e.vol, "id": e.anchor} for e in es],
            "others": [{"year": e.vol, "id": e.anchor} for e in others],
        })
        if not quiet:
            print(f"列传「{z['name']}」：{len(es)} 条，其他出场 {len(others)} 条")
    if not quiet and no_intro:
        print(f"  ~ 人物初见：{len(set(no_intro))} 人在人物志里没有身份介绍：{'、'.join(sorted(set(no_intro))[:30])}"
              f"{'……' if len(set(no_intro)) > 30 else ''}")
    if not quiet and (orphans or implicit):
        print(f"  ~ 归属：立条而无归属 {len(orphans)} 条，只靠故事线自动归入（未确认）{len(implicit)} 条，用 check 看具体条目")
    (SITE_DATA / "annals.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if not quiet:
        print(f"已写出 {(SITE_DATA / 'annals.json').relative_to(ROOT)} 和 {OUT_DIR.relative_to(ROOT)}/")
    for p in probs:
        print("  !", p)
    return 1 if probs else 0


def check(path: str) -> int:
    """检查一个稿件文件：格式、事件编号、引文、书法用词（~ 开头的是提示，不算错误）。"""
    probs = Problems()
    entries = parse_entries(Path(path).resolve(), probs)
    titles = {b["title"] for b in load_benmo(probs)}
    names = {z["name"] for z in load_liezhuan(probs)}
    for e in entries:
        for t in e.shi:
            if t not in titles:
                probs.add(e.where, f"纪事本末里没有「{t}」（可用：{'、'.join(sorted(titles))}）")
        for n in e.zhuan:
            if n not in names:
                probs.add(e.where, f"列传里没有「{n}」")
    notes = []
    for e in order_entries(entries):
        prose = sum(len(re.sub(r"\s", "", g["gang"] + "".join(g["mu"]) + "".join(k["text"] for k in g["kaoyi"])))
                    for g in e.groups)
        quotes = sum(len(g["quotes"]) for g in e.groups)
        tag = (f" 是岁:{e.region}" if e.region else "") + (" 附" if e.minor else "") + (" 存目" if e.cunmu else "") \
            + (" 补条" if e.sup else "") + (" 改系" if e.is_moved else "") \
            + (f" 事:{','.join(e.shi)}" if e.shi else "") + (f" 传:{','.join(e.zhuan)}" if e.zhuan else "")
        print(f"  {','.join(e.ids)}{tag}  {e.section}{e.day or ''}  {len(e.groups)} 组，撰文 {prose} 字，引文 {quotes} 段")
        if e.main and not e.shi and not e.zhuan:
            notes.append(f"{e.where} {','.join(e.ids)}：立条而未写归属（事: 或 传:），或者降为附记、存目")
        if hits := shufa_hits(e):
            notes.append(f"{e.where} {','.join(e.ids)}：书法 {'、'.join(f'「{w}」' for w in hits)}")
    print(f"{len(entries)} 条")
    for p in probs:
        print("  !", p)
    for n in notes:
        print("  ~", n)
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


def zhuan(name: str):
    """列出某人列传收录的条目（日期、纲、目）和其他出场，供写列传概述用。先运行 build。"""
    data = json.loads((SITE_DATA / "annals.json").read_text(encoding="utf-8"))
    idx = {e["id"]: e for v in data["volumes"] for s in v["sections"] for d in s["days"] for e in d["entries"]}
    z = next((x for x in data["liezhuan"] if x["name"] == name), None)
    if not z:
        print(f"列传里没有「{name}」")
        return
    renwu = load_renwu(Problems())
    others = [a for a, c in aliases().items() if c == name]
    print(f"# {name}传　人物志：{next((renwu[n] for n in [name, *others] if n in renwu), '（无）')}")
    if z["summary"]:
        print("现有概述：" + "".join(z["summary"]))
    for r in z["entries"]:
        e = idx[r["id"]]
        print()
        print(f"## {e['when']}{'〔附〕' if e['minor'] else ''}  {e['id']}")
        for g in e["groups"]:
            print("纲：" + g["gang"].replace("**", ""))
            for m in g["mu"]:
                print("目：" + m)
    if z["others"]:
        print()
        print("# 其他出场")
        for r in z["others"]:
            e = idx[r["id"]]
            print(f"  {e['when']}  " + e["groups"][0]["gang"].replace("**", ""))


def long_groups(path: str, limit: int = 300):
    """删定用：列出一个稿件里目超过 limit 字的组。"""
    probs = Problems()
    n = 0
    for e in parse_entries(Path(path).resolve(), probs):
        for g in e.groups:
            size = len(re.sub(r"\s|\*|\[\[|\]\]", "", "".join(g["mu"])))
            if size > limit:
                n += 1
                print(f"{e.anchor}  目 {size} 字  {g['gang'].replace('**', '')[:40]}")
    print(f"共 {n} 组超过 {limit} 字")


def raw_texts():
    """游戏数据里的全部文字，含没收进剧本库的：逐个产出 (来源, 行号, 一行文字)。"""
    root = config.EXCEL.parent
    for f in sorted((root / "story").rglob("*.txt")):
        rel = f.relative_to(root / "story").with_suffix("").as_posix()
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            yield rel, i, line
    for f in sorted(config.EXCEL.glob("*.json")):
        def walk(v, path):
            if isinstance(v, str):
                if re.search(r"[一-鿿]", v):
                    yield path, v
            elif isinstance(v, dict):
                for k, x in v.items():
                    yield from walk(x, f"{path}/{k}")
            elif isinstance(v, list):
                for x in v:
                    yield from walk(x, path)
        for path, v in walk(json.loads(f.read_text(encoding="utf-8")), f.stem):
            yield path, 0, v


def rawfind(pattern: str, limit: int = 60):
    """在全部原始文本里搜。find 只查剧本库，写「剧本不载」之前要用这个查一遍。"""
    rx = re.compile(pattern)
    n = 0
    for src, i, line in raw_texts():
        for m in rx.finditer(line):
            n += 1
            if n <= limit:
                print(f"{src}:{i}  " + " ".join(line[max(0, m.start() - 60):m.end() + 60].splitlines()))
            break
    print(f"共 {n} 处" + (f"，只列前 {limit} 处" if n > limit else ""))


def verify_quotes(out_path: str | None = None):
    """核对【目】【纲】【考异】里的「」短引：在全部剧本、档案、简介、年表、原始游戏文本里找得到才算数。"""
    norm = lambda t: re.sub(r"[\s，。、！？：；,.!?:;“”\"‘’'「」『』《》（）()—\-…·]", "", t.replace("{@Nickname}", "博士"))
    corpus = []
    for sid in episode_index():
        corpus += [(ln[1] or "") + " " + line_text(ln) for ln in lines_of(sid) if ln[0] != "b"]
        corpus.append(episode_index()[sid][1].get("synopsis", ""))
    for c in characters().values():
        prof = c.get("profile") or {}
        corpus += [sec.get("text", "") for sec in prof.get("sections", [])]
        corpus.append(str(prof.get("basic", "")))
    for e in events().values():
        corpus += e["lines"] + (e.get("notes") or []) + [e.get("when") or ""] + [s["text"] for s in e["sources"]]
    corpus += [line for _, _, line in raw_texts()]
    text = norm("\n".join(corpus))
    probs = Problems()
    bad, total = [], 0
    for y in volume_years():
        for e in load_volume(y, probs):
            for g in e.groups:
                fields = [("纲", g["gang"])] + [("目", t) for t in g["mu"]] + [("考异", k["text"]) for k in g["kaoyi"]]
                for name, t in fields:
                    for q in re.findall(r"「([^「」]{4,})」", t):
                        pieces = [norm(x) for x in re.split(r"……|…", q)]
                        pieces = [x for x in pieces if len(x) >= 3]
                        if not pieces:
                            continue
                        total += 1
                        if not all(x in text for x in pieces):
                            bad.append((y, e.where, e.anchor, name, q))
    lines = [f"{y}\t{w}\t{a}\t{n}\t{q}" for y, w, a, n, q in bad]
    print(f"短引 {total} 处，找不到 {len(bad)} 处")
    if out_path:
        Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        print("\n".join(lines))


def show_benmo(title: str):
    """列出一件纪事本末的概述和所收条目（纲、目），供核对概述用。"""
    data = json.loads((SITE_DATA / "annals.json").read_text(encoding="utf-8"))
    idx = {e["id"]: e for v in data["volumes"] for s in v["sections"] for d in s["days"] for e in d["entries"]}
    b = next((x for x in data["benmo"] if x["title"] == title), None)
    if not b:
        print(f"纪事本末里没有「{title}」")
        return
    print(f"# {title}")
    print("现有概述：" + "".join(b["summary"]))
    for r in b["entries"]:
        e = idx[r["id"]]
        print()
        print(f"## {e['when']}{'〔附〕' if e['minor'] else ''}  {e['id']}")
        for g in e["groups"]:
            print("纲：" + g["gang"].replace("**", ""))
            for m in g["mu"]:
                print("目：" + m)


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
    elif cmd == "rawfind":
        rawfind(rest[0])
    elif cmd == "check":
        return check(rest[0])
    elif cmd in ("build", "render"):
        return build()
    elif cmd == "zhuan":
        zhuan(rest[0])
    elif cmd == "benmo":
        show_benmo(rest[0])
    elif cmd == "long":
        long_groups(rest[0])
    elif cmd == "quotes":
        verify_quotes(rest[0] if rest else None)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
