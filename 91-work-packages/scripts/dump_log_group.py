# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""把整個 log group 的訊息存成 .jsonl.gz（一行一則原始訊息），刪除 log group 前用。

用法：uv run dump_log_group.py <log group> <輸出檔.jsonl.gz>

USAGE_LOGS 的 log group 只保留 14 天，刪除或過期後就無法重算費用。
存下來的檔案可以直接餵給 usage_cost.aggregate()（它會跳過非 JSON 的權限確認訊息）。
"""
import gzip
import sys
from datetime import datetime, timezone

import boto3

group, out = sys.argv[1], sys.argv[2]
logs = boto3.client("logs", region_name="ap-northeast-1")
n, first, last = 0, None, None
with gzip.open(out, "wt") as f:
    for page in logs.get_paginator("filter_log_events").paginate(logGroupName=group):
        for e in page["events"]:
            f.write(e["message"] + "\n")
            n += 1
            first = e["timestamp"] if first is None else min(first, e["timestamp"])
            last = e["timestamp"] if last is None else max(last, e["timestamp"])
fmt = lambda t: datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if t else "—"
print(f"{group}：{n} 筆，{fmt(first)} – {fmt(last)} → {out}")
