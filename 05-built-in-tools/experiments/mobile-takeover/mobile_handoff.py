# /// script
# requires-python = ">=3.12"
# dependencies = ["bedrock-agentcore", "playwright", "boto3"]
# ///
"""接手時才切手機版：session 維持 Nova Act 的 1600×1000，接手前用 CDP 模擬手機，viewer 只裁左上角放大。

驗三件事（每步記到 results.csv，截圖存 handoff-*.png）：
  1. 模擬後網站給不給手機版（Wikipedia 看 UA 導到 zh.m.）、Live View 裁切後看不看得清楚
  2. 在 viewer 上點擊，座標對不對（頁面記 pointerdown 的 clientX/Y，跟目標點比）
     A：不 take_control（CDP 連線一直在，同 hephagent BROWSER_HANDOFF_KEEP_AUTOMATION）
     B：take_control（CDP 會被切斷）——模擬撐不撐得過去
  3. 交還後清掉模擬，回到 1600 寬

本機 Chromium（Pixel 7 尺寸）開 viewer 代替手機，不用模擬器。
用法：uv run mobile_handoff.py
"""
import datetime as dt
import json
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from bedrock_agentcore.tools.browser_client import BrowserClient
from playwright.sync_api import sync_playwright

import takeover

HERE = Path(__file__).parent
SESSION_W, SESSION_H = 1600, 1000  # hephagent workspace-browser-session.js:38（nova-act）
MOBILE_W, MOBILE_H = 412, 915  # Pixel 7
PORT = 8772
URL = "https://zh.wikipedia.org/wiki/%E5%8F%B0%E5%8C%97101"
STATE_JS = "() => ({url: location.href, innerWidth, innerHeight, ua: navigator.userAgent.slice(0, 60), touch: navigator.maxTouchPoints})"


class Holder:
    """takeover.make_handler 要的欄位：client、width、height、run"""

    def __init__(self, client, run):
        self.client, self.width, self.height, self.run = client, SESSION_W, SESSION_H, run


def main() -> None:
    run = dt.datetime.now().strftime("%H%M%S") + "-mobile-handoff"
    log = lambda event, **v: takeover.log(run, event, **v)
    client = BrowserClient(takeover.REGION)
    client.start(viewport={"width": SESSION_W, "height": SESSION_H}, session_timeout_seconds=900)
    holder = Holder(client, run)
    events = []
    handler = takeover.make_handler(holder, Path.home() / "WS/hephclaw/backend/browser-assets/dcvjs-esm")
    orig_post = handler.do_POST

    def do_post(self):  # 記下 viewer 事件，等 first_frame 用
        if self.path == "/event":
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            events.append(json.loads(body)["name"])
            log("viewer_" + json.loads(body)["name"])
            return self._json({"ok": True})
        return orig_post(self)

    handler.do_POST = do_post
    server = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    pw = sync_playwright().start()
    try:
        def connect():
            ws_url, headers = client.generate_ws_headers()
            return pw.chromium.connect_over_cdp(ws_url, headers=headers)

        remote = connect()
        ctx = remote.contexts[0]  # 跟 hephagent 一樣用 agentcore-default context，不 new_context
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(URL)
        base = page.evaluate(STATE_JS)
        # 串流含 Chrome 分頁列＋網址列：頁面在串流裡往下偏 toolbar px，裁切高度也要加上
        toolbar = SESSION_H - base["innerHeight"]
        log("baseline", toolbar=toolbar, **base)

        pixel = pw.devices["Pixel 7"]

        def emulate(cdp):
            cdp.send("Emulation.setDeviceMetricsOverride", {"width": MOBILE_W, "height": MOBILE_H, "deviceScaleFactor": 1, "mobile": True})
            cdp.send("Emulation.setUserAgentOverride", {"userAgent": pixel["user_agent"], "platform": "Linux armv8l"})
            cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})

        def clear(cdp):
            cdp.send("Emulation.clearDeviceMetricsOverride")
            cdp.send("Emulation.setUserAgentOverride", {"userAgent": ""})
            cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": False})

        cdp = ctx.new_cdp_session(page)
        emulate(cdp)
        page.goto(URL)
        log("emulated", **page.evaluate(STATE_JS))

        local = pw.chromium.launch()
        vpage = local.new_context(**pixel).new_page()

        def open_viewer(tag):
            events.clear()
            vpage.goto(f"http://localhost:{PORT}/?crop={MOBILE_W}x{MOBILE_H + toolbar}")
            deadline = time.time() + 30
            while "first_frame" not in events and time.time() < deadline:
                vpage.wait_for_timeout(200)
            vpage.wait_for_timeout(2500)
            vpage.screenshot(path=HERE / f"handoff-{tag}.png", full_page=True)
            log("viewer_shot", tag=tag, first_frame="first_frame" in events)

        def tap(point):  # 遠端 CSS px → viewer 座標：scale＝viewer 寬／裁切寬，再加上 #wrap 的位移
            box = vpage.evaluate("() => { const r = document.getElementById('wrap').getBoundingClientRect(); return {top: r.top, left: r.left, scale: innerWidth / %d}; }" % MOBILE_W)
            vpage.touchscreen.tap(box["left"] + point["x"] * box["scale"], box["top"] + (point["y"] + toolbar) * box["scale"])
            vpage.wait_for_timeout(4000)

        # 點擊精準度：頁面記下 pointerdown 的 clientX/Y（sessionStorage，同網域換頁也留著），跟目標點比
        TARGET = {"x": 300, "y": 600}
        RECORD_JS = "() => { sessionStorage.taps = '[]'; addEventListener('pointerdown', e => sessionStorage.taps = JSON.stringify([...JSON.parse(sessionStorage.taps), [Math.round(e.clientX), Math.round(e.clientY), e.pointerType]]), true); }"
        TAPS_JS = "() => JSON.parse(sessionStorage.taps || '[]')"

        # A：不 take_control，CDP 一直連著
        page.evaluate(RECORD_JS)
        open_viewer("A-keep-automation")
        tap(TARGET)
        log("A_tap", target=TARGET, taps=page.evaluate(TAPS_JS), url=page.url)
        clear(cdp)  # 同一條 CDP 連線清得掉嗎
        page.goto(URL)
        log("A_cleared", **page.evaluate(STATE_JS))
        emulate(cdp)
        page.goto(URL)

        # B：take_control，CDP 會被切斷
        page.evaluate(RECORD_JS)
        client.take_control()
        open_viewer("B-take-control")
        tap(TARGET)
        vpage.screenshot(path=HERE / "handoff-B-after-tap.png", full_page=True)
        client.release_control()
        remote = connect()
        ctx = remote.contexts[0]
        page = ctx.pages[0]
        log("B_tap", target=TARGET, taps=page.evaluate(TAPS_JS), **page.evaluate(STATE_JS))

        # 舊連線被切斷後殘留的 override：新連線先 clear，再試「蓋一次 1600 再 clear」
        cdp = ctx.new_cdp_session(page)
        clear(cdp)
        page.reload()
        log("B_clear_only", **page.evaluate(STATE_JS))
        cdp.send("Emulation.setDeviceMetricsOverride", {"width": 0, "height": 0, "deviceScaleFactor": 0, "mobile": False})
        page.reload()
        log("B_override_zero", **page.evaluate(STATE_JS))
        clear(cdp)
        page.reload()
        log("B_override_then_clear", **page.evaluate(STATE_JS))
        cdp.detach()
        page.reload()
        log("B_after_detach", **page.evaluate(STATE_JS))

        # C：接手「期間」網站收到的 UA。take_control 後在 viewer 點連結到 httpbin，
        # 頁面內容就是伺服器當下收到的 header（交還後才讀，但內容是接手中載入的）
        cdp = ctx.new_cdp_session(page)
        emulate(cdp)
        page.goto("https://httpbin.org/html")
        page.evaluate("""() => { document.body.innerHTML = '<a href="https://httpbin.org/headers" style="display:block;height:400px;font-size:48px">headers</a>'; }""")
        client.take_control()
        open_viewer("C-take-control")
        tap({"x": 200, "y": 200})
        vpage.wait_for_timeout(2000)
        vpage.screenshot(path=HERE / "handoff-C-during.png", full_page=True)
        client.release_control()
        remote = connect()
        page = remote.contexts[0].pages[0]
        headers = json.loads(page.inner_text("body"))["headers"]
        log("C_server_saw_during_takeover", url=page.url, ua=headers.get("User-Agent", "")[:60], ch_mobile=headers.get("Sec-Ch-Ua-Mobile"), ch_platform=headers.get("Sec-Ch-Ua-Platform"))
        local.close()
    finally:
        pw.stop()
        client.stop()
        server.shutdown()
        log("session_stopped")


if __name__ == "__main__":
    main()
