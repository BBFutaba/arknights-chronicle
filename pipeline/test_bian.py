"""两编的稿件格式、系年、归属和人物隔离；全部样稿只写进临时目录。

引文经 python -X utf8 -m pipeline.annals show ef_dlg_e0m0_0d5 1 2 核对。
需要先运行 pipeline.build，使用本地导出的真实分集和人物。
"""
import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import annals as a
from .config import ROOT


SID = "ef_dlg_e0m0_0d5"
ANCHOR = "你记不起这些名字，但悲伤令你胸口微痛"


class BianTests(unittest.TestCase):
    def setUp(self):
        # 在替换稿件根目录前加载真实引文/人物；不修改真实稿件。
        for fn in (a.characters, a.events, a.groups, a.powers, a.episode_index):
            fn()
        a.lines_of(SID)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / "manuscripts"
        self.src.mkdir()
        self.output = self.root / "json"
        self.output.mkdir()
        for name, value in (("SRC_DIR", self.src), ("OUT_DIR", self.root / "rendered"),
                            ("SITE_DATA", self.output), ("WU_DIR", self.src / "bowu")):
            p = patch.object(a, name, value)
            p.start()
            self.addCleanup(p.stop)
        a.aliases.cache_clear()
        a.sup_ids.cache_clear()
        self.addCleanup(a.aliases.cache_clear)
        self.addCleanup(a.sup_ids.cache_clear)
        self.write("塔卫二前纪/c.md", self.entry("失年", "塔不书"))
        self.write("塔卫二前纪/b.md", self.entry("旧事", "塔142", " 是岁:塔卫二"))
        self.write("塔卫二前纪/a.md", self.entry("历前", "塔前"))
        # 故意把是岁条写在春季条前，验证按日期重新排列。
        self.write("塔152/a.md", self.entry("岁事", "塔152", " 是岁:四号谷地") + self.entry("春事", "塔152-春"))
        self.write("列传-塔卫二.md", "@传 佩丽卡\n[[佩丽卡]]见[[泰拉·赫拉格]]。\n")
        self.write("纪事本末-塔卫二.md", "@事 迁行\n[[佩丽卡]]迁行。\n")
        self.write("列传索引-塔卫二.md", "佩丽卡 | 塔卫二 | 四号谷地 | 未详 | 终末地工业 | 未 | | 补:春事 | | 剧本\n")
        self.write("本末索引-塔卫二.md", "迁行 | 四号谷地 | 迁徙与营建 | 未了 |\n")

    def write(self, name, text):
        path = self.src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def entry(self, name, when, extra=""):
        return (f"@条 补:{name} 系:{when}{extra} 传:佩丽卡 事:迁行\n"
                "【纲】**迁行。**\n【目】[[佩丽卡]]行。\n"
                "【人物】[[佩丽卡]] · [[泰拉·赫拉格]]\n【原文】\n"
                f"@引 {SID} 1 「{ANCHOR}」\n【考异】日期据剧本。\n\n")

    def test_sample_build_and_order(self):
        self.assertIn(ANCHOR, a.plain(a.lines_of(SID)[0]))
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            result = a.build(quiet=True)
        self.assertEqual(result, 0, log.getvalue())
        data = json.loads((self.output / "annals.json").read_text(encoding="utf-8"))
        self.assertEqual([v["year"] for v in data["volumes"]], ["塔卫二前纪", "塔152"])
        self.assertEqual([v["title"] for v in data["volumes"]],
                         ["塔卫二前纪 · 塔罗斯历一五二年以前", "塔罗斯历一五二年"])
        self.assertEqual([s["label"] for s in data["volumes"][0]["sections"]],
                         ["塔罗斯历以前", "塔罗斯历一四二年", "年份不书"])
        es = [e for v in data["volumes"] for s in v["sections"] for d in s["days"] for e in d["entries"]]
        self.assertEqual([e["id"] for e in es], ["补:历前", "补:旧事", "补:失年", "补:春事", "补:岁事"])
        for e in es:
            self.assertEqual(e["bian"], a.TALOS)
            self.assertEqual(e["zhuan"], ["终末地·佩丽卡"])
            self.assertEqual(e["groups"][0]["people"], ["[[终末地·佩丽卡]]", "[[赫拉格]]"])
        self.assertEqual(data["liezhuan"][0]["name"], "终末地·佩丽卡")
        self.assertIn("[[终末地·佩丽卡]]", data["liezhuan"][0]["summary"][0])
        self.assertEqual(len(data["liezhuan"][0]["entries"]), 5)
        self.assertEqual(len(data["benmo"][0]["entries"]), 5)

    def test_wrong_volume_and_calendar(self):
        cases = [("塔卫二前纪/wrong.md", "塔152", "data/annals/塔152/"),
                 ("塔152/wrong.md", "塔151", "data/annals/塔卫二前纪/"),
                 ("塔153/wrong.md", "塔152", "data/annals/塔152/"),
                 ("1097/wrong.md", "塔152", "另一编"),
                 ("塔152/wrong.md", "1097", "另一编")]
        for path, year, message in cases:
            with self.subTest(path=path, year=year):
                probs = a.Problems()
                a.parse_entries(self.write(path, self.entry("错年", year)), probs)
                self.assertTrue(any(message in p for p in probs), probs)

    def test_terra_order_and_cross_bian_membership(self):
        self.write("不系年/a.md", "@条 补:泰拉 不系年 事:迁行\n【纲】**旧事。**\n【原文】\n"
                   f"@引 {SID} 1 「{ANCHOR}」\n【考异】日期未详。\n")
        probs = a.Problems()
        terra = a.load_volume("不系年", probs)
        talos = [e for vol in (a.TALOS_PRE, "塔152") for e in a.load_volume(vol, probs)]
        benmo = a.load_benmo(probs)
        zhuan = a.load_liezhuan(probs)
        self.assertFalse(probs, probs)
        self.assertEqual(a.volume_years(), ["不系年", "塔卫二前纪", "塔152"])
        self.assertEqual(sorted(talos + terra, key=a.chrono)[0].bian, a.TERRA)
        self.assertEqual(len(a.benmo_members(benmo[0], terra + talos)), 5)
        a.check_memberships(terra + talos, benmo, zhuan, probs)
        self.assertTrue(any("另一编" in p for p in probs), probs)
        # 反向混收以及列传混收也必须报错。
        other = {**benmo[0], "bian": a.TERRA}
        probs = a.Problems()
        a.check_memberships(talos, [other], [{**zhuan[0], "bian": a.TERRA}], probs)
        self.assertTrue(any("列传" in p and "另一编" in p for p in probs), probs)
        self.assertEqual(a.benmo_members(other, talos), [])

    def test_person_fallback_and_explicit_terra(self):
        probs = a.Problems()
        self.assertEqual(a.person_name("佩丽卡", a.TALOS, probs, "fixture"), "终末地·佩丽卡")
        self.assertEqual(a.person_name("泰拉·赫拉格", a.TALOS, probs, "fixture"), "赫拉格")
        self.assertFalse(probs.notes)
        self.assertEqual(a.person_name("赫拉格", a.TALOS, probs, "fixture"), "赫拉格")
        self.assertEqual(len(probs.notes), 1)
        self.assertEqual(a.person_links("[[佩丽卡]]", a.TERRA, probs, "fixture"), "[[佩丽卡]]")
        self.assertFalse(probs)

    def test_all_talos_date_forms_and_ties(self):
        for spec, expected in (("塔152", "152 年"), ("塔152-春", "152 年 春季"),
                               ("塔152-03", "152 年 3 月"), ("塔152-03-14", "152 年 3 月 14 日"),
                               ("塔152-02~04", "152 年 2 ~ 4 月")):
            self.assertEqual(a.parse_override(spec), (152, expected))
        self.write("塔卫二前纪/b.md", self.entry("同日甲", "塔142-03") + self.entry("同日乙", "塔142-03"))
        self.write("塔卫二前纪/d.md", self.entry("同日丙", "塔142-03"))
        probs = a.Problems()
        es = a.load_volume(a.TALOS_PRE, probs)
        self.assertFalse(probs, probs)
        self.assertEqual([e.anchor for e in es], ["补:历前", "补:同日甲", "补:同日乙", "补:同日丙", "补:失年"])

    def test_talos_benmo_has_no_prts_directives(self):
        for directive in ("@线 ef_main_e0", "@加 ev0001", "@减 ev0001"):
            self.write("纪事本末-塔卫二.md", f"@事 迁行\n{directive}\n")
            probs = a.Problems()
            a.load_benmo(probs)
            self.assertTrue(any("不适用" in p for p in probs), probs)

    def test_index_evidence_cannot_cross_bian(self):
        probs = a.Problems()
        a.zhuan_index(probs, {"补:泰拉"}, {"终末地·佩丽卡"}, bian=a.TALOS)
        self.assertTrue(any("条「补:春事」不存在" in p for p in probs), probs)

    @unittest.skipUnless(shutil.which("node"), "网页模块检查需要 Node.js")
    def test_web_rows_links_and_shelves(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(a.build(quiet=True), 0)
        script = r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const root = process.cwd(), sample = process.argv[1];
globalThis.fetch = async (name) => {
  let data = JSON.parse(fs.readFileSync(path.join(root, 'site', name), 'utf8'));
  if (name === 'data/annals.json') {
    const fixture = JSON.parse(fs.readFileSync(path.join(sample, 'annals.json'), 'utf8'));
    for (const key of ['volumes', 'benmo', 'liezhuan']) data[key].push(...fixture[key]);
  }
  return { ok: true, json: async () => data };
};
const moduleAt = (name) => import(pathToFileURL(path.join(root, 'site/js', name)).href);
const { D, loadAll } = await moduleAt('data.js');
await loadAll();
const { href, charChip } = await moduleAt('util.js');
const { inline } = await moduleAt('annals.js');
const talos = D.events.filter((e) => e.bian === '塔卫二编');
assert.deepEqual(talos.map((e) => e.id), ['补:历前', '补:旧事', '补:失年', '补:春事', '补:岁事']);
assert.equal(talos[3].head, '塔罗斯历一五二年');
assert(talos[3].chars.includes('终末地·佩丽卡'));
assert(talos[3].chars.includes('赫拉格'));
assert(D.events.some((e) => e.bian === '泰拉编'));
assert.equal(new URLSearchParams(href.event('补:春事').split('?')[1]).get('bian'), '塔卫二编');
const markup = inline('[[终末地·佩丽卡]]');
assert(markup.includes(href.char('终末地·佩丽卡')));
assert(markup.includes('game-mark'));
assert(!markup.includes('>终末地·佩丽卡<'));
assert(charChip('终末地·佩丽卡').includes('game-mark'));
// 最小 DOM 仅接收页面 HTML，验证索引筛选与直达详情；不代替浏览器视觉检查。
class Element {
  constructor() { this.nodes = new Map(); this.innerHTML = ''; this.style = { setProperty() {} };
    this.classList = { add() {}, remove() {}, toggle() {} }; this.childElementCount = 0; }
  querySelector(s) { if (!this.nodes.has(s)) this.nodes.set(s, new Element()); return this.nodes.get(s); }
  querySelectorAll() { return []; }
  addEventListener() {}
  scrollIntoView() {}
}
globalThis.document = { activeElement: null, addEventListener() {}, removeEventListener() {} };
globalThis.CSS = { escape: (s) => s };
for (const route of ['benmo', 'zhuan']) {
  const mod = await moduleAt(route + '.js'), el = new Element();
  const r = (bian, parts = []) => ({ parts, params: new URLSearchParams(bian ? { bian } : {}) });
  mod.mount(el, r());
  assert(!el.querySelector('.content').innerHTML.includes('塔卫二编'));
  mod.update(r('塔卫二编'));
  const content = el.querySelector('.content').innerHTML;
  assert(content.includes('塔卫二编'));
  assert(content.includes(route === 'benmo' ? '迁行' : '佩丽卡传'));
  mod.update(r('塔卫二编', [route === 'benmo' ? '迁行' : '终末地·佩丽卡']));
  assert(el.querySelector('.content').innerHTML.includes('补:春事'));
  mod.unmount();
}
const timeline = await moduleAt('timeline.js'), timelineEl = new Element();
const route = (bian, parts = []) => ({ parts, params: new URLSearchParams(bian ? { bian } : {}) });
const rowIds = () => [...timelineEl.querySelector('.tl-canvas').innerHTML.matchAll(/class="tl-row[^"]*" data-ev="([^"]*)"/g)].map((m) => m[1]);
timeline.mount(timelineEl, route());
assert(rowIds().length > 0);
assert(!rowIds().some((id) => talos.some((e) => e.id === id)));
timeline.update(route('塔卫二编'));
assert.deepEqual(rowIds(), talos.map((e) => e.id));
timeline.update(route('泰拉编'));
assert(!rowIds().includes('补:春事'));
timeline.unmount();
const annals = await moduleAt('annals.js'), annalsEl = new Element();
annals.mount(annalsEl, route(null, ['塔152']));
assert(annalsEl.querySelector('.content').innerHTML.includes('塔罗斯历一五二年'));
assert(annalsEl.querySelector('.an-side').innerHTML.includes('塔卫二编'));
annals.update(route(null, ['塔卫二前纪']));
assert(annalsEl.querySelector('.content').innerHTML.includes('塔罗斯历以前'));
annals.unmount();
D.annals.volumes = D.annals.volumes.filter((v) => v.bian === '泰拉编');
annals.mount(annalsEl, route(null, ['1097']));
assert(!annalsEl.querySelector('.an-side').innerHTML.includes('塔卫二编'));
annals.unmount();
console.log('Web smoke: timeline switch, volume routes, namespace links and bian shelves OK');
"""
        result = subprocess.run([shutil.which("node"), "--input-type=module",
                                 "-e", script, str(self.output)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
