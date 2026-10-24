"""在一段文字（年表事件描述）里找出提到的人物、地区和势力。

按名字最长优先匹配，避免「推进之王维娜」先被拆成短名字。单个汉字的名字（陈、年、夕……）
太容易误配，只匹配 entities.toml 的 [linker.single_char] 里列出的，并跳过排除词；
拉丁字母的名字（W、Logos）要求前后不是字母数字。
同一个写法同时是人物名和地名时，干员优先，其次地区/势力，最后 NPC。
"""
import re
from collections import Counter

from .entities import Registry

NPC_MIN_LINES = 3  # 台词太少的 NPC 名字多半是临时角色，不参与匹配


class Linker:
    def __init__(self, reg: Registry, char_lines: Counter):
        table: dict[str, tuple[str, str]] = {}

        def add(name: str, kind: str, key: str):
            if name and name not in table and (len(name) >= 2 or name.isascii()):
                table[name] = (kind, key)

        for name, ch in reg.op_by_name.items():
            add(name, "char", ch.name)
        for alias, target in reg.aliases.items():
            if target in reg.chars:
                add(alias, "char", target)
        for p in reg.powers.values():
            for m in p.match:
                add(m, "power", p.id)
        for ch in reg.chars.values():
            if ch.kind == "npc" and char_lines[ch.name] >= NPC_MIN_LINES:
                add(ch.name, "char", ch.name)
        add("博士", "char", reg.doctor.name)

        def pattern(name: str) -> str:
            esc = re.escape(name)
            return rf"(?<![A-Za-z0-9]){esc}(?![A-Za-z0-9])" if name.isascii() else esc

        self.table = table
        self.regex = re.compile("|".join(pattern(n) for n in sorted(table, key=len, reverse=True)))
        self.single = {c: (reg.op_by_name[c].name, excl) for c, excl in reg.single_char_names.items()
                       if c in reg.op_by_name}

    def find(self, text: str) -> tuple[list[str], list[str]]:
        chars, powers = {}, {}
        covered = set()
        for m in self.regex.finditer(text):
            kind, key = self.table[m.group(0)]
            (chars if kind == "char" else powers)[key] = None
            covered.update(range(m.start(), m.end()))
        for c, (name, excluded) in self.single.items():
            for w in excluded:
                covered.update(i for m in re.finditer(re.escape(w), text) for i in range(m.start(), m.end()))
            if any(ch == c and i not in covered for i, ch in enumerate(text)):
                chars[name] = None
        return list(chars), list(powers)
