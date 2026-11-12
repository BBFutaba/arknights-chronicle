"""终末地接入的关键约束；不需要本机客户端或第三方库。"""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import config, endfield, gamedata
from .entities import Character
from .script import Line, Script


class EndfieldTests(unittest.TestCase):
    def test_speaker_rules(self):
        cases = [
            ("工团成员{e1m2_员工锤}", "工团成员", "", "内部编号"),
            ("不幸的干员{m01lv01tape-遇袭干员A}", "不幸的干员", "", "内部编号"),
            ("被救的工团成员{sm1|3-工团成员B}", "被救的工团成员", "", "内部编号"),
            ("被困的工人{肖娜}", "肖娜", "", "前为泛称"),
            ("？？？{亨德森}", "亨德森", "", "前为泛称"),
            ("无线电通信{阿奎多}", "阿奎多", "", "前为泛称"),
            ("录音{佩吉}", "佩吉", "", "前为泛称"),
            ("方明{焦虑的市民}", "方明", "", "后为泛称"),
            ("温柔的女声{萨米的声音}", "温柔的女声", "", "后为泛称"),
            ("老雪祀{婴儿老雪祀}", "老雪祀", "", "后为泛称"),
            ("老俞{俞秀丽}", "俞秀丽", "老俞", "两侧姓名"),
            ("峰{沈峤峨}", "沈峤峨", "峰", "两侧姓名"),
            ("莱万汀&管理员{莱万汀、管理员}", "莱万汀&管理员", "", "群体或扮演"),
            ("伊冯{伊冯}", "伊冯", "", "同名"),
            ("{管理员}", "管理员", "", "原称"),
        ]
        for original, name, alias, rule in cases:
            with self.subTest(original=original):
                result = endfield.speaker_name(original)
                self.assertEqual(result[:2], (name, alias))
                self.assertTrue(result[2].startswith(rule))

    def test_speaker_changes_preserve_shared_lines_and_namespace(self):
        shared = Line("dialogue", "不要改变台词", "老俞{俞秀丽")
        original = [shared, Line("narration", "旁白"), Line("decision", options=["继续"])]
        reg = SimpleNamespace(chars={"俞秀丽": Character("俞秀丽", "npc")})
        def episode():
            return SimpleNamespace(script=Script(original), synopsis="",
                                   speaker_aliases={"老俞": "俞秀丽"})
        a, b = episode(), episode()
        for ep in (a, b):
            d = endfield.analyze_episode(ep, reg)
            self.assertEqual(len(d.script.lines), len(original))
            self.assertEqual([(x.kind, x.text, x.options) for x in d.script.lines],
                             [(x.kind, x.text, x.options) for x in original])
            self.assertEqual(d.script.lines[0].speaker, "俞秀丽")
            self.assertEqual(sum(ep.speaker_audit.values()), 1)
        self.assertEqual(shared.speaker, "老俞{俞秀丽")
        self.assertEqual(reg.chars["终末地·俞秀丽"].aliases, ["终末地·老俞"])
        self.assertEqual(reg.chars["俞秀丽"].aliases, [])

    def test_task_titles_number_across_media_without_changing_ids(self):
        loader = object.__new__(endfield.Loader)
        loader.groups, loader.episode_ids = {}, set()
        loader.missions = {"e0m2": {"missionName": "进程·复苏"}}
        loader.mission_groups, loader.mission_rank = {}, {}
        loader.dialogs, loader.options, loader.used_dialogs, loader.used_options = {}, {}, set(), set()
        loader.audit = {"excluded": [], "uncertain": [], "missing": []}
        group = loader.group("fixture", "测试", "主线")
        loader.group_for = lambda _: (group, "e0m2")
        for key, medium in [("dlg_e0m2_2", "剧情"), ("dlg_e0m2_1", "剧情"),
                            ("radio_e0m2_9", "无线电"), ("sns_e0m2_4", "讯息")]:
            loader.add(group, key, key, [Line("narration", key)], avg=medium)
        ids = {ep.story_id for ep in group.episodes}
        for method in ("setup_groups", "load_dialogs", "load_radio", "load_sns", "load_narrative", "load_subtitles"):
            setattr(loader, method, lambda: None)
        with patch("builtins.print"):
            loader.load()
        self.assertEqual({ep.story_id for ep in group.episodes}, ids)
        self.assertEqual([ep.title for ep in group.episodes],
                         ["进程·复苏 · 对话 1", "进程·复苏 · 对话 2", "进程·复苏 · 无线电 3", "进程·复苏 · 讯息 4"])
        self.assertTrue(all(not ep.code for ep in group.episodes))

    def test_text_keeps_both_genders(self):
        self.assertEqual(endfield.clean("<color=red>{F}她\n{M}他</color> {@nickname}"),
                         "〔女〕她 〔男〕他 管理员")

    def test_player_glossary_and_images_are_readable(self):
        text = '{player}：<entry=narrativeNote_1>枢壤仪 <image="sns_emoji_004"> <image>record.png</image>'
        self.assertEqual(endfield.clean(text), "管理员：枢壤仪 〔表情：sns_emoji_004〕 〔图片：record.png〕")

    def test_graph_order_is_not_dialogue_number(self):
        loader = object.__new__(endfield.Loader)
        loader.dialogs = {
            "dlg_009": {"dialogText": "先说"},
            "dlg_001": {"dialogText": "后说"},
        }
        loader.options = {"opt": {"optionText": "继续"}}
        loader.used_dialogs, loader.used_options, loader.used_black = set(), set(), set()
        loader.i18n, loader.texts = {}, {}
        loader.audit = {"missing": [], "excluded": []}
        data = {"nodes": [
            {"$id": "start", "$type": "Start"},
            {"$id": "last", "$type": "Trunk", "_trunkId": "dlg_001"},
            {"$id": "first", "$type": "Trunk", "_trunkId": "dlg_009"},
            {"$id": "choice", "$type": "Option", "_normalOptions": [{"_optionId": "opt"}]},
        ], "connections": [
            {"_sourceNode": {"$ref": a}, "_targetNode": {"$ref": b}}
            for a, b in [("start", "first"), ("first", "choice"), ("choice", "last"), ("last", "first")]
        ]}
        lines = loader.tree(data, "fixture")
        self.assertEqual([l.text for l in lines if l.kind == "narration"], ["先说", "后说"])
        self.assertEqual([l.options for l in lines if l.kind == "decision"], [["继续"]])
        self.assertTrue(any(l.kind == "branch" and "first" in l.text for l in lines))

    def test_namespaces_and_player_choices(self):
        original = Character("安德烈", "npc")
        reg = SimpleNamespace(chars={"安德烈": original, "博士": Character("博士", "doctor")})
        ep = SimpleNamespace(script=Script([Line("dialogue", "你好", "安德烈"),
                                           Line("decision", options=["回答"])]), synopsis="")
        d = endfield.analyze_episode(ep, reg)
        self.assertIs(reg.chars["安德烈"], original)
        self.assertEqual(dict(d.lines), {"终末地·安德烈": 1, "终末地·管理员": 1})
        self.assertFalse(d.mentions)

    def test_timeline_uses_time_and_standalone_options(self):
        loader = object.__new__(endfield.Loader)
        asset = "dialog/timeline/dlgtl_fixture/playable/dlgtl_fixture_actor.playable"
        loader.assets = {asset: "fixture"}
        loader.timeline_cache = {}
        loader.audit = {"missing": [], "timelines": {}}
        loader.options = {"choice": {"optionText": "选择"}}
        loader.i18n, loader.texts, loader.used_options = {}, {}, set()
        loader.dialog = lambda key: [Line("narration", key)]
        objects = [
            (Path("0_1_MonoBehaviour.json"), {"_trunkId": "last", "startTime": 9}),
            (Path("0_2_MonoBehaviour.json"), {"_trunkId": "first", "startTime": 1}),
            (Path("0_3_MonoBehaviour.json"), {"options": [{"_optionId": "choice", "logicId": 7}]}),
            (Path("0_4_MonoBehaviour.json"), {"m_Clips": [{"m_Asset": {"m_FileID": 0, "m_PathID": 3}, "m_Start": 4}]}),
        ]
        loader.objects = lambda _: iter(objects)
        result = loader.timeline("dlgtl_fixture")
        visible = [l for l in result if l.kind != "branch"]
        self.assertEqual([l.kind for l in visible], ["narration", "decision", "narration"])
        self.assertEqual([visible[0].text, visible[2].text], ["first", "last"])
        self.assertEqual(visible[1].options, ["选择"])

    def test_optional_local_data(self):
        with patch.object(config, "ENDFIELD", config.ROOT / "__missing_endfield_client__"):
            self.assertEqual(endfield.load(), ({}, {}))

    def test_main_acts_use_numeric_order(self):
        groups = [endfield.Group(f"ef_main_e{n}", str(n), "终末地·主线", None) for n in [10, 2, 1]]
        self.assertEqual([g.id for g in sorted(groups, key=gamedata.sort_key)],
                         ["ef_main_e1", "ef_main_e2", "ef_main_e10"])


if __name__ == "__main__":
    unittest.main()
