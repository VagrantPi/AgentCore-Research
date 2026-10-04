# /// script
# requires-python = ">=3.12"
# dependencies = ["bedrock-agentcore", "playwright", "boto3", "websocket-client"]
# ///
"""重現「開著 Live View 時自動化卡死」並在卡住當下蒐集證據。

主執行緒：開 session → 模擬器 Safari 開 Live View → Playwright 開維基、每 0.5 秒捲一次，共 RUN_SECONDS 秒。
看門狗：主執行緒超過 STALL_SECONDS 沒有進展時，用另一條 CDP 連線（websocket-client）查瀏覽器與頁面是否回應、
從遠端截圖、查 automation stream 狀態、截模擬器畫面，全部存到 hang/<session>/。

用法：uv run lv_hang.py --sim <udid> --port 8771 [--viewport 1280x720] [--no-liveview]
"""
import argparse
import json
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import websocket
from bedrock_agentcore.tools.browser_client import BrowserClient
from playwright.sync_api import sync_playwright

import takeover

HERE = Path(__file__).parent
REGION = "ap-northeast-1"
RUN_SECONDS = 60
STALL_SECONDS = 45  # goto 有 30 秒逾時；20 秒時會把 21 秒的慢連線誤判成卡死
PAGES = [
    "https://zh.wikipedia.org/",
    "https://zh.wikipedia.org/wiki/%E5%8F%B0%E5%8C%97101",
    "https://github.com/explore",
    "https://www.bbc.com/news",
]
takeover.OUT = HERE / "lv_hang_events.csv"


class Progress:
    def __init__(self):
        self.t0 = time.time()
        self.last = time.time()
        self.step = "start"
        self.lock = threading.Lock()

    def mark(self, step: str):
        with self.lock:
            self.last, self.step = time.time(), step
        print(f"{time.time() - self.t0:6.1f}s {step}", flush=True)


def raw_cdp(client: BrowserClient, out: Path) -> dict:
    """另開一條 automation 連線，問瀏覽器還活不活著。每個指令 10 秒逾時。"""
    result = {}
    ws_url, headers = client.generate_ws_headers()
    hdrs = [f"{k}: {v}" for k, v in headers.items() if k.lower() not in ("host", "upgrade", "connection", "sec-websocket-version", "sec-websocket-key")]
    try:
        ws = websocket.create_connection(ws_url, header=hdrs, timeout=10)
    except Exception as e:
        return {"connect_error": f"{type(e).__name__}: {e}"[:300]}
    msg_id = 0

    def call(method, params=None, session=None):
        nonlocal msg_id
        msg_id += 1
        payload = {"id": msg_id, "method": method, "params": params or {}}
        if session:
            payload["sessionId"] = session
        t = time.time()
        ws.send(json.dumps(payload))
        while True:
            try:
                m = json.loads(ws.recv())
            except Exception as e:
                return {"error": f"{type(e).__name__}: {e}"[:200], "ms": round((time.time() - t) * 1000)}
            if m.get("id") == msg_id:
                m["ms"] = round((time.time() - t) * 1000)
                return m

    result["browser_version"] = call("Browser.getVersion").get("result", {}).get("product")
    targets = call("Target.getTargets")
    infos = targets.get("result", {}).get("targetInfos", [])
    result["targets"] = [{k: t.get(k) for k in ("type", "url", "attached", "title")} for t in infos]
    page = next((t for t in infos if t.get("type") == "page"), None)
    if page:
        att = call("Target.attachToTarget", {"targetId": page["targetId"], "flatten": True})
        sid = att.get("result", {}).get("sessionId")
        result["attach"] = {"ok": bool(sid), "ms": att.get("ms"), "error": att.get("error")}
        if sid:
            ev = call("Runtime.evaluate", {"expression": "[document.readyState, location.href, document.hasFocus(), document.visibilityState, window.scrollY]", "returnByValue": True, "timeout": 5000}, sid)
            result["evaluate"] = ev.get("result", {}).get("result", {}).get("value") or ev.get("error") or ev.get("result")
            result["evaluate_ms"] = ev.get("ms")
            shot = call("Page.captureScreenshot", {"format": "png"}, sid)
            data = shot.get("result", {}).get("data")
            result["screenshot_ms"] = shot.get("ms")
            if data:
                import base64
                (out / "remote.png").write_bytes(base64.b64decode(data))
            else:
                result["screenshot_error"] = shot.get("error") or shot.get("error", shot)
    ws.close()
    return result


def watchdog(p: Progress, client: BrowserClient, sim: str | None, stop: threading.Event, out: Path, found: list):
    while not stop.wait(2):
        with p.lock:
            stalled = time.time() - p.last
            step = p.step
        if stalled < STALL_SECONDS or found:
            continue
        found.append(step)
        out.mkdir(parents=True, exist_ok=True)
        print(f"!!! STALL {stalled:.0f}s at step: {step}", flush=True)
        evidence = {"stalled_seconds": round(stalled), "stalled_step": step}
        try:
            evidence["streams"] = client.get_session().get("streams")
        except Exception as e:
            evidence["get_session_error"] = str(e)[:200]
        evidence["raw_cdp"] = raw_cdp(client, out)
        if sim:
            subprocess.run(["xcrun", "simctl", "io", sim, "screenshot", str(out / "simulator.png")], capture_output=True)
        (out / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
        print(json.dumps(evidence, ensure_ascii=False, default=str)[:1500], flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim")
    ap.add_argument("--port", type=int, default=8771)
    ap.add_argument("--viewport", default="1280x720")
    ap.add_argument("--no-liveview", action="store_true")
    ap.add_argument("--full", action="store_true", help="完整工作負載：300 秒、4 個網站")
    ap.add_argument("--browser-id", default="aws.browser.v1", help="卡住的 3 次都在自訂 Browser；預設系統 browser")
    a = ap.parse_args()
    w, h = map(int, a.viewport.split("x"))
    client = BrowserClient(REGION)
    sid = client.start(identifier=a.browser_id, viewport={"width": w, "height": h}, session_timeout_seconds=420)
    out = HERE / "hang" / sid
    p = Progress()
    p.mark(f"session {sid} browser {a.browser_id}")
    server = None
    if not a.no_liveview:
        shim = type("S", (), {"client": client, "width": w, "height": h, "run": f"hang-{sid}"})
        server = ThreadingHTTPServer(("127.0.0.1", a.port), takeover.make_handler(shim, Path.home() / "WS/hephclaw/backend/browser-assets/dcvjs-esm"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        subprocess.run(["xcrun", "simctl", "openurl", a.sim, f"http://localhost:{a.port}/"], check=True)
        p.mark("liveview opened")
    stop, found = threading.Event(), []
    dog = threading.Thread(target=watchdog, args=(p, client, a.sim, stop, out, found), daemon=True)
    dog.start()
    with sync_playwright() as pw:
        ws_url, headers = client.generate_ws_headers()
        browser = pw.chromium.connect_over_cdp(ws_url, headers=headers)
        p.mark("cdp connected")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(30000)
        page.on("dialog", lambda d: (p.mark(f"dialog {d.type}"), d.dismiss()))
        page.on("crash", lambda: p.mark("page crash"))
        page.on("close", lambda: p.mark("page close"))
        browser.on("disconnected", lambda: p.mark("browser disconnected"))
        # --full：跟 viewport_cost.py 一樣的 300 秒、4 個網站（卡住的 3 次都是這個工作負載）
        pages = PAGES if a.full else PAGES[:1]
        seconds = 300 if a.full else RUN_SECONDS
        i = 0
        while time.time() - p.t0 < seconds:
            for url in pages:
                if time.time() - p.t0 >= seconds:
                    break
                p.mark(f"goto {url}")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    p.mark(f"goto error {type(e).__name__}: {str(e)[:120]}")
                    continue
                p.mark("loaded")
                for _ in range(20 if a.full else 10_000):
                    if time.time() - p.t0 >= seconds:
                        break
                    i += 1
                    p.mark(f"evaluate scroll #{i}")
                    try:
                        page.evaluate("window.scrollBy(0, 400)")
                    except Exception as e:
                        p.mark(f"evaluate error {type(e).__name__}: {str(e)[:120]}")
                        break
                    p.mark(f"wait #{i}")
                    page.wait_for_timeout(500)
    stop.set()
    dog.join(timeout=90)  # 等看門狗把證據寫完，不然 daemon 執行緒會被砍
    client.stop()
    if server:
        server.shutdown()
    print("RESULT", "HANG" if found else "OK", sid, found[0] if found else "", flush=True)


if __name__ == "__main__":
    main()
