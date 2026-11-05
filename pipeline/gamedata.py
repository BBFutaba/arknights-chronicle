"""读取 ArknightsGameData 里的数据表和剧本文件。

剧情组有三个来源：
    story_review_table        主线、活动、故事集（剧情回顾里能看到的部分）
    handbook_info_table       干员密录：每位干员的密录归一个组，组 id 用干员 id（char_xxx）
    load_extra_groups         剧情回顾之外的文本：集成战略、生息演算、记录点、活动里的任务和手册
    story_review_meta_table   活动档案里的隐藏剧情（如《长夜临光》的「逃离」），并入所属活动组
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import cache

from . import config

CN_TZ = timezone(timedelta(hours=8))

# story_review_table 的 entryType → vault 里的分类；NONE 类就是干员密录，改从 handbook_info_table 读
CATEGORIES = {"MAINLINE": "主线", "ACTIVITY": "活动", "MINI_ACTIVITY": "故事集"}
MEMORY = "干员密录"
ROGUE, SANDBOX, OTHER = "集成战略", "生息演算", "其他文本"
EXTRA_CATEGORIES = (ROGUE, SANDBOX, OTHER)
CATEGORY_ORDER = [*CATEGORIES.values(), MEMORY, *EXTRA_CATEGORIES]


@dataclass
class Episode:
    story_id: str
    group_id: str
    code: str
    title: str
    avg: str  # 行动前 / 行动后 / 幕间 等
    sort: int
    txt: str  # 相对 story/ 的路径，不含 .txt
    info: str | None  # 官方简介文件路径


@dataclass
class Group:
    id: str
    name: str
    category: str  # 主线 / 活动 / 故事集 / 干员密录
    start: datetime | None
    episodes: list[Episode] = field(default_factory=list)

    @property
    def chapter(self) -> int | None:
        if self.category == "主线" and self.id.startswith("main_"):
            return int(self.id.split("_")[1])
        return None

    @property
    def label(self) -> str:
        """主线显示「序章 / 第N章」，其他显示开放月份（干员密录是这位干员第一篇密录的上线月份）。"""
        if self.chapter is not None:
            return "序章" if self.chapter == 0 else f"第{self.chapter}章"
        return self.start.strftime("%Y-%m") if self.start else ""


@cache
def excel(name: str) -> dict:
    with open(config.EXCEL / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def _ts(v) -> datetime | None:
    return datetime.fromtimestamp(v, CN_TZ) if isinstance(v, int) and v > 0 else None


def story_exists(rel: str) -> bool:
    return (config.STORY / f"{rel}.txt").exists()


def load_groups() -> dict[str, Group]:
    groups = load_review_groups()
    add_hidden_stories(groups)
    groups.update(load_memory_groups())
    groups.update(load_extra_groups(groups))
    return groups


def load_review_groups() -> dict[str, Group]:
    groups = {}
    for gid, g in excel("story_review_table").items():
        category = CATEGORIES.get(g.get("entryType"))
        if not category:
            continue  # NONE 类是干员密录，由 load_memory_groups 按干员归组
        grp = Group(gid, g["name"], category, _ts(g.get("startTime")) or _ts(g.get("startShowTime")))
        for s in g.get("infoUnlockDatas") or []:
            if not s.get("storyTxt"):
                continue
            grp.episodes.append(Episode(
                story_id=s["storyId"], group_id=gid,
                code=s.get("storyCode") or "", title=s.get("storyName") or "",
                avg=s.get("avgTag") or "", sort=s.get("storySort") or 0,
                txt=s["storyTxt"], info=s.get("storyInfo"),
            ))
        grp.episodes.sort(key=lambda e: e.sort)
        groups[gid] = grp
    return groups


def _code_prefix(grp: Group) -> str:
    """活动关卡代号的公共前缀，如长夜临光的 NL-1、NL-ST-1 → NL。"""
    heads = {e.code.split("-")[0] for e in grp.episodes if "-" in e.code}
    return heads.pop() if len(heads) == 1 else ""


def add_hidden_stories(groups: dict[str, Group]):
    """活动档案（story_review_meta_table 的 actArchive）里的剧情，不在剧情回顾的分集表里。

    目前只有《长夜临光》的三篇隐藏剧情。游戏里没有关卡代号，按 PRTS 的写法编作 NL-HD-1 等，
    这样年表出处里的 [[NL-HD-1/NBT]] 能对上。分集 id 沿用「组 id_剧本文件名」的格式，
    排在原有分集之后，不影响原有分集。
    """
    meta = excel("story_review_meta_table")
    res = meta["actArchiveResData"]["avgs"]
    used = {e.txt.lower() for g in groups.values() for e in g.episodes}
    for cid, comp in meta["actArchiveData"]["components"].items():
        grp = groups.get(cid)  # 复刻（act13sre 等）和肉鸽、生息演算的档案没有对应的剧情组
        if grp is None:
            continue
        avgs = sorted(((comp.get("avg") or {}).get("avgs") or {}).values(), key=lambda a: a["avgSortId"])
        prefix = _code_prefix(grp)
        base = max((e.sort for e in grp.episodes), default=0)
        for a in avgs:
            r = res.get(a["avgId"])
            if not r or not r.get("contentPath") or r["contentPath"].lower() in used:
                continue
            txt = r["contentPath"]
            if not story_exists(txt):
                continue
            used.add(txt.lower())
            n = a["avgSortId"]
            grp.episodes.append(Episode(
                story_id=f"{cid}_{txt.rsplit('/', 1)[-1]}", group_id=cid,
                code=f"{prefix}-HD-{n}" if prefix else f"HD-{n}", title=r.get("desc") or "",
                avg="幕间", sort=base + n, txt=txt, info=r.get("breifPath"),
            ))


def load_memory_groups() -> dict[str, Group]:
    """干员密录：handbook_info_table 里每位干员的 handbookAvgList，一位干员一个组。

    组 id 用干员 id（char_xxx），组名是干员名；分集 id 沿用游戏的 storyId
    （story_<干员>_set_<n>_story_<m>），标题写作「干员名 · 密录标题」，一套密录分几篇时加「（m）」。
    分集的 sort 是「套序号 × 100 + 篇序号」，memory_set 靠它找 PRTS 链接指的那一套。
    """
    chars = excel("character_table")
    tags = {s["storyId"]: s.get("avgTag") for g in excel("story_review_table").values()
            if g.get("entryType") == "NONE" for s in g.get("infoUnlockDatas") or []}
    groups = {}
    for cid, hb in excel("handbook_info_table")["handbookDict"].items():
        sets = sorted(hb.get("handbookAvgList") or [], key=lambda s: s["sortId"])
        if not sets:
            continue
        name = chars.get(cid, {}).get("name") or cid
        times = [t for s in sets if (t := _ts(s.get("storyGetTime")))]
        grp = Group(cid, name, MEMORY, min(times) if times else None)
        for s in sets:
            stories = sorted(s["avgList"], key=lambda a: a["storySort"])
            for i, a in enumerate(stories, 1):
                if not story_exists(a["storyTxt"]):
                    continue
                title = f"{name} · {s['storySetName']}" + (f"（{i}）" if len(stories) > 1 else "")
                grp.episodes.append(Episode(
                    story_id=a["storyId"], group_id=cid, code="", title=title,
                    avg=tags.get(a["storyId"]) or "幕间", sort=s["sortId"] * 100 + i,
                    txt=a["storyTxt"], info=a.get("storyInfo"),
                ))
        if grp.episodes:
            groups[cid] = grp
    return groups


def _walk(v):
    if isinstance(v, dict):
        yield v
        for x in v.values():
            yield from _walk(x)
    elif isinstance(v, list):
        for x in v:
            yield from _walk(x)


def _extra_titles() -> dict[str, str]:
    """数据表里给这些文本起的名字：相对 story/ 的小写路径 → 标题。"""
    titles = {}
    for d in _walk(excel("roguelike_topic_table")):
        if "clientEndbookItemDatas" in d:
            head = d.get("title") or ""
            if d.get("avgId"):
                titles[d["avgId"].lower()] = f"结局 · {head}"
            for it in d["clientEndbookItemDatas"] or []:
                if it.get("textId"):
                    titles[it["textId"].lower()] = f"{head} · {it.get('endbookName') or ''}"
        elif d.get("chatStoryId"):
            titles[d["chatStoryId"].lower()] = d.get("chatDesc") or ""
    for d in _walk(excel("sandbox_perm_table")):
        if d.get("avgId") and d.get("avgName"):
            titles[d["avgId"].lower()] = d["avgName"]
    for d in _walk(excel("story_review_meta_table")):
        if d.get("textId") and d.get("titleName"):
            titles[d["textId"].lower()] = d["titleName"]
    for d in _walk(excel("activity_table")):
        if d.get("investNpcName") and d.get("storyId"):
            titles[d["storyId"].lower()] = f"访谈 · {d['investNpcName']}"
    for d in _walk(excel("zone_table")):
        if d.get("textPath") and d.get("bindStageId"):
            titles[d["textPath"].lower()] = f"记录点 · {d['bindStageId'].removeprefix('main_')}"
    return titles


_EXTRA_SKIP = re.compile(r"/(training|guide|tutorial|uiavg|traininglevel|level)/|tutorial_|/guide_|/training_|_entry_tr")


def _extra_group_of(rel: str) -> tuple[str, str, str] | None:
    """按路径归组：(组 id, 组名, 分类)；不是剧情的返回 None。"""
    low = rel.lower()
    if _EXTRA_SKIP.search(low):
        return None
    if m := re.match(r"obt/rogue/(?:rogue_(\d)/|month_chat_rogue_(\d)_)", low):
        n = m[1] or m[2]
    elif m := re.match(r"obt/roguelike/ro(\d)/level_rogue", low):
        n = m[1]
    else:
        n = None
    if n:
        gid = f"rogue_{n}"
        return gid, f"集成战略 · {excel('roguelike_topic_table')['topics'][gid]['name']}", ROGUE
    if low.startswith("activities/act1sandbox/"):
        return "sandbox_0", "生息演算 · 沙中之火", SANDBOX
    if m := re.match(r"obt/sandboxperm/sandbox_(\d)/", low):
        return f"sandbox_{m[1]}", {"1": "生息演算 · 沙洲遗闻", "2": "生息演算 · 重启锚点"}.get(m[1], m[1]), SANDBOX
    if m := re.match(r"obt/record/main_(\d+)/", low):
        return f"record_main_{m[1]}", f"第 {m[1]} 章记录点", OTHER
    if low.startswith("activities/act21side/task/"):
        return "act21side_task", "叙拉古人 · 任务文本", OTHER
    if re.match(r"activities/act29side/(chat_|mark/)", low):
        return "act29side_extra", "崔林特尔梅之金 · 访谈与手册", OTHER
    if low.startswith("activities/act42side/mark/"):
        return "act42side_mark", f"{excel('story_review_table')['act42side']['name']} · 物证", OTHER
    if m := re.match(r"activities/(act4fun|act3fun|act5fun|act7fun|act1lock|act5d1|act12d6|act17d7)/", low):
        name = excel("activity_table")["basicInfo"].get(m[1], {}).get("name") or m[1]
        return m[1], f"{name} · {m[1]}" if "fun" in m[1] or "d7" in m[1] else name, OTHER
    return None


@cache
def _avatar_names() -> dict[str, str]:
    """对白 head 里的头像 id → 人名：《叙拉古人》的角色卡，加上该活动剧本里头像后面紧跟的说话人。"""
    names = {}
    for d in _walk(excel("activity_table")):
        if d.get("avgChar") and d.get("charCardName"):
            names[re.sub(r"^avg_|#.*$", "", d["avgChar"])] = d["charCardName"]
    votes: dict[str, dict[str, int]] = {}
    for f in (config.STORY / "activities" / "act21side").glob("level_*.txt"):
        last = None
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            if m := re.match(r'\[Character\(name="avg_(npc_[^"#$]+)', line, re.I):
                last = m[1]
            elif m := re.match(r'\[name="([^"]+)"\]', line):
                if last and "？" not in m[1]:
                    v = votes.setdefault(last, {})
                    v[m[1]] = v.get(m[1], 0) + 1
                last = None
    for k, v in votes.items():  # 同一头像常被多人共用，只取几乎只有一个人用的
        top = max(v, key=v.get)
        if v[top] >= 50 and v[top] >= 0.8 * sum(v.values()):
            names.setdefault(k, top)
    return names


def head_name(head: str) -> str | None:
    """dialog 指令的 head（char_xxx、npc_4065_judge_1、npc_694_1）→ 说话人名，认不出返回 None。"""
    chars = excel("character_table")
    if head in chars:
        return chars[head]["name"]
    names = _avatar_names()
    if got := names.get(head) or names.get(head.removeprefix("npc_")):
        return got
    if m := re.fullmatch(r"npc_(\d+_[a-z0-9]+)_\d+", head):
        if (cid := f"char_{m[1]}") in chars:
            return chars[cid]["name"]
    return None


def _natural(rel: str) -> list:
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", rel.lower())]


def load_extra_groups(existing: dict[str, Group]) -> dict[str, Group]:
    """剧情回顾之外、数据里有的文本。排序按路径；分集 id 是「组 id_文件名」，不影响原有分集。"""
    used = {e.txt.lower() for g in existing.values() for e in g.episodes}
    titles = _extra_titles()
    groups: dict[str, Group] = {}
    rels = [f.relative_to(config.STORY).with_suffix("").as_posix() for f in config.STORY.rglob("*.txt")]
    for rel in sorted(rels, key=_natural):
        if rel.lower() in used or not (got := _extra_group_of(rel)):
            continue
        text = read_story(rel)
        if not re.search(r"[一-鿿]", re.sub(r"\[[^\]]*\]", "", text)):
            continue
        gid, name, category = got
        grp = groups.setdefault(gid, Group(gid, name, category, None))
        stem = rel.rsplit("/", 1)[-1]
        sid = f"{gid}_{stem}"
        if any(e.story_id == sid for e in grp.episodes):
            sid = f"{gid}_{rel.replace('/', '_')}"
        grp.episodes.append(Episode(sid, gid, "", titles.get(rel.lower()) or stem, "文本", len(grp.episodes) + 1, rel, None))
    return groups


MEMORY_LINK_RE = re.compile(r"^(.+?)/干员密录/(\d+)(?:-(\d+))?$")


def memory_set(grp: Group, n: int, part: int | None = None) -> list[Episode]:
    """第 n 套密录的分集（PRTS 链接写作 [[干员/干员密录/n]]，分篇的写作 [[干员/干员密录/n-m]]）。"""
    eps = [e for e in grp.episodes if e.sort // 100 == n]
    if part is not None:
        eps = [e for e in eps if e.sort % 100 == part]
    return eps


def sort_key(g: Group):
    """主线按章节号，活动、故事集和干员密录按开放时间。"""
    order = CATEGORY_ORDER.index(g.category)
    return (order, g.chapter if g.chapter is not None else 0, g.start or datetime.max.replace(tzinfo=CN_TZ), g.id)


def read_story(rel: str) -> str:
    return (config.STORY / f"{rel}.txt").read_text(encoding="utf-8-sig")


def read_info(rel: str | None) -> str | None:
    """官方简介：storyInfo 写作 info/xxx，实际文件在 story/[uc]info/xxx.txt。"""
    if not rel:
        return None
    p = config.STORY / "[uc]info" / f"{rel.removeprefix('info/')}.txt"
    return p.read_text(encoding="utf-8-sig").strip() if p.exists() else None
