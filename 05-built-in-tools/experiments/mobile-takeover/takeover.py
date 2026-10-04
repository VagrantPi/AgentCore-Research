# /// script
# requires-python = ">=3.12"
# dependencies = ["bedrock-agentcore", "playwright", "boto3"]
# ///
"""AgentCore Browser Live View 接手測試：本機 server 持有一個 Browser session，模擬器 Safari 開 viewer 頁。

- GET  /          viewer.html（DCV 連線流程照抄 hephclaw web/browser-view/dcv-session.mjs）
- GET  /config    新簽一個 Live View URL（最長 300 秒）
- GET  /dcvjs-esm/*  DCV Web Client SDK 檔案，執行時直接讀 --dcv-dir，不放進 repo
- POST /event     viewer 回報（page_loaded、first_frame…）
- POST /take、/release   take_control／release_control（automation stream DISABLED／ENABLED）
- GET  /check     Playwright 經 CDP 讀目前頁面的標題與 URL（交還後代表「自動化接著做」）
- POST /goto?url=  Playwright 導到指定網址
- POST /stop      關 session、結束

用法：uv run takeover.py --viewport 1280x720
每一步附加一列到 results.csv。
"""
import argparse
import csv
import datetime as dt
import json
import mimetypes
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bedrock_agentcore.tools.browser_client import BrowserClient
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "results.csv"
REGION = "ap-northeast-1"
START_URL = "https://zh.wikipedia.org/"


def log(run: str, event: str, **values) -> None:
    new = not OUT.exists()
    with OUT.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "run", "event", "values"])
        w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"), run, event, json.dumps(values, ensure_ascii=False)])
    print(event, values, flush=True)


class Session:
    def __init__(self, width: int, height: int, run: str):
        self.width, self.height, self.run = width, height, run
        self.client = BrowserClient(REGION)
        t0 = time.perf_counter()
        self.session_id = self.client.start(viewport={"width": width, "height": height}, session_timeout_seconds=1800)
        log(run, "session_started", session_id=self.session_id, ms=round((time.perf_counter() - t0) * 1000), viewport=f"{width}x{height}")
        self.pw = sync_playwright().start()
        self.browser = None
        self.page = self._connect()
        self.page.goto(START_URL)
        log(run, "navigated", url=self.page.url, title=self.page.title())

    def _connect(self):
        # 接手時 automation stream 會被關掉，交還後要重新連 CDP
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        ws_url, headers = self.client.generate_ws_headers()
        self.browser = self.pw.chromium.connect_over_cdp(ws_url, headers=headers)
        context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        return context.pages[0] if context.pages else context.new_page()

    def check(self) -> dict:
        try:
            info = {"title": self.page.title(), "url": self.page.url, "reconnected": False}
        except Exception as e:
            first_error = f"{type(e).__name__}: {e}"[:200]
            self.page = self._connect()
            info = {"title": self.page.title(), "url": self.page.url, "reconnected": True, "first_error": first_error}
        return info

    def stop(self) -> None:
        try:
            self.browser.close()
        except Exception:
            pass
        self.pw.stop()
        self.client.stop()


def make_handler(s: Session, dcv_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: dict, code: int = 200) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode())

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                log(s.run, "viewer_requested", ua=self.headers.get("User-Agent", "")[:120])
                self._send(200, (HERE / "viewer.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/config":
                self._json({"signedUrl": s.client.generate_live_view_url(expires=300), "width": s.width, "height": s.height})
            elif path.startswith("/dcvjs-esm/"):
                f = (dcv_dir / path.removeprefix("/dcvjs-esm/")).resolve()
                if not f.is_relative_to(dcv_dir.resolve()) or not f.is_file():
                    return self._send(404, b"not found", "text/plain")
                ctype = "text/javascript" if f.suffix in (".js", ".mjs") else (mimetypes.guess_type(f.name)[0] or "application/octet-stream")
                self._send(200, f.read_bytes(), ctype)
            elif path == "/check":
                info = s.check()
                log(s.run, "check", **info)
                self._json(info)
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            u = urlparse(self.path)
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if u.path == "/event":
                log(s.run, "viewer_" + json.loads(body).pop("name"), **{k: v for k, v in json.loads(body).items() if k != "name"})
                self._json({"ok": True})
            elif u.path in ("/take", "/release"):
                t0 = time.perf_counter()
                (s.client.take_control if u.path == "/take" else s.client.release_control)()
                log(s.run, u.path[1:], ms=round((time.perf_counter() - t0) * 1000), stream=s.client.get_session().get("streams", {}).get("automationStream", {}).get("streamStatus"))
                self._json({"ok": True})
            elif u.path == "/goto":
                url = parse_qs(u.query)["url"][0]
                s.page.goto(url)
                log(s.run, "goto", url=s.page.url, title=s.page.title())
                self._json({"ok": True})
            elif u.path == "/stop":
                self._json({"ok": True})
                raise KeyboardInterrupt
            else:
                self._send(404, b"not found", "text/plain")

    return Handler


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--viewport", default="1280x720")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--dcv-dir", type=Path, default=Path.home() / "WS/hephclaw/backend/browser-assets/dcvjs-esm")
    a = p.parse_args()
    w, h = map(int, a.viewport.split("x"))
    run = dt.datetime.now().strftime("%H%M%S") + f"-{a.viewport}"
    s = Session(w, h, run)
    # 單執行緒 server：Playwright sync API 只能在建立它的執行緒用
    server = HTTPServer(("127.0.0.1", a.port), make_handler(s, a.dcv_dir))
    log(run, "server_ready", url=f"http://localhost:{a.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        s.stop()
        log(run, "session_stopped")


if __name__ == "__main__":
    main()
