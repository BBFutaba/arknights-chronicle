"""解析明日方舟 AVG 剧本（story/*.txt）。

剧本是一行一条指令的格式，例如：
    [Background(image="bg_cher_7", fadetime=0)]
    [Character(name="char_002_amiya_1#5")]
    [name="阿米娅"]   天灾……
    [Decision(options="选项一;选项二", values="1;2")]
没有指令前缀的行是旁白。这里只保留和剧情内容有关的部分：台词、旁白、选项、
立绘、背景图和「地点·时间」戳，演出类指令（音效、镜头、特效等）全部忽略。
"""
import re
from collections import Counter
from dataclasses import dataclass, field

PARAM_RE = re.compile(r'([A-Za-z_]\w*)\s*=\s*("(?:[^"\\]|\\.)*"|[^,]*)')
RICH_TAG_RE = re.compile(r"</?(?:color|i|b|u|size|p)(?:=[^>]*)?>|</>", re.I)
SEGMENT_RE = re.compile(r"<p=(\d+)>(.*?)</>")


@dataclass
class Line:
    kind: str  # dialogue | narration | decision | branch | stamp
    text: str = ""
    speaker: str | None = None
    options: list[str] | None = None


@dataclass
class Script:
    lines: list[Line] = field(default_factory=list)
    portraits: Counter = field(default_factory=Counter)  # 立绘 id（去掉表情/差分后缀）
    backgrounds: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)  # 剧情 CG
    stamps: list[tuple[str, str]] = field(default_factory=list)  # (地点, 时间)


def clean_text(s: str) -> str:
    s = s.replace("Dr.{@nickname}", "博士").replace("{@nickname}", "博士").replace("{@nbs}", " ")
    s = s.replace("\\n", " ")
    s = RICH_TAG_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def split_command(line: str) -> tuple[str, str] | None:
    """把 "[head]rest" 拆开；方括号要跳过引号和圆括号里的内容。不是指令行时返回 None。"""
    if not line.startswith("["):
        return None
    in_quote, depth = False, 0
    for i in range(1, len(line)):
        c = line[i]
        if c == '"':
            in_quote = not in_quote
        elif in_quote:
            continue
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "]" and depth <= 0:
            return line[1:i].strip(), line[i + 1:]
    return None


def parse_params(s: str) -> dict[str, str]:
    out = {}
    for m in PARAM_RE.finditer(s):
        v = m.group(2).strip()
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1].replace('\\"', '"')
        out[m.group(1).lower()] = v
    return out


def parse_head(head: str) -> tuple[str, dict[str, str]]:
    m = re.match(r"([A-Za-z_][\w.]*)\s*(.*)$", head, re.S)
    if not m:
        return "", {}
    name, rest = m.group(1).lower(), m.group(2).strip()
    if rest.startswith("("):
        return name, parse_params(rest[1:].rstrip(")"))
    if rest.startswith("="):  # [name="阿米娅"] 这类直接写参数的指令
        return name, parse_params(head)
    return name, {}


def portrait_base(raw: str) -> str:
    """char_002_amiya_1#5 / avg_npc_624_1#1$1 → 去掉 # 和 $ 之后的表情差分。"""
    return re.split(r"[#$]", raw.strip(), maxsplit=1)[0]


def parse_script(text: str) -> Script:
    sc = Script()

    def say(kind: str, txt: str, speaker: str | None = None):
        txt = clean_text(txt)
        if txt:
            sc.lines.append(Line(kind, txt, speaker))

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        parts = split_command(line)
        if parts is None:
            say("narration", line)
            continue
        head, rest = parts
        cmd, p = parse_head(head)

        if cmd in ("name", "multiline"):
            speaker = clean_text(p.get("name", ""))
            say("dialogue" if speaker else "narration", rest, speaker or None)
        elif cmd in ("narration", "title", "avatarid"):
            say("narration", rest)
        elif cmd == "voicewithin":
            say("dialogue", rest, None)
        elif cmd in ("subtitle", "sticker"):
            say("narration", p.get("text", ""))
        elif cmd in ("animtext", "spellsticker"):
            segs = [clean_text(t) for _, t in sorted(SEGMENT_RE.findall(rest))]
            segs = [s for s in segs if s]
            if not segs:
                continue
            if p.get("name") == "group_location_stamp":
                place, when = segs[0], (segs[1] if len(segs) > 1 else "")
                sc.stamps.append((place, when))
                sc.lines.append(Line("stamp", f"{place} · {when}" if when else place))
            else:
                say("narration", " ".join(segs))
        elif cmd == "decision":
            opts = [clean_text(o) for o in p.get("options", "").split(";")]
            opts = [o for o in opts if o]
            if opts:
                sc.lines.append(Line("decision", options=opts))
        elif cmd == "predicate":
            refs = p.get("references", "")
            if refs:
                sc.lines.append(Line("branch", refs.replace(";", "/")))
        elif cmd in ("character", "charslot", "charactercutin"):
            for key in ("name", "name2"):
                if p.get(key):
                    sc.portraits[portrait_base(p[key])] += 1
        elif cmd == "background":
            img = p.get("image")
            if img and img not in sc.backgrounds:
                sc.backgrounds.append(img)
        elif cmd == "image":
            img = p.get("image")
            if img and img not in sc.images:
                sc.images.append(img)
    return sc
