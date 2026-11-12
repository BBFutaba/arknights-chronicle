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
  - 没有年份的放在标明的区段里，不参与对数：外纪开头年代不详的远古、泰拉编末尾的「不系年」、
    塔卫二编的「塔罗斯历以前」和「年份不书」（各在书中的位置）。

管理员苏醒：塔卫二编以管理员在帝江号上苏醒为界（书中「管理员苏醒于帝江号」一条，塔罗斯历一五二年春）。
这一条自成一层，轴上画一圈绿环；塔卫二编每条都标出在苏醒之前还是之后：书中排在它前面的是之前
（前纪、年份不明的区段、一五二年里苏醒前数周的事），后面的是之后；之前的按书中年份算出「苏醒前 N 年」。
一五二年是本编推定的「当下」，所以年数随之而定，原文说的「沉睡十年」正对上一四二年的极点远征。

两种历法：书里塔罗斯历不与泰拉历换算，原文也没有给出对应（见 data/annals/丛目/终末地-纪年线索.md）。
所以塔卫二编画在泰拉编后面，中间断开、不按比例，并在塔罗斯历元年处标明「对应泰拉历：原文未载」。
将来官方给出对应年份，只改下面的 TALOS_YEAR_ONE_IN_TERRA 一处再跑一次：标注改成「＝泰拉历某年」，
两编按换算后的年份排在同一根轴上（断开取消，间距照上面的规则算）。

横向 x、y 按关联远近，力导向排布：
  - 两条之间的关联 = 共有的人物（【人物】和 传:）、本末（事:）、故事线（剧情组）、地域（是岁、纲里的地名）
    按稀有程度加权（越常见的越轻，如博士），再加上考异里互相引用（见 evXXXX）。
  - 每条只连关联最强的 NEIGHBORS 条，彼此相吸；排斥只在 z 相距 REPEL_WINDOW 以内的条目之间算，所以很快；
    中轴本身也推开靠得太近的点，没有关联的条目落在轴外一圈，不压在轴上。
  - 网页悬停时画出的细线就是这里存的 rel（每条最多 REL_SHOWN 条）。
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
OUT = ROOT / "site" / "data" / "timeline3d.json"

# 塔罗斯历元年对应的泰拉历年份。原文未载，书中也不换算，所以是 None。
# 官方给出对应时填一个数（如 1100），再运行本模块；网页的标注和两编的间距都随之改变。
TALOS_YEAR_ONE_IN_TERRA: float | None = None

# 管理员苏醒：书中那一条的 id（补条名）和它所在的年份
AWAKENING_ID = "补:管理员苏醒于帝江号"
AWAKENING_YEAR = 152

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
REPEL_WINDOW = 4.0     # 排斥只算 z 相距这么近的
ITERATIONS = 300
SEED = "kezhoulu"

TERRA, TALOS = "泰拉编", "塔卫二编"

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
def load_entries(annals: dict, region_names: list[str], talos_regions: list[str] = ()) -> tuple[list[dict], list[dict]]:
    aliases = annals.get("aliases", {})
    entries, vols = [], []
    for vi, v in enumerate(annals["volumes"]):
        bian = v.get("bian") or TERRA
        year = v["year"]
        vol = {"index": vi, "year": year, "title": v["title"], "bian": bian, "n": 0}
        vols.append(vol)
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
                    entries.append({
                        "id": e["id"], "ids": e.get("ids", []), "vol": vi, "year": year, "bian": bian,
                        "sec": si, "sec_label": s["label"], "day": day if dated_day else None,
                        "people": people, "zhuan": {aliases.get(n, n) for n in e.get("zhuan", [])},
                        "benmo": set(e.get("benmo", [])), "threads": {t for t in e.get("threads", []) if t != "lore"},
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
        if keys and keys[-1]["k"] == k and e["id"] != AWAKENING_ID:  # 苏醒那一条另起一层，前后分得开
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


# ---------------------------------------------------------------------------------------------- 横向布局
def unit_hash(s: str) -> float:
    return zlib.crc32(f"{SEED}:{s}".encode("utf-8")) / 0xFFFFFFFF


def layout(entries: list[dict], top: list[list[tuple[int, float]]]) -> tuple[list[float], list[float], int, int]:
    n = len(entries)
    # 起点：同一本末或同一故事线的从同一个方向出发，收敛快些
    xs, ys = [], []
    for e in entries:
        anchor = min(e["benmo"]) if e["benmo"] else min(e["threads"]) if e["threads"] else e["id"]
        a = 2 * math.pi * unit_hash(anchor) + 0.6 * (unit_hash(e["id"]) - 0.5)
        r = 1.0 + 0.4 * unit_hash(e["id"] + "r")
        xs.append(r * math.cos(a))
        ys.append(r * math.sin(a))

    # 相吸：对称的近邻图，强度随关联变强，随时间相隔变远而减弱
    edges: dict[tuple[int, int], float] = {}
    all_w = sorted(w for lst in top for _, w in lst)
    half = all_w[len(all_w) // 2] if all_w else 1.0
    for i, lst in enumerate(top):
        for j, w in lst:
            a, b = min(i, j), max(i, j)
            s = w / (w + half) / (1 + abs(entries[i]["z"] - entries[j]["z"]) / 40)
            edges[(a, b)] = max(edges.get((a, b), 0.0), s)
    edge_list = [(a, b, s) for (a, b), s in sorted(edges.items())]

    # 排斥：z 固定，近邻对只算一次
    order = sorted(range(n), key=lambda i: (entries[i]["z"], i))
    pairs = []
    for p in range(n):
        i = order[p]
        zi = entries[i]["z"]
        for q in range(p + 1, n):
            j = order[q]
            dz = entries[j]["z"] - zi
            if dz >= REPEL_WINDOW:
                break
            f = 1 - dz / REPEL_WINDOW
            pairs.append((i, j, f * f))

    REPEL, ATTRACT, GRAVITY, AXIS = 0.05, 0.35, 0.25, 0.25
    for it in range(ITERATIONS):
        step = 0.25 * (1 - it / ITERATIONS) + 0.01
        fx, fy = [0.0] * n, [0.0] * n
        for i, j, f in pairs:
            dx, dy = xs[i] - xs[j], ys[i] - ys[j]
            d2 = dx * dx + dy * dy + 1e-3
            k = REPEL * f / d2
            fx[i] += dx * k
            fy[i] += dy * k
            fx[j] -= dx * k
            fy[j] -= dy * k
        for a, b, s in edge_list:
            dx, dy = xs[b] - xs[a], ys[b] - ys[a]
            k = ATTRACT * s
            fx[a] += dx * k
            fy[a] += dy * k
            fx[b] -= dx * k
            fy[b] -= dy * k
        for i in range(n):
            x, y = xs[i], ys[i]
            r2 = x * x + y * y + 1e-3
            # 拉回中轴，同时被中轴推开：孤立的点停在半径 sqrt(AXIS / GRAVITY) 的一圈上
            gx = -GRAVITY * x + AXIS * x / r2
            gy = -GRAVITY * y + AXIS * y / r2
            tx, ty = fx[i] + gx, fy[i] + gy
            d = math.hypot(tx, ty)
            if d > step:
                tx, ty = tx * step / d, ty * step / d
            xs[i] = x + tx
            ys[i] = y + ty
    # 归一：九成五的点落在半径 1 以内
    radii = sorted(math.hypot(x, y) for x, y in zip(xs, ys))
    scale = 1 / (radii[int(0.95 * (n - 1))] or 1)
    return [x * scale for x in xs], [y * scale for y in ys], len(pairs), len(edge_list)


# ---------------------------------------------------------------------------------------------- 管理员苏醒
def talos_year(e: dict) -> int | None:
    m = re.match(r"^塔(\d+)$", str(e["year"]))
    if m:
        return int(m[1])
    if e["sec_label"].startswith("塔罗斯历"):
        return label_year(e["sec_label"])
    return None


def awakening_marks(entries: list[dict], keys: list[dict]) -> tuple[list, dict | None]:
    """塔卫二编每条相对管理员苏醒的位置（泰拉编为 null），和轴上那一圈的位置。"""
    at = next((i for i, e in enumerate(entries) if e["id"] == AWAKENING_ID), None)
    if at is None:
        return [None] * len(entries), None
    wake, before, after = [], 0, 0
    for i, e in enumerate(entries):
        if e["bian"] != TALOS:
            wake.append(None)
        elif i == at:
            wake.append("管理员苏醒")
        elif i > at:
            wake.append("苏醒后")
            after += 1
        else:
            before += 1
            y = talos_year(e)
            wake.append("苏醒前 · 塔罗斯历以前" if e["sec_label"] == "塔罗斯历以前"
                        else "苏醒前 · 年数不明" if y is None
                        else "苏醒前 · 同年" if y >= AWAKENING_YEAR else f"苏醒前 {AWAKENING_YEAR - y} 年")
    key = next(k for k in keys if at in k["members"])
    return wake, {
        "id": AWAKENING_ID, "z": round(key["z0"], 3), "year": AWAKENING_YEAR,
        "label": "管理员苏醒", "when": "塔罗斯历一五二年春", "before": before, "after": after,
        "note": f"管理员沉睡十年，醒于帝江号。塔卫二编以此为界：之前 {before} 条，之后 {after} 条；"
                "之前的按书中年份标出苏醒前几年（一五二年是本编推定的当下）。",
    }


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
    entries, vols = load_entries(annals, region_names, talos_regions)
    keys = order_keys(build_keys(entries))
    axis = place_z(entries, keys)
    ticks, eras = ticks_for(entries, vols, keys)
    rel = relations(entries)
    top = neighbors(entries, rel, NEIGHBORS)
    xs, ys, n_pairs, n_edges = layout(entries, top)

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
    wake, awakening = awakening_marks(entries, keys)
    data = {
        "version": 1,
        "count": len(entries),
        "scale": {
            "per_layer": PER_LAYER, "step_layer": STEP_LAYER, "step_day": STEP_DAY, "step_section": STEP_SECTION,
            "step_volume": STEP_VOLUME, "log_weight": LOG_WEIGHT,
            "text": f"每个日期占一层，同一天的事件在同一层（一天超过 {PER_LAYER} 条按书中次序分层）；"
                    "两层之间隔一格，再按相隔年数取对数加一段。事多的年份拉长，空旷的年代压缩。",
        },
        "calendar": calendar,
        "awakening": awakening,
        "length": round(axis["length"], 3),
        "breaks": [{"z0": round(a, 3), "z1": round(b, 3), "label": "断开 · 不按比例"} for a, b in axis["breaks"]],
        "bands": [{**b, "z0": round(b["z0"], 3), "z1": round(b["z1"], 3)} for b in axis["bands"]],
        "eras": eras,
        "ticks": ticks,
        "ids": [e["id"] for e in entries],
        "z": [round(e["z"], 3) for e in entries],
        "x": [round(x, 4) for x in xs],
        "y": [round(y, 4) for y in ys],
        "rel": [[j for j, _ in lst[:REL_SHOWN]] for lst in top],
        "wake": wake,
    }
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if not quiet:
        print(f"立体时间轴：{len(entries)} 条，轴长 {axis['length']:.0f}，排斥对 {n_pairs}，相吸 {n_edges}，"
              f"{time.perf_counter() - t0:.1f} 秒 → {out.relative_to(ROOT)}")
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
