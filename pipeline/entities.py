"""人物、地区、势力的登记表：把剧本里的说话人、立绘 id 和地名归一到实体。

确定性规则（不依赖 AI）：
- 干员来自 character_table；同名的多个 id（如三种阿米娅）合并，异格干员并入本体。
- 说话人名先查 data/curated/entities.toml 的别名，再匹配干员名；路人按规则过滤，其余建 NPC。
- 立绘 id 能对上干员 id 时，即使没说话也算出场。
- 国家和组织来自 handbook_team_table，再加上 entities.toml 里的补充。
"""
import re
import tomllib
from collections import Counter
from dataclasses import dataclass, field

from . import config, gamedata

PROFESSIONS = {
    "PIONEER": "先锋", "WARRIOR": "近卫", "TANK": "重装", "SNIPER": "狙击",
    "CASTER": "术师", "MEDIC": "医疗", "SUPPORT": "辅助", "SPECIAL": "特种",
}
GENERIC_TAIL_RE = re.compile(r"[一-鿿][A-ZＡ-Ｚ甲乙丙0-9０-９]+$")  # 整合运动A、士兵2
UNKNOWN_RE = re.compile(r"[？?…·.\s]+")
MULTI_SPEAKER_RE = re.compile(r"[&＆]")  # 「炎熔&芙蓉」同时说话


@dataclass
class Character:
    name: str
    kind: str  # operator | npc | doctor
    char_ids: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    appellation: str = ""
    profession: str = ""
    rarity: int = 0
    powers: list[str] = field(default_factory=list)  # 所属国家/组织/小队的 power id


@dataclass
class Power:
    id: str
    name: str  # 显示名，如「龙门」
    kind: str  # region | faction
    parent: str | None = None
    match: list[str] = field(default_factory=list)


def _book_aliases() -> dict[str, str]:
    """编年史的别名表（data/annals/别名.md）：每行「别名=正名」，同一个人只留一个人物页。"""
    path = config.ROOT / "data" / "annals" / "别名.md"
    if not path.exists():
        return {}
    pairs = (s.strip().split("=", 1) for s in path.read_text(encoding="utf-8").splitlines()
             if "=" in s and not s.startswith("<!--"))
    return {a.strip(): b.strip() for a, b in pairs}


class Registry:
    def __init__(self):
        with open(config.CURATED / "entities.toml", "rb") as f:
            cur = tomllib.load(f)
        sp = cur.get("speakers", {})
        self.aliases: dict[str, str] = {**cur.get("aliases", {}), **_book_aliases()}
        self.ignore = set(sp.get("ignore", []))
        self.generic_suffixes = tuple(sp.get("generic_suffixes", []))
        self.keep = set(sp.get("keep", []))
        self.doctor_names = set(sp.get("doctor", ["博士"]))
        self.mention_min = cur.get("mentions", {}).get("min_count", 2)
        self.single_char_names: dict[str, list[str]] = cur.get("linker", {}).get("single_char", {})

        self.chars: dict[str, Character] = {}
        self.op_by_name: dict[str, Character] = {}  # 含异格名
        self.op_by_id: dict[str, Character] = {}
        self.doctor = Character("博士", "doctor")
        self.chars["博士"] = self.doctor
        self._load_operators()

        self.powers: dict[str, Power] = {}
        self._load_powers(cur)

    # ------------------------------------------------------------------ 人物
    @staticmethod
    def _operator(c: dict) -> Character:
        return Character(
            c["name"], "operator", appellation=c.get("appellation") or "",
            profession=PROFESSIONS[c["profession"]],
            rarity=int(str(c.get("rarity", "0")).removeprefix("TIER_") or 0),
        )

    def _register_operator(self, cid: str, c: dict, ch: Character):
        """登记一个干员 id；同一人物的多个 id（含异格）的所属势力取并集。"""
        ch.char_ids.append(cid)
        ch.powers += [p for p in (c.get("nationId"), c.get("groupId"), c.get("teamId")) if p and p not in ch.powers]
        self.chars.setdefault(ch.name, ch)
        self.op_by_name[c["name"]] = ch
        self.op_by_id[cid] = ch

    def _load_operators(self):
        table = gamedata.excel("character_table")
        ops = [(cid, c) for cid, c in table.items()
               if cid.startswith("char_") and c.get("profession") in PROFESSIONS]
        for cid, c in ops:
            if not c.get("isSpChar"):
                self._register_operator(cid, c, self.op_by_name.get(c["name"]) or self._operator(c))
        # 异格干员：名字以本体名结尾的并入本体（假日威龙陈 → 陈），否则单独建页
        bases = sorted(self.op_by_name, key=len, reverse=True)
        for cid, c in ops:
            if not c.get("isSpChar"):
                continue
            base = next((b for b in bases if c["name"] != b and c["name"].endswith(b)), None)
            if base:
                ch = self.op_by_name[base]
                if c["name"] not in ch.aliases:
                    ch.aliases.append(c["name"])
            else:
                ch = self.op_by_name.get(c["name"]) or self._operator(c)
            self._register_operator(cid, c, ch)
        for alias, target in self.aliases.items():
            self._merge_alias(alias, target)

    def _merge_alias(self, alias: str, target: str):
        """别名和正名合成一个人物，名字用正名。两边都是干员时（电弧、Raidian）档案优先用正名的。"""
        a, t = self.op_by_name.get(alias), self.op_by_name.get(target)
        if a is None and t is None:
            return  # 两边都是 NPC，建人物时再记别名
        if t is None:  # 正名不是干员（送葬人=费德里科）：这个干员改用正名
            del self.chars[alias]
            a.name = target
            self.chars[target] = t = self.op_by_name[target] = a
        elif a is not None and a is not t:
            t.char_ids += a.char_ids
            t.powers += [p for p in a.powers if p not in t.powers]
            t.aliases += [n for n in a.aliases if n not in t.aliases]
            del self.chars[alias]
            for cid in a.char_ids:
                self.op_by_id[cid] = t
            for n, c in self.op_by_name.items():
                if c is a:
                    self.op_by_name[n] = t
        self.op_by_name[alias] = t
        if alias not in t.aliases:
            t.aliases.append(alias)

    def canonical(self, raw: str) -> str:
        name = raw.strip().strip("“”\"「」『』")
        # 「Mantra？」：身份未揭晓时的写法，和「Mantra」是同一个人
        return self.aliases.get(name) or self.aliases.get(name.rstrip("？?")) or name

    def is_generic(self, name: str) -> bool:
        if name in self.keep:
            return False
        return name.endswith(self.generic_suffixes) or bool(GENERIC_TAIL_RE.search(name))

    def resolve_speakers(self, raw: str) -> list[Character]:
        """说话人名可能是「A&B」多人同时说话，逐个解析，丢掉路人。"""
        return [ch for part in MULTI_SPEAKER_RE.split(raw) if (ch := self.resolve_speaker(part))]

    def resolve_speaker(self, raw: str) -> Character | None:
        """返回说话人对应的人物；路人、群体和未知身份返回 None。"""
        name = self.canonical(raw)
        if not name or name in self.ignore or UNKNOWN_RE.fullmatch(name):
            return None
        if name in self.doctor_names:
            return self.doctor
        if name in self.op_by_name:
            return self.op_by_name[name]
        if name.rstrip("？?") in self.op_by_name:  # 「阿米娅？」：身份未揭晓时的写法
            return self.op_by_name[name.rstrip("？?")]
        if self.is_generic(name) or name in self.power_names:  # 「整合运动」这类以势力名说话的
            return None
        ch = self.chars.get(name)
        if ch is None:
            ch = self.chars[name] = Character(name, "npc", aliases=[a for a, t in self.aliases.items() if t == name])
        return ch

    def resolve_portrait(self, base: str) -> Character | None:
        """char_148_nearl_1 → 依次尝试 char_148_nearl_1、char_148_nearl。"""
        parts = base.split("_")
        while len(parts) >= 3:
            ch = self.op_by_id.get("_".join(parts))
            if ch:
                return ch
            parts.pop()
        return None

    # ------------------------------------------------------------------ 地区/势力
    def _load_powers(self, cur: dict):
        extra_match = cur.get("mentions", {}).get("match", {})
        parents = {}
        for pid, t in gamedata.excel("handbook_team_table").items():
            if pid == "none":
                continue
            parent_name, _, short = t["powerName"].rpartition("-")
            kind = "region" if t.get("powerLevel") == 0 and pid != "rhodes" else "faction"
            self.powers[pid] = Power(pid, short, kind)
            parents[pid] = parent_name
        for kind, key in (("region", "regions"), ("faction", "factions")):
            for item in cur.get(key, []):
                pid = f"x_{item['name']}"
                self.powers[pid] = Power(pid, item["name"], kind)
                parents[pid] = item.get("parent", "")
        by_name = {p.name: p.id for p in self.powers.values()}
        full_name = {pid: t["powerName"] for pid, t in gamedata.excel("handbook_team_table").items()}
        by_name.update({v: k for k, v in full_name.items() if k in self.powers})
        for pid, pname in parents.items():
            self.powers[pid].parent = by_name.get(pname) if pname else None
        for p in self.powers.values():
            p.match = ([p.name] if len(p.name) >= 2 else []) + list(extra_match.get(p.name, []))
        self.power_names = {p.name for p in self.powers.values()} | set(full_name.values())

    def mentions(self, text: str) -> Counter:
        c = Counter()
        for p in self.powers.values():
            n = sum(text.count(m) for m in p.match)
            if n >= self.mention_min:
                c[p.id] = n
        return c

    def ancestors(self, pid: str) -> list[str]:
        out = []
        while (pid := self.powers[pid].parent) and pid not in out:
            out.append(pid)
        return out
