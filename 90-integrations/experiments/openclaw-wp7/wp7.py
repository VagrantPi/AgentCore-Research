"""WP7 量測：直接呼叫 InvokeAgentRuntime 模擬使用者（取代範例的 Router Lambda）。

payload 照範例 lambda/router/index.py：{"action":"chat","userId","actorId","channel","message"}。
channel 用 "test"，容器就不會自己去打 Telegram。

子命令：
  first     #1、#2：新使用者第一則訊息的回覆時間，以及等到完整 OpenClaw 後的回覆時間 → first.csv
  burst     #1 對照：N 位新使用者同時發第一則訊息 → burst.csv
  restore   #3：先在 S3 塞 500 個小檔，再用新 session 發訊，量到 OpenClaw ready 的時間 → restore.csv
  idle      #3 對照：同一個 session 等閒置逾時後再發訊 → restore.csv
  load      #4：10 位使用者各聊 10 輪 → load.csv
  boundary  #5／#6：範圍外的請求，完整回覆存 boundary.jsonl
  logs      從 Runtime log 撈指定時間窗的行（restore、token、tool）
  tokens    加總 proxy log 的 token 數
"""

import argparse
import csv
import hashlib
import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config

from vpc import REGION, load

HERE = Path(__file__).parent
BUCKET = "wp7-openclaw-050571774557"
CFG = Config(region_name=REGION, read_timeout=900, retries={"mode": "standard", "total_max_attempts": 2})
data = boto3.client("bedrock-agentcore", config=CFG)
LOAD_PROMPTS = [
    "嗨，今天過得怎麼樣？", "推薦一本適合週末讀的書", "幫我想三個晚餐的點子", "用一句話解釋什麼是通膨",
    "給我一個早上提神的小建議", "幫我把「明天開會改到下午三點」寫成禮貌的訊息", "推薦一個適合新手的運動",
    "東京有什麼值得去的博物館？", "幫我想一個寵物名字", "謝謝，今天就聊到這裡",
]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def user(name):
    actor = f"test:{name}"
    uid = "user_" + hashlib.sha256(actor.encode()).hexdigest()[:16]
    return uid, actor


def new_session(uid):
    return f"ses_{uid}_{uuid.uuid4().hex[:12]}".ljust(33, "0")


def invoke(sid, payload):
    arn = load()["runtime"]["arn"]
    t0 = time.perf_counter()
    r = data.invoke_agent_runtime(agentRuntimeArn=arn, runtimeSessionId=sid, qualifier="DEFAULT",
                                  contentType="application/json", accept="application/json",
                                  payload=json.dumps(payload).encode())
    body = r["response"].read().decode()
    ms = round((time.perf_counter() - t0) * 1000)
    try:
        return ms, json.loads(body)
    except json.JSONDecodeError:
        return ms, {"raw": body}


def chat(sid, name, message):
    uid, actor = user(name)
    return invoke(sid, {"action": "chat", "userId": uid, "actorId": actor, "channel": "test", "message": message})


def status(sid):
    _, body = invoke(sid, {"action": "status"})
    return json.loads(body.get("response", "{}"))


def wait_ready(sid, t0, timeout=420):
    while time.time() - t0 < timeout:
        st = status(sid)
        if st.get("openclawReady"):
            return round(time.time() - t0, 1), st
        time.sleep(5)
    return None, status(sid)


def append(path, row):
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
    print(row)


def stop(sid):
    data.stop_runtime_session(agentRuntimeArn=load()["runtime"]["arn"], runtimeSessionId=sid, qualifier="DEFAULT")


def cmd_first(a):
    for name in a.users.split(","):
        uid, _ = user(name)
        sid = new_session(uid)
        t0 = time.time()
        first_ms, b1 = chat(sid, name, "你好，請用兩句話自我介紹")
        ready_s, st = wait_ready(sid, t0)
        full_ms, b2 = chat(sid, name, "你剛剛說了什麼？再用一句話總結")
        append(HERE / "first.csv", {
            "at": now(), "user": name, "session": sid, "first_reply_ms": first_ms,
            "openclaw_ready_s": ready_s, "full_reply_ms": full_ms,
            "first_msg_to_full_reply_s": round(time.time() - t0, 1),
            "first_reply": b1.get("response", b1)[:120], "full_reply": b2.get("response", b2)[:120],
        })
        if not a.keep:
            stop(sid)


def cmd_burst(a):
    """#1 對照：N 位新使用者同時發第一則訊息，看預熱池用光後的首則回覆時間。"""
    def one(name):
        uid, _ = user(name)
        sid = new_session(uid)
        ms, body = chat(sid, name, "你好，請用兩句話自我介紹")
        stop(sid)
        return {"at": now(), "user": name, "session": sid, "first_reply_ms": ms,
                "ok": "response" in body, "burst": a.n}
    with ThreadPoolExecutor(a.n) as ex:
        for row in ex.map(one, [f"{a.prefix}{i:02d}" for i in range(1, a.n + 1)]):
            append(HERE / "burst.csv", row)


def seed(name, n):
    """在 S3 的 {namespace}/.openclaw/workspace/ 放 n 個小檔（namespace = actorId 的 ':' 換成 '_'）。"""
    s3 = boto3.client("s3", region_name=REGION)
    prefix = f"test_{name}/.openclaw/workspace/notes"
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(lambda i: s3.put_object(Bucket=BUCKET, Key=f"{prefix}/note-{i:03d}.md",
                                            Body=f"# note {i}\n\n" + "lorem ipsum " * 20), range(n)))
    return prefix


def cmd_restore(a):
    for name in a.users.split(","):
        prefix = seed(name, a.files)
        uid, _ = user(name)
        sid = new_session(uid)
        t0 = time.time()
        first_ms, _ = chat(sid, name, "你好")
        ready_s, st = wait_ready(sid, t0)
        full_ms, _ = chat(sid, name, "我的工作區 notes 資料夾裡有幾個檔案？")
        append(HERE / "restore.csv", {
            "at": now(), "kind": "new_session", "user": name, "session": sid, "seeded": f"s3://{BUCKET}/{prefix} x{a.files}",
            "first_reply_ms": first_ms, "openclaw_ready_s": ready_s, "full_reply_ms": full_ms,
            "openclaw_logs_tail": " | ".join(st.get("openclawLogs", [])[-3:])[:200],
        })
        if not a.keep:
            stop(sid)


def cmd_idle(a):
    """同一個 session：先發訊等 ready，閒置超過 idle timeout 後再發訊。"""
    name = a.user
    prefix = seed(name, a.files)
    uid, _ = user(name)
    sid = new_session(uid)
    t0 = time.time()
    chat(sid, name, "你好")
    ready1, _ = wait_ready(sid, t0)
    print(f"first ready {ready1}s; idling {a.wait}s ...", flush=True)
    time.sleep(a.wait)
    t1 = time.time()
    first_ms, _ = chat(sid, name, "我回來了，notes 資料夾裡有幾個檔案？")
    ready2, st = wait_ready(sid, t1)
    append(HERE / "restore.csv", {
        "at": now(), "kind": f"same_session_after_idle_{a.wait}s", "user": name, "session": sid,
        "seeded": f"s3://{BUCKET}/{prefix} x{a.files}", "first_reply_ms": first_ms, "openclaw_ready_s": ready2,
        "full_reply_ms": "", "openclaw_logs_tail": f"first session ready {ready1}s",
    })
    stop(sid)


def run_user(name, rounds, delay):
    time.sleep(delay)
    uid, _ = user(name)
    sid = new_session(uid)
    for i, prompt in enumerate(LOAD_PROMPTS[:rounds], 1):
        ms, body = chat(sid, name, prompt)
        append(HERE / "load.csv", {"at": now(), "user": name, "session": sid, "round": i, "latency_ms": ms,
                                   "reply": str(body.get("response", body))[:80].replace("\n", " ")})
    stop(sid)


def cmd_load(a):
    names = [f"{a.prefix}{i:02d}" for i in range(1, a.users + 1)]
    with ThreadPoolExecutor(a.users) as ex:
        list(ex.map(lambda p: run_user(p[1], a.rounds, p[0] * a.stagger), enumerate(names)))


BOUNDARY = ["查今天的新聞，列三則標題", "幫我寫一支 Python 爬蟲抓 https://example.com 的頁面標題，並且實際執行給我看結果"]


def cmd_boundary(a):
    name = a.user
    uid, actor = user(name)
    sid = new_session(uid)
    t0 = time.time()
    if a.wait_full:
        invoke(sid, {"action": "warmup", "userId": uid, "actorId": actor, "channel": "test"})
        ready_s, _ = wait_ready(sid, t0)
        print("openclaw ready", ready_s)
    for prompt in a.prompt or BOUNDARY:
        ms, body = chat(sid, name, prompt)
        rec = {"at": now(), "tag": a.tag, "user": name, "session": sid, "prompt": prompt, "latency_ms": ms, "full": a.wait_full,
               "status": status(sid), "reply": body}
        with (HERE / "boundary.jsonl").open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(ms, str(body.get("response", body))[:400])
    stop(sid)


def log_group():
    return f"/aws/bedrock-agentcore/runtimes/{load()['runtime']['id']}-DEFAULT"


def fetch(since, until, pattern):
    logs = boto3.client("logs", region_name=REGION)
    kw = {"logGroupName": log_group(), "startTime": int(datetime.fromisoformat(since).replace(tzinfo=timezone.utc).timestamp() * 1000)}
    if until:
        kw["endTime"] = int(datetime.fromisoformat(until).replace(tzinfo=timezone.utc).timestamp() * 1000)
    if pattern:
        kw["filterPattern"] = pattern
    for page in logs.get_paginator("filter_log_events").paginate(**kw):
        for e in page["events"]:
            yield e


def cmd_logs(a):
    for e in fetch(a.since, a.until, a.pattern):
        ts = datetime.fromtimestamp(e["timestamp"] / 1000, timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        print(ts, e["logStreamName"][-12:], e["message"].rstrip()[:a.width])


def cmd_tokens(a):
    pat = re.compile(r"\[proxy\] (?:Stream complete|Response): (\d+)in/(\d+)out")
    tin = tout = calls = 0
    for e in fetch(a.since, a.until, '"[proxy]"'):
        m = pat.search(e["message"])
        if m:
            tin, tout, calls = tin + int(m[1]), tout + int(m[2]), calls + 1
    print(json.dumps({"since": a.since, "until": a.until, "calls": calls, "input_tokens": tin, "output_tokens": tout}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("first"); f.add_argument("--users", required=True); f.add_argument("--keep", action="store_true")
    u = sp.add_parser("burst"); u.add_argument("--n", type=int, default=20); u.add_argument("--prefix", default="b")
    r = sp.add_parser("restore"); r.add_argument("--users", required=True); r.add_argument("--files", type=int, default=500); r.add_argument("--keep", action="store_true")
    i = sp.add_parser("idle"); i.add_argument("--user", required=True); i.add_argument("--files", type=int, default=500); i.add_argument("--wait", type=int, default=1900)
    l = sp.add_parser("load"); l.add_argument("--users", type=int, default=10); l.add_argument("--rounds", type=int, default=10)
    l.add_argument("--stagger", type=float, default=15); l.add_argument("--prefix", default="load")
    b = sp.add_parser("boundary"); b.add_argument("--user", required=True); b.add_argument("--tag", required=True); b.add_argument("--wait-full", action="store_true")
    b.add_argument("--prompt", action="append", help="自訂問題，可重複；省略時用 BOUNDARY")
    g = sp.add_parser("logs"); g.add_argument("--since", required=True); g.add_argument("--until"); g.add_argument("--pattern"); g.add_argument("--width", type=int, default=300)
    t = sp.add_parser("tokens"); t.add_argument("--since", required=True); t.add_argument("--until")
    a = p.parse_args()
    globals()[f"cmd_{a.cmd}"](a)
