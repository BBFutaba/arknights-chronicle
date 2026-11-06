r"""本地 OCR（GPU 版）：命令行、输出路径和文件格式都与 ocr_tool.py 相同，识别改走显卡。

用 GPU 专用 venv 运行（见下面“安装”），在项目根目录执行：

    <gpu venv>/python pipeline/ocr_gpu.py book
    <gpu venv>/python pipeline/ocr_gpu.py video
    <gpu venv>/python pipeline/ocr_gpu.py comic 0694 3116
    <gpu venv>/python pipeline/ocr_gpu.py records      《泰拉记事》，长图先切片

与 ocr_tool.py 的区别：
  - 结果已存在就跳过（book 的全文.txt、video 的字幕/<片名>.txt、comic 的 ocr.txt）；加 --force 才重做。
  - 模型是 PP-OCRv6 small（rapidocr 3.x 自带，不用联网下载），错字比 ocr_tool.py 用的 PP-OCR v3 少得多，
    --model 可换 v5server / v5mobile / v6medium。
  - 单进程，CPU 只占 2~4 个核心，不再开十个进程。
  - 竖排对白按日漫习惯把同一气泡里的竖列从右到左排好（ocr_tool.py 是从左到右）。
  - 试跑选项：--raw 换 Raw Data 位置，--limit 只处理前 N 页/片。

两种显卡后端，装哪个 venv 就用哪个（--provider auto）：
  DirectML（推荐，只要 ~0.4 GB，不依赖 CUDA 版本；onnxruntime 的 DirectML 不支持多线程并发，所以单线程）：
    py -3.13 -m venv %LOCALAPPDATA%\chronicle-ocr-gpu\venv-dml
    <venv-dml>/python -m pip install onnxruntime-directml==1.24.4 rapidocr pillow
  CUDA（快约 1.5 倍，约 2.6 GB，要 CUDA 13 的 cuBLAS/cuDNN 轮子；默认 3 个线程共用一块卡）：
    py -3.13 -m venv %LOCALAPPDATA%\chronicle-ocr-gpu\venv
    <venv>/python -m pip install "onnxruntime-gpu[cuda,cudnn]==1.31.1" rapidocr pillow

OCR 有错字，只作检索和起草用。要引用原话时，回去看页面或帧的图片核对。
"""
import argparse
import concurrent.futures as cf
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "Raw Data"
BOOK_PDF_NAME = "01.明日方舟官方世界观设定集丨大地巡旅.pdf"
BOOK_PAGES = 454
THREADS = 1  # main() 按后端改：CUDA 3，DirectML 只能 1
MODELS = {  # 名字: (OCRVersion, ModelType)
    "v6small": ("PP-OCRv6", "small"),
    "v6medium": ("PP-OCRv6", "medium"),
    "v5server": ("PP-OCRv5", "server"),
    "v5mobile": ("PP-OCRv5", "mobile"),
}
_engine = None


def _paths():
    return RAW / BOOK_PDF_NAME, RAW / "大地巡旅", RAW / "视频", RAW / "漫画"


def _init(model, provider, gpu_mem_gb):
    global _engine
    import onnxruntime as ort
    ort.set_default_logger_severity(3)  # 去掉 “No registered plugin EP device” 之类的无害警告
    have = ort.get_available_providers()
    if provider == "auto":
        provider = "cuda" if "CUDAExecutionProvider" in have else "dml" if "DmlExecutionProvider" in have else "none"
    missing = (provider == "cuda" and "CUDAExecutionProvider" not in have) or               (provider == "dml" and "DmlExecutionProvider" not in have)
    if provider == "none" or missing:
        sys.exit(f"onnxruntime 里没有可用的 GPU 提供程序（有：{have}）。要用 onnxruntime-gpu 或 onnxruntime-directml，不能是普通的 onnxruntime。")
    if provider == "cuda" and hasattr(ort, "preload_dlls"):
        ort.preload_dlls()  # pip 装的 CUDA 13 / cuDNN 库不在系统 PATH 里，要先加载，否则静默退回 CPU
    from rapidocr import RapidOCR
    from rapidocr.utils.typings import ModelType, OCRVersion
    version, kind = MODELS[model]
    params = {
        "Global.log_level": "error",  # 没字的帧会逐帧打印 “text detection result is empty”，太吵
        "Det.ocr_version": OCRVersion(version), "Det.model_type": ModelType(kind),
        "Rec.ocr_version": OCRVersion(version), "Rec.model_type": ModelType(kind),
        "EngineConfig.onnxruntime.intra_op_num_threads": 2,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    }
    if provider == "cuda":
        params.update({
            "EngineConfig.onnxruntime.use_cuda": True,
            # 默认的 EXHAUSTIVE 会对每个新输入尺寸重新搜索卷积算法，页面和文字行尺寸都在变，会很慢
            "EngineConfig.onnxruntime.cuda_ep_cfg.cudnn_conv_algo_search": "HEURISTIC",
            "EngineConfig.onnxruntime.cuda_ep_cfg.gpu_mem_limit": int(gpu_mem_gb * (1 << 30)),
        })
    else:
        # 不要设 dml_ep_cfg：rapidocr 3.10 把它原样（omegaconf 对象）传给 onnxruntime，会报错并悄悄退回 CPU
        params["EngineConfig.onnxruntime.use_dml"] = True
    _engine = RapidOCR(params=params)
    # 引擎若没能真的用上 GPU（缺 DLL、参数出错之类）会悄悄退回 CPU，这里查一下
    want = "CUDAExecutionProvider" if provider == "cuda" else "DmlExecutionProvider"
    session = _engine._load_det_model().session.session  # 模型是第一次用才载入，这里顺便预载
    if session.get_providers()[0] != want:
        sys.exit(f"检测模型没跑在 GPU 上：{session.get_providers()}")
    print(f"OCR 引擎：{model}，{provider}", flush=True)
    return provider


def _ocr(path):
    """返回 [(x, y, 文字, 置信度)]，顺序与 ocr_tool.py 一致（引擎的阅读顺序）。"""
    return [(x0, y0, text, score) for x0, y0, x1, y1, text, score in _ocr_boxes(path)]


def _ocr_boxes(path):
    r = _engine(str(path))
    if r.txts is None:
        return []
    found = []
    for box, text, score in zip(r.boxes, r.txts, r.scores):
        text = text.strip()
        if text:
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            found.append((int(box[0][0]), int(box[0][1]), int(max(xs)), int(max(ys)), text, float(score)))
    return found


def _ocr_all(files, chunk=None):
    """几个线程共用一个引擎：一张图在 CPU 上做前后处理时，另一张在 GPU 上跑。"""
    with cf.ThreadPoolExecutor(max_workers=THREADS) as pool:
        return list(pool.map(_ocr, files))


# ---------------------------------------------------------------- 书


def book(force=False, limit=0):
    pdf, book_dir, _, _ = _paths()
    target = book_dir / "全文.txt"
    if target.exists() and not force:
        print("已有", target, "，跳过（--force 重做）", flush=True)
        return
    pages = book_dir / "页"
    pages.mkdir(parents=True, exist_ok=True)
    need = limit or BOOK_PAGES
    if len(list(pages.glob("p-*.jpg"))) < need:
        print("渲染页面", flush=True)
        # pdftoppm 单进程渲染 454 页约 2 分钟，分 4 段并行约 40 秒
        step = -(-need // 4)
        procs = [subprocess.Popen(["pdftoppm", "-jpeg", "-jpegopt", "quality=85", "-r", "200", "-f", str(first),
                                   "-l", str(min(first + step - 1, need)), str(pdf), str(pages / "p")],
                                  stderr=subprocess.DEVNULL) for first in range(1, need + 1, step)]
        if any([proc.wait() for proc in procs]):
            sys.exit("pdftoppm 渲染失败")
    files = sorted(pages.glob("p-*.jpg"))
    if limit:
        files = files[:limit]
    print(f"OCR {len(files)} 页", flush=True)
    results = _ocr_all(files)
    out = []
    for path, lines in zip(files, results):
        number = int(path.stem.split("-")[1])
        # 书上印的页码是页边一个三位数
        printed = [t for x, y, t, s in lines if re.fullmatch(r"\d{3}", t) and (x < 200 or x > 1400)]
        head = f"=== PDF {number}" + (f" | 书页 {printed[0]}" if printed else "") + " ==="
        out.append(head)
        for x, y, text, score in lines:
            out.append(("[?] " if score < 0.7 else "") + text)
    target.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("完成", target, sum(len(re.findall(r"[一-鿿]", s)) for s in out), "字", flush=True)


# ---------------------------------------------------------------- 影片


def _seen_key(text):
    return re.sub(r"[\s，。、！？!?,.:：·…\-—_\"'“”‘’]", "", text)


def video(force=False, limit=0):
    _, _, video_dir, _ = _paths()
    out_dir = video_dir / "字幕"
    out_dir.mkdir(exist_ok=True)
    manifest = json.loads((video_dir / ".video-download.json").read_text(encoding="utf-8"))
    url_of = {name: item["url"] for item in manifest.values() for name in item["files"]}
    done = 0
    for mp4 in sorted(video_dir.glob("*.mp4")):
        target = out_dir / (mp4.stem + ".txt")
        if target.exists() and not force:
            continue
        if limit and done >= limit:
            break
        done += 1
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-threads", "2", "-i", str(mp4), "-vf", "fps=1",
                            "-q:v", "2", str(Path(tmp) / "f%05d.jpg")], check=True)
            frames = sorted(Path(tmp).glob("f*.jpg"))
            results = _ocr_all(frames)
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


# ---------------------------------------------------------------- 漫画


def _vertical_order(found):
    """竖排对白：同一气泡里并排的竖列要从右到左读。found 是引擎顺序的 [(x0,y0,x1,y1,文字,置信度)]，
    引擎按“上到下、左到右”排，同一气泡的几列会被倒着读。这里把相邻的竖列并成一组，组内按 x 从大到小，
    整组放在其中第一列原来的位置。横排的框不动。"""
    def tall(b):
        return (b[3] - b[1]) >= 1.3 * (b[2] - b[0])

    n = len(found)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        if not tall(found[i]):
            continue
        for j in range(i + 1, n):
            if not tall(found[j]):
                continue
            a, b = found[i], found[j]
            width = min(a[2] - a[0], b[2] - b[0])
            gap = max(a[0], b[0]) - min(a[2], b[2])  # 水平间隙，重叠时为负
            overlap = min(a[3], b[3]) - max(a[1], b[1])  # 竖向重叠
            if gap <= 0.9 * width and overlap >= 0.35 * min(a[3] - a[1], b[3] - b[1]):
                parent[find(j)] = find(i)
    groups = {}
    for i in range(n):
        if tall(found[i]):
            groups.setdefault(find(i), []).append(i)
    ordered, emitted = [], set()
    for i in range(n):
        if i in emitted:
            continue
        if tall(found[i]):
            for j in sorted(groups[find(i)], key=lambda k: -found[k][2]):
                ordered.append(found[j])
                emitted.add(j)
        else:
            ordered.append(found[i])
            emitted.add(i)
    return ordered


def _comic_ocr(path):
    return [(x0, y0, text, score) for x0, y0, x1, y1, text, score in _vertical_order(_ocr_boxes(path))]


def comic(cids, force=False, limit=0):
    _, _, _, comic_dir = _paths()
    for cid in cids:
        folders = [p for p in comic_dir.iterdir() if p.is_dir() and p.name.startswith(f"{cid} ")]
        if not folders:
            print("未下载", cid, flush=True)
            continue
        folder = folders[0]
        if (folder / "ocr.txt").exists() and not force:
            print("已有", folder.name, "ocr.txt，跳过", flush=True)
            continue
        files = sorted(p for ep in sorted(d for d in folder.iterdir() if d.is_dir()) for p in sorted(ep.glob("p*.jpg")))
        if limit:
            files = files[:limit]
        with cf.ThreadPoolExecutor(max_workers=THREADS) as pool:
            results = list(pool.map(_comic_ocr, files))
        out = []
        for path, found in zip(files, results):
            out.append(f"### {path.parent.name} {path.stem}")
            for x, y, text, score in found:
                if "HYPERGRYPH" in text.upper() or score < 0.5:
                    continue
                out.append(("[?] " if score < 0.7 else "") + text)
        (folder / "ocr.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
        print(folder.name, len(files), "页", flush=True)


# ---------------------------------------------------------------- 泰拉记事


def _tiles(path, folder):
    """长图切片：引擎会把长边压到 2000，宽 1000、高 5000 的图字就糊了。
    切片留在 <篇>/切片/，也给人看图用（整张长图读进来同样会被压小）。返回 [(切片路径, 核心区上沿, 核心区下沿)]，
    核心区是这张切片负责的范围，相邻切片互相重叠，文字框中心落在核心区内才算，免得重复。"""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    image = Image.open(path).convert("RGB")
    if image.width > 1200:
        image = image.resize((1200, image.height * 1200 // image.width))
    width, height = image.size
    tile, overlap = int(width * 1.5), int(width * 0.15)
    tops = list(range(0, max(height - overlap, 1), tile - overlap))
    out = []
    for k, top in enumerate(tops, 1):
        bottom = min(top + tile, height)
        target = folder / f"{path.stem}-{k:02d}.jpg"
        image.crop((0, top, width, bottom)).save(target, quality=90)
        out.append((target, 0 if k == 1 else overlap // 2, bottom - top if k == len(tops) else bottom - top - overlap // 2))
    return out


def _tile_ocr(tile):
    path, core_top, core_bottom = tile
    kept = [b for b in _ocr_boxes(path) if core_top <= (b[1] + b[3]) / 2 < core_bottom]
    return [(text, score) for _, _, _, _, text, score in _vertical_order(kept)]


def records(force=False, limit=0):
    base = RAW / "泰拉记事"
    whole = []
    folders = sorted(p for p in base.iterdir() if p.is_dir())
    for folder in folders[:limit or None]:
        images = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp"))
        if not (folder / "ocr.txt").exists() or force:
            tile_dir = folder / "切片"
            tile_dir.mkdir(exist_ok=True)
            out = []
            for image in images:
                tiles = _tiles(image, tile_dir)
                with cf.ThreadPoolExecutor(max_workers=THREADS) as pool:
                    results = list(pool.map(_tile_ocr, tiles))
                for (tile, _, _), found in zip(tiles, results):
                    out.append(f"### {tile.stem}")
                    out += [("[?] " if score < 0.7 else "") + text for text, score in found if score >= 0.5]
            (folder / "ocr.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
            print(folder.name, len(images), "图", flush=True)
        whole.append(f"=== {folder.name} ===")
        whole.append((folder / "ocr.txt").read_text(encoding="utf-8").rstrip())
    (base / "全文.txt").write_text("\n".join(whole) + "\n", encoding="utf-8")
    print("完成", base / "全文.txt", flush=True)


def main():
    global RAW, THREADS
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("what", choices=["book", "video", "comic", "records"])
    parser.add_argument("cids", nargs="*")
    parser.add_argument("--force", action="store_true", help="已有结果也重做")
    parser.add_argument("--raw", type=Path, default=RAW, help="Raw Data 的位置（试跑时指到别处）")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 页/片/页（试跑用）")
    parser.add_argument("--model", choices=list(MODELS), default="v6small")
    parser.add_argument("--threads", type=int, default=0, help="共用显卡的线程数（默认 CUDA 3、DirectML 1；DirectML 不能并发）")
    parser.add_argument("--provider", choices=["auto", "cuda", "dml"], default="auto",
                        help="auto：onnxruntime-gpu 就用 CUDA，onnxruntime-directml 就用 DirectML")
    parser.add_argument("--gpu-mem-gb", type=float, default=3.0, help="CUDA 时 onnxruntime 在显卡上的内存上限")
    args = parser.parse_args()
    RAW = args.raw
    provider = _init(args.model, args.provider, args.gpu_mem_gb)
    THREADS = 1 if provider == "dml" else (args.threads or 3)
    if args.what == "book":
        book(args.force, args.limit)
    elif args.what == "video":
        video(args.force, args.limit)
    elif args.what == "records":
        records(args.force, args.limit)
    else:
        comic(args.cids, args.force, args.limit)


if __name__ == "__main__":
    main()
