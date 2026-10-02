# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""#8：把 cost_day.py 的一天用量換算成一位使用者的月費（估算）。

- Memory：event 數、檢索次數是 cost_day.py 自己計數；record 數從 API 實際列出
- Runtime：USAGE_LOGS 依 session 加總（91-work-packages/scripts/usage_cost.py），另外印出 metric 供 #5 比對
- Browser：沒實跑，用官網單價 × 假設的規格

單價：官網定價頁，2026-10-02 查。
"""
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import ACCOUNT, REGION, client, load_state

EVENT_PER_1K, RETRIEVE_PER_1K, STORE_PER_1K_MONTH = 0.25, 0.50, 0.75
VCPU_H, GB_H = 0.0895, 0.00945
BROWSER_VCPU, BROWSER_GB = 1, 4          # 假設，未實測
DAYS = 30

st = load_state()
actor = st.get("costActor", "wp5-user-cost")
dp = client("bedrock-agentcore")
records = {}
for name, sid in st["strategies"].items():
    n, tok = 0, None
    while True:
        r = dp.list_memory_records(memoryId=st["memoryId"], namespacePath=f"/strategy/{sid}/actor/{actor}/", maxResults=100,
                                   **({"nextToken": tok} if tok else {}))
        n += len(r["memoryRecordSummaries"])
        if not (tok := r.get("nextToken")):
            break
    records[name] = n
cost_days = st["costDays"]
n_days = len(cost_days)
rec_day = sum(records.values()) / n_days
print(f"{n_days} 天：event {100 * n_days}、檢索 {20 * n_days}、record {records}，平均每天 {rec_day:.1f} 筆")

# Runtime：USAGE_LOGS
root = Path(__file__).resolve().parents[4]
since = datetime.fromisoformat(cost_days[0]["startedAt"]) - timedelta(minutes=5)
until = datetime.fromisoformat(cost_days[-1]["lastInvokeAt"]) + timedelta(minutes=30)
csv = subprocess.run(["uv", "run", "-q", str(root / "91-work-packages/scripts/usage_cost.py"),
                      "--log-group", "/aws/vendedlogs/bedrock-agentcore/wp0-usage",
                      "--since", since.strftime("%Y-%m-%dT%H:%M"), "--until", until.strftime("%Y-%m-%dT%H:%M")],
                     capture_output=True, text=True, check=True).stdout
print(csv)
rows_rt = [l.split(",") for l in csv.splitlines() if any(d["session"] in l for d in cost_days)]
if len(rows_rt) != n_days:
    sys.exit(f"USAGE_LOGS 裡只找到 {len(rows_rt)} / {n_days} 個成本模擬的 session")
for r in rows_rt:
    print(f"USAGE_LOGS {r[1]}：{r[2]} 秒、{r[3]} vCPU-h、{r[4]} GB-h、${r[5]}")
secs, vcpu, gb = (sum(float(r[i]) for r in rows_rt) for i in (2, 3, 4))
rt_day = sum(float(r[5]) for r in rows_rt) / n_days

# #5：metric 只到 runtime 層級，和 USAGE_LOGS 裡同一個 runtime 所有 session 的加總比
wp0_rows = [l.split(",") for l in csv.splitlines() if l.startswith("wp0_min,")]
log_sum = {"CPUUsed-vCPUHours": sum(float(r[3]) for r in wp0_rows), "MemoryUsed-GBHours": sum(float(r[4]) for r in wp0_rows)}
cw = client("cloudwatch")
runtime_arn = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:runtime/wp0_min-HsBwOc6VWU"
for metric in ["CPUUsed-vCPUHours", "MemoryUsed-GBHours"]:
    pts = cw.get_metric_statistics(Namespace="AWS/Bedrock-AgentCore", MetricName=metric,
                                   Dimensions=[{"Name": "Service", "Value": "AgentCore.Runtime"},
                                               {"Name": "Resource", "Value": runtime_arn}],
                                   StartTime=since, EndTime=until, Period=300, Statistics=["Sum"])["Datapoints"]
    m = sum(p["Sum"] for p in pts)
    print(f"#5 {metric}：metric {m:.6f}、USAGE_LOGS {log_sum[metric]:.6f}（{len(wp0_rows)} 個 session），"
          f"差 {(log_sum[metric] - m) / m * 100:+.2f}%")
print(f"成本 session 合計：{secs:.0f} 秒、{vcpu:.6f} vCPU-h、{gb:.6f} GB-h；平均每天 ${rt_day:.6f}")

mem_event = 100 * DAYS / 1000 * EVENT_PER_1K
mem_retrieve = 20 * DAYS / 1000 * RETRIEVE_PER_1K
mem_store = rec_day * DAYS / 2 / 1000 * STORE_PER_1K_MONTH   # 一個月內線性累積，平均存量 = 月底的一半
browser = 10 / 60 * DAYS * (BROWSER_VCPU * VCPU_H + BROWSER_GB * GB_H)
rows = [("Memory 短期（event）", mem_event), ("Memory 檢索", mem_retrieve), ("Memory 長期儲存", mem_store),
        ("Runtime", rt_day * DAYS), ("Browser（假設 1 vCPU、4 GB）", browser)]
for k, v in rows:
    print(f"{k}：${v:.4f} / 月")
print(f"合計：${sum(v for _, v in rows):.4f} / 月")
