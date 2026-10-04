# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp<2", "bedrock-agentcore", "playwright", "boto3", "httpx"]
# ///
"""WP2 #8：接手登入由 server 主導。HephAgora 的 com.wp2.login-web 以 http binding 呼叫這個 MCP server。

工具 login_and_check：
  開 AgentCore Browser（server 自己的 AWS 憑證）→ 開測試站登入頁 → 偵測到密碼欄位就 take_control
  → 產生一次性 viewer ticket → 把 viewer 連結推給 App（模擬推播端點 /push，寫 pushes.jsonl）
  → 等使用者在 viewer 按「交還」→ release_control → 重連 CDP → 讀登入結果，只回結構化結果（不含任何 URL）。

同一個程序也提供手機要開的 viewer（/viewer/<ticket>/）、DCV 檔案、交還端點。
每個 CDP 指令都包逾時：automation stream 偶爾會吞指令（見 05-built-in-tools/experiments/mobile-takeover/README.md）。

用法：uv run browser_skill.py   # MCP 在 http://0.0.0.0:13200/mcp
"""
import asyncio
import csv
import datetime as dt
import json
import secrets
import time
from pathlib import Path

import httpx
from bedrock_agentcore.tools.browser_client import BrowserClient
from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

HERE = Path(__file__).parent
REGION = "ap-northeast-1"
PORT = 13200
VIEWER_BASE = f"http://localhost:{PORT}"  # 手機（模擬器）打開推播連結的位址
PUSH_URL = f"http://localhost:{PORT}/push"  # 模擬 App 推播服務
APP_USER = "userB"  # HephAgora 不把 actor 傳給 binding，這次單一使用者用固定對象（見 README 限制）
LOGIN_URL = "https://the-internet.herokuapp.com/login"
DCV_DIR = Path.home() / "WS/hephclaw/backend/browser-assets/dcvjs-esm"
# 工具從開始算的總預算：要比 HephAgora binding 的 timeout_ms（300 秒）早結束，才能自己回乾淨的結果。
# 曾用「固定等 240 秒」：開頁花了 62 秒，總共 302 秒，被 HephAgora 先判逾時。
TOOL_BUDGET = 270
CDP_TIMEOUT = 30
VIEWPORT = {"width": 390, "height": 844}

mcp = FastMCP("wp2-login-web", host="0.0.0.0", port=PORT)
TICKETS: dict[str, dict] = {}


def log(run: str, event: str, **values) -> None:
    out = HERE / "events.csv"
    new = not out.exists()
    with out.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "run", "event", "values"])
        w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"), run, event, json.dumps(values, ensure_ascii=False)])
    print(run, event, values, flush=True)


async def cdp(coro, what: str, run: str, timeout: float = CDP_TIMEOUT):
    """CDP 指令一律有逾時；逾時記一筆再往上拋，由呼叫端決定重連。"""
    try:
        return await asyncio.wait_for(coro, timeout)
    except asyncio.TimeoutError:
        log(run, "cdp_timeout", what=what, seconds=timeout)
        raise


async def retry_once(pw, client, run, state, step, what):
    """CDP 指令逾時：重連 CDP 再做一次（automation stream 偶爾吞指令）。state = {"browser", "page"}。"""
    try:
        return await cdp(step(state["page"]), what, run)
    except asyncio.TimeoutError:
        try:
            await asyncio.wait_for(state["browser"].close(), 10)
        except Exception:
            pass
        state["browser"], state["page"] = await connect(pw, client, run)
        log(run, "cdp_reconnected", what=what)
        return await cdp(step(state["page"]), what + " (retry)", run)


async def connect(pw, client: BrowserClient, run: str):
    ws_url, headers = await asyncio.to_thread(client.generate_ws_headers)
    browser = await cdp(pw.chromium.connect_over_cdp(ws_url, headers=headers), "connect_over_cdp", run, 60)
    ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    return browser, page


@mcp.tool()
async def login_and_check() -> dict:
    """登入測試網站並回報登入結果。需要使用者登入時，會請使用者在手機上接手瀏覽器。"""
    client = BrowserClient(REGION)
    session_id = await asyncio.to_thread(client.start, viewport=VIEWPORT, session_timeout_seconds=600)
    run = f"login-{session_id[-6:]}"
    t0 = time.time()
    log(run, "session_started", session_id=session_id)
    ticket = None
    try:
        async with async_playwright() as pw:
            st = dict(zip(("browser", "page"), await connect(pw, client, run)))
            await retry_once(pw, client, run, st, lambda p: p.goto(LOGIN_URL, wait_until="domcontentloaded"), "goto")
            needs_login = await retry_once(pw, client, run, st, lambda p: p.locator("input[type=password]").count(), "detect") > 0
            log(run, "login_page_detected" if needs_login else "no_login_needed", seconds=round(time.time() - t0, 1))
            if not needs_login:
                return {"status": "no_login_needed"}

            await asyncio.to_thread(client.take_control)
            ticket = secrets.token_urlsafe(16)
            done = asyncio.Event()
            TICKETS[ticket] = {"client": client, "done": done, "run": run}
            log(run, "take_control", seconds=round(time.time() - t0, 1))
            async with httpx.AsyncClient() as h:
                r = await h.post(PUSH_URL, json={"user": APP_USER, "title": "需要你登入測試網站",
                                                 "url": f"{VIEWER_BASE}/viewer/{ticket}/"}, timeout=10)
            log(run, "pushed", status=r.status_code, seconds=round(time.time() - t0, 1))

            try:
                await asyncio.wait_for(done.wait(), max(0, TOOL_BUDGET - (time.time() - t0)))
                handed_back = True
            except asyncio.TimeoutError:
                handed_back = False
            await asyncio.to_thread(client.release_control)
            log(run, "release_control", handed_back=handed_back, seconds=round(time.time() - t0, 1))
            if not handed_back:
                return {"status": "user_did_not_complete_login", "waited_seconds": round(time.time() - t0)}

            # 接手時 automation stream 被關掉，原本的 CDP 連線已失效，交還後一定重連
            try:
                await asyncio.wait_for(st["browser"].close(), 10)
            except Exception:
                pass
            st["browser"], st["page"] = await connect(pw, client, run)
            flash = await retry_once(pw, client, run, st, lambda p: p.locator("#flash").inner_text(), "read_flash")
            logged_in = "logged into a secure area" in flash
            log(run, "result", logged_in=logged_in, flash=flash.strip()[:80], seconds=round(time.time() - t0, 1))
            return {"status": "logged_in" if logged_in else "login_failed", "message": flash.strip().splitlines()[0][:100]}
    finally:
        if ticket:
            TICKETS.pop(ticket, None)
        await asyncio.to_thread(client.stop)
        log(run, "session_stopped", seconds=round(time.time() - t0, 1))


@mcp.custom_route("/viewer/{ticket}/", methods=["GET"])
async def viewer(request: Request) -> Response:
    if request.path_params["ticket"] not in TICKETS:
        return Response("連結已失效", status_code=410)
    return FileResponse(HERE / "viewer.html", headers={"Cache-Control": "no-store"})


@mcp.custom_route("/viewer/{ticket}/config", methods=["GET"])
async def viewer_config(request: Request) -> Response:
    t = TICKETS.get(request.path_params["ticket"])
    if not t:
        return JSONResponse({"error": "expired"}, status_code=410)
    signed = await asyncio.to_thread(t["client"].generate_live_view_url, 300)
    return JSONResponse({"signedUrl": signed, **VIEWPORT}, headers={"Cache-Control": "no-store"})


@mcp.custom_route("/viewer/{ticket}/event", methods=["POST"])
async def viewer_event(request: Request) -> Response:
    t = TICKETS.get(request.path_params["ticket"])
    body = await request.json()
    log(t["run"] if t else "expired", "viewer_" + body.pop("name"), **body)
    return JSONResponse({"ok": True})


@mcp.custom_route("/viewer/{ticket}/handback", methods=["POST"])
async def handback(request: Request) -> Response:
    t = TICKETS.get(request.path_params["ticket"])
    if not t:
        return JSONResponse({"error": "expired"}, status_code=410)
    log(t["run"], "handback_clicked")
    t["done"].set()
    return JSONResponse({"ok": True})


@mcp.custom_route("/dcvjs-esm/{path:path}", methods=["GET"])
async def dcv(request: Request) -> Response:
    f = (DCV_DIR / request.path_params["path"]).resolve()
    if not f.is_relative_to(DCV_DIR.resolve()) or not f.is_file():
        return Response("not found", status_code=404)
    return FileResponse(f, media_type="text/javascript" if f.suffix in (".js", ".mjs") else None)


@mcp.custom_route("/push", methods=["POST"])
async def push(request: Request) -> Response:
    """模擬 App 推播服務：只記下來，由測試者（扮演手機）讀 pushes.jsonl 打開連結。"""
    body = await request.json()
    with (HERE / "pushes.jsonl").open("a") as f:
        f.write(json.dumps({"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **body}, ensure_ascii=False) + "\n")
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
