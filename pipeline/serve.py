"""在本机起一个静态服务器打开剧情浏览器（只监听 127.0.0.1）。

用法：python -m pipeline.serve [--port 8765] [--no-browser]
"""
import argparse
import functools
import http.server
import webbrowser

from . import config


class Handler(http.server.SimpleHTTPRequestHandler):
    """每次都向服务器确认文件是否有变化，重新构建或改了网页后刷新就能看到。"""

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    if not (config.SITE_DATA / "meta.json").exists():
        raise SystemExit("还没有生成数据，请先运行：python -m pipeline.build")
    handler = functools.partial(Handler, directory=str(config.SITE))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        url = f"http://127.0.0.1:{args.port}/"
        print(f"剧情浏览器：{url}（Ctrl+C 停止）")
        if not args.no_browser:
            webbrowser.open(url)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
