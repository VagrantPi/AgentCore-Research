# /// script
# requires-python = ">=3.12"
# dependencies = ["bedrock-agentcore", "playwright", "boto3"]
# ///
"""Browser 視窗尺寸（與有沒有開 Live View）對費用的影響：USAGE_LOGS 實測。

  uv run viewport_cost.py setup                      # 建自訂 Browser wp6_viewport，USAGE_LOGS 投遞到 wp0-usage-dst
  uv run viewport_cost.py run --round 1 --viewport 390x844 [--liveview <sim udid> --port 8771]
  uv run viewport_cost.py report                     # session 結束滿 1 小時後再跑
  uv run viewport_cost.py teardown

每個 run 開一個 session，跑同一段工作負載 WORKLOAD_SECONDS 秒後立刻 stop()，記到 viewport_runs.csv。
"""
import argparse
import csv
import datetime as dt
import json
import statistics
import subprocess
import sys
import threading
import time
from collections import defaultdict
from http.server import ThreadingHTTPServer
from pathlib import Path

import boto3
from bedrock_agentcore.tools.browser_client import BrowserClient
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "91-work-packages" / "scripts"))
from usage_cost import PRICE_GB_HOUR, PRICE_VCPU_HOUR, aggregate, fetch  # noqa: E402
import takeover  # noqa: E402

takeover.OUT = HERE / "viewport_viewer_events.csv"  # viewer 事件不要混進接手實驗的 results.csv

REGION = "ap-northeast-1"
NAME = "wp6_viewport"
SRC = "wp6_viewport-usage-src"
DST = "wp0-usage-dst"
LOG_GROUP = "/aws/vendedlogs/bedrock-agentcore/wp0-usage"
TAGS = {"wp": "WP6", "owner": "kais", "project": "hyfai"}
RUNS = HERE / "viewport_runs.csv"
WORKLOAD_SECONDS = 300
PAGES = [
    "https://zh.wikipedia.org/",
    "https://zh.wikipedia.org/wiki/%E5%8F%B0%E5%8C%97101",
    "https://github.com/explore",
    "https://www.bbc.com/news",
]


def ctl():
    return boto3.client("bedrock-agentcore-control", region_name=REGION)


def find_browser():
    for b in ctl().list_browsers(type="CUSTOM").get("browserSummaries", []):
        if b.get("name") == NAME:
            return b
    return None


def cmd_setup(_):
    c = ctl()
    b = find_browser()
    if b is None:
        b = c.create_browser(name=NAME, networkConfiguration={"networkMode": "PUBLIC"}, tags=TAGS)
        print("created", b["browserArn"])
    bid = b["browserId"]
    while (status := c.get_browser(browserId=bid)["status"]) not in ("READY",) and not status.endswith("FAILED"):
        time.sleep(5)
    arn = c.get_browser(browserId=bid)["browserArn"]
    print("status", status, arn)
    logs = boto3.client("logs", region_name=REGION)
    logs.put_delivery_source(name=SRC, resourceArn=arn, logType="USAGE_LOGS", tags=TAGS)
    dst_arn = logs.get_delivery_destination(name=DST)["deliveryDestination"]["arn"]
    try:
        print("delivery", logs.create_delivery(deliverySourceName=SRC, deliveryDestinationArn=dst_arn, tags=TAGS)["delivery"]["id"])
    except logs.exceptions.ConflictException:
        print("delivery exists")


def cmd_teardown(_):
    logs = boto3.client("logs", region_name=REGION)
    for d in logs.describe_deliveries().get("deliveries", []):
        if d["deliverySourceName"] == SRC:
            logs.delete_delivery(id=d["id"])
            print("deleted delivery", d["id"])
    try:
        logs.delete_delivery_source(name=SRC)
        print("deleted delivery source")
    except logs.exceptions.ResourceNotFoundException:
        pass
    b = find_browser()
    if b:
        ctl().delete_browser(browserId=b["browserId"])
        print("deleted browser", b["browserId"])


def workload(page, deadline: float) -> int:
    loaded = 0
    while time.time() < deadline:
        for url in PAGES:
            if time.time() >= deadline:
                break
            try:
                print(f"{time.time() - deadline + WORKLOAD_SECONDS:6.1f}s goto {url}", flush=True)
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                print(f"{time.time() - deadline + WORKLOAD_SECONDS:6.1f}s loaded", flush=True)
                loaded += 1
                for _ in range(20):
                    if time.time() >= deadline:
                        break
                    # 第 1 輪用 page.mouse.wheel，390×844＋Live View 那個 session 卡到逾時；改用 scrollBy
                    page.evaluate("window.scrollBy(0, 400)")
                    page.wait_for_timeout(500)
            except Exception as e:
                print("page error", url, type(e).__name__, flush=True)
    return loaded


def cmd_run(a):
    w, h = map(int, a.viewport.split("x"))
    bid = find_browser()["browserId"]
    client = BrowserClient(REGION)
    session_id = client.start(identifier=bid, viewport={"width": w, "height": h}, session_timeout_seconds=360)
    started = time.time()
    events = []
    server = None
    if a.liveview:
        # viewer server 在背景執行緒；handler 只用 boto 簽 URL，不碰 Playwright
        shim = type("S", (), {"client": client, "width": w, "height": h, "run": f"r{a.round}-{a.viewport}-lv"})
        server = ThreadingHTTPServer(("127.0.0.1", a.port), takeover.make_handler(shim, Path.home() / "WS/hephclaw/backend/browser-assets/dcvjs-esm"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        subprocess.run(["xcrun", "simctl", "openurl", a.liveview, f"http://localhost:{a.port}/"], check=True)
    with sync_playwright() as pw:
        ws_url, headers = client.generate_ws_headers()
        browser = pw.chromium.connect_over_cdp(ws_url, headers=headers)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(30000)
        page.on("dialog", lambda d: (print("dialog", d.type, d.message[:80], flush=True), d.dismiss()))
        loaded = workload(page, started + WORKLOAD_SECONDS)
        try:
            browser.close()
        except Exception:
            pass
    client.stop()
    stopped = time.time()
    if server:
        server.shutdown()
    new = not RUNS.exists()
    with RUNS.open("a", newline="") as f:
        wr = csv.writer(f)
        if new:
            wr.writerow(["round", "viewport", "liveview", "session_id", "started_utc", "stopped_utc", "pages_loaded"])
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec="seconds")
        wr.writerow([a.round, a.viewport, bool(a.liveview), session_id, iso(started), iso(stopped), loaded])
    print("done", a.viewport, "liveview" if a.liveview else "", loaded, "pages", round(stopped - started), "s", flush=True)


def cmd_report(a):
    runs = [r for r in csv.DictReader(RUNS.open()) if int(r["round"]) >= a.min_round]
    since = min(dt.datetime.fromisoformat(r["started_utc"]) for r in runs) - dt.timedelta(minutes=5)
    totals = aggregate(fetch(LOG_GROUP, REGION, since, None))
    by_session = {sid: v for (_, sid), v in totals.items()}
    groups = defaultdict(list)
    print("viewport,liveview,round,session_id,seconds,vcpu_hours,gb_hours,usd,usd_per_hour,avg_vcpu,avg_gb")
    for r in runs:
        v = by_session.get(r["session_id"])
        if not v:
            print(f"{r['viewport']},{r['liveview']},{r['round']},{r['session_id']},MISSING")
            continue
        sec, vcpu, gb = v
        if sec > WORKLOAD_SECONDS + 30:
            print(f"{r['viewport']},{r['liveview']},{r['round']},{r['session_id']},{sec:.0f},INVALID（超過工作負載時間）")
            continue
        usd = vcpu * PRICE_VCPU_HOUR + gb * PRICE_GB_HOUR
        hours = sec / 3600
        row = (usd / hours, vcpu / hours, gb / hours)
        groups[(r["viewport"], r["liveview"])].append(row)
        print(f"{r['viewport']},{r['liveview']},{r['round']},{r['session_id']},{sec:.0f},{vcpu:.6f},{gb:.6f},{usd:.6f},{row[0]:.4f},{row[1]:.3f},{row[2]:.3f}")
    print("\nviewport,liveview,n,usd_per_hour_mean,min,max,avg_vcpu_mean,avg_gb_mean")
    for (vp, lv), rows in sorted(groups.items()):
        per_h = [x[0] for x in rows]
        print(f"{vp},{lv},{len(rows)},{statistics.mean(per_h):.4f},{min(per_h):.4f},{max(per_h):.4f},"
              f"{statistics.mean(x[1] for x in rows):.3f},{statistics.mean(x[2] for x in rows):.3f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    sub.add_parser("teardown")
    rp = sub.add_parser("report")
    rp.add_argument("--min-round", type=int, default=2, help="第 1 輪的工作負載不同（mouse.wheel），預設不採用")
    r = sub.add_parser("run")
    r.add_argument("--round", type=int, required=True)
    r.add_argument("--viewport", required=True)
    r.add_argument("--liveview", help="模擬器 UDID；給了就用它的 Safari 開 Live View")
    r.add_argument("--port", type=int, default=8771)
    a = p.parse_args()
    {"setup": cmd_setup, "teardown": cmd_teardown, "report": cmd_report, "run": cmd_run}[a.cmd](a)
