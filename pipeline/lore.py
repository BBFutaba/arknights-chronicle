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
    load_more(b, names)
    return {gid: g for gid, g in b.groups.items() if g.episodes}


# ---- 2026-11-13 第二次盘点后补接（全部接在原有各组之后，原有分集的行号不变） ----

MARKUP = re.compile(r"<[@$][^>]*>|<color=|\{[^}]*\}")
FLAVOR_SKIP = re.compile(r"^(附加条件|紧急作战|初始危险等级|<@lv\.fs>|<@lv\.muitem>)")
GAMEPLAY = re.compile(r"[0-9%]|消耗|活动期间|累计|通关|可获得|获得以下效果")
CJK = re.compile(r"[一-鿿]")


def flavor(text) -> list[str]:
    """关卡类说明只留叙述：去掉带玩法标记（<@lv.…>、<color=…>）的行和「附加条件」行。"""
    if not isinstance(text, str):
        return []
    out = []
    for raw in text.replace("\\n", "\n").split("\n"):
        if not raw.strip() or MARKUP.search(raw) or FLAVOR_SKIP.match(raw.strip()):
            continue
        out += clean(raw)
    return out


def prose(text, least=12) -> list[str]:
    """没有结构可依的表（活动、生息演算、集成战略的选项等）只留像叙述的字串：
    不带玩法标记、不含数字和「消耗」「通关」一类玩法词，至少 least 个汉字。"""
    if not isinstance(text, str) or MARKUP.search(text) or GAMEPLAY.search(TAG.sub("", text)):
        return []
    lines = clean(text)
    return lines if sum(len(CJK.findall(s)) for s in lines) >= least else []


def strings(v, path=""):
    """（路径，字串）逐个列出，路径用于标题。"""
    if isinstance(v, str):
        yield path, v
    elif isinstance(v, dict):
        for k, a in v.items():
            yield from strings(a, f"{path}/{k}" if path else str(k))
    elif isinstance(v, list):
        for a in v:
            yield from strings(a, path)


def prose_rows(v, least=12, seen=None):
    """把一棵数据里像叙述的字串收成（路径，几行），同文去重。"""
    seen = set() if seen is None else seen
    rows = []
    for p, s in strings(v):
        body = prose(s, least)
        key = "\n".join(body)
        if body and key not in seen:
            seen.add(key)
            rows.append((p, body))
    return rows


def script_lines(rel: str) -> list[Line]:
    """剧本文件读成旁白：「名：台词」，舞台指令去掉。"""
    out = []
    for raw in gamedata.read_story(rel).splitlines():
        raw = raw.strip()
        if m := re.match(r'\[name="([^"]*)"[^\]]*\](.*)', raw, re.I):
            who, said = m[1].strip(), "".join(clean(m[2]))
            if said:
                out.append(Line("narration", f"{who}：{said}" if who else said))
        elif raw and not raw.startswith("["):
            out += [Line("narration", s) for s in clean(raw)]
        elif m := re.match(r'\[Decision\(options="([^"]+)"', raw, re.I):
            out.append(Line("narration", "（选项）" + " / ".join(s for s in m[1].split(";") if s.strip())))
        elif m := re.match(r'\[(?:Subtitle|Sticker|Dialog|multiline)[^\]]*text="([^"]+)"', raw, re.I):
            out += [Line("narration", s) for s in clean(m[1])]
        elif (m := re.match(r'\[(?!HEADER)[^\]]*\]\s*(\S.*)', raw, re.I)) and CJK.search(m[1]):
            out += [Line("narration", s) for s in clean(m[1])]
    return out


def load_more(b: Builder, names: dict[str, str]):
    """第二次盘点（2026-11-13）找出的余下文本：家具套装主题、关卡与剧情线说明、剧情插图题记、悖论模拟、活动里的叙述、
    集成战略的关卡与区域、旧版集成战略、生息演算「沙中之火」、保全派驻、杂项文案、教程与引导对白。
    关卡、活动这类表里叙述和玩法混在一起，只按标记和玩法词粗分（见 flavor、prose）；纯玩法表（技能、天赋、任务条件、商店）不收。"""
    x = gamedata.excel

    themes = x("building_data")["customData"]["themes"]
    b.paged("furniture_themes", "家具套装主题", [
        (r.get("name") or k, clean(r.get("desc"))) for k, r in sorted(themes.items(), key=lambda kv: (kv[1].get("sortId", 0), kv[0]))],
        40, "excel/building_data.json/customData/themes")

    st = x("stage_table")
    seen, rows = set(), []
    for k, r in st["stages"].items():
        body = flavor(r.get("description"))
        key = "\n".join(body)
        if body and key not in seen:
            seen.add(key)
            rows.append((f"{r.get('code') or k} {r.get('name') or ''}（{k}）".strip(), body))
    for k, r in x("retro_table")["stageList"].items():
        body = flavor(r.get("description"))
        key = "\n".join(body)
        if body and key not in seen:
            seen.add(key)
            rows.append((f"{r.get('code') or k} {r.get('name') or ''}（{k}）".strip(), body))
    b.paged("stages", "关卡说明", rows, 120, "excel/stage_table.json/stages")

    rows = []
    for k, r in st["storylineStorySets"].items():
        data = r.get("mainlineData") or r.get("ssData") or {}
        rows.append((k.removeprefix("setId_"), clean(data.get("desc"))))
    b.paged("storylines", "剧情线简介", rows, 60, "excel/stage_table.json/storylineStorySets")

    b.paged("cg", "剧情插图题记", [
        (f"{r.get('displayName') or k}（{k.removeprefix('cgId_')}）", clean(r.get("displayDesc")))
        for k, r in sorted(st["cgGalleryDisplays"].items(), key=lambda kv: (kv[1].get("storySetId") or "", kv[1].get("sortId", 0)))],
        120, "excel/stage_table.json/cgGalleryDisplays")

    rows = []
    for cid, r in x("handbook_info_table")["handbookStageData"].items():
        rows.append((f"{names.get(cid, cid)} · {r.get('name') or r.get('code')}", flavor(r.get("description"))))
    b.paged("paradox", "悖论模拟", rows, 60, "excel/handbook_info_table.json/handbookStageData")

    # 活动表：每个活动一集；活动之外的几块（周年探索、叙拉古、七周年、节庆祝福……）各一集
    at = x("activity_table")
    info = at.get("basicInfo", {})
    g = b.group("actplay", "活动玩法里的叙述")
    seen = set()
    for typ, acts in sorted(at.get("activity", {}).items()):
        for aid, data in sorted(acts.items()):
            rows = prose_rows(data, seen=seen)
            if rows:
                b.episode(g, aid, f"{info.get(aid, {}).get('name') or aid}（{aid}）",
                          [Line("narration", s) for _, body in rows for s in body], f"excel/activity_table.json/activity/{typ}/{aid}")
    for key in sorted(at):
        if key in ("activity", "basicInfo", "missionData", "missionGroup", "homeActConfig", "actThemes", "carData"):
            continue
        rows = prose_rows(at[key], seen=seen)
        if rows:
            b.episode(g, key, key, [Line("narration", s) for _, body in rows for s in body], f"excel/activity_table.json/{key}")

    # 集成战略：关卡、区域、选项、挑战、月度小队、通宝等，每期一集或几集
    topics = x("roguelike_topic_table")
    for tid, d in topics["details"].items():
        tname = topics["topics"].get(tid, {}).get("name", tid)
        rows, seen = [], set()
        for k, r in d.get("stages", {}).items():
            body = flavor(r.get("description"))
            if body and "\n".join(body) not in seen:
                seen.add("\n".join(body))
                rows.append((f"{r.get('name') or k}（{k}）", body))
        for sec in ("zones", "choices", "challenges", "archiveComp", "endings", "difficulties"):
            rows += [(f"{sec}/{p}", body) for p, body in prose_rows(d.get(sec, {}), 8, seen)]
        rows += [(f"modules/{p}", body) for p, body in prose_rows(topics.get("modules", {}).get(tid, {}), 12, seen)]
        b.paged(f"{tid}_more", f"集成战略 · {tname} · 关卡、区域与其他", rows, 150, f"excel/roguelike_topic_table.json/details/{tid}")

    old = x("roguelike_table")
    rows = [(f"{r.get('name') or k}", texts(r, ("usage", "description"))) for k, r in old.get("itemTable", {}).get("items", {}).items()]
    rows += [(f"{r.get('title') or k}（{k}）", clean(r.get("description"))) for k, r in old.get("choiceScenes", {}).items()]
    rows += [(f"{r.get('name') or k}（{k}）", flavor(r.get("description"))) for k, r in old.get("stages", {}).items()]
    rows += prose_rows({s: old.get(s, {}) for s in ("zones", "choices", "endings", "outBuffs")}, 8)
    b.paged("rogue_legacy", "集成战略 · 旧版傀影", rows, 80, "excel/roguelike_table.json")

    rows = []
    sb = x("sandbox_table")
    for aid, data in sb.get("sandboxActTables", {}).items():
        rows += prose_rows(data)
    rows += [(r.get("itemName") or k, texts(r, ("itemUsage", "itemDesc"))) for k, r in sb.get("itemDatas", {}).items()
             if isinstance(r, dict) and not MARKUP.search(str(r.get("itemDesc", "")))]
    b.paged("sandbox_0", "生息演算 · 沙中之火", rows, 80, "excel/sandbox_table.json")

    ct = x("climb_tower_table")
    rows = [(f"{r.get('name')} · {r.get('subName') or ''}（{k}）", clean(r.get("desc"))) for k, r in ct.get("towers", {}).items()]
    rows += [(f"{r.get('code')} {r.get('name')}（{k}）", flavor(r.get("desc"))) for k, r in ct.get("levels", {}).items()]
    b.paged("climb", "保全派驻", rows, 120, "excel/climb_tower_table.json")

    g = b.group("misc", "杂项文案")
    dm = x("display_meta_table")

    def ep(key, title, rows, source):
        b.episode(g, key, title, [Line("narration", s) for t, body in rows for s in ([f"【{t}】"] if t else []) + body], source)

    tips = x("tip_table")
    ep("tips", "加载提示", [("", clean(r.get("tip"))) for r in tips.get("tips", [])]
       + [(r.get("title") or "", texts(r, ("desc", "tip", "text"))) for r in (tips.get("worldViewTips") or [])], "excel/tip_table.json")
    ep("avatars", "头像说明", [(r.get("avatarItemName"), texts(r, ("avatarItemDesc",))) for r in
                            dm["playerAvatarData"].get("avatarList", []) if len("".join(texts(r, ("avatarItemDesc",)))) > 4],
       "excel/display_meta_table.json/playerAvatarData")
    hb = dm["homeBackgroundData"]
    ep("backgrounds", "首页背景与主题", [(r.get("bgName"), texts(r, ("bgDes",))) for r in hb.get("homeBgDataList", [])]
       + [(r.get("tmName"), texts(r, ("tmDes",))) for r in hb.get("themeList", [])], "excel/display_meta_table.json/homeBackgroundData")
    ep("namecards", "名片", [(p, body) for p, body in prose_rows(dm["nameCardV2Data"], 8)], "excel/display_meta_table.json/nameCardV2Data")
    ep("brands", "时装品牌", [(r.get("brandName") or k, texts(r, ("description",))) for k, r in x("skin_table")["brandList"].items()],
       "excel/skin_table.json/brandList")
    zr = []
    for zid, z in x("zone_table")["zoneRecordGroupedData"].items():
        for rec in z.get("records", []):
            for rw in rec.get("rewards", []):
                if rw.get("textDesc"):
                    zr.append((f"{zid} {rec.get('recordTitleName') or ''}", clean(rw["textDesc"])))
    ep("zone_records", "章节记录点", zr, "excel/zone_table.json/zoneRecordGroupedData")
    cr = []
    for sid, s in x("crisis_v2_table")["recalRuneData"].get("seasons", {}).items():
        for lid, lv in s.get("stages", {}).items():
            cr.append((f"{sid} {lid}", flavor(lv.get("levelDesc"))))
    ep("recalrune", "危机合约 · 回溯", cr, "excel/crisis_v2_table.json/recalRuneData")
    tx = []
    for cid, r in x("handbook_table").items():
        for a in r.get("storyTextAudio", []):
            for s in a.get("stories", []):
                tx.append(("", clean(s.get("storyText"))))
        for a in r.get("infoTextAudio", []):
            for s in a.get("infoList", []):
                tx.append(("", clean(s.get("infoText"))))
    ep("handbook_special", "德克萨斯特别档案", tx, "excel/handbook_table.json")
    barks = []
    for t in ("ark_odc_table", "arkvent_table"):
        for p, s in strings(x(t)):
            if p.endswith("/content") and clean(s):
                barks.append(("", clean(s)))
    ep("barks", "活动场景闲谈", barks, "excel/ark_odc_table.json; excel/arkvent_table.json")
    mt = [(k, body) for k, s in x("main_text").get("strings", {}).items() if not k.startswith("&&") for body in [prose(s)] if body]
    ep("main_text", "活动小游戏文案", mt, "excel/main_text.json/strings")

    # 剧本库里没进任何组的文件：教程、引导、训练关、小游戏对白
    from .gamedata import load_review_groups, load_memory_groups, load_extra_groups, add_hidden_stories
    groups = load_review_groups()
    add_hidden_stories(groups)
    groups.update(load_memory_groups())
    groups.update(load_extra_groups(groups))
    used = {e.txt.lower() for gg in groups.values() for e in gg.episodes if e.txt}
    g = b.group("tutorial", "教程、引导与小游戏对白")
    rels = sorted(f.relative_to(gamedata.config.STORY).with_suffix("").as_posix() for f in gamedata.config.STORY.rglob("*.txt"))
    for rel in rels:
        if rel.lower() in used or rel.lower().startswith("[uc]info/"):
            continue
        lines = script_lines(rel)
        if sum(len(CJK.findall(l.text)) for l in lines) >= 20:
            b.episode(g, re.sub(r"[^0-9A-Za-z_]+", "_", rel), rel, lines, f"story/{rel}.txt")


def analyze_episode(ep, reg) -> EpisodeData:
    """设定文本没有说话人，不记出场。"""
    d = EpisodeData(ep, "", ep.script)
    d.lines = Counter()
    return d
