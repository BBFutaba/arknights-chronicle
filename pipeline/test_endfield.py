"""终末地接入的关键约束；不需要本机客户端或第三方库。"""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import config, endfield, gamedata
from .entities import Character
from .script import Line, Script


class EndfieldTests(unittest.TestCase):
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
