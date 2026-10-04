# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""把 WP5 的原始量測資料存進 results/，避免 log 過期（USAGE_LOGS 投遞的 log group 只保留 14 天）後無法重算。

- usage-logs-wp5.jsonl.gz：USAGE_LOGS 裡所有 session ID 以 wp5- 開頭的原始紀錄（一行一筆 = 一個 session 的一秒）
- metrics-wp0_min.csv：wp0_min 的 CPUUsed-vCPUHours、MemoryUsed-GBHours，5 分鐘一點
- cost-days.json：1 天版與 3 天版每天的 session ID、開始與最後呼叫時間（cost_report.py 的輸入）
"""
import csv
import gzip
import json
import pathlib
from datetime import datetime, timezone

from common import ACCOUNT, REGION, client, load_state

OUT = pathlib.Path(__file__).with_name("results")
SINCE = datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc)    # WP5 第一次呼叫 Runtime 之前
UNTIL = datetime(2026, 10, 4, 13, 0, tzinfo=timezone.utc)   # 3 天版最後一個 session 結束之後

logs = client("logs")
n = 0
with gzip.open(OUT / "usage-logs-wp5.jsonl.gz", "wt") as f:
    for page in logs.get_paginator("filter_log_events").paginate(
            logGroupName="/aws/vendedlogs/bedrock-agentcore/wp0-usage",
            startTime=int(SINCE.timestamp() * 1000), endTime=int(UNTIL.timestamp() * 1000),
            filterPattern='"wp5-"'):   # 欄位名有點號，JSON filter 寫不出來，先文字比對再精確篩
        for e in page["events"]:
            if not e["message"].startswith("{"):
                continue
            if json.loads(e["message"])["attributes"].get("session.id", "").startswith("wp5-"):
                f.write(e["message"] + "\n")
                n += 1
print("usage-logs-wp5.jsonl.gz", n, "筆")

cw = client("cloudwatch")
runtime_arn = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:runtime/wp0_min-HsBwOc6VWU"
rows = {}
for metric in ["CPUUsed-vCPUHours", "MemoryUsed-GBHours"]:
    pts = cw.get_metric_statistics(Namespace="AWS/Bedrock-AgentCore", MetricName=metric,
                                   Dimensions=[{"Name": "Service", "Value": "AgentCore.Runtime"},
                                               {"Name": "Resource", "Value": runtime_arn}],
                                   StartTime=SINCE, EndTime=UNTIL, Period=300, Statistics=["Sum"])["Datapoints"]
    for p in pts:
        rows.setdefault(p["Timestamp"], {})[metric] = p["Sum"]
with open(OUT / "metrics-wp0_min.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp_utc", "CPUUsed-vCPUHours", "MemoryUsed-GBHours"])
    for ts in sorted(rows):
        w.writerow([ts.strftime("%Y-%m-%dT%H:%M"), rows[ts].get("CPUUsed-vCPUHours", 0), rows[ts].get("MemoryUsed-GBHours", 0)])
print("metrics-wp0_min.csv", len(rows), "點（只含 wp0_min；同時段 WP1 等其他 runtime 不在內）")

st = load_state()
days = {
    "1day": {"actor": "wp5-user-cost", "session": st["costRuntimeSession"],
             "startedAt": st["costStartedAt"], "lastInvokeAt": st["costLastInvokeAt"]},
    "3day": {"actor": st["costActor"], "memoryId": st["memoryId"], "days": st["costDays"]},
}
old = OUT / "cost-days.json"
if old.exists():   # record 數是 Memory 刪除前記下的，重新匯出時保留
    days["3day"] |= {k: v for k, v in json.loads(old.read_text())["3day"].items() if k.startswith(("records", "_records"))}
old.write_text(json.dumps(days, ensure_ascii=False, indent=1))
print("cost-days.json")
