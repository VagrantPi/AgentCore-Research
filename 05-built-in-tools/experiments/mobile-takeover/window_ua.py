# /// script
# requires-python = ">=3.12"
# dependencies = ["bedrock-agentcore", "playwright", "boto3"]
# ///
"""縮 Chrome 視窗（window_bounds.py）＋每個分頁補手機 UA／client hints／touch。

驗：主分頁模擬後網站拿到什麼；新分頁、彈出視窗在 context.on("page") 補模擬，**第一個請求**伺服器收到的 UA 是不是手機（有沒有競態）；
交還時清得掉。新分頁與彈出視窗都開 httpbin.org/headers，頁面內容就是伺服器當下收到的 header。
用法：uv run window_ua.py
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
WIN_W, WIN_H = 500, 1003  # Chrome 視窗最小寬 500
PORT = 8774
URL = "https://zh.wikipedia.org/wiki/%E5%8F%B0%E5%8C%97101"
HEADERS = "https://httpbin.org/headers"
STATE_JS = "() => ({url: location.href, innerWidth, ua: navigator.userAgent.slice(0, 50), touch: navigator.maxTouchPoints, coarse: matchMedia('(pointer: coarse)').matches, mobile: navigator.userAgentData?.mobile})"
LINKS = f"""<a id=tab target=_blank href="{HEADERS}?tab">tab</a>
<a id=pop href="#" onclick="window.open('{HEADERS}?popup','pop','width=500,height=600');return false">popup</a>"""
UA = "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
UA_META = {"platform": "Android", "platformVersion": "14", "architecture": "", "model": "Pixel 7", "mobile": True,
           "brands": [{"brand": "Chromium", "version": "130"}, {"brand": "Not?A_Brand", "version": "99"}]}


class Holder:
    def __init__(self, client, run):
        self.client, self.width, self.height, self.run = client, SESSION_W, SESSION_H, run


def server_saw(page) -> dict:
    h = json.loads(page.inner_text("body"))["headers"]
    return {"ua": h.get("User-Agent", "")[:50], "ch_mobile": h.get("Sec-Ch-Ua-Mobile"), "ch_platform": h.get("Sec-Ch-Ua-Platform")}


def main() -> None:
    run = dt.datetime.now().strftime("%H%M%S") + "-window-ua"
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
        sessions = {}  # page → CDP session；override 綁在 session 上，要一直留著

        def emulate(p):
            s = sessions[p] = ctx.new_cdp_session(p)
            s.send("Emulation.setUserAgentOverride", {"userAgent": UA, "platform": "Linux armv8l", "userAgentMetadata": UA_META})
            s.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
            return s

        def resize(p, w, h):
            s = sessions.get(p) or ctx.new_cdp_session(p)
            wid = s.send("Browser.getWindowForTarget")["windowId"]
            s.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"left": 0, "top": 0, "width": w, "height": h}})

        # 接手：縮視窗＋主分頁模擬；之後開的分頁一出現就補
        emulate(page)
        resize(page, WIN_W, WIN_H)
        ctx.on("page", lambda p: (emulate(p), resize(p, WIN_W, WIN_H)))
        # on("page") 觸發時新頁第一個請求已送出（桌面 UA）：網路層改寫 header 補上。
        # hephagent 接手期間本來就 route.continue 全部放行（workspace-browser-agent-network.js:163），掛在那裡
        mobile_headers = {"user-agent": UA, "sec-ch-ua-mobile": "?1", "sec-ch-ua-platform": '"Android"'}
        ctx.route("**/*", lambda route: route.continue_(headers={**route.request.headers, **mobile_headers}))
        page.reload()
        log("main_emulated", **page.evaluate(STATE_JS))

        local = pw.chromium.launch()
        vpage = local.new_context(**pw.devices["Pixel 7"]).new_page()

        def shot(tag):
            events.clear()
            vpage.goto(f"http://localhost:{PORT}/?crop={WIN_W}x{WIN_H}")
            deadline = time.time() + 30
            while "first_frame" not in events and time.time() < deadline:
                vpage.wait_for_timeout(200)
            vpage.wait_for_timeout(2500)
            vpage.screenshot(path=HERE / f"window-ua-{tag}.png", full_page=True)

        shot("1-main")

        page.goto("https://httpbin.org/html")
        page.evaluate(f"() => {{ document.body.innerHTML = `{LINKS}`; }}")
        for sel in ("#tab", "#pop"):
            with ctx.expect_page() as info:
                page.click(sel)
            p = info.value
            p.wait_for_load_state()
            p.wait_for_timeout(500)  # 讓 on("page") 的 resize 跑完
            log(f"{sel[1:]}_first_load", server=server_saw(p), page=p.evaluate(STATE_JS))
            p.reload()
            log(f"{sel[1:]}_reload", server=server_saw(p))
        shot("2-popup")

        # 交還：清模擬、關新開的、視窗回 1600×1000
        for p, s in list(sessions.items()):
            if p != page:
                p.close()
                continue
            s.send("Emulation.setUserAgentOverride", {"userAgent": ""})
            s.send("Emulation.setTouchEmulationEnabled", {"enabled": False})
        resize(page, SESSION_W, SESSION_H)
        page.goto(URL)
        log("restored", **page.evaluate(STATE_JS))
        local.close()
    finally:
        pw.stop()
        client.stop()
        server.shutdown()
        log("session_stopped")


if __name__ == "__main__":
    main()
