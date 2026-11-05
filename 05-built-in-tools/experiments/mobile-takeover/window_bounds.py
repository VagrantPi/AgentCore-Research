# /// script
# requires-python = ">=3.12"
# dependencies = ["bedrock-agentcore", "playwright", "boto3"]
# ///
"""接手時把 Chrome 視窗本身縮成手機寬（Browser.setWindowBounds），取代只裁網頁區域。

驗：AgentCore 允不允許改視窗大小；縮小後開 3 個新分頁＋1 個彈出視窗，在 Live View 裡看不看得到；交還後能不能回 1600×1000。
每步記到 results.csv，截圖存 window-*.png（full＝整個桌面，crop＝只看左上角視窗那塊）。
用法：uv run window_bounds.py
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
WIN_W, WIN_H = 500, 1003  # Chrome 視窗最小寬 500（要 412 會被拉到 500）；頁面 915＋工具列 88
PORT = 8773
URL = "https://zh.wikipedia.org/wiki/%E5%8F%B0%E5%8C%97101"
STATE_JS = "() => ({url: location.href, innerWidth, innerHeight, outerWidth, outerHeight, screenX, screenY})"
LINKS = """<meta name=viewport content="width=device-width">
<a id=t1 target=_blank href="https://zh.wikipedia.org/wiki/1">tab1</a>
<a id=t2 target=_blank href="https://zh.wikipedia.org/wiki/2">tab2</a>
<a id=t3 target=_blank href="https://zh.wikipedia.org/wiki/3">tab3</a>
<a id=pop href="#" onclick="window.open('https://zh.wikipedia.org/wiki/4','pop','width=500,height=600');return false">popup</a>"""


class Holder:
    def __init__(self, client, run):
        self.client, self.width, self.height, self.run = client, SESSION_W, SESSION_H, run


def main() -> None:
    run = dt.datetime.now().strftime("%H%M%S") + "-window-bounds"
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
        ws_url, headers = client.generate_ws_headers()
        ctx = pw.chromium.connect_over_cdp(ws_url, headers=headers).contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(URL)
        cdp = ctx.new_cdp_session(page)
        win = cdp.send("Browser.getWindowForTarget")
        log("window_before", **win, page=page.evaluate(STATE_JS))

        local = pw.chromium.launch()
        vpage = local.new_context(**pw.devices["Pixel 7"]).new_page()

        def shot(tag, crop=True):
            events.clear()
            vpage.goto(f"http://localhost:{PORT}/" + (f"?crop={WIN_W}x{WIN_H}" if crop else ""))
            deadline = time.time() + 30
            while "first_frame" not in events and time.time() < deadline:
                vpage.wait_for_timeout(200)
            vpage.wait_for_timeout(2500)
            vpage.screenshot(path=HERE / f"window-{tag}.png", full_page=True)
            log("viewer_shot", tag=tag, first_frame="first_frame" in events)

        def set_bounds(bounds):
            try:
                cdp.send("Browser.setWindowBounds", {"windowId": win["windowId"], "bounds": bounds})
                return None
            except Exception as e:  # noqa: BLE001  實驗要記下錯誤
                return f"{type(e).__name__}: {e}"[:200]

        # 先轉 normal（maximized／fullscreen 時不能設尺寸），再設大小與位置
        err = set_bounds({"windowState": "normal"}) or set_bounds({"left": 0, "top": 0, "width": WIN_W, "height": WIN_H})
        page.wait_for_timeout(1000)
        log("window_resized", error=err, bounds=cdp.send("Browser.getWindowForTarget")["bounds"], page=page.evaluate(STATE_JS))
        shot("1-resized")

        # 3 個新分頁＋1 個彈出視窗（Playwright click 算使用者手勢，不會被擋）
        page.set_content(LINKS)
        for sel in ("#t1", "#t2", "#t3"):
            with ctx.expect_page():
                page.click(sel)
        page.wait_for_timeout(2000)
        shot("2-tabs-crop")
        with ctx.expect_page() as popup_info:
            page.click("#pop")
        popup = popup_info.value
        popup.wait_for_load_state()
        # 彈出視窗是另一個 window：同樣縮到左上角 500 寬（hephagent 可在 context.on("page") 做）
        ps = ctx.new_cdp_session(popup)
        pid = ps.send("Browser.getWindowForTarget")["windowId"]
        ps.send("Browser.setWindowBounds", {"windowId": pid, "bounds": {"left": 0, "top": 0, "width": WIN_W, "height": WIN_H}})
        popup.wait_for_timeout(1000)
        log("popup_resized", bounds=ps.send("Browser.getWindowForTarget")["bounds"], page=popup.evaluate(STATE_JS))
        ps.detach()
        tabs = []
        for p in ctx.pages:
            s = ctx.new_cdp_session(p)
            tabs.append({"url": p.url, **s.send("Browser.getWindowForTarget")["bounds"], "windowId": s.send("Browser.getWindowForTarget")["windowId"]})
            s.detach()
        log("tabs_opened", tabs=tabs)
        shot("3-popup-crop")
        popup.close()
        page.wait_for_timeout(1000)
        shot("4-popup-closed-crop")

        # 交還：關掉新開的，視窗回 1600×1000
        for p in ctx.pages:
            if p != page:
                p.close()
        err = set_bounds({"left": 0, "top": 0, "width": SESSION_W, "height": SESSION_H})
        page.goto(URL)
        log("window_restored", error=err, bounds=cdp.send("Browser.getWindowForTarget")["bounds"], page=page.evaluate(STATE_JS))
        shot("5-restored", crop=False)
        local.close()
    finally:
        pw.stop()
        client.stop()
        server.shutdown()
        log("session_stopped")


if __name__ == "__main__":
    main()
