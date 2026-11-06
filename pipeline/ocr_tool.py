"""本地 OCR：把扫描书、影片字幕、漫画变成可检索的文字，只留在 Raw Data/，不进 git。

用独立的 venv 运行（装了 rapidocr-onnxruntime），不依赖本项目其他模块：

    <ocr venv>/python pipeline/ocr_tool.py book
    <ocr venv>/python pipeline/ocr_tool.py video
    <ocr venv>/python pipeline/ocr_tool.py comic 0694 3116

OCR 有错字，只作检索和起草用。要引用原话时，回去看页面或帧的图片核对。
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "Raw Data"
BOOK_PDF = RAW / "01.明日方舟官方世界观设定集丨大地巡旅.pdf"
BOOK = RAW / "大地巡旅"
VIDEO = RAW / "视频"
COMIC = RAW / "漫画"
WORKERS = 10
_engine = None


def _init():
    global _engine
    # 这个版本的 rapidocr 不能传线程数。不限的话每个进程都开满全部核心，互相抢占，反而慢几十倍。
    import onnxruntime as ort
    plain_options = ort.SessionOptions

    def limited_options():
        options = plain_options()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        return options

    ort.SessionOptions = limited_options
    from rapidocr_onnxruntime import RapidOCR
    _engine = RapidOCR()


def _ocr(path):
    """返回 [(x, y, 文字, 置信度)]，按引擎给的阅读顺序。"""
    result, _ = _engine(str(path))
    return [(int(box[0][0]), int(box[0][1]), text.strip(), float(score)) for box, text, score in (result or []) if text.strip()]


def _pool():
    return cf.ProcessPoolExecutor(max_workers=WORKERS, initializer=_init)


# ---------------------------------------------------------------- 书


def book():
    pages = BOOK / "页"
    pages.mkdir(parents=True, exist_ok=True)
    if len(list(pages.glob("p-*.jpg"))) < 454:
        print("渲染页面", flush=True)
        subprocess.run(["pdftoppm", "-jpeg", "-jpegopt", "quality=85", "-r", "200", str(BOOK_PDF), str(pages / "p")],
                       check=True, stderr=subprocess.DEVNULL)
    files = sorted(pages.glob("p-*.jpg"))
    print(f"OCR {len(files)} 页", flush=True)
    with _pool() as pool:
        results = list(pool.map(_ocr, files, chunksize=2))
    out = []
    for path, lines in zip(files, results):
        number = int(path.stem.split("-")[1])
        # 书上印的页码是页边一个三位数
        printed = [t for x, y, t, s in lines if re.fullmatch(r"\d{3}", t) and (x < 200 or x > 1400)]
        head = f"=== PDF {number}" + (f" | 书页 {printed[0]}" if printed else "") + " ==="
        out.append(head)
        for x, y, text, score in lines:
            out.append(("[?] " if score < 0.7 else "") + text)
    (BOOK / "全文.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("完成", BOOK / "全文.txt", sum(len(re.findall(r"[一-鿿]", s)) for s in out), "字", flush=True)


# ---------------------------------------------------------------- 影片


def _seen_key(text):
    return re.sub(r"[\s，。、！？!?,.:：·…\-—_\"'“”‘’]", "", text)


def video():
    out_dir = VIDEO / "字幕"
    out_dir.mkdir(exist_ok=True)
    manifest = json.loads((VIDEO / ".video-download.json").read_text(encoding="utf-8"))
    url_of = {name: item["url"] for item in manifest.values() for name in item["files"]}
    pool = _pool()
    for mp4 in sorted(VIDEO.glob("*.mp4")):
        target = out_dir / (mp4.stem + ".txt")
        if target.exists():
            continue
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf", "fps=1", "-q:v", "2",
                            str(Path(tmp) / "f%05d.jpg")], check=True)
            frames = sorted(Path(tmp).glob("f*.jpg"))
            results = list(pool.map(_ocr, frames, chunksize=4))
        lines, last_seen = [f"# {mp4.stem}", f"# 来源 {url_of.get(mp4.name, '')}"], {}
        for second, found in enumerate(results):
            for x, y, text, score in found:
                if score < 0.6 or "bilibili" in text.lower():
                    continue
                key = _seen_key(text)
                if len(key) < 2:
                    continue
                # 字幕和标签常停留好几秒，只记第一次出现
                if key in last_seen and second - last_seen[key] <= 8:
                    last_seen[key] = second
                    continue
                last_seen[key] = second
                lines.append(f"{second // 60:02d}:{second % 60:02d}  {text}")
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(mp4.stem, len(frames), "秒", len(lines) - 2, "行", flush=True)
    pool.shutdown()


# ---------------------------------------------------------------- 漫画


def comic(cids):
    pool = _pool()
    for cid in cids:
        folders = [p for p in COMIC.iterdir() if p.is_dir() and p.name.startswith(f"{cid} ")]
        if not folders:
            print("未下载", cid, flush=True)
            continue
        folder = folders[0]
        files = sorted(p for ep in sorted(d for d in folder.iterdir() if d.is_dir()) for p in sorted(ep.glob("p*.jpg")))
        results = list(pool.map(_ocr, files, chunksize=4))
        out = []
        for path, found in zip(files, results):
            out.append(f"### {path.parent.name} {path.stem}")
            for x, y, text, score in found:
                if "HYPERGRYPH" in text.upper() or score < 0.5:
                    continue
                out.append(("[?] " if score < 0.7 else "") + text)
        (folder / "ocr.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
        print(folder.name, len(files), "页", flush=True)
    pool.shutdown()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("what", choices=["book", "video", "comic"])
    parser.add_argument("cids", nargs="*")
    args = parser.parse_args()
    if args.what == "book":
        book()
    elif args.what == "video":
        video()
    else:
        comic(args.cids)


if __name__ == "__main__":
    main()
