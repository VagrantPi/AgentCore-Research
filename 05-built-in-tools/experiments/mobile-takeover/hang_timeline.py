# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3"]
# ///
"""把幾個 session 的 USAGE_LOGS 依秒排成時間線（每 10 秒加總 vCPU 秒數），看卡住之後遠端 Chrome 還有沒有在動。

用法：uv run hang_timeline.py <session_id> [...]
"""
import datetime as dt
import json
import sys
from collections import defaultdict

import boto3

LOG_GROUP = "/aws/vendedlogs/bedrock-agentcore/wp0-usage"
since = int(dt.datetime(2026, 10, 4, 9, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)
logs = boto3.client("logs", region_name="ap-northeast-1")

for sid in sys.argv[1:]:
    recs = []
    for page in logs.get_paginator("filter_log_events").paginate(logGroupName=LOG_GROUP, startTime=since, filterPattern=f'"{sid}"'):
        for e in page["events"]:
            try:
                r = json.loads(e["message"])
            except json.JSONDecodeError:
                continue
            if r["attributes"].get("session.id") == sid:
                vcpu_h = sum(v for k, v in r["metrics"].items() if k.endswith("vcpu.hours.used"))
                gb_h = sum(v for k, v in r["metrics"].items() if k.endswith("gb_hours.used"))
                recs.append((r.get("event_timestamp") or e["timestamp"], vcpu_h * 3600, gb_h * 3600))
    recs.sort()
    if not recs:
        print(sid, "沒有紀錄")
        continue
    t0 = recs[0][0]
    buckets = defaultdict(lambda: [0.0, 0.0, 0])
    for ts, vcpu_s, gb_s in recs:
        b = buckets[int((ts - t0) / 1000 // 10)]
        b[0] += vcpu_s
        b[1] += gb_s
        b[2] += 1
    print(f"== {sid}（{len(recs)} 秒）  每 10 秒：平均 vCPU、平均 GB")
    print("  ".join(f"{k * 10:>3}s:{v[0] / v[2]:.2f}/{v[1] / v[2]:.1f}" for k, v in sorted(buckets.items())))
