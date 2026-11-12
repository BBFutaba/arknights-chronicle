"""明日方舟（泰拉编）里项目原先没读的设定文本，归档成可读、可搜、可引的分集。

2026-11-12 盘点后接入（盘点由 Codex 只读完成，表和字段见下面的 SOURCES）：模组故事、敌人图鉴、物品、蚀刻章、
时装、家具、活动档案、来信、多索雷斯标志物、招聘词条、干员语音、集成战略和生息演算的事件与藏品。

- 每张表一组，组 id 以 lore_ 开头，类别「设定文本」。只归档，不判断叙事价值，也不进编年史的故事线。
- 条目多的表按原表顺序每 page 条合成一集，一条是「【名称】」一行加正文几行；模组故事、语音按条或按人成集。
- 正文一律作旁白、不记说话人：语音、模组若记成干员说话，会把干员的出场集数撑大（关系图和人物页按出场集数算）。
- 文本里的富文本标记（<@ba.kw>…</>）去掉，换行拆成几行。
"""
from __future__ import annotations

import re
from collections import Counter

from . import gamedata
from .analyze import EpisodeData
from .endfield import Episode, Group
from .script import Line, Script

CATEGORY = "设定文本"
TAG = re.compile(r"<[@$][^>]*>|</>|<color=[^>]*>|</color>|<i>|</i>|<b>|</b>")


def clean(text) -> list[str]:
    if not isinstance(text, str):
        return []
    text = TAG.sub("", text).replace("\\n", "\n")
    return [s.strip() for s in text.split("\n") if s.strip()]


def char_names() -> dict[str, str]:
    return {cid: c.get("name", cid) for cid, c in gamedata.excel("character_table").items()}


class Builder:
    def __init__(self):
        self.groups: dict[str, Group] = {}

    def group(self, gid: str, name: str) -> Group:
        gid = "lore_" + gid
        if gid not in self.groups:
            self.groups[gid] = Group(gid, name, CATEGORY, None, game="terra", description="", display_label="")
        return self.groups[gid]

    def episode(self, g: Group, key: str, title: str, lines: list[Line], source: str):
        if not lines:
            return
        g.episodes.append(Episode(f"{g.id}_{key}", g.id, "", title, "文本", len(g.episodes), "", None,
                                  Script(lines), "", source, ""))

    def paged(self, gid: str, name: str, records: list[tuple[str, list[str]]], page: int, source: str):
        """records 是（名称，正文几行）；按原顺序每 page 条一集，标题写首末两条的名称。"""
        g = self.group(gid, name)
        records = [(t, body) for t, body in records if body]
        for i in range(0, len(records), page):
            chunk = records[i:i + page]
            lines = []
            for title, body in chunk:
                lines.append(Line("narration", f"【{title}】"))
                lines += [Line("narration", s) for s in body]
            first, last = chunk[0][0], chunk[-1][0]
            self.episode(g, f"{i // page + 1:03d}", f"{first} … {last}" if len(chunk) > 1 else first, lines, source)


def texts(record: dict, keys: tuple[str, ...]) -> list[str]:
    out = []
    for k in keys:
        out += clean(record.get(k))
    return out


def load() -> dict[str, Group]:
    b = Builder()
    names = char_names()
    x = gamedata.excel

    # 模组故事：只收进阶模组（初始证章是千篇一律的说明），一条一集
    g = b.group("modules", "模组故事")
    for key, r in sorted(x("uniequip_table")["equipDict"].items(), key=lambda kv: (kv[1].get("charId", ""), kv[0])):
        if r.get("type") == "ADVANCED":
            b.episode(g, key, f"{names.get(r.get('charId'), r.get('charId'))} · {r.get('uniEquipName')}",
                      [Line("narration", s) for s in clean(r.get("uniEquipDesc"))], f"excel/uniequip_table.json/equipDict/{key}")

    # 敌人图鉴：全部敌人（含首领），描述和能力说明
    rows = sorted(x("enemy_handbook_table")["enemyData"].values(), key=lambda r: (r.get("sortId", 0), r["enemyId"]))
    b.paged("enemies", "敌人图鉴", [
        (f"{r.get('name')}（{r.get('enemyIndex') or r['enemyId']}）",
         clean(r.get("description")) + [s for a in (r.get("abilityList") or []) for s in clean(a.get("text"))])
        for r in rows], 40, "excel/enemy_handbook_table.json/enemyData")

    rows = sorted(x("item_table")["items"].values(), key=lambda r: (r.get("sortId", 0), r["itemId"]))
    b.paged("items", "物品说明", [(r.get("name") or r["itemId"], texts(r, ("usage", "description"))) for r in rows],
            60, "excel/item_table.json/items")

    b.paged("medals", "蚀刻章", [(r.get("medalName") or r["medalId"], texts(r, ("description", "getMethod")))
                               for r in x("medal_table")["medalList"]], 60, "excel/medal_table.json/medalList")

    rows = []
    for key, r in x("skin_table")["charSkins"].items():
        d = r.get("displaySkin") or {}
        body = texts(d, ("content", "dialog", "usage", "description"))
        if body:
            rows.append((f"{names.get(r.get('charId'), r.get('charId'))} · {d.get('skinName') or d.get('skinGroupName') or key}", body))
    b.paged("skins", "时装", rows, 30, "excel/skin_table.json/charSkins")

    rows = sorted(x("building_data")["customData"]["furnitures"].values(), key=lambda r: (r.get("sortId", 0), r["id"]))
    b.paged("furniture", "家具", [(r.get("name") or r["id"], texts(r, ("usage", "description"))) for r in rows],
            60, "excel/building_data.json/customData/furnitures")

    # 活动档案：图片、新闻、日志、地标等各类，跳过剧情目录（avgs）
    rows = []
    for kind, items in x("story_review_meta_table")["actArchiveResData"].items():
        if kind == "avgs" or not isinstance(items, dict):
            continue
        for key, r in items.items():
            if not isinstance(r, dict):
                continue
            body = [s for k, v in r.items() if k not in ("id", "desc", "assetPath", "type", "subType", "titleName")
                    for s in clean(v)]
            rows.append((f"{r.get('desc') or r.get('titleName') or key}（{key}）", body))
    b.paged("archives", "活动档案", rows, 30, "excel/story_review_meta_table.json/actArchiveResData")

    mails = x("display_meta_table")["mailArchiveData"].get("mailArchiveInfoDict", {})
    b.paged("mails", "来信存档", [(r.get("title") or k, clean(r.get("content")))
                              for k, r in sorted(mails.items(), key=lambda kv: (kv[1].get("sortId", 0), kv[0]))],
            20, "excel/display_meta_table.json/mailArchiveData")

    b.paged("charms", "多索雷斯标志物", [(r.get("name") or r["id"], texts(r, ("desc", "itemUsage", "itemDesc")))
                                    for r in x("charm_table")["charmList"]], 60, "excel/charm_table.json/charmList")

    b.paged("recruit", "招聘与召唤物说明", [(r.get("name") or k, texts(r, ("itemUsage", "itemDesc")))
                                       for k, r in x("character_table").items()], 80, "excel/character_table.json")

    # 干员语音：每套语音（干员或时装语音）一集，「标题：台词」
    voices: dict[str, list] = {}
    for r in x("charword_table")["charWords"].values():
        voices.setdefault(r.get("wordKey") or r["charId"], []).append(r)
    g = b.group("voices", "干员语音")
    for key in sorted(voices):
        rows = sorted(voices[key], key=lambda r: r.get("voiceIndex", 0))
        cid = rows[0]["charId"]
        title = names.get(cid, cid) + ("" if key == cid else f"（{key}）")
        b.episode(g, key, title, [Line("narration", f"{r.get('voiceTitle')}：{s}") for r in rows for s in clean(r.get("voiceText"))[:1]]
                  + [Line("narration", s) for r in rows for s in clean(r.get("voiceText"))[1:]], f"excel/charword_table.json/{key}")

    # 集成战略：每一期的事件场景和藏品
    topics = x("roguelike_topic_table")
    for tid, d in topics["details"].items():
        tname = topics["topics"].get(tid, {}).get("name", tid)
        b.paged(f"{tid}_scenes", f"集成战略 · {tname} · 事件", [
            (f"{r.get('title') or k}（{k}）", clean(r.get("description"))) for k, r in d.get("choiceScenes", {}).items()],
            40, f"excel/roguelike_topic_table.json/details/{tid}/choiceScenes")
        b.paged(f"{tid}_relics", f"集成战略 · {tname} · 藏品与道具", [
            (r.get("name") or k, texts(r, ("usage", "description"))) for k, r in d.get("items", {}).items()],
            60, f"excel/roguelike_topic_table.json/details/{tid}/items")

    # 生息演算：事件场景、物品
    sand = x("sandbox_perm_table")
    for sid, topic in sand.get("detail", {}).get("SANDBOX_V2", {}).items():
        scenes = topic.get("eventSceneData", {}) if isinstance(topic, dict) else {}
        b.paged(f"{sid}_scenes", f"生息演算 · {sid} · 事件", [
            (f"{r.get('title') or k}（{k}）", clean(r.get("desc") or r.get("description"))) for k, r in scenes.items()],
            40, f"excel/sandbox_perm_table.json/detail/SANDBOX_V2/{sid}/eventSceneData")
    items = sand.get("itemData", {})
    b.paged("sandbox_items", "生息演算 · 物品", [
        (r.get("itemName") or k, texts(r, ("itemUsage", "itemDesc", "desc", "description"))) for k, r in items.items()
        if isinstance(r, dict)], 60, "excel/sandbox_perm_table.json/itemData")
    return {gid: g for gid, g in b.groups.items() if g.episodes}


def analyze_episode(ep, reg) -> EpisodeData:
    """设定文本没有说话人，不记出场。"""
    d = EpisodeData(ep, "", ep.script)
    d.lines = Counter()
    return d
