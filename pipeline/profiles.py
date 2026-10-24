"""人物资料：干员档案来自 handbook_info_table，剧情 NPC 的简介来自敌人图鉴（作为敌人出场过的才有）。
PRTS 干员页上的档案也是这两张表的内容，直接读本地数据即可。
"""
import re
from functools import cache

from . import gamedata
from .entities import Character

TAG_RE = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return TAG_RE.sub("", s).replace("\r", "").strip()


def operator_profile(ch: Character) -> dict | None:
    """{"basic": {"性别": "女", ...}, "sections": [{"title": "客观履历", "text": ...}, ...]}"""
    handbook = gamedata.excel("handbook_info_table")["handbookDict"]
    h = next((handbook[cid] for cid in ch.char_ids if cid in handbook), None)
    if not h:
        return None
    basic, sections = {}, []
    for s in h.get("storyTextAudio") or []:
        text = _clean("\n".join(x.get("storyText", "") for x in s.get("stories") or []))
        if not text:
            continue
        if s.get("storyTitle") == "基础档案":
            parts = re.split(r"【([^】]+)】", text)
            basic = {k.strip(): v.strip() for k, v in zip(parts[1::2], parts[2::2])}
        else:
            sections.append({"title": s.get("storyTitle", ""), "text": text})
    return {"basic": basic, "sections": sections}


@cache
def _enemy_descriptions() -> dict[str, str]:
    out = {}
    for e in gamedata.excel("enemy_handbook_table")["enemyData"].values():
        name = (e.get("name") or "").strip("“”\" ")
        desc = _clean(e.get("description") or "")
        if name and desc and name not in out:
            out[name] = desc
    return out


def npc_description(name: str) -> str | None:
    return _enemy_descriptions().get(name)
