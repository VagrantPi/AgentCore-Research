# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""WP1 #10 成本情境：N 位使用者各用一個固定 session，每 5 分鐘呼叫一次，量實際用量。

子命令：
  setup     建立 runtime（閒置逾時 30 分鐘）與 USAGE_LOGS 投遞（送到 WP0 的 wp0-usage-dst）
  run       跑負載，每次呼叫寫一列到 CSV；結束時不 stop session，讓它自然閒置逾時
  cleanup   刪除 delivery、delivery source、runtime

計畫見 WP1 回填區；費用用 91-work-packages/scripts/usage_cost.py 從 USAGE_LOGS 算。

用法：
  uv run cost_scenario.py setup
  uv run cost_scenario.py run --users 2 --calls 2 --interval 20 --label dry --stop --out cost_dry.csv   # 乾跑
  nohup caffeinate -dims uv run cost_scenario.py run > cost_scenario.log 2>&1 &                         # 正式
  uv run cost_scenario.py cleanup
"""

import argparse
import csv
import json
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

HERE = Path(__file__).parent
NAME = "wp1_cost_v1_img_pub"
SRC = "wp1_cost-usage-src"
DST = "wp0-usage-dst"
ROLE = "arn:aws:iam::050571774557:role/wp/wp0-runtime-exec"
IMAGE = "050571774557.dkr.ecr.ap-northeast-1.amazonaws.com/wp-agentcore-coldstart:wp1"
LIFECYCLE = {"idleRuntimeSessionTimeout": 1800, "maxLifetime": 28800}
TAGS = {"wp": "WP1", "owner": "kais", "project": "hyfai"}


def ctl(region):
    return boto3.client("bedrock-agentcore-control", region_name=region)


def find_runtime(c):
    for page in c.get_paginator("list_agent_runtimes").paginate():
        for r in page["agentRuntimes"]:
            if r["agentRuntimeName"] == NAME:
                return r
    return None


def cmd_setup(args):
    c = ctl(args.region)
    r = find_runtime(c)
    if r:
        print(f"runtime exists: {r['agentRuntimeArn']}")
        arn, rid = r["agentRuntimeArn"], r["agentRuntimeId"]
    else:
        resp = c.create_agent_runtime(
            agentRuntimeName=NAME, roleArn=ROLE,
            agentRuntimeArtifact={"containerConfiguration": {"containerUri": IMAGE}},
            networkConfiguration={"networkMode": "PUBLIC"}, lifecycleConfiguration=LIFECYCLE,
            platformVersion="V1", tags=TAGS)
        arn, rid = resp["agentRuntimeArn"], resp["agentRuntimeId"]
        print(f"created {arn}")
    while (status := c.get_agent_runtime(agentRuntimeId=rid)["status"]) not in ("READY",) \
            and not status.endswith("FAILED"):
        time.sleep(10)
    print(f"status {status}")

    logs = boto3.client("logs", region_name=args.region)
    logs.put_delivery_source(name=SRC, resourceArn=arn, logType="USAGE_LOGS", tags=TAGS)
    dst_arn = logs.get_delivery_destination(name=DST)["deliveryDestination"]["arn"]
    try:
        d = logs.create_delivery(deliverySourceName=SRC, deliveryDestinationArn=dst_arn, tags=TAGS)
        print(f"delivery {d['delivery']['id']}")
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConflictException":
            raise
        print("delivery exists")


def cmd_run(args):
    arn = find_runtime(ctl(args.region))["agentRuntimeArn"]
    # 失敗不重試：要看的是真實成功率，重試會掩蓋漏打
    data = boto3.client("bedrock-agentcore", config=Config(
        region_name=args.region, read_timeout=120, retries={"total_max_attempts": 1}))
    sessions = [f"wp1-cost-{args.label}-u{u + 1:02d}-{uuid.uuid4()}" for u in range(args.users)]
    t0 = time.time()
    lock = threading.Lock()
    out = (HERE / args.out).open("w", newline="")
    w = csv.DictWriter(out, fieldnames=["ts_utc", "user", "call", "session_id", "status",
                                        "latency_ms", "boot_token", "first_request"])
    w.writeheader()
    print(f"start {datetime.fromtimestamp(t0, timezone.utc):%Y-%m-%dT%H:%M:%S}Z "
          f"users={args.users} calls={args.calls} interval={args.interval}s", flush=True)

    def user(u):
        for k in range(args.calls):
            time.sleep(max(0.0, t0 + k * args.interval + u * args.stagger - time.time()))
            row = {"ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "user": u + 1, "call": k + 1, "session_id": sessions[u]}
            t = time.perf_counter()
            try:
                resp = data.invoke_agent_runtime(
                    agentRuntimeArn=arn, runtimeSessionId=sessions[u], qualifier="DEFAULT",
                    contentType="application/json", payload=b'{"prompt":"ping"}')
                body = json.loads(resp["response"].read())
                row.update(status="ok", boot_token=body["boot_token"],
                           first_request=body["first_request"])
            except Exception as e:  # 記錄任何錯誤後繼續，下一輪照打
                row["status"] = e.response["Error"]["Code"] if isinstance(e, ClientError) else type(e).__name__
            row["latency_ms"] = round((time.perf_counter() - t) * 1000)
            with lock:
                w.writerow(row)
                out.flush()
            print(f"u{u + 1:02d} #{k + 1} {row['status']} {row['latency_ms']}ms", flush=True)

    with ThreadPoolExecutor(max_workers=args.users) as pool:
        list(pool.map(user, range(args.users)))
    out.close()
    end = datetime.now(timezone.utc)
    print(f"last call {end:%Y-%m-%dT%H:%M:%S}Z", flush=True)

    if args.stop:  # 只給乾跑用：正式情境要讓 session 自然閒置逾時
        for sid in sessions:
            data.stop_runtime_session(agentRuntimeArn=arn, runtimeSessionId=sid, qualifier="DEFAULT")
        print("stopped all sessions")
    summarize(HERE / args.out)


def summarize(path):
    ok, boots, total = defaultdict(int), defaultdict(set), 0
    with path.open() as f:
        for r in csv.DictReader(f):
            total += 1
            if r["status"] == "ok":
                ok[r["user"]] += 1
                boots[r["user"]].add(r["boot_token"])
    print(f"\nok {sum(ok.values())}/{total}")
    for u in sorted(ok, key=int):
        print(f"user {u}: ok={ok[u]} boot_tokens={len(boots[u])}")


def cmd_cleanup(args):
    logs = boto3.client("logs", region_name=args.region)
    for d in logs.describe_deliveries()["deliveries"]:
        if d["deliverySourceName"] == SRC:
            logs.delete_delivery(id=d["id"])
            print(f"deleted delivery {d['id']}")
    try:
        logs.delete_delivery_source(name=SRC)
        print(f"deleted {SRC}")
    except ClientError as e:
        print(f"{SRC}: {e.response['Error']['Code']}")
    c = ctl(args.region)
    if r := find_runtime(c):
        c.delete_agent_runtime(agentRuntimeId=r["agentRuntimeId"])
        print(f"deleted {NAME}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--region", default="ap-northeast-1")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    r = sub.add_parser("run")
    r.add_argument("--users", type=int, default=20)
    r.add_argument("--calls", type=int, default=24, help="每位使用者的呼叫次數")
    r.add_argument("--interval", type=float, default=300, help="同一位使用者兩次呼叫的間隔秒數")
    r.add_argument("--stagger", type=float, default=15, help="使用者之間錯開的秒數")
    r.add_argument("--label", default="run", help="放進 session ID，區分乾跑與正式")
    r.add_argument("--out", default="cost_scenario.csv")
    r.add_argument("--stop", action="store_true", help="結束後 stop 所有 session（乾跑用）")
    s = sub.add_parser("summary")
    s.add_argument("--out", default="cost_scenario.csv")
    sub.add_parser("cleanup")
    args = p.parse_args()
    {"setup": cmd_setup, "run": cmd_run, "cleanup": cmd_cleanup,
     "summary": lambda a: summarize(HERE / a.out)}[args.cmd](args)


if __name__ == "__main__":
    main()
