"""导出网页用的数据到 site/data/。网页本体（index.html、app.js、style.css）在 site/ 下手写维护。

site/data/ 整个目录都是生成的，每次构建先清空再写：
    meta.json        构建信息、数据版本、PRTS 出处
    groups.json      剧情组和分集目录（含官方简介、出场人物、相关事件）
    stories/<组>.json 剧本全文，阅读时按组加载
    characters.json  人物：档案、出场、相关事件、常同场人物
    powers.json      地区与势力
    events.json      年表事件和故事线
"""
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations

from . import config, gamedata, profiles
from .analyze import EpisodeData
from .chronicle import Event
from .entities import Registry
from .linker import Linker

LINE_KIND = {"dialogue": "d", "narration": "n", "decision": "c", "branch": "b", "stamp": "s"}
CO_TOP = 24  # 每个人物保留的常同场人物数


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


class SiteExporter:
    def __init__(self, reg: Registry, groups: dict[str, gamedata.Group], built: dict[str, list[EpisodeData]],
                 events: list[Event], prts_meta: dict, data_version: str):
        self.reg = reg
        self.groups = sorted((groups[g] for g in built), key=gamedata.sort_key)
        self.built = built
        self.events = events
        self.prts_meta = prts_meta
        self.data_version = data_version

        self.eps = [d for g in self.groups for d in built[g.id]]
        self.char_lines = Counter()
        for d in self.eps:
            self.char_lines.update(d.lines)
        linker = Linker(reg, self.char_lines)
        self.ev_chars, self.ev_powers = {}, {}
        for e in events:
            self.ev_chars[e.id], self.ev_powers[e.id] = linker.find("\n".join(e.lines))

        self.story_events, self.group_events = defaultdict(list), defaultdict(list)
        self.char_events, self.power_events = defaultdict(list), defaultdict(list)
        for e in events:
            for sid in e.story_ids:
                self.story_events[sid].append(e.id)
            for gid in e.group_ids:
                self.group_events[gid].append(e.id)
            for n in self.ev_chars[e.id]:
                self.char_events[n].append(e.id)
            for p in self.ev_powers[e.id]:
                self.power_events[p].append(e.id)

    # ------------------------------------------------------------------ 剧情
    def export_groups(self) -> list:
        out = []
        for g in self.groups:
            eps = []
            for d in self.built[g.id]:
                e = d.ep
                eps.append({
                    "id": e.story_id, "code": e.code, "title": e.title, "avg": e.avg,
                    "synopsis": d.synopsis or "",
                    "chars": [[n, d.lines.get(n, 0)] for n in sorted(d.present, key=lambda n: (-d.lines.get(n, 0), n))],
                    "others": d.unlinked.most_common(12),
                    "powers": [[p, c] for p, c in d.mentions.most_common()],
                    "stamps": [list(s) for s in d.script.stamps],
                    "events": self.story_events.get(e.story_id, []),
                })
            out.append({
                "id": g.id, "name": g.name, "category": g.category, "label": g.label, "chapter": g.chapter,
                "date": g.start.strftime("%Y-%m-%d") if g.start else None,
                "events": self.group_events.get(g.id, []), "episodes": eps,
            })
        return out

    def export_story(self, g: gamedata.Group) -> dict:
        out = {}
        for d in self.built[g.id]:
            lines = []
            for l in d.script.lines:
                k = LINE_KIND[l.kind]
                lines.append([k, l.speaker or "", l.options if k == "c" else l.text])
            out[d.ep.story_id] = {"lines": lines, "backgrounds": d.script.backgrounds}
        return out

    # ------------------------------------------------------------------ 人物
    def export_characters(self) -> dict:
        appear = defaultdict(lambda: defaultdict(list))  # 人物 → 组 → [分集 id]
        co = defaultdict(Counter)
        for g in self.groups:
            for d in self.built[g.id]:
                for n in d.present:
                    appear[n][g.id].append(d.ep.story_id)
                for a, b in combinations(sorted(d.present - {self.reg.doctor.name}), 2):
                    co[a][b] += 1
                    co[b][a] += 1
        names = set(appear) | set(self.char_events)
        names |= {c.name for c in self.reg.chars.values() if c.kind == "operator"}
        out = {}
        for n in sorted(names):
            c = self.reg.chars[n]
            entry = {
                "kind": c.kind, "aliases": c.aliases, "appellation": c.appellation,
                "profession": c.profession, "rarity": c.rarity,
                "powers": [p for p in c.powers if p in self.reg.powers],
                "lines": self.char_lines.get(n, 0),
                "appear": [[gid, sids] for gid, sids in appear[n].items()],
                "events": self.char_events.get(n, []),
                "co": co[n].most_common(CO_TOP),
            }
            if c.kind == "operator":
                entry["profile"] = profiles.operator_profile(c)
            elif desc := profiles.npc_description(n):
                entry["description"] = desc
            out[n] = entry
        return out

    # ------------------------------------------------------------------ 地区/势力
    def export_powers(self, characters: dict) -> dict:
        mentions = defaultdict(lambda: defaultdict(list))  # power → 组 → [[分集 id, 次数]]
        for g in self.groups:
            for d in self.built[g.id]:
                for p, c in d.mentions.items():
                    mentions[p][g.id].append([d.ep.story_id, c])
        members = defaultdict(list)
        for n, c in characters.items():
            for p in c["powers"]:
                members[p].append(n)
        used = set(mentions) | set(members) | set(self.power_events)
        for p in list(used):
            used.update(self.reg.ancestors(p))
        out = {}
        for p in self.reg.powers.values():
            if p.id not in used:
                continue
            out[p.id] = {
                "name": p.name, "kind": p.kind, "parent": p.parent if p.parent in used else None,
                "children": [x.id for x in self.reg.powers.values() if x.parent == p.id and x.id in used],
                "members": sorted(members[p.id], key=lambda n: (-len(characters[n]["appear"]), n)),
                "mentions": [[gid, eps] for gid, eps in mentions[p.id].items()],
                "events": self.power_events.get(p.id, []),
            }
        return out

    # ------------------------------------------------------------------ 年表
    def export_events(self) -> dict:
        threads = {g.id: {"name": g.name, "category": g.category, "label": g.label} for g in self.groups}
        threads["lore"] = {"name": "设定与档案", "category": "设定", "label": ""}
        evs = []
        for e in self.events:
            evs.append({
                "id": e.id, "era": e.era, "when": e.when, "year": e.year, "lines": e.lines,
                "parallel": e.parallel, "notes": e.notes,
                "thread": next(iter(e.group_ids), "lore"),
                "sources": [{"text": s.text, "groups": s.group_ids, "stories": s.story_ids} for s in e.sources],
                "chars": self.ev_chars[e.id], "powers": self.ev_powers[e.id],
            })
        return {"threads": threads, "events": evs}

    def export(self) -> dict:
        if config.SITE_DATA.exists():
            shutil.rmtree(config.SITE_DATA)
        groups = self.export_groups()
        characters = self.export_characters()
        powers = self.export_powers(characters)
        events = self.export_events()
        for g in self.groups:
            dump(config.SITE_DATA / "stories" / f"{g.id}.json", self.export_story(g))
        dump(config.SITE_DATA / "groups.json", groups)
        dump(config.SITE_DATA / "characters.json", characters)
        dump(config.SITE_DATA / "powers.json", powers)
        dump(config.SITE_DATA / "events.json", events)
        stats = {
            "groups": len(groups), "episodes": len(self.eps), "events": len(self.events),
            "characters": len(characters), "powers": len(powers),
        }
        dump(config.SITE_DATA / "meta.json", {
            "built_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "data_version": self.data_version,
            "prts": self.prts_meta, "stats": stats,
        })
        return stats
