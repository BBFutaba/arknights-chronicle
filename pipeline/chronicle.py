"""解析 PRTS「泰拉年表」：每条事件的日期、描述和出处，并把出处对应到本地的剧情组和分集。

年表源码是按时间顺序排列的 wikitable：
    ===='''1098 年'''====
    {|class="wikitable"
    !rowspan="15"|1098 年（时间未知）       ← 年份级行标题
    |{{并行折叠框|事件描述|*第九章 风暴瞭望：[[9-21 重燃/NBT|9-21]]}}
    !1 月 18 日                             ← 年内日期行标题
    |{{并行折叠框|...}}
页面本身的顺序就是时间顺序，事件按出现顺序编号即可。
"""
import html
import re
from dataclasses import dataclass, field

from . import gamedata, prts

TEMPLATE = "{{并行折叠框|"
HEADING_RE = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$")
YEAR_RE = re.compile(r"(约?前\s*)?(\d+)\s*年")
STORY_LINK_RE = re.compile(r"^(.*?)/(BEG|END|NBT)$")
CODE_TITLE_RE = re.compile(r"^([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)[\s_]+(.+)$")
CODE_ONLY_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")
CHAPTER_PREFIX_RE = re.compile(r"^第[一二三四五六七八九十零〇百]+章\s*|^序章\s*")
AVG_BY_SUFFIX = {"BEG": "行动前", "END": "行动后", "NBT": "幕间"}


@dataclass
class Source:
    text: str  # 出处原文（已去掉 wiki 标记），如「第九章 风暴瞭望：9-21」
    kind: str  # story（对应到了剧情）| lore（大地巡旅、情报处理室、档案等）
    group_ids: list[str] = field(default_factory=list)
    story_ids: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)  # 形如剧情链接、但本地找不到的目标


@dataclass
class Event:
    id: str
    order: int
    era: str  # 所在章节，如「结晶纪元 · 12世纪 · 1098 年」
    when: str  # 日期标签，如「1098 年 7 月」
    year: int | None
    lines: list[str]  # 事件描述，PRTS 用 <br> 分隔的多句拆成多行
    parallel: bool  # PRTS 标注为平行世界内容
    notes: list[str]
    sources: list[Source]

    @property
    def group_ids(self) -> list[str]:
        return list(dict.fromkeys(g for s in self.sources for g in s.group_ids))

    @property
    def story_ids(self) -> list[str]:
        return list(dict.fromkeys(i for s in self.sources for i in s.story_ids))


# ---------------------------------------------------------------- wiki 文本处理
def balanced_end(text: str, start: int, open_: str = "{{", close: str = "}}") -> int:
    """text[start:] 以 open_ 开头，返回与之配对的 close 之后的位置。"""
    depth, i = 0, start
    while i < len(text):
        if text.startswith(open_, i):
            depth += 1
            i += len(open_)
        elif text.startswith(close, i):
            depth -= 1
            i += len(close)
            if depth == 0:
                return i
        else:
            i += 1
    return len(text)


def split_params(body: str) -> list[str]:
    """按顶层的 | 拆分模板参数，跳过嵌套的 {{ }} 和 [[ ]]。"""
    parts, depth, cur, i = [], 0, [], 0
    while i < len(body):
        two = body[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            cur.append(two)
            i += 2
        elif two in ("}}", "]]"):
            depth -= 1
            cur.append(two)
            i += 2
        elif body[i] == "|" and depth == 0:
            parts.append("".join(cur))
            cur = []
            i += 1
        else:
            cur.append(body[i])
            i += 1
    parts.append("".join(cur))
    return parts


def replace_templates(text: str, fn) -> str:
    """把 text 里的每个 {{...}} 交给 fn(名字, 参数列表) 处理，由内向外。"""
    out, i = [], 0
    while (j := text.find("{{", i)) != -1:
        end = balanced_end(text, j)
        inner = replace_templates(text[j + 2:end - 2], fn)
        name, *params = split_params(inner)
        out += [text[i:j], fn(name.strip().lower(), params)]
        i = end
    out.append(text[i:])
    return "".join(out)


def clean(text: str, notes: list[str] | None = None) -> str:
    def template(name, params):
        if name == "ruby" and len(params) >= 2:
            return f"{params[0]}（{params[1]}）"
        if name == "popup" and notes is not None:
            content = next((p.split("=", 1)[1] for p in params if p.startswith("内容=")), "")
            if content:
                notes.append(content)
        return ""

    text = replace_templates(text, template)
    text = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("'''", "").replace("''", "")
    text = html.unescape(text).replace(" ", " ")
    return "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in text.splitlines()).strip()


# ---------------------------------------------------------------- 出处对应到分集
class StoryIndex:
    def __init__(self, groups: dict[str, gamedata.Group]):
        self.groups = groups
        self.by_name = {}
        self.memory = {}  # 干员名 → 干员密录组 id
        for g in groups.values():
            if g.category == gamedata.MEMORY:
                # 密录组以干员名为名（「空」「林」「陈」……），不能参与出处标签的子串匹配
                self.memory.setdefault(g.name, g.id)
                continue
            if g.category in gamedata.EXTRA_CATEGORIES:
                continue  # 年表的出处只链到剧情回顾里的组
            self.by_name.setdefault(g.name, g.id)
        self.names = sorted(self.by_name, key=len, reverse=True)

    def memory_episodes(self, target: str) -> list[gamedata.Episode] | None:
        """[[伺夜/干员密录/2]]、[[暴行/干员密录/2-2]] → 分集；不是密录链接时返回 None。"""
        m = gamedata.MEMORY_LINK_RE.match(target.strip())
        if not m:
            return None
        gid = self.memory.get(m.group(1).strip())
        if gid is None:
            return []
        return gamedata.memory_set(self.groups[gid], int(m.group(2)), int(m.group(3)) if m.group(3) else None)

    def group_from_label(self, label: str) -> list[str]:
        """「第九章 风暴瞭望」「孤星」「第十二章 惊霆无声、第十三章 恶兆湍流」→ 剧情组 id。"""
        label = CHAPTER_PREFIX_RE.sub("", label.strip())
        if label in self.by_name:
            return [self.by_name[label]]
        found, rest = [], label
        for n in self.names:
            if n in rest:
                found.append(self.by_name[n])
                rest = rest.replace(n, "")
        return found

    def episodes(self, target: str, group_ids: list[str]) -> list[gamedata.Episode]:
        m = STORY_LINK_RE.match(target.strip())
        if not m:
            return []
        base, avg = m.group(1).strip(), AVG_BY_SUFFIX[m.group(2)]
        if mm := CODE_TITLE_RE.match(base):
            code, title = mm.group(1), mm.group(2).strip()
        elif CODE_ONLY_RE.match(base):
            code, title = base, ""
        else:
            code, title = "", base
        pools = [[e for g in group_ids for e in self.groups[g].episodes]] if group_ids else []
        pools.append([e for g in self.groups.values() if g.category in gamedata.CATEGORIES.values() for e in g.episodes])
        for pool in pools:
            for match in (lambda e: code and e.code == code, lambda e: title and e.title == title):
                hits = [e for e in pool if match(e)]
                if hits:
                    exact = [e for e in hits if e.avg == avg]
                    return exact or hits
        return []


def parse_sources(raw: str, index: StoryIndex) -> list[Source]:
    out = []
    for line in raw.splitlines():
        line = line.strip().lstrip("*").strip()
        if not line:
            continue
        text = clean(line)
        prefix = re.split(r"[:：]", text, maxsplit=1)[0] if re.search(r"[:：]", text) else ""
        group_ids = index.group_from_label(prefix) if prefix else []
        story_ids, unmatched = [], []
        for target, label in re.findall(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]", line):
            if target.strip() == "剧情一览":
                group_ids += [g for g in index.group_from_label(label) if g not in group_ids]
                continue
            eps = index.memory_episodes(target)
            if eps is None:
                eps = index.episodes(target, group_ids)
            if not eps and (STORY_LINK_RE.match(target.strip()) or gamedata.MEMORY_LINK_RE.match(target.strip())):
                unmatched.append(target.strip())
            for e in eps:
                story_ids.append(e.story_id)
                if e.group_id not in group_ids:
                    group_ids.append(e.group_id)
        out.append(Source(text, "story" if group_ids else "lore", group_ids,
                          list(dict.fromkeys(story_ids)), unmatched))
    return out


# ---------------------------------------------------------------- 主解析
def header_text(lines: list[str]) -> str:
    first = lines[0].lstrip("!")
    if "|" in first and "||" not in first:
        first = first.rsplit("|", 1)[1]
    return clean("\n".join([first] + lines[1:])).replace("\n", " ")


def heading_year(heading: str) -> int | None:
    m = YEAR_RE.search(heading)
    return int(m.group(2)) if m and not m.group(1) else None


def parse_year(text: str) -> int | None:
    m = YEAR_RE.search(text)
    if not m:
        return None
    return -int(m.group(2)) if m.group(1) and "前" in m.group(1) else int(m.group(2))


def parse_chronicle(text: str, groups: dict[str, gamedata.Group]) -> list[Event]:
    index = StoryIndex(groups)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    # 先把每个事件模板换成占位符，剩下的就能按行处理
    events_raw = []

    def stash(m_start: int) -> str:
        end = balanced_end(text, m_start)
        events_raw.append(text[m_start + len(TEMPLATE):end - 2])
        return f"\x00{len(events_raw) - 1}\x00", end

    parts, i = [], 0
    while (j := text.find(TEMPLATE, i)) != -1:
        token, end = stash(j)
        parts += [text[i:j], token]
        i = end
    parts.append(text[i:])
    body = "".join(parts)

    events: list[Event] = []
    headings: dict[int, str] = {}
    year_head: str | None = None
    date_head: str | None = None
    pending_header: list[str] | None = None

    def flush_header():
        nonlocal pending_header, year_head, date_head
        if pending_header is None:
            return
        h = header_text(pending_header)
        pending_header = None
        if YEAR_RE.search(h) or re.search(r"世纪|纪元|元年|TT\s*\d", h):
            year_head, date_head = h, None
        else:
            date_head = h

    for line in body.splitlines():
        s = line.strip()
        if m := HEADING_RE.match(s):
            flush_header()
            level = len(m.group(1))
            headings = {k: v for k, v in headings.items() if k < level}
            headings[level] = clean(m.group(2))
            year_head = date_head = None
            continue
        if s.startswith("{|") or s.startswith("|}"):
            flush_header()
            year_head = date_head = None
            continue
        if s.startswith("!"):
            flush_header()
            pending_header = [s]
            continue
        if s.startswith("|") and pending_header is not None:
            flush_header()
        elif pending_header is not None and "\x00" not in s:
            pending_header.append(s)
            continue
        for k in re.findall(r"\x00(\d+)\x00", s):
            params = split_params(events_raw[int(k)])
            notes: list[str] = []
            desc = clean(params[0], notes)
            sources = parse_sources(params[1], index) if len(params) > 1 else []
            era = " · ".join(v for _, v in sorted(headings.items()) if v not in ("注释与链接",))
            heading = headings[max(headings)] if headings else ""
            if year_head:
                base = re.sub(r"\s*（时间未知）", "", year_head) if date_head else year_head
                when = f"{base} {date_head}" if date_head else base
                year = parse_year(year_head)
            else:
                when = date_head or heading
                year = heading_year(heading)
            if year is None:
                year = heading_year(heading)
            events.append(Event(
                id=f"ev{len(events) + 1:04d}", order=len(events), era=era, when=when, year=year,
                lines=[l for l in desc.splitlines() if l], parallel=any("平行" in n for n in notes),
                notes=[clean(n) for n in notes], sources=sources,
            ))
    return events


def load_events(groups: dict[str, gamedata.Group]) -> tuple[list[Event], dict]:
    page = prts.load_page("泰拉年表")
    meta = {"title": page["title"], "revid": page["revid"], "timestamp": page["timestamp"]}
    return parse_chronicle(page["content"], groups), meta
