"""把本地版网页打包成一个 HTML 文件，双击就能看，不用起服务器。

内容和 python -m pipeline.serve 打开的一样，含剧本全文和干员档案正文，所以只留在本地：
文件已写进 .gitignore，不要上传。数据有更新时，先运行 python -m pipeline.build，再运行这个。

    python -m pipeline.bundle

做法：JS 模块合进一个脚本；data/ 下每个 JSON 单独 gzip 后以 base64 存在页面里，
用到时才解压（DecompressionStream），fetch 换成读这些内嵌数据，网页代码不用改。
"""
from __future__ import annotations

import base64
import gzip
import re
import sys

from .config import ROOT

SITE = ROOT / "site"
OUT = ROOT / "刻舟录-完整版.html"

IMPORT_NAMED = re.compile(r"^import\s+\{([^}]*)\}\s+from\s+'\./([\w.]+)';?[ \t]*$", re.M)
IMPORT_STAR = re.compile(r"^import\s+\*\s+as\s+(\w+)\s+from\s+'\./([\w.]+)';?[ \t]*$", re.M)
EXPORT = re.compile(r"^export\s+((?:async\s+)?function\*?|const|let|class)\s+(\w+)", re.M)

# 换掉 fetch：只读页面里内嵌的数据
FETCH_SHIM = """
window.fetch = async (path) => {
  const el = document.getElementById('d:' + path);
  if (!el) return new Response(null, { status: 404 });
  const bin = atob(el.textContent);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip')));
};
"""


def bundle_js() -> str:
    """按依赖顺序把 ES 模块改写成立即执行的函数。"""
    order: list[str] = []

    def visit(name: str):
        if name in order:
            return
        text = (SITE / "js" / name).read_text(encoding="utf-8")
        for m in list(IMPORT_NAMED.finditer(text)) + list(IMPORT_STAR.finditer(text)):
            visit(m[2])
        order.append(name)

    visit("main.js")
    out = ["const __m = {};"]
    for name in order:
        text = (SITE / "js" / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        text = IMPORT_NAMED.sub(lambda m: f"const {{{m[1].replace(' as ', ': ')}}} = __m['{m[2]}'];", text)
        text = IMPORT_STAR.sub(lambda m: f"const {m[1]} = __m['{m[2]}'];", text)
        names = [m[2] for m in EXPORT.finditer(text)]
        text = EXPORT.sub(lambda m: f"{m[1]} {m[2]}", text)
        if re.search(r"^(import|export)\b", text, re.M):
            raise SystemExit(f"{name} 里有打包脚本不认识的 import/export 写法")
        # main.js 有顶层 await，只有它要包进异步函数
        head = "async () =>" if name == "main.js" else "() =>"
        out.append(f"__m['{name}'] = ({head} {{\n'use strict';\n{text}\nreturn {{ {', '.join(names)} }};\n}})();")
    return "\n".join(out)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    data_dir = SITE / "data"
    if not (data_dir / "annals.json").exists():
        print("site/data 还没有生成，先运行 python -m pipeline.build")
        return 1
    html = (SITE / "index.html").read_text(encoding="utf-8")
    css = (SITE / "style.css").read_text(encoding="utf-8")
    vendor = (SITE / "vendor" / "force-graph.min.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    js = bundle_js().replace("</script", "<\\/script")
    blobs, raw = [], 0
    for path in sorted(data_dir.rglob("*.json")):
        content = path.read_bytes()
        raw += len(content)
        key = path.relative_to(SITE).as_posix()
        b64 = base64.b64encode(gzip.compress(content, 9, mtime=0)).decode("ascii")
        blobs.append(f'<script type="text/plain" id="d:{key}">{b64}</script>')
    html = html.replace('<link rel="stylesheet" href="style.css">', f"<style>\n{css}\n</style>")
    scripts = "\n".join(blobs) + f"\n<script>{vendor}</script>\n<script>{FETCH_SHIM}\n{js}\n</script>"
    html, n = re.subn(r'<script src="vendor/force-graph\.min\.js"></script>\s*<script type="module" src="js/main\.js"></script>',
                      lambda m: scripts, html)
    if n != 1:
        raise SystemExit("index.html 的 script 写法变了，打包脚本要跟着改")
    OUT.write_text(html, encoding="utf-8", newline="\n")
    print(f"写到 {OUT.name}：{OUT.stat().st_size / 1e6:.1f} MB（数据 {len(blobs)} 个文件，原始 {raw / 1e6:.1f} MB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
