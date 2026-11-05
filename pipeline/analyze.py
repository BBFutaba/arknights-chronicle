"""把一集剧本解析结果和实体登记表对上：谁出场、说了多少、提到了哪些地区势力。"""
import re
from collections import Counter
from dataclasses import dataclass, field

from . import gamedata
from .entities import Registry
from .script import Script, parse_script


@dataclass
class EpisodeData:
    ep: gamedata.Episode
    synopsis: str | None
    script: Script
    lines: Counter = field(default_factory=Counter)  # 人物名 → 台词数
    present: set[str] = field(default_factory=set)  # 出场人物（说话或有立绘）
    unlinked: Counter = field(default_factory=Counter)  # 未建页的说话人 → 台词数
    mentions: Counter = field(default_factory=Counter)  # power id → 提及次数

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in self.script.lines if l.kind in ("dialogue", "narration"))


def analyze_episode(ep: gamedata.Episode, reg: Registry) -> EpisodeData:
    sc = parse_script(gamedata.read_story(ep.txt))
    d = EpisodeData(ep, gamedata.read_info(ep.info), sc)
    for line in sc.lines:  # dialog 指令的说话人是头像 id
        if line.speaker and re.match(r"(char|npc)_", line.speaker):
            line.speaker = gamedata.head_name(line.speaker)
    for line in sc.lines:
        if line.kind == "decision":
            d.lines[reg.doctor.name] += 1
        elif line.kind == "dialogue" and line.speaker:
            chars = reg.resolve_speakers(line.speaker)
            for ch in chars:
                d.lines[ch.name] += 1
            if not chars:
                d.unlinked[line.speaker] += 1
    d.present.update(d.lines)
    for base in sc.portraits:
        ch = reg.resolve_portrait(base)
        if ch:
            d.present.add(ch.name)
    d.mentions = reg.mentions(d.text)
    return d


def to_record(d: EpisodeData, reg: Registry) -> dict:
    """data/structured/episodes.jsonl 的一行，供后续 AI 抽取阶段使用。"""
    e = d.ep
    return {
        "story_id": e.story_id, "group_id": e.group_id, "code": e.code, "title": e.title,
        "avg": e.avg, "sort": e.sort, "txt": e.txt, "synopsis": d.synopsis,
        "characters": {n: d.lines.get(n, 0) for n in sorted(d.present, key=lambda n: -d.lines.get(n, 0))},
        "unlinked_speakers": dict(d.unlinked.most_common()),
        "mentions": {reg.powers[p].name: n for p, n in d.mentions.most_common()},
        "stamps": d.script.stamps, "backgrounds": d.script.backgrounds, "images": d.script.images,
        "lines": [
            {k: v for k, v in (("k", l.kind), ("s", l.speaker), ("t", l.text), ("o", l.options)) if v}
            for l in d.script.lines
        ],
    }
