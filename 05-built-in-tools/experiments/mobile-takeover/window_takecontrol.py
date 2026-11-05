# /// script
# requires-python = ">=3.12"
# dependencies = ["bedrock-agentcore", "playwright", "boto3"]
# ///
"""縮視窗後 take_control（CDP 被切斷），視窗還是不是 500 寬；交還後從新連線能不能縮回 1600×1000。

接手期間沒有 CDP，用 viewer 截圖看（window-tc-during.png）；交還後重連讀 window bounds 與 innerWidth。
用法：uv run window_takecontrol.py
"""
import datetime as dt
import json
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from bedrock_agentcore.tools.browser_client import BrowserClient
from playwright.sync_api import sync_playwright

import takeover  # noqa: E402

HERE = Path(__file__).parent
SESSION_W, SESSION_H = 1600, 1000
WIN_W, WIN_H = 500, 1003
PORT = 8775
URL = "https://zh.wikipedia.org/wiki/%E5%8F%B0%E5%8C%97101"
STATE_JS = "() => ({url: location.href, innerWidth, innerHeight})"


class Holder:
    def __init__(self, client, run):
        self.client, self.width, self.height, self.run = client, SESSION_W, SESSION_H, run


def main() -> None:
    run = dt.datetime.now().strftime("%H%M%S") + "-window-takecontrol"
    log = lambda event, **v: takeover.log(run, event, **v)  # noqa: E731
    client = BrowserClient(takeover.REGION)
    client.start(viewport={"width": SESSION_W, "height": SESSION_H}, session_timeout_seconds=900)
    events = []
    handler = takeover.make_handler(Holder(client, run), Path.home() / "WS/hephclaw/backend/browser-assets/dcvjs-esm")
    orig_post = handler.do_POST

    def do_post(self):
        if self.path == "/event":
            events.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))["name"])
            return self._json({"ok": True})
        return orig_post(self)

    handler.do_POST = do_post
    server = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    pw = sync_playwright().start()
    try:
        def connect():
            ws_url, headers = client.generate_ws_headers()
            ctx = pw.chromium.connect_over_cdp(ws_url, headers=headers).contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            return ctx, page, ctx.new_cdp_session(page)

        def bounds(cdp, b=None):
            wid = cdp.send("Browser.getWindowForTarget")["windowId"]
            if b:
                cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": b})
            return cdp.send("Browser.getWindowForTarget")["bounds"]

        ctx, page, cdp = connect()
        page.goto(URL)
        log("resized", bounds=bounds(cdp, {"left": 0, "top": 0, "width": WIN_W, "height": WIN_H}), page=page.evaluate(STATE_JS))

        client.take_control()
        log("take_control", stream=client.get_session().get("streams", {}).get("automationStream", {}).get("streamStatus"))
        local = pw.chromium.launch()
        vpage = local.new_context(**pw.devices["Pixel 7"]).new_page()
        vpage.goto(f"http://localhost:{PORT}/?crop={WIN_W}x{WIN_H}")
        deadline = time.time() + 30
        while "first_frame" not in events and time.time() < deadline:
            vpage.wait_for_timeout(200)
        vpage.wait_for_timeout(5000)  # 接手期間多等一下，看視窗會不會被拉回去
        vpage.screenshot(path=HERE / "window-tc-during.png", full_page=True)
        log("during_shot", first_frame="first_frame" in events)

        client.release_control()
        ctx, page, cdp = connect()
        log("after_release", bounds=bounds(cdp), page=page.evaluate(STATE_JS))
        log("restored", bounds=bounds(cdp, {"left": 0, "top": 0, "width": SESSION_W, "height": SESSION_H}), page=page.evaluate(STATE_JS))
        local.close()
    finally:
        pw.stop()
        client.stop()
        server.shutdown()
        log("session_stopped")


if __name__ == "__main__":
    main()
