"""时间轴立体视图（#/timeline3d）的布局：读 site/data/annals.json，写 site/data/timeline3d.json。

    python -X utf8 -m pipeline.timeline3d

只用标准库，结果是确定的（同样的编年史，同样的布局）。pipeline.build 最后会调一次；
只跑 pipeline.annals build 时不会，要看新条目就再跑一次这个。网页对布局里没有的条目会临时放在前一条旁边。

纵轴 z 是时间，不按比例：
  - 编年史里每个日期（卷、小节、日）占一层，同一天的条目在同一层；一天超过 PER_LAYER 条时按书中次序分成几层。
  - 相邻两层之间隔一格（单年卷里同小节 STEP_DAY、换小节 STEP_SECTION；外纪、前纪这类合卷里换一个年份
    STEP_SPARSE；换卷 STEP_VOLUME），再加上两处「距今年数取对数」之差乘 LOG_WEIGHT
    （距今：泰拉编算到一一〇三年末，塔卫二编算到一五二年末）。
    事多的年份按条目数拉长，空旷的年代按对数压缩，相隔很久的两件事之间还看得出一段空。
  - 「不系年」卷（原文与年表都无年份的剧情）不上立体轴：它在泰拉编末尾，后面紧接塔罗斯历，放上去像是
    泰拉历走到头接上了塔罗斯历。这些条目在编年史和平面时间轴里照旧。
  - 没有年份的放在标明的区段里，不参与对数：外纪开头年代不详的远古、
    塔卫二编的「塔罗斯历以前」和「年份不书」（各在书中的位置）。

两个起点（AWAKENINGS）：泰拉编的博士苏醒（ev0501，一〇九六年十二月二十三日，罗德岛从石棺中救出博士，主线由此
开始）和塔卫二编的管理员苏醒（「管理员苏醒于帝江号」，塔罗斯历一五二年春）。这一条自成一层，网页在那里画一个
圆形截面，字写在截面上。同一编的每条都标出在苏醒之前还是之后：书中排在它前面的是之前，后面的是之后，按书中
年份算出「苏醒前 N 年」「苏醒后 N 年」。塔卫二编的一五二年是本编推定的「当下」，所以年数随之而定，原文说的
「沉睡十年」正对上一四二年的极点远征。

两种历法：书里塔罗斯历不与泰拉历换算，原文也没有给出对应（见 data/annals/丛目/终末地-纪年线索.md）。
所以塔卫二编画在泰拉编后面，中间断开、不按比例，并在塔罗斯历元年处标明「对应泰拉历：原文未载」。
将来官方给出对应年份，只改下面的 TALOS_YEAR_ONE_IN_TERRA 一处再跑一次：标注改成「＝泰拉历某年」，
两编按换算后的年份排在同一根轴上（断开取消，间距照上面的规则算）。

横向 x、y 排成双螺旋，像 DNA：
  - 每条条目的故事线（剧情组）和网页一样，取它引用的第一个剧情分集所属的组（主线、活动、故事集、终末地各类任务）。
  - 故事线走在「股」上：股是绕中轴转的螺旋线，每 PERIOD 长转一圈。同一故事线隔得太远的条目（回忆里的旧事）
    在 RUN_GAP 处断成几段，各段分别上股，免得一条线横跨几百年。主线一股（A），对面一股（B）给泰拉编的活动、
    塔卫二编的角色任务，两股相对，就是双螺旋的两条主链；故事集、支线、区域任务、塔卫二编的活动走两条内股（C、D）。
    同一股上时间重叠的几段并排成几道（lane），错开一点角度、往里收一点。网页把同一故事线前后相邻的条目沿股连起来。
  - 没有故事线的（设定资料、档案、语音、物品题记、附记）是「碱基」：放在螺旋里面，靠向和它关联最强的那条故事线
    所在的股；附近没有相关的，就落在两条主链之间的横档上。
  - 截面半径随时间起伏：事件越密、同时进行的故事线越多，截面越粗；空旷的年代收细。按高斯核平滑，看起来是有机的。
  - 两条之间的关联 = 共有的人物（【人物】和 传:）、本末（事:）、故事线（剧情组）、地域（是岁、纲里的地名）
    按稀有程度加权（越常见的越轻，如博士），再加上考异里互相引用（见 evXXXX）。网页悬停时画出的细线就是这里存的
    rel（每条最多 REL_SHOWN 条）；碱基靠向哪股也按它定。
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "site" / "data" / "annals.json"
POWERS = ROOT / "site" / "data" / "powers.json"
GROUPS = ROOT / "site" / "data" / "groups.json"
OUT = ROOT / "site" / "data" / "timeline3d.json"

# 塔罗斯历元年对应的泰拉历年份。原文未载，书中也不换算，所以是 None。
# 官方给出对应时填一个数（如 1100），再运行本模块；网页的标注和两编的间距都随之改变。
TALOS_YEAR_ONE_IN_TERRA: float | None = None

# 两个起点：博士苏醒（泰拉编主线由此开始）、管理员苏醒（塔卫二编）。书中那一条的 id、年份、标注
AWAKENINGS = [
    {"id": "ev0501", "bian": "泰拉编", "year": 1096, "label": "博士苏醒", "when": "泰拉历一〇九六年十二月二十三日",
     "lead": "罗德岛潜入切尔诺伯格，从「石棺」中救出博士，主线由此开始。"},
    {"id": "补:管理员苏醒于帝江号", "bian": "塔卫二编", "year": 152, "label": "管理员苏醒", "when": "塔罗斯历一五二年春",
     "lead": "管理员沉睡十年，醒于帝江号（一五二年是本编推定的当下）。"},
]
AWAKENING_IDS = {a["id"] for a in AWAKENINGS}

# 纵轴
PER_LAYER = 4          # 一层最多几条，多了按书中次序分层
STEP_LAYER = 1.1       # 同一天分出来的层之间
STEP_DAY = 0.7         # 单年卷里，同一小节换一天
STEP_SECTION = 1.2     # 单年卷里换小节（月、季、是岁）
STEP_SPARSE = 0.5      # 合卷（外纪、前纪）里换一个年份：事少的年代压紧
STEP_VOLUME = 1.6      # 换卷
LOG_WEIGHT = 3.0       # 「距今年数取对数」之差乘以它
BAND_GAP = 3.0         # 进出没有年份的区段
BREAK_GAP = 12.0       # 两种历法之间的断开

# 横向
NEIGHBORS = 8          # 每条连几条最相关的
REL_SHOWN = 6          # 悬停时画几条线
SEED = "kezhoulu"
PERIOD = 22.0          # 螺旋转一圈的轴长
R_MIN, R_MAX = 2.8, 12.0   # 截面半径的范围（网页里的长度单位）
SIGMA_DENSITY = 3.0    # 算事件密度的高斯核宽度
RUN_GAP = 14.0         # 同一故事线前后两条相隔超过这么远（多是回忆里的旧事），股就断开，分成两段
SIGMA_SMOOTH = 3.0     # 半径再平滑一遍
RADIUS_DZ = 0.5        # 半径表的采样间距
# 股：相位（弧度）和半径倍数。A、B 是两条主链，C、D 是内股
SLOTS = {"A": (0.0, 1.0), "B": (math.pi, 1.0), "C": (math.pi / 2, 0.72), "D": (3 * math.pi / 2, 0.72)}
# 故事线类别 → 依次可用的股；不在表里的类别（档案、语音、物品等）不上股，算碱基
PREFER = {
    "主线": "AC", "活动": "BDC", "故事集": "CDB",
    "终末地·主线": "AC", "终末地·角色任务": "BD", "终末地·支线": "CD", "终末地·区域任务": "DC",
    "终末地·活动": "DCB", "终末地·其他任务": "DC",
}
STORY_LINE = {"主线", "活动", "故事集"}  # 和网页 data.js 一致：泰拉编只认这三类，终末地的组都认

TERRA, TALOS = "泰拉编", "塔卫二编"
UNDATED = "不系年"     # 这一卷不上立体轴，见文件开头

DIG = {"〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
UNIT = {"十": 10, "百": 100, "千": 1000, "万": 10000}
NUM = "[〇零一二两三四五六七八九十百千万]+"
DATE_DAY = re.compile(rf"^(是月|月末|前后|[春夏秋冬]|{NUM}月({NUM}日)?|{NUM}日)$")
SEASON = {"春": 3, "夏": 6, "秋": 9, "冬": 12}


def cn_num(s: str) -> int:
    """一〇九七、七百七十七、一万、元 → 整数。"""
    if s == "元":
        return 1
    if not any(c in UNIT for c in s):
        return int("".join(str(DIG[c]) for c in s))
    total = section = num = 0
    for c in s:
        if c in DIG:
            num = DIG[c]
        elif UNIT[c] == 10000:
            total += (section + num) * 10000
            section = num = 0
        else:
            section += (num or 1) * UNIT[c]
            num = 0
    return total + section + num


def label_year(label: str) -> int | None:
    """合卷小节的标题 → 年份（只用来算间距）。范围取起年，「九世纪」取八〇〇，认不出的返回 None。"""
    s = re.sub(r"^(泰拉历|塔罗斯历)", "", label.strip())
    m = re.match(rf"^(约)?(前)?({NUM}|元)", s)
    if not m:
        return None
    n = cn_num(m[3])
    if s[m.end():].startswith("世纪"):
        n = (n - 1) * 100
    return -n if m[2] else n


def arabic(label: str) -> str:
    """刻度上的字：汉字数字换成阿拉伯数字，「八〇二年」写成「802年」，「塔罗斯历一一年」写成「塔11年」。"""
    if label.strip() == "泰拉历元年":
        return label.strip()
    s = re.sub(r"^泰拉历", "", label.strip())
    talos = s.startswith("塔罗斯历")
    s = re.sub(r"^塔罗斯历", "", s)
    s = re.sub(NUM, lambda m: str(cn_num(m[0])), s)
    return f"塔{s}" if talos else s


def month_of(label: str) -> float | None:
    """单年卷的小节 → 月份（1–12，可带小数）。"""
    if label in SEASON:
        return SEASON[label]
    if label == "年初":
        return 1
    if label in ("年末", "是岁"):
        return 12.9
    m = re.match(rf"^(正|{NUM})月", label)
    if m:
        return 1 if m[1] == "正" else cn_num(m[1])
    return None


def day_of(label: str | None) -> float:
    if not label or label in ("是月", "前后"):
        return 0
    if label == "月末":
        return 28
    m = re.search(rf"({NUM})日$", label)
    return cn_num(m[1]) - 1 if m else 0


# ---------------------------------------------------------------------------------------------- 读编年史
def load_entries(annals: dict, region_names: list[str], talos_regions: list[str] = (),
                 ep_group: dict | None = None, category: dict | None = None) -> tuple[list[dict], list[dict]]:
    aliases = annals.get("aliases", {})
    ep_group, category = ep_group or {}, category or {}
    entries, vols = [], []
    for vi, v in enumerate(annals["volumes"]):
        bian = v.get("bian") or TERRA
        year = v["year"]
        vol = {"index": vi, "year": year, "title": v["title"], "bian": bian, "n": 0}
        vols.append(vol)  # 下标要和卷号对上，所以不系年也登记，只是不取它的条目
        if year == UNDATED:
            continue
        for si, s in enumerate(v["sections"]):
            for d in s["days"]:
                day = d.get("label")
                dated_day = bool(day) and bool(DATE_DAY.match(day))
                for e in d["entries"]:
                    vol["n"] += 1
                    people, text = set(), []
                    for g in e["groups"]:
                        for t in g.get("people", []):
                            for m in re.findall(r"\[\[([^\]|]+)", t):
                                people.add(aliases.get(m, m))
                        text.append(g.get("gang", ""))
                        text.extend(g.get("mu", []))
                        for k in g.get("kaoyi", []):
                            text.append(k.get("text", "") if isinstance(k, dict) else str(k))
                    gang = "".join(g.get("gang", "") for g in e["groups"])
                    regions = {r for r in (region_names if bian == TERRA else [*region_names, *talos_regions]) if r in gang}
                    if day and not dated_day:
                        regions.add(day)
                    # 故事线：和网页一样，先看引用的剧情分集属于哪个组，再看条目自己写的
                    sids = [q["sid"] for g in e["groups"] for q in g.get("quotes", []) if q.get("type") == "story" and q.get("sid")]
                    thread = next((t for t in [*(ep_group.get(x) for x in sids), *e.get("threads", [])]
                                   if t and t != "lore" and (category.get(t) in STORY_LINE or t.startswith("ef_"))), None)
                    entries.append({
                        "id": e["id"], "ids": e.get("ids", []), "vol": vi, "year": year, "bian": bian,
                        "sec": si, "sec_label": s["label"], "day": day if dated_day else None,
                        "people": people, "zhuan": {aliases.get(n, n) for n in e.get("zhuan", [])},
                        "benmo": set(e.get("benmo", [])),
                        "threads": {t for t in [*e.get("threads", []), thread] if t and t != "lore"},
                        "thread": thread, "cat": category.get(thread, ""),
                        "regions": regions, "refs": set(re.findall(r"ev\d{4}", "".join(text))),
                    })
    return entries, vols


def band_of(e: dict, deep: set[int]) -> str | None:
    if e["year"] == "不系年":
        return "undated"
    if e["sec_label"] == "塔罗斯历以前":
        return "talos-pre"
    if e["sec_label"] == "年份不书":
        return "talos-unknown"
    if e["vol"] == 0 and e["sec"] in deep:
        return "deep"
    return None


BANDS = {
    "deep": ("年代不详", "外纪开头：前文明和泰拉纪元前，原文没有年数，按书中次序排在最前。"),
    "undated": ("不系年", "原文与年表都无年份的剧情，放在泰拉编末尾，不按时间排。"),
    "talos-pre": ("塔罗斯历以前", "塔罗斯历元年之前，相隔多久不明。"),
    "talos-unknown": ("年份不书", "属塔罗斯历，年份不明，照书中位置放在一五二年之前。"),
}


# ---------------------------------------------------------------------------------------------- 纵轴
def build_keys(entries: list[dict]) -> list[dict]:
    """连续的、同卷同小节同日的条目合成一个日期（key）。"""
    # 外纪开头连续几个认不出年份的小节算「年代不详」
    deep, seen_year = set(), False
    for e in entries:
        if e["vol"] != 0:
            break
        if label_year(e["sec_label"]) is not None:
            seen_year = True
        elif not seen_year:
            deep.add(e["sec"])
    keys = []
    for i, e in enumerate(entries):
        band = band_of(e, deep)
        k = (e["vol"], e["sec"], e["day"]) if not band else (band,)
        if keys and keys[-1]["k"] == k and e["id"] not in AWAKENING_IDS:  # 苏醒那一条另起一层，前后分得开
            keys[-1]["members"].append(i)
            continue
        single = isinstance(e["year"], int) or bool(re.match(r"^塔\d+$", str(e["year"])))
        keys.append({"k": k, "members": [i], "band": band, "vol": e["vol"], "sec": e["sec"], "single": single,
                     "cal": TALOS if e["bian"] == TALOS else TERRA, "t": key_time(e, band)})
    return keys


def key_time(e: dict, band: str | None) -> float | None:
    """这个日期在自己历法里的年份（带小数），只用来算间距。"""
    if band:
        return None
    y = e["year"]
    if isinstance(y, int):
        month = month_of(e["sec_label"]) or 1
        return y + (month - 1 + day_of(e["day"]) / 31) / 12
    m = re.match(r"^塔(\d+)$", str(y))
    if m:
        month = month_of(e["sec_label"]) or 1
        return int(m[1]) + (month - 1 + day_of(e["day"]) / 31) / 12
    return label_year(e["sec_label"])


def order_keys(keys: list[dict]) -> list[dict]:
    """书中次序。给了塔罗斯历元年的泰拉历年份时，两编按换算后的年份合排。"""
    if TALOS_YEAR_ONE_IN_TERRA is None:
        return keys
    terra = [k for k in keys if k["cal"] == TERRA and k["band"] != "undated"]
    talos = [k for k in keys if k["cal"] == TALOS]
    undated = [k for k in keys if k["band"] == "undated"]
    for k in talos:
        if k["t"] is not None:
            k["t"] = TALOS_YEAR_ONE_IN_TERRA + k["t"] - 1
        k["cal"] = TERRA

    def effective(seq, backward):  # 没有年份的跟着邻居：泰拉编跟前一个，塔卫二编的区段跟后一个
        out, last = [], -math.inf if not backward else math.inf
        for k in (reversed(seq) if backward else seq):
            last = k["t"] if k["t"] is not None else last
            out.append(last)
        return out[::-1] if backward else out

    a, b = effective(terra, False), effective(talos, True)
    merged, i, j = [], 0, 0
    while i < len(terra) or j < len(talos):
        if j >= len(talos) or (i < len(terra) and a[i] <= b[j]):
            merged.append(terra[i])
            i += 1
        else:
            merged.append(talos[j])
            j += 1
    return merged + undated


def place_z(entries: list[dict], keys: list[dict]) -> dict:
    """给每个日期一个 z，同时记下刻度、区段、断开处和塔罗斯历元年的位置。"""
    t_end = {TERRA: 1104.0, TALOS: 153.0}
    if TALOS_YEAR_ONE_IN_TERRA is not None:
        t_end = {TERRA: max([1104.0] + [k["t"] + 1 for k in keys if k["t"] is not None])}

    def log_now(t, cal):
        return -math.log1p(max(0.0, t_end[cal] - t))

    z, prev = 0.0, None
    last_log = {}
    breaks, bands = [], []
    for k in keys:
        if prev is not None:
            if k["cal"] != prev["cal"]:
                gap = BREAK_GAP
                breaks.append([prev["z1"], prev["z1"] + gap])
            elif k["band"] != prev["band"] and (k["band"] or prev["band"]):
                gap = BAND_GAP
            elif k["band"]:
                gap = STEP_SPARSE
            else:
                gap = (STEP_VOLUME if k["vol"] != prev["vol"] else STEP_SPARSE if not k["single"]
                       else STEP_DAY if k["sec"] == prev["sec"] else STEP_SECTION)
            z += gap
        if k["t"] is not None:
            L = log_now(k["t"], k["cal"])
            if k["cal"] in last_log and L > last_log[k["cal"]]:
                z += LOG_WEIGHT * (L - last_log[k["cal"]])
            last_log[k["cal"]] = max(L, last_log.get(k["cal"], -math.inf))
        k["z0"] = z
        for j, i in enumerate(k["members"]):
            entries[i]["z"] = z + (j // PER_LAYER) * STEP_LAYER
        z += ((len(k["members"]) - 1) // PER_LAYER) * STEP_LAYER
        k["z1"] = z
        if k["band"]:
            if bands and bands[-1]["kind"] == k["band"] and bands[-1]["open"]:
                bands[-1]["z1"] = k["z1"]
            else:
                if bands:
                    bands[-1]["open"] = False
                label, note = BANDS[k["band"]]
                bands.append({"kind": k["band"], "z0": k["z0"], "z1": k["z1"], "label": label, "note": note, "open": True})
        elif bands:
            bands[-1]["open"] = False
        prev = k
    for b in bands:
        b.pop("open")
    return {"length": z, "breaks": breaks, "bands": bands}


def ticks_for(entries: list[dict], vols: list[dict], keys: list[dict]) -> tuple[list, list]:
    """刻度：year 每年（合卷里每个小节的年份），sec 月季，day 日；era 每卷开头。"""
    ticks, eras, seen = [], {}, set()
    for k in keys:
        e = entries[k["members"][0]]
        v = vols[e["vol"]]
        era = eras.setdefault(e["vol"], {"vol": v["year"], "label": short_title(v), "title": v["title"],
                                         "bian": v["bian"], "z0": k["z0"], "z1": k["z1"], "n": 0})
        era["z0"], era["z1"] = min(era["z0"], k["z0"]), max(era["z1"], k["z1"])
        era["n"] += len(k["members"])
        if k["band"]:
            continue
        first_of_volume = e["vol"] not in seen
        first_of_section = (e["vol"], e["sec"]) not in seen
        seen.update([e["vol"], (e["vol"], e["sec"])])
        if isinstance(v["year"], int) or re.match(r"^塔\d+$", str(v["year"])):
            if first_of_volume:
                ticks.append([k["z0"], short_title(v), "year"])
            if first_of_section:
                ticks.append([k["z0"], e["sec_label"], "sec"])
            if e["day"] and e["day"] != "是月":
                ticks.append([k["z0"], e["day"], "day"])
        elif first_of_section:
            ticks.append([k["z0"], arabic(e["sec_label"]), "year"])
    out = [[round(t[0], 3), t[1], t[2]] for t in ticks]
    era_list = sorted(eras.values(), key=lambda x: x["z0"])
    for x in era_list:
        x["z0"], x["z1"] = round(x["z0"], 3), round(x["z1"], 3)
    return out, era_list


def short_title(v: dict) -> str:
    y = v["year"]
    if isinstance(y, int):
        return str(y)
    return str(y)   # 塔152、外纪、前纪甲、不系年、塔卫二前纪


# ---------------------------------------------------------------------------------------------- 关联
def relations(entries: list[dict]) -> list[dict[int, float]]:
    """两两之间的关联强度。按特征倒排，越常见的特征越轻（log(1 + N/df)）。"""
    n = len(entries)
    index: dict[str, list[int]] = {}
    base: dict[str, float] = {}

    def add(feature, i, weight):
        index.setdefault(feature, []).append(i)
        base[feature] = weight

    for i, e in enumerate(entries):
        for p in sorted(e["people"] - e["zhuan"]):   # 集合按名字排，结果才不随进程变
            add(f"人:{p}", i, 1.0)
        for p in sorted(e["zhuan"]):
            add(f"传:{p}", i, 1.5)   # 入了此人列传的条目，比只是出场更近
            add(f"人:{p}", i, 1.0)
        for b in sorted(e["benmo"]):
            add(f"事:{b}", i, 2.2)
        for t in sorted(e["threads"]):
            add(f"线:{t}", i, 1.4)
        for r in sorted(e["regions"]):
            add(f"地:{r}", i, 0.5)
    rel: list[dict[int, float]] = [dict() for _ in range(n)]
    for f, members in index.items():
        members = sorted(set(members))
        if len(members) < 2:
            continue
        w = base[f] * math.log1p(n / len(members))
        for a in range(len(members)):
            ra = rel[members[a]]
            for b in range(a + 1, len(members)):
                ra[members[b]] = ra.get(members[b], 0.0) + w
    # 考异里的互见
    by_prts = {}
    for i, e in enumerate(entries):
        for pid in e["ids"]:
            by_prts.setdefault(pid, i)
    for i, e in enumerate(entries):
        for ref in sorted(e["refs"]):
            j = by_prts.get(ref)
            if j is not None and j != i:
                a, b = min(i, j), max(i, j)
                rel[a][b] = rel[a].get(b, 0.0) + 3.0
    full = [dict() for _ in range(n)]
    for a in range(n):
        for b, w in rel[a].items():
            full[a][b] = w
            full[b][a] = w
    return full


def neighbors(entries: list[dict], rel: list[dict[int, float]], k: int) -> list[list[tuple[int, float]]]:
    """每条最相关的 k 条；一样相关时取时间上近的。"""
    out = []
    for i, r in enumerate(rel):
        zi = entries[i]["z"]
        best = sorted(r.items(), key=lambda kv: (-round(kv[1], 6), abs(entries[kv[0]]["z"] - zi), kv[0]))[:k]
        out.append(best)
    return out


# ---------------------------------------------------------------------------------------------- 横向布局：双螺旋
def unit_hash(s: str) -> float:
    return zlib.crc32(f"{SEED}:{s}".encode("utf-8")) / 0xFFFFFFFF


def gauss_smooth(values: list[float], sigma_samples: float) -> list[float]:
    w = int(3 * sigma_samples) + 1
    kernel = [math.exp(-0.5 * (k / sigma_samples) ** 2) for k in range(-w, w + 1)]
    out = []
    for i in range(len(values)):
        acc = norm = 0.0
        for k, kv in zip(range(-w, w + 1), kernel):
            j = i + k
            if 0 <= j < len(values):
                acc += values[j] * kv
                norm += kv
        out.append(acc / norm)
    return out


def radius_profile(entries: list[dict], length: float) -> dict:
    """截面半径：事件密度（高斯核）和同时进行的故事线条数各占一份，按九五分位归一，平滑后映到 R_MIN..R_MAX。"""
    z0 = -3.0
    n = int((length + 6) / RADIUS_DZ) + 1
    zs = [z0 + i * RADIUS_DZ for i in range(n)]
    dens = [0.0] * n
    reach = int(4 * SIGMA_DENSITY / RADIUS_DZ)
    for e in entries:
        c = int(round((e["z"] - z0) / RADIUS_DZ))
        for i in range(max(0, c - reach), min(n, c + reach + 1)):
            dens[i] += math.exp(-0.5 * ((zs[i] - e["z"]) / SIGMA_DENSITY) ** 2)
    spans: dict[str, list[float]] = {}
    for e in entries:
        if e["thread"]:
            a = spans.setdefault(e["thread"], [e["z"], e["z"]])
            a[0], a[1] = min(a[0], e["z"]), max(a[1], e["z"])
    conc = [0.0] * n
    for a, b in spans.values():
        for i in range(max(0, int((a - 3 - z0) / RADIUS_DZ)), min(n, int((b + 3 - z0) / RADIUS_DZ) + 1)):
            conc[i] += 1

    def norm(vals):
        top = sorted(vals)[int(0.95 * (len(vals) - 1))] or 1.0
        return [min(1.15, v / top) for v in vals]

    d, c = norm([math.log1p(v) for v in dens]), norm(conc)
    mix = gauss_smooth([0.62 * a + 0.38 * b for a, b in zip(d, c)], SIGMA_SMOOTH / RADIUS_DZ)
    # 拉开对比：第五百分位收到最细，第九十五百分位撑到最粗
    q = sorted(mix)
    lo, hi = q[int(0.05 * (n - 1))], q[int(0.95 * (n - 1))]
    r = [R_MIN + (R_MAX - R_MIN) * min(1.0, max(0.0, (v - lo) / ((hi - lo) or 1.0))) for v in mix]
    return {"z0": z0, "dz": RADIUS_DZ, "r": [round(v, 3) for v in r]}


def radius_at(prof: dict, z: float) -> float:
    t = (z - prof["z0"]) / prof["dz"]
    i = max(0, min(len(prof["r"]) - 2, int(t)))
    f = min(1.0, max(0.0, t - i))
    return prof["r"][i] * (1 - f) + prof["r"][i + 1] * f


def split_runs(entries: list[dict]) -> None:
    """同一故事线按 RUN_GAP 断成几段，每条写上 run（「组 id#段号」）；不上股的类别 run 为 None。"""
    by_thread: dict[str, list[int]] = {}
    for i, e in enumerate(entries):
        e["run"] = None
        if e["thread"] and e["cat"] in PREFER:
            by_thread.setdefault(e["thread"], []).append(i)
    for t, idx in by_thread.items():
        idx.sort(key=lambda i: entries[i]["z"])
        k, prev = 0, None
        for i in idx:
            if prev is not None and entries[i]["z"] - prev > RUN_GAP:
                k += 1
            entries[i]["run"] = f"{t}#{k}"
            prev = entries[i]["z"]


LANE_SHIFT = [0.0, 0.32, -0.32, 0.64, -0.64, 0.96, -0.96, 1.2, -1.2]


def assign_strands(entries: list[dict]) -> dict[str, tuple[float, float]]:
    """每段分到一股：按类别依次试可用的股，挑当时空着的最靠外一道（lane）；同一道上时间不重叠。"""
    spans: dict[str, list] = {}
    for e in entries:
        if e["run"]:
            a = spans.setdefault(e["run"], [e["z"], e["z"], e["cat"], e["bian"]])
            a[0], a[1] = min(a[0], e["z"]), max(a[1], e["z"])
    lanes: dict[tuple[str, str], list[list[tuple[float, float]]]] = {}
    out = {}
    for run, (a, b, cat, bian) in sorted(spans.items(), key=lambda kv: (kv[1][0], kv[0])):
        best = None
        for rank, slot in enumerate(PREFER[cat]):
            rows = lanes.setdefault((bian, slot), [])
            lane = next((i for i, row in enumerate(rows) if all(y + 1.5 < a or b + 1.5 < x for x, y in row)), len(rows))
            if best is None or (lane, rank) < best[0]:
                best = ((lane, rank), slot, lane)
        _, slot, lane = best
        rows = lanes[(bian, slot)]
        while len(rows) <= lane:
            rows.append([])
        rows[lane].append((a, b))
        phase, k = SLOTS[slot]
        li = min(lane, len(LANE_SHIFT) - 1)
        out[run] = (phase + LANE_SHIFT[li], k * (1 - 0.05 * min(lane, 6)))
    return out


def helix_layout(entries: list[dict], top: list[list[tuple[int, float]]], length: float):
    """返回 xs、ys、半径表、每条故事线的（相位，半径倍数）、每股主链的 z 范围。"""
    prof = radius_profile(entries, length)
    omega = 2 * math.pi / PERIOD
    split_runs(entries)
    strands = assign_strands(entries)
    n = len(entries)
    xs, ys = [0.0] * n, [0.0] * n

    def at(phase, k, z, dr=0.0):
        r = radius_at(prof, z) * k + dr
        return r * math.cos(phase + omega * z), r * math.sin(phase + omega * z)

    # 股上的条目：同一层的几条沿股左右排开
    layer: dict[tuple[str, float], list[int]] = {}
    for i, e in enumerate(entries):
        if e["run"] in strands:
            layer.setdefault((e["run"], e["z"]), []).append(i)
    for (t, z), members in layer.items():
        phase, k = strands[t]
        m = len(members)
        for j, i in enumerate(members):
            off = (j - (m - 1) / 2) * 0.16
            dr = 0.0 if m == 1 else (0.35 if j % 2 else -0.35)
            xs[i], ys[i] = at(phase + off, k, z, dr)
    # 碱基：靠向关联最强、时间相近的那条股上的条目所在的股；没有就落在两条主链之间的横档上
    for i, e in enumerate(entries):
        if e["run"] in strands:
            continue
        h1, h2 = unit_hash(e["id"] + "a"), unit_hash(e["id"] + "r")
        near = next((j for j, _ in top[i] if entries[j]["run"] in strands and abs(entries[j]["z"] - e["z"]) <= 10), None)
        if near is not None:
            phase, k = strands[entries[near]["run"]]
            xs[i], ys[i] = at(phase + (h1 - 0.5) * 0.7, k * (0.22 + 0.42 * h2), e["z"])
        else:
            side = (h2 - 0.5) * 1.15      # 横档上的位置：-0.575..0.575 倍半径
            xs[i], ys[i] = at(0.0 + (h1 - 0.5) * 0.2, side, e["z"])
    # 每编两条主链画在这一编第一条到最后一条之间
    spans: dict[str, list[float]] = {}
    for e in entries:
        a = spans.setdefault(e["bian"], [e["z"], e["z"]])
        a[0], a[1] = min(a[0], e["z"]), max(a[1], e["z"])
    backbones = [{"bian": b, "z0": round(a - 1.5, 3), "z1": round(c + 1.5, 3)} for b, (a, c) in spans.items()]
    return xs, ys, prof, omega, strands, backbones


# ---------------------------------------------------------------------------------------------- 管理员苏醒
def entry_year(e: dict) -> int | None:
    """这一条在自己历法里的年份：单年卷取卷年，合卷取小节标题里的年份；认不出（远古、年份不书）为 None。"""
    if isinstance(e["year"], int):
        return e["year"]
    m = re.match(r"^塔(\d+)$", str(e["year"]))
    if m:
        return int(m[1])
    return label_year(e["sec_label"])


def awakening_marks(entries: list[dict], keys: list[dict]) -> tuple[list, list[dict]]:
    """每条相对本编那一次苏醒的位置（书中次序在前为前、在后为后），和两次苏醒在轴上的位置。"""
    wake = [None] * len(entries)
    marks = []
    for a in AWAKENINGS:
        at = next((i for i, e in enumerate(entries) if e["id"] == a["id"]), None)
        if at is None:
            continue
        before = after = 0
        for i, e in enumerate(entries):
            if e["bian"] != a["bian"]:
                continue
            y = entry_year(e)
            if i == at:
                wake[i] = a["label"]
            elif i > at:
                after += 1
                wake[i] = "苏醒后" if y is None or y <= a["year"] else f"苏醒后 {y - a['year']} 年"
            else:
                before += 1
                wake[i] = ("苏醒前 · 塔罗斯历以前" if e["sec_label"] == "塔罗斯历以前"
                           else "苏醒前 · 年数不明" if y is None
                           else "苏醒前 · 同年" if y >= a["year"] else f"苏醒前 {a['year'] - y} 年")
        key = next(k for k in keys if at in k["members"])
        marks.append({
            "id": a["id"], "bian": a["bian"], "z": round(key["z0"], 3), "year": a["year"],
            "label": a["label"], "when": a["when"], "before": before, "after": after,
            "note": f"{a['lead']}{a['bian']}以此为界：之前 {before} 条，之后 {after} 条，每条标出苏醒前后几年。",
        })
    return wake, marks


# ---------------------------------------------------------------------------------------------- 入口
def build(src: Path = SRC, out: Path = OUT, quiet: bool = False) -> dict:
    t0 = time.perf_counter()
    annals = json.loads(src.read_text(encoding="utf-8"))
    region_names, talos_regions = [], []
    if POWERS.exists():
        powers = json.loads(POWERS.read_text(encoding="utf-8"))
        regions = [p for p in powers.values() if p.get("kind") == "region" and len(p["name"]) > 1]
        region_names = sorted({p["name"] for p in regions if p.get("game") != "endfield"})
        talos_regions = sorted({p["name"] for p in regions if p.get("game") == "endfield"})
    ep_group, category = {}, {}
    if GROUPS.exists():
        for g in json.loads(GROUPS.read_text(encoding="utf-8")):
            category[g["id"]] = g["category"]
            for ep in g["episodes"]:
                ep_group[ep["id"]] = g["id"]
    entries, vols = load_entries(annals, region_names, talos_regions, ep_group, category)
    keys = order_keys(build_keys(entries))
    axis = place_z(entries, keys)
    ticks, eras = ticks_for(entries, vols, keys)
    rel = relations(entries)
    top = neighbors(entries, rel, NEIGHBORS)
    xs, ys, prof, omega, strands, backbones = helix_layout(entries, top, axis["length"])
    thread_ids = sorted(strands)
    thread_at = {t: i for i, t in enumerate(thread_ids)}

    epoch = next((k for k in keys if k["band"] is None and entries[k["members"][0]]["bian"] == TALOS), None)
    known = TALOS_YEAR_ONE_IN_TERRA is not None
    terra_year = (f"{TALOS_YEAR_ONE_IN_TERRA:g}" if known else None)
    calendar = {
        "talos_year_one_in_terra": TALOS_YEAR_ONE_IN_TERRA,
        "z": round(epoch["z0"], 3) if epoch else None,
        "label": "塔罗斯历元年",
        "terra": f"＝ 泰拉历 {terra_year} 年" if known else "对应泰拉历：原文未载",
        "note": ("塔卫二沿用从泰拉带来的历法，另起纪年。"
                 + (f"据官方说法，塔罗斯历元年即泰拉历 {terra_year} 年，两编按此排在同一根轴上。" if known else
                    "原文没有说塔罗斯历元年是泰拉历哪一年，书中也不换算，所以两编之间断开，不按比例。")),
    }
    wake, awakenings = awakening_marks(entries, keys)
    data = {
        "version": 3,
        "count": len(entries),
        "scale": {
            "per_layer": PER_LAYER, "step_layer": STEP_LAYER, "step_day": STEP_DAY, "step_section": STEP_SECTION,
            "step_volume": STEP_VOLUME, "log_weight": LOG_WEIGHT,
            "text": f"每个日期占一层，同一天的事件在同一层（一天超过 {PER_LAYER} 条按书中次序分层）；"
                    "两层之间隔一格，再按相隔年数取对数加一段。事多的年份拉长，空旷的年代压缩。",
        },
        "calendar": calendar,
        "awakenings": awakenings,
        "length": round(axis["length"], 3),
        "breaks": [{"z0": round(a, 3), "z1": round(b, 3), "label": "断开 · 不按比例"} for a, b in axis["breaks"]],
        "bands": [{**b, "z0": round(b["z0"], 3), "z1": round(b["z1"], 3)} for b in axis["bands"]],
        "eras": eras,
        "ticks": ticks,
        "ids": [e["id"] for e in entries],
        "z": [round(e["z"], 3) for e in entries],
        "x": [round(x, 3) for x in xs],
        "y": [round(y, 3) for y in ys],
        "helix": {
            "omega": round(omega, 6), "period": PERIOD, "radius": prof, "backbones": backbones,
            "phases": [0.0, math.pi],
            "threads": thread_ids,
            "strand": [[round(strands[t][0], 4), round(strands[t][1], 4)] for t in thread_ids],
            "text": "故事线走在绕中轴转的螺旋股上：主线一股，对面一股是泰拉编的活动、塔卫二编的角色任务，"
                    "这两股是双螺旋的两条主链；故事集、支线、区域任务等走里面两股。没有故事线的设定、档案、附记"
                    "放在螺旋里面，靠向和它关联最强的那条故事线。截面粗细随事件密度和同时进行的故事线条数起伏。",
        },
        "th": [thread_at.get(e["run"], -1) for e in entries],
        "rel": [[j for j, _ in lst[:REL_SHOWN]] for lst in top],
        "wake": wake,
    }
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if not quiet:
        on = sum(1 for e in entries if e["run"] in strands)
        print(f"立体时间轴：{len(entries)} 条，轴长 {axis['length']:.0f}，{len(strands)} 段故事线上股（{on} 条），"
              f"半径 {min(prof['r']):.1f}–{max(prof['r']):.1f}，{time.perf_counter() - t0:.1f} 秒 → {out.relative_to(ROOT)}")
    return data


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not SRC.exists():
        print("还没有 site/data/annals.json，先运行 python -X utf8 -m pipeline.build")
        return 1
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
