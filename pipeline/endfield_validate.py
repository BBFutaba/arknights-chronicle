"""终末地接入验收：与事前备份逐项比较，并导出可审阅的组清单。

只读客户端/备份，只写 site/data/endfield-validation.json 与 endfield-report.md。
不会调用 git、网络、publish 或 deploy。quotes/check 仍单独用 annals 命令验收。
"""
import json
from pathlib import Path

from . import config
from .site import dump


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def differences(before, after, path=""):
    if type(before) is not type(after):
        yield path + ": 类型变化"
    elif isinstance(before, dict):
        for key in sorted(before.keys() | after.keys()):
            if key not in before:
                yield f"{path}/{key}: 新增"
            elif key not in after:
                yield f"{path}/{key}: 缺失"
            else:
                yield from differences(before[key], after[key], f"{path}/{key}")
    elif isinstance(before, list):
        if len(before) != len(after):
            yield f"{path}: 长度 {len(before)} → {len(after)}"
        for i, (a, b) in enumerate(zip(before, after)):
            yield from differences(a, b, f"{path}/{i}")
    elif before != after:
        yield f"{path}: {str(before)[:80]!r} → {str(after)[:80]!r}"


def main():
    backup = config.ENDFIELD.parent.parent / "_build_before/site_data"
    if not backup.exists():
        raise SystemExit("缺少事前备份，不能验证旧数据不变")
    site = config.SITE_DATA
    groups = read(site / "groups.json")
    chars = read(site / "characters.json")
    old_chars = read(backup / "characters.json")
    ef_groups = [g for g in groups if g.get("game") == "endfield"]
    old_groups = {g["id"]: g for g in read(backup / "groups.json")}
    new_old_groups = {g["id"]: g for g in groups if not g["id"].startswith("ef_")}
    diffs = list(differences(old_groups, new_old_groups, "groups.json"))
    diffs += list(differences(old_chars, {n: c for n, c in chars.items() if c.get("game") != "endfield"}, "characters.json"))
    changed_files = []
    for p in sorted(backup.rglob("*")):
        if not p.is_file() or p.name in {"groups.json", "characters.json", "meta.json", "events.json"}:
            continue
        rel = p.relative_to(backup)
        q = site / rel
        if not q.exists():
            diffs.append(f"{rel}: 文件缺失")
        elif p.read_bytes() != q.read_bytes():
            changed_files.append(rel.as_posix())
            if p.suffix == ".json":
                diffs.extend(differences(read(p), read(q), rel.as_posix()))
            else:
                diffs.append(f"{rel}: 字节不同")
    events = read(site / "events.json")
    events["threads"] = {k: v for k, v in events["threads"].items() if not k.startswith("ef_")}
    diffs += list(differences(read(backup / "events.json"), events, "events.json"))
    before_meta, after_meta = read(backup / "meta.json"), read(site / "meta.json")
    allowed_meta = list(differences(before_meta, after_meta, "meta.json"))
    old_speakers, ef_speakers = set(), set()
    for p in (backup / "stories").glob("*.json"):
        for ep in read(p).values():
            old_speakers.update(l[1] for l in ep["lines"] if l[0] == "d" and l[1])
    rows, schema_errors = [], []
    for g in ef_groups:
        stories = read(site / "stories" / (g["id"] + ".json"))
        count = 0
        for ep in g["episodes"]:
            sid = ep["id"]
            if not sid.startswith("ef_"):
                schema_errors.append(sid)
            for line in stories[sid]["lines"]:
                if len(line) != 3 or line[0] not in {"d", "n", "c", "b", "s"}:
                    schema_errors.append(sid + ": bad line")
                kind, speaker, text = line
                if kind in ("d", "n"):
                    count += len(text)
                elif kind == "c":
                    count += sum(len(o) for o in text)
                if kind == "d" and speaker:
                    ef_speakers.add(speaker.removeprefix("终末地·"))
                    if speaker in old_chars:
                        schema_errors.append(sid + ": speaker links to Arknights " + speaker)
            for name, _ in ep["chars"]:
                if not name.startswith("终末地·") or chars[name].get("game") != "endfield":
                    schema_errors.append(sid + ": bad character " + name)
        rows.append([g["id"], g["category"], g["name"], len(g["episodes"]), count])
    for name, c in chars.items():
        if c.get("game") == "endfield":
            if any(chars[n].get("game") != "endfield" for n, _ in c["co"]):
                schema_errors.append(name + ": cross-game co-occurrence")
    collisions = sorted(old_speakers & ef_speakers)
    total = [len(rows), sum(r[3] for r in rows), sum(r[4] for r in rows)]
    result = {"groups": rows, "total": total, "speaker_collisions": collisions,
              "arknights_differences": diffs, "changed_old_files": changed_files,
              "metadata_changes": allowed_meta, "schema_errors": schema_errors}
    dump(site / "endfield-validation.json", result)
    report = ["# 终末地接入数据验收", "", "字符数为台词、旁白、选项的 Python len 之和；不计分支/跳转说明。", "",
              "| 组 id | 分类 | 名称 | 分集数 | 字符数 |", "|---|---|---|---:|---:|"]
    report += ["| " + " | ".join(str(x).replace("|", "\\|") for x in r) + " |" for r in rows]
    report += ["", f"合计：{total[0]} 组，{total[1]} 集，{total[2]:,} 字符。", "", "## 同名说话人", "",
               "、".join(collisions) or "无", "", "所有终末地人物键及导出的具名说话人均加「终末地·」；不继承明日方舟别名和势力。", "",
               "## 旧数据逐项差异", ""]
    report += diffs or ["无。旧组、旧人物、旧剧本、年表事件和书稿生成物完全相同。"]
    report += ["", "## 构建元数据变化（预期）", ""] + allowed_meta
    report += ["", "## 顺序与覆盖限制", "",
               "官方 episode 的 missionIdList 定义章/幕内任务顺序；对话树连接定义场内分支；演员轨 startTime 定义时间轴台词顺序；无线电 index 与 SNS 消息连接分别定义组内顺序。",
               "任务的 mainPathQuests、prevQuestIdList 和 flowIndex 保存在 endfield-audit.json/mission_structure。未还原所有场景触发器，目录中的自然编号不能充当完整播放顺序；对话、无线电、SNS 分集保留独立。",
               "dung01、indie 等没有取得统一官方上级名称的地图键原样保留，不编造区域名称。",
               "字幕和未定位黑屏文本单列，字幕文本键顺序尚未以轨道时间验证。具体分集和源路径见 endfield-audit.json/uncertain；缺失引用与未接入类别分别见 missing、excluded。",
               "时间轴选项保留 logicId/optionIndex，但尚未恢复所有跳转；按 startTime 展示的是候选轨道全集，部分片段互斥，不能作为一次玩家实机播放路径。",
               "未连入入口的对话节点、未解析对话/选项、未被 PRTS/终端引用的 RichContent、物品混合功能 desc 均未硬塞；音视频本体及未解析的字幕轨不作正文。",
               "Dialog2DTextTable 的 34 条文本卡片尚未绑定到具体演出，未单独收录；战斗呼喊、环境触发配置、活动 UI/教程/预设聊天及数值玩法表不直接当作叙事。其 CN 字符串仍可用 rawfind 检索。",
               "网页通过组名筛选‘终末地’或 #/story/<组>/<分集> 访问；前端分类按钮和‘博士的选项’为现有硬编码，受本轮禁止修改 site/js 限制而保留。",
               "公开版 publish.py 的 ignore_patterns('stories') 排除所有游戏的剧本目录；新增审计文件仅有 ID、来源和结构，无全文。没有运行 publish/deploy。"]
    report += ["", "## 修改文件及原因", "",
               "新增 pipeline/endfield.py（标准库适配器）、pipeline/endfield_validate.py（旧数据比较与本报告）、pipeline/test_endfield.py（顺序、选项、隔离和缺数据测试）。",
               "修改 config.py（本机可选来源路径）、build.py（合并终末地并保留离线构建）、gamedata.py（兼容新增分类排序）、site.py（游戏字段、来源与人物键）、linker.py（旧年表不匹配终末地人物）、annals.py（rawfind、选项说话人和分支显示）。",
               "build.py 的 data_version 沿用现有 meta.json，不执行 git；它不会自动检测明日方舟来源版本变化。默认只写 site/data，data/structured/episodes.jsonl 改为显式 --structured 写入，以遵守本轮允许的写入范围。",
               "未修改 entities.toml、data/annals、site/js 或客户端存档；事前副本与验收样例只在 Raw Data/终末地/_build_before。"]
    report += ["", "## 可回查的顺序证据", ""]
    for relative, anchor in [
        ("ab_text/Bundles/Windows/main/c1286e60e0fd0544030d52c9.ab/0_3294152773492880582_MonoBehaviour.json", '"missionIdList"'),
        ("ab_text/Bundles/Windows/main/48640ea3fcd7f637f67463de.ab/0_-4721928068648621067_dlg_e1m1_1.json", '"connections"'),
        ("Json/MissionRuntimeAsset/e1m1.json", '"mainPathQuests"'),
    ]:
        p = config.ENDFIELD / relative
        if p.exists():
            no = next((i for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if anchor in line), 0)
            report.append(f"- `{p.relative_to(config.ROOT).as_posix()}:{no}`：{anchor}")
    for fname, needles in [("endfield.py", ["def load_dialogs", "def load_subtitles", "def timeline"]),
                            ("publish.py", ['ignore=shutil.ignore_patterns("stories")'])]:
        for no, line in enumerate((config.ROOT / "pipeline" / fname).read_text(encoding="utf-8").splitlines(), 1):
            if any(needle in line for needle in needles):
                report.append(f"- `pipeline/{fname}:{no}`：{line.strip()}")
    log = backup.parent / "build_after.log"
    if log.exists():
        lines = log.read_text(encoding="utf-8").splitlines()
        errors = [line for line in lines if line.lstrip().startswith("!")]
        report += ["", "## 构建命令输出末尾", "", "```text", *lines[-5:], "```",
                   f"! 开头的报错：{len(errors)}。"]
    quote_before, quote_after = backup.parent / "quotes_before.txt", backup.parent / "quotes_after_command.txt"
    if quote_before.exists() and quote_after.exists():
        b, a = quote_before.read_text(encoding="utf-8"), quote_after.read_text(encoding="utf-8")
        report += ["", f"短引找不到：改前 {len(b.splitlines())}，改后 {len(a.splitlines())}；未找到的逐项清单{'完全一致' if a == b else '有差异'}。"]
    (site / "endfield-report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"终末地：{total[0]} 组，{total[1]} 集，{total[2]:,} 字符")
    print(f"同名说话人 {len(collisions)}；明日方舟差异 {len(diffs)}；结构/命名空间错误 {len(schema_errors)}")
    print("完整清单与逐项差异：site/data/endfield-report.md")
    if schema_errors or diffs:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
