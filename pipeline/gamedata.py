"""读取 ArknightsGameData 里的数据表和剧本文件。"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import cache

from . import config

CN_TZ = timezone(timedelta(hours=8))

# story_review_table 的 entryType → vault 里的分类
CATEGORIES = {"MAINLINE": "主线", "ACTIVITY": "活动", "MINI_ACTIVITY": "故事集"}


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
    category: str  # 主线 / 活动 / 故事集
    start: datetime | None
    episodes: list[Episode] = field(default_factory=list)

    @property
    def chapter(self) -> int | None:
        if self.category == "主线" and self.id.startswith("main_"):
            return int(self.id.split("_")[1])
        return None

    @property
    def label(self) -> str:
        """主线显示「序章 / 第N章」，活动显示开放月份。"""
        if self.chapter is not None:
            return "序章" if self.chapter == 0 else f"第{self.chapter}章"
        return self.start.strftime("%Y-%m") if self.start else ""


@cache
def excel(name: str) -> dict:
    with open(config.EXCEL / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def _ts(v) -> datetime | None:
    return datetime.fromtimestamp(v, CN_TZ) if isinstance(v, int) and v > 0 else None


def load_groups() -> dict[str, Group]:
    groups = {}
    for gid, g in excel("story_review_table").items():
        category = CATEGORIES.get(g.get("entryType"))
        if not category:
            continue  # NONE 类（干员密录等）暂不在范围内
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


def sort_key(g: Group):
    """主线按章节号，活动和故事集按开放时间。"""
    order = list(CATEGORIES.values()).index(g.category)
    return (order, g.chapter if g.chapter is not None else 0, g.start or datetime.max.replace(tzinfo=CN_TZ), g.id)


def read_story(rel: str) -> str:
    return (config.STORY / f"{rel}.txt").read_text(encoding="utf-8-sig")


def read_info(rel: str | None) -> str | None:
    """官方简介：storyInfo 写作 info/xxx，实际文件在 story/[uc]info/xxx.txt。"""
    if not rel:
        return None
    p = config.STORY / "[uc]info" / f"{rel.removeprefix('info/')}.txt"
    return p.read_text(encoding="utf-8-sig").strip() if p.exists() else None
