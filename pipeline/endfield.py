"""终末地 27010254 的只读适配器（仅 Python 标准库）。

文本以 TextTable.key → I18nTextTable_CN.id 或直接 id 解引用，绝不混用旧版本。
与 script.clean_text 一样去掉颜色/样式、合并换行；{F}…{M}… 两种文本均保留为
「〔女〕…〔男〕…」，{player}/昵称占位符称「管理员」。entry 链接去标签留原词；
image 标签转成「〔图片：资源键〕」或「〔表情：资源键〕」，不猜图片内容。
未知占位符原样保留供检查。
说话人来自 DialogTextTable/RadioTable.actorName，按其 id 解引用 CN 表；例如
dlg_a1m6d5_5_019 的 actorNameId=yuxiuli，actorName 解得「老俞{俞秀丽}」。
花括号是本地化文本中的开发标记：前半是场上称呼，后半可能是身份名、资源编号、
演出阶段或群体说明，并非一律是真名。按以下顺序整理，只改 speaker，不增删剧本行：
1. 后半含 ASCII 字母、数字、-、_：内部编号，保留前称，不从编号里猜人名。
2. 群体（&/、等）或扮演标记：保留前称；后半与前称相同时直接去括号。
3. 前称是幻影、蚀影、影子、心魔（如「罗丹的幻影{罗丹」「竺的蚀影{竺」）：保留前称，
   幻象的话不并入本人名下。
4. 后半是泛称（含「的」、问号、声音/系统/年龄阶段等）：保留前称，存表备查。
5. 前半是泛称（含「的」、问号、无线电/录音/职业等），后半是姓名：取后名。
6. 两边均为姓名式称呼：取后面的全名，前称记为此人的别名；同一别名若指向多个
   正名则不全局归并（如「峰」的两种原文异写），避免无据合并。
编者另定的个别例外在 SPEAKER_FIX（如「小橡{小祥」取画面称呼小橡，「塔塔{TA-TA原型机」并入原型机）。
完整映射、导出剧本中的命中行数和规则写到 site/data/endfield-speakers.tsv；
「？？？{亨德森}」等揭名据内部标记，编者应查表，不能视为场上已公开身份。
选项用 decision，条件/跳转用 branch；并列分支全部展示，回边只显示跳转不展开。
时间轴保留选项 logicId/optionIndex，但尚未还原所有跳转：时间序表示候选轨道全集，
不声称是一条玩家会连续经历的实机路径；不能据此认定互斥台词同时发生。
DialogTree 按 connections 遍历；Timeline 按 startTime；无线电按 index；
SNS 按 nextContentId/optionNextContentId。跨场景顺序不能从编号假定为实际触发顺序，
此时每个场景独立成集，目录仅按自然编号，audit 中注明。ID 使用原始资源键，
不使用中文标题或遍历序号，因而改名/插入资源不会重命名旧分集。
分集显示名用任务名＋媒介＋任务内目录序号；无任务时按所在组编号。编号沿用
原目录顺序，不能据此认定跨媒介的实机触发先后；资源键只作 id，不重复作 code。

所有人物页键均为「终末地·整理后的名字」，不套用明日方舟别名/势力/博士规则。
剧本和出场使用整理后的说话人；审计表保留原写法，别名仅在终末地命名空间内使用。
编者的别名表 data/annals/别名-塔卫二.md（book_aliases）再把说话人并到正名的人物页，
剧本里照旧显示原称。CharacterTable 里的可操作干员（load_operators）先登记成干员页，
带职业、星级、英文代号和按原文分段的档案，供人物页和 @档 用。
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from functools import cache
import csv
import html
import json
import re

from . import config, gamedata
from .analyze import EpisodeData
from .entities import Character, Power
from .script import Line, Script

PREFIX = "终末地·"
LORE = "图鉴与文案"  # 2026-11-12 盘点后补接的图鉴、文案，见 Loader.load_lore


def generic_speaker(name):
    """描述/媒介/职业称呼；不据长度猜姓名。未识别的非编号称呼按姓名式处理。"""
    return (not name or bool(re.search(r"[的？?]|^(?:婴儿|少年老|成年老|老年老|变声器)", name))
            or name in {"少年", "老人", "护士", "巡卫", "天师", "行商", "女记者", "基地警卫",
                        "客栈帮工", "卖花少女", "红发少女", "年轻天师", "鲁珀青年", "裂地者",
                        "无线电", "无线电通信", "录音", "留声带", "喇叭广播", "播报音", "系统语音",
                        "异口同声", "武陵众人", "影子"}
            or name.endswith(("声音", "呢喃", "系统", "语音播报器", "蚀影")))


# 编者定的例外：画面称呼与剧中他人的称呼一致，内部名疑是异写，取画面称呼为正名
SPEAKER_FIX = {
    "小橡{小祥": ("小橡", "小祥", "编者定：画面与庄方宜都作小橡，取前称，内部名为别名"),
    # 内部名带字母，按规则 1 会当成编号；它其实就是取名以前的说话人名
    "塔塔{TA-TA原型机": ("TA-TA原型机", "塔塔", "编者定：陈千语为原型机取名塔塔，并为一人"),
    # 后半「变声器伊冯」按规则 4 当成泛称；喇叭广播又是泛称，不能用别名表全局并入伊冯
    "喇叭广播{变声器伊冯": ("伊冯", "", "编者定：伊冯用变声器广播，并入伊冯"),
    # 后半是同一个内部编号，前称是泛称：按规则 1 会各成一页，其实是一个人（按原写法逐条定，不全局并）
    "惊恐的男人{c33m1-杰弗里": ("杰弗里", "", "编者定：内部名同作 c33m1-杰弗里，并入杰弗里"),
    "模糊的男声{c33m1-杰弗里": ("杰弗里", "", "编者定：内部名同作 c33m1-杰弗里，并入杰弗里"),
    "史尔特尔的声音{c16-史尔特尔": ("史尔特尔", "", "编者定：内部名同作 c16-史尔特尔，并入史尔特尔"),
    "神色悲戚的天师{e10m3-神色悲戚的天师": ("赵叔", "", "编者定：庄方宜当面称他赵叔，以赵叔为正名"),
    "严肃的天师{sm2l8m1-韩天师": ("韩天师", "", "编者定：内部名作韩天师，只此一任务；主线 e11 的严肃的天师不并"),
    "年长的天师{sm2l8m1-陈天师": ("陈天师", "", "编者定：内部名作陈天师"),
    "烦恼的应龙队员{gm02m21-炤": ("炤", "", "编者定：内部名作炤，并入炤"),
}

BOOK_ALIASES = config.ROOT / "data" / "annals" / "别名-塔卫二.md"


@cache
def book_aliases():
    """塔卫二编的别名表：每行「别名=正名」，两边都不带「终末地·」。剧本里说话人是别名的，
    台词和出场算到正名的人物页，剧本里照旧显示原称；书里写 [[别名]] 也连到正名。"""
    out = {}
    text = BOOK_ALIASES.read_text(encoding="utf-8") if BOOK_ALIASES.exists() else ""
    for raw in re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines():
        if "=" in raw and not raw.startswith("#"):
            a, _, c = raw.partition("=")
            out[a.strip()] = c.split("#", 1)[0].strip()
    return out


def add_book_aliases(reg):
    """别名记到正名的人物页上（人物页「又名」、网页按别名找人都靠它）。"""
    for alias, target in book_aliases().items():
        ch = reg.chars.get(PREFIX + target)
        if ch and PREFIX + alias not in ch.aliases:
            ch.aliases.append(PREFIX + alias)


def speaker_name(raw):
    """返回（规范名，姓名式别称或空串，审计规则）；不改变任何台词或行类型。"""
    raw = raw.strip("{}")
    if "{" not in raw:
        return raw, "", "原称"
    front, back = (s.strip() for s in raw.split("{", 1))
    back = back.rstrip("}")
    if f"{front}{{{back}" in SPEAKER_FIX:
        return SPEAKER_FIX[f"{front}{{{back}"]
    if re.search(r"[A-Za-z0-9_-]", back):
        return front, "", "内部编号：取前称"
    if re.search(r"[&＆、，,]", front + back) or "饰" in back:
        return front, "", "群体或扮演：取前称"
    if front == back:
        return front, "", "同名：去标记"
    if re.search(r"幻影|蚀影|影子|心魔", front):
        return front, "", "幻象：取前称"
    if generic_speaker(back):
        return front, "", "后为泛称：取前称"
    if generic_speaker(front):
        return back, "", "前为泛称：取后名（内部身份）"
    return back, front, "两侧姓名：取后名，前称为别名"


def write_speakers(episodes, path):
    counts = Counter()
    for ep in episodes:
        counts.update(getattr(ep, "speaker_audit", {}))
    with path.open("w", encoding="utf-8", newline="") as f:
        out = csv.writer(f, delimiter="\t", lineterminator="\n")
        out.writerow(["原写法", "改后说话人", "行数", "依据规则"])
        for (raw, name, rule), count in sorted(counts.items()):
            out.writerow([PREFIX + raw, PREFIX + name if name else "", count, rule])


def natural(value):
    return tuple((1, int(x)) if x.isdigit() else (0, x.lower())
                 for x in re.split(r"(\d+)", str(value)))


def clean(text, breaks=False):
    """breaks=True 时保留原文分段（干员档案用），每段照常清理。"""
    if breaks:
        text = re.sub(r"<br\s*/?>|\\n", "\n", html.unescape(text or ""), flags=re.I)
        return "\n".join(p for p in (clean(s) for s in text.split("\n")) if p)
    text = html.unescape(text or "")
    text = text.replace("{F}", "〔女〕").replace("{M}", "〔男〕")
    for token in ("{@nickname}", "{nickname}", "{playerName}", "{player}"):
        text = text.replace(token, "管理员")
    text = re.sub(r"<image>(.*?)</image>", lambda m: "〔图片：" + m[1].strip() + "〕", text, flags=re.I | re.S)
    def image_label(match):
        key = match[2]
        kind = "表情" if key.startswith("sns_emoji_") else "图片"
        return f"〔{kind}：{key}〕"
    text = re.sub(r'''<image=(["'])(.*?)\1(?:\s+[^>]*)?>''', image_label, text, flags=re.I)
    text = re.sub(r"<entry=[^>]+>", "", text, flags=re.I)
    text = re.sub(r"<br\s*/?>|\\n", " ", text, flags=re.I)
    text = re.sub(r"</?(?:color|size|b|i|u|s|alpha|align|line-height|link)(?:[= ][^>]*)?>|<[@#][^>]+>|</>", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def parse_basic(text):
    """「【代号】莱万汀 【性别】女 …」→ {"代号": "莱万汀", "性别": "女", …}；栏内分段并成一行。"""
    parts = re.split(r"【([^】]+)】", text)
    return {k.strip(): re.sub(r"\s+", " ", v).strip() for k, v in zip(parts[1::2], parts[2::2])}


def walk(value, path=""):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from walk(child, f"{path}/{key}")
    elif isinstance(value, list):
        for key, child in enumerate(value):
            yield from walk(child, f"{path}/{key}")


@dataclass
class Group(gamedata.Group):
    game: str = "endfield"
    description: str = ""
    display_label: str = ""

    @property
    def label(self):
        return self.display_label


@dataclass
class Episode(gamedata.Episode):
    script: Script = field(default_factory=Script)
    synopsis: str = ""
    source: str = ""
    order_note: str = ""


class Loader:
    def __init__(self, root):
        self.root = root
        self.tables = {}
        self.i18n = self.table("I18nTextTable_CN")
        self.texts = self.table("TextTable")
        self.groups = {}
        self.audit = {"source_build": root.name, "uncertain": [], "excluded": [], "missing": [], "timelines": {}}
        self.operators = {}  # 干员名 → {ids, rarity, profession, appellation, profile}，见 load_operators
        self.assets = {}
        inventory = root.parent.parent / "inventory/client_ab_assets.tsv"
        if inventory.exists():
            with inventory.open(encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f, delimiter="\t"):
                    p = row["asset_path"]
                    if any(s in p for s in ("/dialog/json/", "/dialog/timeline/", "/mission/episode/", "/subtitle/")):
                        if p.endswith((".json", ".asset", ".playable")):
                            self.assets[p] = row["bundle_path"]
        self.dialogs = self.table("DialogTextTable")
        self.options = self.table("DialogOptionTable")
        self.missions = {}
        for p in sorted((root / "Json/MissionRuntimeAsset").glob("*.json")):
            if not p.stem.endswith("_meta"):
                d = self.read(p)
                if "missionId" in d:
                    self.missions[d["missionId"]] = d
        self.mission_groups = {}
        self.used_dialogs = set()
        self.used_options = set()
        self.used_black = set()
        self.episode_ids = set()
        self.timeline_cache = {}
        self.mission_rank = {}

    @staticmethod
    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def table(self, name):
        if name not in self.tables:
            p = self.root / "TableCfg" / f"{name}.json"
            self.tables[name] = self.read(p) if p.exists() else {}
        return self.tables[name]

    def text(self, value, breaks=False):
        if isinstance(value, dict):
            if "key" in value:
                return self.text(self.texts.get(value["key"], {}), breaks)
            ident = str(value.get("id", 0))
            if ident != "0" and ident not in self.i18n:
                self.audit["missing"].append("I18n:" + ident)
            return clean(self.i18n.get(ident, value.get("text", "")), breaks)
        return clean(value, breaks) if isinstance(value, str) else ""

    def objects(self, asset):
        """只读清单定位的结构化对象；.strings/.allstrings 均不当作正文。"""
        folder = self.root / "ab_text" / self.assets.get(asset, "__missing__")
        for p in sorted(folder.glob("*.json")):
            if any(x in p.name for x in (".strings.", ".allstrings.", ".poolrefs.")):
                continue
            yield p, self.read(p)

    def source(self, path):
        return path.relative_to(self.root).as_posix()

    def group(self, gid, name, category, description="", label=""):
        gid = "ef_" + gid
        if gid not in self.groups:
            self.groups[gid] = Group(gid, PREFIX + name, PREFIX + category, None,
                                     description=description, display_label=label)
        return self.groups[gid]

    def add(self, group, key, title, lines, synopsis="", source="", note="", avg="剧情"):
        if not lines:
            return
        sid = "ef_" + key
        if sid in self.episode_ids:
            raise ValueError(f"duplicate Endfield episode: {sid}")
        self.episode_ids.add(sid)
        group.episodes.append(Episode(sid, group.id, "", title, avg,
                                      len(group.episodes), "", None, Script(lines),
                                      synopsis, source, note))
        if note:
            self.audit["uncertain"].append({"episode": sid, "source": source, "note": note})

    def say(self, row, text_key="dialogText"):
        text = self.text(row.get(text_key, {}))
        if not text:
            return []
        name = self.text(row.get("actorName", {})).strip("{}")
        return [Line("dialogue" if name else "narration", text, name or None)]

    def dialog(self, key):
        if key not in self.dialogs:
            self.audit["missing"].append("DialogTextTable:" + key)
            return []
        self.used_dialogs.add(key)
        return self.say(self.dialogs[key])

    def decision(self, keys):
        values = []
        for key in keys:
            if key not in self.options:
                self.audit["missing"].append("DialogOptionTable:" + key)
                continue
            self.used_options.add(key)
            if text := self.text(self.options[key].get("optionText", {})):
                values.append(text)
        return [Line("decision", speaker="管理员", options=values)] if values else []

    def setup_groups(self):
        # 官方 episode 资源给出章/幕名与 missionIdList，不按任务名猜测主支线。
        for asset in sorted(self.assets, key=natural):
            if "/mission/episode/" not in asset:
                continue
            for path, row in self.objects(asset):
                if "missionIdList" not in row:
                    continue
                key = row["m_Name"]
                category = "主线" if key.startswith("main_") else "角色任务"
                title = " · ".join(filter(None, (self.text(row.get("chapterNum")),
                                                self.text(row.get("episodeNum")),
                                                self.text(row.get("episodeName")))))
                g = self.group(key, title or key, category)
                for rank, mid in enumerate(row["missionIdList"]):
                    self.mission_groups[mid] = g
                    self.mission_rank[mid] = rank
        # 补充任务分段（e5m0d5 等）：最长的已登记任务 id 前缀优先。
        for mid in sorted(self.missions, key=natural):
            if mid in self.mission_groups:
                continue
            m = self.missions[mid]
            parent = next((k for k in sorted(self.mission_groups, key=len, reverse=True)
                           if re.fullmatch(re.escape(k) + r"d\d+", mid)), None)
            if parent:
                self.mission_groups[mid] = self.mission_groups[parent]
                self.mission_rank[mid] = self.mission_rank.get(parent, 0)
                continue
            if m.get("charId"):
                cid = m["charId"]
                name = self.text(self.table("CharacterTable").get(cid, {}).get("name")) or cid
                g = self.group("character_" + cid, name, "角色任务")
            elif m["missionType"] == 11:
                g = self.group("activity_" + mid, self.text(m["missionName"]) or mid, "活动",
                               self.text(m.get("missionDescription")))
            else:
                view = self.table("MissionTypeInfoTable").get(str(m["missionType"]), {}).get("missionViewType", "")
                category = {"MissionViewSide": "支线", "MissionViewDiscovery": "区域任务",
                            "MissionViewMain": "主线补遗"}.get(view, "其他任务")
                # 地图键来自客户端 levelId；有官方地图名时用 TextTable，缺失时保留键。
                region = m.get("levelId", "").split("_")[0] or "other"
                slug = {"支线": "side", "区域任务": "region", "主线补遗": "main_extra", "其他任务": "other"}[category]
                g = self.group(f"tasks_{slug}_{region}", self.region_name(region), category)
            self.mission_groups[mid] = g

    def group_for(self, key):
        rest = re.sub(r"^(?:dlg|radio|sns)_", "", key)
        mid = next((m for m in sorted(self.missions, key=len, reverse=True)
                    if rest == m or rest.startswith(m + "_")), None)
        if mid:
            return self.mission_groups[mid], mid
        if rest.startswith("npc_"):
            return self.group("npc_dialog", "干员与乘员交谈", "人物交谈"), None
        region = re.match(r"map\d+", rest)
        region = region[0] if region else "other"
        return self.group("ambient_" + region, self.region_name(region), "区域对话"), None

    def region_name(self, region):
        for row in self.table("DomainDataTable").values():
            if row.get("domainShopGroupId") == "domainshop_" + region:
                return self.text(row.get("domainName")) or region
        for key in (f"scene_{region}_location_tips_1", region + "_name"):
            if key in self.texts:
                return self.text(self.texts[key])
        return "未归属区域" if region == "other" else region

    def timeline(self, name):
        # 演员轨上的 DialogTrunkPlayableAsset 带 startTime，不能按 dlg 后缀排序。
        if name in self.timeline_cache:
            return self.timeline_cache[name]
        assets = [a for a in self.assets if a.endswith("_actor.playable") and
                  re.fullmatch(r"[fm]?_?" + re.escape(name), a.split("/")[-3])]
        out = []
        for asset in sorted(assets):
            all_objects = list(self.objects(asset))
            rows = [(p, d) for p, d in all_objects
                    if d.get("_trunkId") and "startTime" in d and not d.get("disableWhenLanguageIsCN")]
            if not rows:
                continue
            gender = "女" if "/f_" in asset else "男" if "/m_" in asset else ""
            if len(assets) > 1:
                out.append(Line("branch", "性别轨道：" + (gender or "通用")))
            objects = {int(p.stem.split("_")[1]): d for p, d in all_objects
                       if re.match(r"^\d+_-?\d+_", p.name)}
            clips = defaultdict(list)
            for _, track in all_objects:
                if track.get("m_Muted"):
                    continue
                for clip in track.get("m_Clips", []):
                    ref = clip.get("m_Asset", {})
                    if ref.get("m_FileID") == 0:
                        clips[ref.get("m_PathID")].append((clip.get("m_Start", 0),
                                                         clip.get("optionIndex", track.get("OptionIndex", 0))))
            events = []
            for p, row in rows:
                ident = int(p.stem.split("_")[1])
                branch = clips.get(ident, [(row["startTime"], 0)])[0][1]
                events.append((row["startTime"], p.name, branch, self.dialog(row["_trunkId"])))
            for ident, obj in objects.items():
                if not obj.get("options") or ident not in clips:
                    continue
                opts = obj["options"]
                keys = [o["_optionId"] for o in opts if o.get("_optionId")]
                for start, branch in clips[ident]:
                    choices = self.decision(keys)
                    for opt in opts:
                        if opt.get("_optionId"):
                            choices.append(Line("branch", f"选项 {opt['_optionId']}：逻辑 {opt.get('logicId', '')}，轨道 {opt.get('optionIndex', 0)}"))
                    events.append((start, str(ident), branch, choices))
            evidence = self.audit["timelines"].setdefault(name, [])
            for start, ident, branch, lines in sorted(events, key=lambda x: (x[0], x[1])):
                if branch:
                    out.append(Line("branch", f"时间轴选项轨道 {branch}（{start:g} 秒）"))
                out.extend(lines)
                evidence.append({"asset": asset, "object": ident, "startTime": start, "optionIndex": branch})
        if not out:
            self.audit["missing"].append("Timeline:" + name)
        self.timeline_cache[name] = out
        return out

    def tree(self, data, source):
        nodes = {n.get("$id", f"unidentified_{i}"): n for i, n in enumerate(data.get("nodes", []))}
        edges = defaultdict(list)
        for conn in data.get("connections", []):
            a = conn.get("_sourceNode", {}).get("$ref")
            b = conn.get("_targetNode", {}).get("$ref")
            if a in nodes and b in nodes:
                # ExActor/Camera/Summary 是并行演出及跳过摘要，不是正文流程。
                if not re.search(r"Ex(?:Actor|Camera|Summary)Node$", nodes[b].get("$type", "")):
                    edges[a].append(b)
        lines, seen = [], set()

        def visit(key):
            if key in seen:
                lines.append(Line("branch", "接节点 " + key))
                return
            seen.add(key)
            node = nodes[key]
            if "Condition" in node.get("$type", "") or "If" in node.get("$type", ""):
                conditions = [(p, row.get("constValue")) for p, row in walk(node) if "constValue" in row]
                lines.append(Line("branch", f"条件节点 {key}：" + json.dumps(conditions, ensure_ascii=False)))
            # walk 保持 actionGroup/列表本来的顺序；只提取实际叙事引用。
            options = []
            for _, row in walk(node):
                if isinstance(row.get("_trunkId"), str) and row["_trunkId"]:
                    lines.extend(self.dialog(row["_trunkId"]))
                if isinstance(row.get("_optionId"), str) and row["_optionId"]:
                    options.append(row["_optionId"])
                if isinstance(row.get("name"), str) and re.match(r"(?:[fm]_)?dlgtl_", row["name"]):
                    lines.extend(self.timeline(row["name"]))
                if isinstance(row.get("key"), str) and row["key"].startswith("black_"):
                    key = row["key"]
                    if text := self.text(self.texts.get(key, {})):
                        lines.append(Line("narration", text))
                        self.used_black.add(key)
            lines.extend(self.decision(options))
            targets = edges[key]
            for i, target in enumerate(targets):
                if len(targets) > 1:
                    label = options[i] if len(options) == len(targets) else f"分支 {i + 1}"
                    lines.append(Line("branch", f"节点 {key} {label} → {target}"))
                visit(target)

        if nodes:
            visit(next(iter(nodes)))
        # 未连入入口的编辑残留不能冒充会播放的台词。
        unreachable = [n for k, n in nodes.items() if k not in seen and
                       any("_trunkId" in row for _, row in walk(n))]
        if unreachable:
            self.audit["excluded"].append({"source": source, "kind": "对话树未达节点", "count": len(unreachable)})
        return lines

    def load_dialogs(self):
        summary_map, summaries = self.table("DialogSummaryMapTable"), self.table("DialogSummaryTable")
        for asset in sorted(self.assets, key=natural):
            if "/dialog/json/" not in asset:
                continue
            key = asset.rsplit("/", 1)[-1].removesuffix(".json")
            for path, data in self.objects(asset):
                if data.get("type") != "Beyond.Gameplay.DialogTree":
                    continue
                g, mid = self.group_for(key)
                mission = self.missions.get(mid, {})
                title = self.text(mission.get("missionName")) or key
                source = self.source(path)
                lines = self.tree(data, source)
                summary = self.text(summaries.get(summary_map.get(key), {}))
                self.add(g, key, title + " · " + key, lines, summary or self.text(mission.get("missionDescription")),
                         source, "场内依对话树/时间轴；场景在任务各环节间的触发先后未完全还原，目录仅按场景自然编号。")

    def load_radio(self):
        for key, row in sorted(self.table("RadioTable").items(), key=lambda x: natural(x[0])):
            g, mid = self.group_for(key)
            m = self.missions.get(mid, {})
            lines = [line for r in sorted(row.get("radioSingleDataList", []), key=lambda x: x["index"])
                     for line in self.say(r, "radioText")]
            self.add(g, key, (self.text(m.get("missionName")) or "无线电") + " · " + key, lines,
                     source="TableCfg/RadioTable.json/" + key,
                     note="组内按 index；与面对面对话、过场的相互触发先后未合并。", avg="无线电")

    def load_sns(self):
        chats = self.table("SNSChatTable")
        options = self.table("SNSDialogOptionTable")
        for key, row in sorted(self.table("SNSDialogTable").items(), key=lambda x: natural(x[0])):
            g, mid = self.group_for(key)
            contents = row.get("dialogContentData", {})
            lines, seen = [], set()

            def visit(cid):
                cid = str(cid)
                if cid in seen:
                    lines.append(Line("branch", "接消息 " + cid))
                    return
                if cid not in contents or cid == "-1":
                    return
                seen.add(cid)
                c = contents[cid]
                text = self.text(c.get("content"))
                if text:
                    speaker = self.text(chats.get(c.get("speaker"), {}).get("name"))
                    if not c.get("speaker"):
                        speaker = "管理员"
                    lines.append(Line("dialogue", text, speaker or None))
                opts = [options[k] for k in c.get("dialogOptionIds", []) if k in options]
                if opts:
                    lines.append(Line("decision", speaker="管理员", options=[self.text(o["optionDesc"]) for o in opts]))
                    for o in opts:
                        lines.append(Line("branch", self.text(o["optionDesc"]) + " → " + str(o["optionNextContentId"])))
                        visit(o["optionNextContentId"])
                else:
                    visit(c.get("nextContentId", -1))

            roots = [c["contentId"] for c in contents.values() if c.get("preContentId") == 0 and c["contentId"] > 0]
            for cid in roots:
                visit(cid)
            self.add(g, key, "讯息 · " + key, lines, source="TableCfg/SNSDialogTable.json/" + key,
                     note="按消息连接展开全部选项；与任务场景的相互触发先后未合并。", avg="讯息")

    def load_operators(self):
        """可操作的干员：人物页标作干员，带稀有度、职业、英文代号和档案。档案保留原文分段，
        供 @档 引用；基础档案拆成栏目。同名的几个 id（男女管理员）同栏文字相同的只留一份，
        不同的在栏目名后注明性别；基础档案同一栏目取值不同的用「／」并列。"""
        professions = {r.get("profession"): self.text(r.get("name"))
                       for r in self.table("CharProfessionTable").values()}
        records = defaultdict(list)  # 干员名 → [(性别, 栏目, 文字)]
        basics = defaultdict(lambda: defaultdict(list))  # 干员名 → 栏目 → [取值]
        for cid, row in sorted(self.table("CharacterTable").items(), key=lambda x: natural(x[0])):
            name = self.text(row.get("name")) or cid
            op = self.operators.setdefault(name, {"ids": [], "rarity": 0, "profession": "", "appellation": ""})
            op["ids"].append(cid)
            op["rarity"] = max(op["rarity"], int(row.get("rarity") or 0))
            op["profession"] = op["profession"] or professions.get(row.get("profession"), "")
            op["appellation"] = op["appellation"] or row.get("engName") or ""
            texts = [(self.text(r.get("recordTitle")), self.text(r.get("recordDesc"), breaks=True))
                     for r in sorted(row.get("profileRecord", []), key=lambda x: x["recordIndex"])]
            basic = parse_basic(next((t for title, t in texts if title == "基础档案"), ""))
            for k, v in basic.items():
                if v not in basics[name][k]:
                    basics[name][k].append(v)
            records[name] += [(basic.get("性别", ""), title, t) for title, t in texts if t and title != "基础档案"]
        for name, recs in records.items():
            by_title = defaultdict(dict)
            for sex, title, t in recs:
                by_title[title].setdefault(re.sub(r"\s", "", t), (sex, t))
            sections = [{"title": f"{title}（{sex or i + 1}）" if len(variants) > 1 else title, "text": t}
                        for title, variants in by_title.items()
                        for i, (sex, t) in enumerate(variants.values())]
            self.operators[name]["profile"] = {"basic": {k: "／".join(v) for k, v in basics[name].items()},
                                               "sections": sections}

    def load_narrative(self):
        rich = self.table("RichContentTable")
        categories = self.table("PrtsCategory")
        first = self.table("PrtsFirstLv")
        used = set()

        def rich_lines(cid):
            return [Line("narration", self.text(c["content"])) for c in rich.get(cid, {}).get("contentList", [])
                    if self.text(c["content"])]

        for key, row in sorted(self.table("PrtsAllItem").items(), key=lambda x: natural(x[0])):
            cid = row.get("contentId")
            if cid not in rich:
                self.audit["excluded"].append({"source": "PrtsAllItem/" + key, "kind": row.get("type"), "reason": "非 RichContent（图像/媒体另由无线电接入）"})
                continue
            cat = first.get(row.get("firstLvId"), {}).get("categoryId", "other")
            name = self.text(categories.get(cat, {}).get("name")) or cat
            g = self.group("prts_" + cat, name, "文献档案")
            self.add(g, "prts_" + key, self.text(row.get("name")) or self.text(rich[cid].get("title")), rich_lines(cid),
                     source="TableCfg/RichContentTable.json/" + cid, avg="文献")
            used.add(cid)
        g = self.group("terminal", "终端记录", "文献档案")
        for key, row in sorted(self.table("PrtsReading").items(), key=lambda x: natural(x[0])):
            for r in sorted(row.get("list", {}).values(), key=lambda x: x["order"]):
                cid = r.get("contentId")
                if cid not in rich or cid in used:
                    continue
                self.add(g, "terminal_" + r["uniqId"], self.text(r.get("name")), rich_lines(cid),
                         source="TableCfg/RichContentTable.json/" + cid, avg="文献")
                used.add(cid)
        self.rich_used = used  # 剩下的在 load_lore 里另成一组「未入终端的文献」
        self.audit["excluded"].append({"kind": "未被 PRTS/终端引用的 RichContent", "ids": sorted(set(rich) - used), "reason": "另成「图鉴与文案 · 未入终端的文献」，含玩法说明/测试或来源不明内容，未逐项判定"})
        self.load_operators()
        for cid, row in self.table("CharacterTable").items():
            name = self.text(row.get("name")) or cid
            g = self.group("profiles", "干员档案", "干员档案")
            for r in sorted(row.get("profileRecord", []), key=lambda x: x["recordIndex"]):
                text = self.text(r.get("recordDesc"))
                self.add(g, "profile_" + r["id"], name + " · " + self.text(r.get("recordTitle")),
                         [Line("narration", text)] if text else [], source="TableCfg/CharacterTable.json/" + cid + "/profileRecord/" + r["id"], avg="档案")
            g = self.group("voices", "干员语音", "干员语音")
            for r in sorted(row.get("profileVoice", []), key=lambda x: x["voiceIndex"]):
                text = self.text(r.get("voiceDesc"))
                self.add(g, "voice_" + r["id"], name + " · " + self.text(r.get("voiceTitle")),
                         [Line("dialogue", text, name)] if text else [], source="TableCfg/CharacterTable.json/" + cid + "/profileVoice/" + r["id"], avg="语音")
        g = self.group("notes", "叙事注释", "文献档案")
        for key, row in sorted(self.table("NarrativeNoteEntryTable").items()):
            text = self.text(row.get("entryDesc"))
            self.add(g, key, self.text(row.get("entryName")), [Line("narration", text)] if text else [], source="TableCfg/NarrativeNoteEntryTable.json/" + key, avg="文献")
        items = self.table("ItemTable")
        g = self.group("weapons", "武器故事", "物品叙事")
        for key, row in sorted(self.table("WeaponBasicTable").items()):
            text = self.text(row.get("weaponDesc"))
            self.add(g, "weapon_" + key, self.text(items.get(key, {}).get("name")) or key,
                     [Line("narration", text)] if text else [], source="TableCfg/WeaponBasicTable.json/" + key, avg="物品")
        g = self.group("items", "物品与收集品题记", "物品叙事")
        for key, row in sorted(items.items()):
            # decoDesc 是与功能 desc 分开的风味栏：全部保留，不按长度猜叙事价值。
            text = self.text(row.get("decoDesc"))
            if text:
                self.add(g, "item_" + key, self.text(row.get("name")) or key, [Line("narration", text)],
                         source="TableCfg/ItemTable.json/" + key + "/decoDesc", avg="物品")
        self.audit["excluded"].append({"kind": "ItemTable.desc", "reason": "功能说明和叙事混合；本轮只接独立 decoDesc 和武器故事"})

    def lore_page(self, gid, name, records, page, source):
        """records 是（名称，正文几行）；按原顺序每 page 条一集，一条是「【名称】」一行加正文。"""
        g = self.group(gid, name, LORE)
        records = [(t, body) for t, body in records if body]
        for i in range(0, len(records), page):
            chunk = records[i:i + page]
            lines = []
            for title, body in chunk:
                if page > 1:
                    lines.append(Line("narration", f"【{title}】"))
                lines += [x if isinstance(x, Line) else Line("narration", x) for x in body]
            title = chunk[0][0] if len(chunk) == 1 else f"{chunk[0][0]} … {chunk[-1][0]}"
            self.add(g, f"{gid}_{i // page + 1:03d}", title, lines, source=source, avg="文本")

    def load_lore(self):
        """项目原先没读的图鉴和文案（2026-11-12 盘点）：敌人图鉴、未入终端的文献、调查物件、远程通讯、场景短对白、
        闲谈、邮件、干员兴趣专长、驿站委托、拍照挑战的故事、说明书、百科条目、地图标记、玩法说明、加载提示、活动简介。
        只归档成可读、可搜、可引的分集，不判断叙事价值；技能数值、教程、成就条件等纯玩法文本不收。
        除远程通讯外都作旁白，不记说话人（免得撑大出场集数）。"""
        t = self.text
        chars = {cid: t(r.get("name")) for cid, r in self.table("CharacterTable").items()}
        abilities = self.table("EnemyAbilityDescTable")
        rows = []
        for key, r in sorted(self.table("EnemyTemplateDisplayInfoTable").items(), key=lambda x: natural(x[0])):
            nick = t(r.get("nickname"))
            nick = nick if nick and nick != t(r.get("name")) else ""
            body = [s for s in (nick and "别称：" + nick, t(r.get("description"), breaks=True)) if s]
            body += ["能力：" + t(abilities[a].get("description")) for a in r.get("abilityDescIds", [])
                     if a in abilities and t(abilities[a].get("description"))]
            rows.append((t(r.get("name")) or key, body))
        self.lore_page("lore_enemies", "敌人图鉴", rows, 20, "TableCfg/EnemyTemplateDisplayInfoTable.json")

        rich = self.table("RichContentTable")
        rows = [(t(rich[cid].get("title")) or cid, [t(c["content"]) for c in rich[cid].get("contentList", []) if t(c["content"])])
                for cid in sorted(set(rich) - getattr(self, "rich_used", set()), key=natural)]
        self.lore_page("lore_documents", "未入终端的文献", rows, 1, "TableCfg/RichContentTable.json")

        self.lore_page("lore_inspect", "调查物件", [
            (t(r.get("dialog2dTitle")) or k, [t(r.get("dialog2dText"), breaks=True)])
            for k, r in sorted(self.table("Dialog2DTextTable").items(), key=lambda x: natural(x[0]))], 1,
            "TableCfg/Dialog2DTextTable.json")

        rows = []
        for k, r in sorted(self.table("RemoteCommonTable").items(), key=lambda x: natural(x[0])):
            body = []
            for part in sorted(r.get("remoteCommSingleDataList", []), key=lambda x: x.get("index", 0)):
                text, who = t(part.get("remoteCommText")), t(part.get("actorName")).strip("{}")
                if text:
                    body.append(Line("dialogue" if who else "narration", text, who or None))
            rows.append((k, body))
        self.lore_page("lore_remote", "远程通讯", rows, 1, "TableCfg/RemoteCommonTable.json")

        rows = []
        for k, r in sorted(self.table("EnvTalkTable").items(), key=lambda x: natural(x[0])):
            body = []
            for part in sorted(r.get("envTalkDataList", []), key=lambda x: x.get("index", 0)):
                text = t(part.get("text"))
                who = chars.get(part.get("actorId", ""), "")
                if text:
                    body.append(f"{who}：{text}" if who else text)
            rows.append((k, body))
        self.lore_page("lore_envtalk", "场景短对白", rows, 60, "TableCfg/EnvTalkTable.json")

        self.lore_page("lore_bark", "闲谈", [(k, [t(r.get("barkText"))]) for k, r in self.table("AIBarkText").items()],
                       100, "TableCfg/AIBarkText.json")
        self.lore_page("lore_mail", "邮件", [
            (t(r.get("title")) or k, [t(r.get("mailContent"), breaks=True)])
            for k, r in sorted(self.table("MailTemplateTable").items(), key=lambda x: natural(x[0])) if "test" not in k], 1,
            "TableCfg/MailTemplateTable.json")
        self.lore_page("lore_tags", "干员兴趣与专长", [
            (chars.get(k, k), [t(v.get("desc")) for v in r.get("tagDesc", {}).values() if t(v.get("desc"))])
            for k, r in sorted(self.table("CharacterTagDesTable").items(), key=lambda x: natural(x[0]))], 40,
            "TableCfg/CharacterTagDesTable.json")
        rows = []
        for k, r in sorted(self.table("KiteStationEntrustTasksTable").items()):
            for part in sorted(r.get("list", {}).values(), key=lambda x: x.get("entrustIdx", 0)):
                rows.append((t(part.get("name")) or k, [s for s in (t(part.get("desc")), t(part.get("completeDesc"))) if s]))
        self.lore_page("lore_kite", "驿站委托", rows, 40, "TableCfg/KiteStationEntrustTasksTable.json")
        self.lore_page("lore_snapshot", "拍照挑战的故事", [
            (k, [s for s in (t(r.get("normalStoryDesc"), breaks=True), t(r.get("completeStoryDesc"), breaks=True)) if s])
            for k, r in sorted(self.table("ActivitySnapshotChallengeTable").items(), key=lambda x: natural(x[0]))], 24,
            "TableCfg/ActivitySnapshotChallengeTable.json")
        self.lore_page("lore_instructions", "说明书", [
            (t(r.get("title")) or k, [t(r.get("content"), breaks=True)])
            for k, r in sorted(self.table("InstructionBook").items(), key=lambda x: natural(x[0]))], 20,
            "TableCfg/InstructionBook.json")
        self.lore_page("lore_wiki", "百科条目说明", [
            (k.removeprefix("wiki_"), [t(r.get("desc"), breaks=True)])
            for k, r in sorted(self.table("WikiEntryDataTable").items(), key=lambda x: natural(x[0]))], 60,
            "TableCfg/WikiEntryDataTable.json")
        self.lore_page("lore_mapmarks", "地图标记", [
            (t(r.get("name")) or k, [t(r.get("desc"))])
            for k, r in sorted(self.table("MapMarkTempTable").items(), key=lambda x: natural(x[0]))], 60,
            "TableCfg/MapMarkTempTable.json")
        self.lore_page("lore_mechanics", "玩法与挑战说明", [
            (t(r.get("gameName")) or k, [t(r.get("desc"), breaks=True)])
            for k, r in sorted(self.table("GameMechanicTable").items(), key=lambda x: natural(x[0]))], 80,
            "TableCfg/GameMechanicTable.json")
        self.lore_page("lore_tips", "加载提示", [
            (t(r.get("tipsTitle")) or k, [t(r.get("text"))])
            for k, r in sorted(self.table("LoadingTipsTable").items(), key=lambda x: natural(x[0]))], 60,
            "TableCfg/LoadingTipsTable.json")
        self.lore_page("lore_activities", "活动简介", [
            (t(r.get("name")) or k, [s for s in (t(r.get("desc"), breaks=True), t(r.get("tips"), breaks=True)) if s])
            for k, r in sorted(self.table("ActivityTable").items(), key=lambda x: natural(x[0]))], 30,
            "TableCfg/ActivityTable.json")

    def load_subtitles(self):
        """字幕和未定位的黑屏文本独立成集，不拼到任务中猜测播放位置。"""
        scenes = defaultdict(list)
        for key in sorted(self.texts, key=natural):
            if key.startswith(("cs_video_", "cutscene_")):
                scene = re.sub(r"_\d+$", "", key)
                scenes[scene].append((key, self.text(self.texts[key])))
        g = self.group("subtitles", "过场字幕", "过场字幕")
        for scene, rows in scenes.items():
            lines = [Line("narration", t) for _, t in rows if t]
            self.add(g, "subtitle_" + scene, scene, lines,
                     source="TableCfg/TextTable.json/" + scene,
                     note="字幕按原始文本键的自然序；字幕轨的时间及说话人未完全定位，不等同于已验证播放顺序。", avg="字幕")
        g = self.group("intertitles", "黑屏叙事文本", "过场字幕")
        for key in sorted(self.texts, key=natural):
            if key.startswith("black_") and key not in self.used_black:
                text = self.text(self.texts[key])
                self.add(g, key, key, [Line("narration", text)] if text else [],
                         source="TableCfg/TextTable.json/" + key,
                         note="未定位到可解析的对话树节点；单列文本，不推断任务中的播放位置。", avg="字幕")

    def load(self):
        self.setup_groups()
        print("终末地：读取对话树与时间轴……", flush=True)
        self.load_dialogs()
        print("终末地：读取无线电、讯息与叙事文本……", flush=True)
        self.load_radio()
        self.load_sns()
        self.load_narrative()
        self.load_subtitles()
        self.load_lore()
        # 未被对话树使用的台词不硬塞到看似连续的任务正文。
        self.audit["excluded"].extend([
            {"kind": "未达或未解析对话", "ids": sorted(set(self.dialogs) - self.used_dialogs)},
            {"kind": "未达或未解析选项", "ids": sorted(set(self.options) - self.used_options)},
        ])
        self.audit["missing"] = sorted(set(self.audit["missing"]))
        self.audit["mission_structure"] = {}
        for mid, mission in self.missions.items():
            # 保存实际任务依赖，供查环节；编号与插入顺序并不等于任务执行顺序。
            self.audit["mission_structure"][mid] = {
                "source": f"Json/MissionRuntimeAsset/{mid}.json",
                "mainPathQuests": mission.get("mainPathQuests", []),
                "quests": {qid: {"prev": q.get("prevQuestIdList", []), "flowIndex": q.get("flowIndex", 0)}
                           for qid, q in mission.get("questDic", {}).items()},
            }
        for group in self.groups.values():
            def order(ep):
                key = ep.story_id.removeprefix("ef_")
                rest = re.sub(r"^(?:dlg|radio|sns)_", "", key)
                mid = next((m for m in sorted(self.mission_groups, key=len, reverse=True)
                            if rest == m or rest.startswith(m + "_")), "")
                return self.mission_rank.get(mid, 9999), natural(mid), natural(key)
            group.episodes.sort(key=order)
            numbers = Counter()
            for index, ep in enumerate(group.episodes):
                ep.sort = index
                if ep.avg in ("剧情", "无线电", "讯息"):
                    _, mid = self.group_for(ep.story_id.removeprefix("ef_"))
                    title = self.text(self.missions.get(mid, {}).get("missionName")) or group.name.removeprefix(PREFIX)
                    kind = "对话" if ep.avg == "剧情" else ep.avg
                    numbers[mid] += 1
                    ep.title = f"{title} · {kind} {numbers[mid]}"
                elif ep.avg == "字幕":
                    ep.title = f"{group.name.removeprefix(PREFIX)} · 字幕 {index + 1}"
        # 只将无歧义的姓名式别称用于独立出现的旧称；不归并两个资源中的异写。
        aliases = defaultdict(set)
        for group in self.groups.values():
            for ep in group.episodes:
                for line in ep.script.lines:
                    name, alias, _ = speaker_name(line.speaker or "")
                    if alias:
                        aliases[alias].add(name)
        for group in self.groups.values():
            for ep in group.episodes:
                ep.speaker_aliases = {a: next(iter(ns)) for a, ns in aliases.items() if len(ns) == 1}
        return {k: g for k, g in self.groups.items() if g.episodes}


def analyze_episode(ep, reg):
    ep.speaker_audit = Counter()
    aliases = getattr(ep, "speaker_aliases", {})
    normalized = []
    for line in ep.script.lines:
        raw = line.speaker or ""
        name, alias, rule = speaker_name(raw)
        name = aliases.get(name, name)
        if "{" in raw.strip("{}"):
            ep.speaker_audit[raw.strip("{}"), name, rule] += 1
        normalized.append(replace(line, speaker=name or line.speaker))
    # Timeline 缓存的 Line 可被多集共享：复制，避免改写其他分集的源名和审计计数。
    ep.script = replace(ep.script, lines=normalized)
    d = EpisodeData(ep, ep.synopsis, ep.script)
    for line in ep.script.lines:
        raw = "管理员" if line.kind == "decision" else line.speaker if line.kind == "dialogue" else None
        if not raw or re.fullmatch(r"[？?…·.\s]+", raw):
            continue
        name = PREFIX + book_aliases().get(raw, raw)  # 别名表里的人：台词算到正名，剧本照旧显示原称
        if name not in reg.chars:
            reg.chars[name] = Character(name, "npc")
            reg.chars[name].game = "endfield"
        if name != PREFIX + raw and PREFIX + raw not in reg.chars[name].aliases:
            reg.chars[name].aliases.append(PREFIX + raw)
        for alias, target in aliases.items():
            if target == raw and PREFIX + alias not in reg.chars[name].aliases:
                reg.chars[name].aliases.append(PREFIX + alias)
        # 单独 analyze_episode 的测试/调用也保留当前行的别名。
        for original in ep.speaker_audit:
            target, alias, _ = speaker_name(original[0])
            if alias and target == raw and PREFIX + alias not in reg.chars[name].aliases:
                reg.chars[name].aliases.append(PREFIX + alias)
        d.lines[name] += 1
    d.present.update(d.lines)
    return d


def register_operators(reg, operators):
    """可操作干员先登记成「终末地·名」的干员页（带档案），剧本里同名的说话人之后并入这一页。"""
    for name, op in operators.items():
        key = PREFIX + name
        ch = reg.chars.get(key) or Character(key, "operator")
        ch.kind, ch.game = "operator", "endfield"
        ch.rarity, ch.profession, ch.appellation = op["rarity"], op["profession"], op["appellation"]
        ch.char_ids = list(op["ids"])  # 立绘和头像按 id 取（pipeline.images）
        ch.profile = op.get("profile")
        reg.chars[key] = ch


TALOS_BOWU = config.ROOT / "data" / "annals" / "博物志"
TALOS_PEOPLE = config.ROOT / "data" / "annals" / "人物志" / "塔卫二.md"
POWER_MEN = {"地理": "region", "势力": "faction"}
# 塔卫二编博物志不另立、沿用泰拉编条目的地区势力（见 塔卫二-地理势力.md 开头的说明）
SHARED_POWERS = {"罗德岛": "rhodes"}
# 人物志里打头的名字修饰的不是这个人，不算入籍：人物 → 名字
NOT_MEMBER = {
    "终末地·德鲁安": "塞什卡",  # 「塞什卡血液样本的物流负责人」：塞什卡说的是血液样本，书里没写他是谁的人
}


def talos_power_entries():
    """塔卫二编博物志地理、势力两门的条目：条目名 → (region|faction, 上级条目名, [别名])。"""
    out = {}
    for path in sorted(TALOS_BOWU.glob("塔卫二-*.md")):
        for m in re.finditer(r"^@物 (\S+)(.*)$", path.read_text(encoding="utf-8"), re.M):
            tags = dict(t.split(":", 1) for t in m[2].split() if ":" in t)
            if tags.get("门") in POWER_MEN:
                out[m[1]] = (POWER_MEN[tags["门"]], tags.get("上"), [a for a in tags.get("别", "").split(",") if a])
    return out


def identity_names(text, names):
    """人物志一行的第一句身份（「本名…」一句跳过）里写到的地区势力名；重叠的取最长的。
    名字要么打头（「联盟工团施工队长」），要么紧跟「的」（「北部禁区的大厨」），
    「来自甚大裂隙彼岸」「藏身裂地者旧基地的难民」这类只是提到，不算。"""
    clauses = [c for c in re.split(r"[，；。]", re.sub(r"\[\[([^\]|]+)(\|[^\]]*)?\]\]", r"\1", text)) if c]
    first = next((c for c in clauses if not c.startswith("本名")), "")
    hits = sorted(((m.start(), -len(n), n) for n in names for m in re.finditer(re.escape(n), first)))
    out, end = [], 0
    for start, neg, n in hits:
        if start >= end:
            end = start - neg
            if start == 0 or first[end:end + 1] == "的":
                out.append(n)
    return out


def register_powers(reg):
    """塔卫二编的地区势力：取自塔卫二编博物志的地理、势力两门，id 作「ef_条目名」，上级照条目的「上:」。
    干员按档案「身份认证」入籍（档案没写的看人物志），其他人物按人物志第一句身份里写到的名字；
    只登记有人入籍的和它们的上级。名字只在塔卫二编里认：match 留空，泰拉剧本里的同名不算提及。"""
    entries = talos_power_entries()
    by_name = {}
    for name, (_, _, aliases) in entries.items():
        for n in (name, *aliases):
            by_name.setdefault(n, name)

    def pid_of(name):
        if name in SHARED_POWERS:
            return SHARED_POWERS[name] if SHARED_POWERS[name] in reg.powers else None
        entry = by_name.get(name)
        if not entry:
            return None
        node = entry
        while node and "ef_" + node not in reg.powers:
            kind, up, _ = entries[node]
            p = Power("ef_" + node, node, kind, parent="ef_" + up if up in entries else None)
            p.game = "endfield"
            reg.powers[p.id] = p
            node = up if up in entries else None
        return "ef_" + entry

    people = {}
    if TALOS_PEOPLE.exists():
        for line in re.sub(r"<!--.*?-->", "", TALOS_PEOPLE.read_text(encoding="utf-8"), flags=re.S).splitlines():
            key, sep, desc = line.partition("：")
            if sep and key.startswith(PREFIX):
                people[key] = desc
    names = [n for n in [*by_name, *SHARED_POWERS] if len(n) >= 2]
    for key, ch in reg.chars.items():
        if getattr(ch, "game", "") != "endfield":
            continue
        ident = ((getattr(ch, "profile", None) or {}).get("basic") or {}).get("身份认证", "")
        found = [n for n in re.split(r"[／/、]", ident) if n in by_name or n in SHARED_POWERS]
        pids = [p for n in (found or identity_names(people.get(key, ""), names))
                if n != NOT_MEMBER.get(key) and (p := pid_of(n))]
        ancestors = {a for p in pids for a in reg.ancestors(p)}  # 「裂地者碾骨氏族」只记碾骨氏族
        ch.powers += [p for p in dict.fromkeys(pids) if p not in ancestors and p not in ch.powers]


def load():
    """返回（剧情组，审计，可操作干员）。"""
    if not (config.ENDFIELD / "TableCfg/I18nTextTable_CN.json").exists():
        print("终末地：未发现本机客户端数据，跳过。")
        return {}, {}, {}
    loader = Loader(config.ENDFIELD)
    groups = loader.load()
    return groups, loader.audit, loader.operators


def raw_texts():
    """rawfind 的原始 CN 文本；含未接入类别，保留哈希键便于回查。"""
    p = config.ENDFIELD / "TableCfg/I18nTextTable_CN.json"
    if p.exists():
        for key, value in json.loads(p.read_text(encoding="utf-8")).items():
            yield f"endfield/TableCfg/I18nTextTable_CN/{key}", 0, value
