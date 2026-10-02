# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""把 wp1_cost_v1_img_pub 的原始 USAGE_LOGS 存成 jsonl.gz，log group 只保留 14 天，留給之後分析。

用法：uv run dump_usage_logs.py   # 輸出 wp1_cost_usage_logs.jsonl.gz
"""

import gzip
import json

import boto3

logs = boto3.client("logs", region_name="ap-northeast-1")
n = 0
with gzip.open("wp1_cost_usage_logs.jsonl.gz", "wt") as f:
    for page in logs.get_paginator("filter_log_events").paginate(
            logGroupName="/aws/vendedlogs/bedrock-agentcore/wp0-usage",
            startTime=1790923380000,  # 2026-10-02T06:43:00Z，乾跑開始前
            filterPattern='"wp1_cost_v1_img_pub"'):
        for e in page["events"]:
            f.write(json.dumps({"timestamp": e["timestamp"], "ingestion": e["ingestionTime"],
                                "stream": e["logStreamName"], **json.loads(e["message"])}) + "\n")
            n += 1
print(n)
