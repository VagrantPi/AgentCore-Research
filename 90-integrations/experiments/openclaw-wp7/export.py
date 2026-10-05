"""把 CloudWatch 每分鐘指標（只保留 15 天）存進 repo：Sonnet 4.6 token 與 guardrail text unit。

用法：uv run --with boto3 python export.py   # 輸出 bedrock_metrics.json

原始 USAGE_LOGS 不在這裡匯出：WP0 刪 log group 前已整組存到
`91-work-packages/evidence/usage-logs/wp0-usage.jsonl.gz`（`scripts/dump_log_group.py`）。
每個 session 的加總見 `wp7-cost.csv`、`01-runtime/experiments/cold-start/wp1-vpc-cost.csv`。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import boto3

HERE = Path(__file__).parent
START = datetime(2026, 10, 4, 2, 40, tzinfo=timezone.utc)
END = datetime(2026, 10, 4, 10, 40, tzinfo=timezone.utc)
cw = boto3.client("cloudwatch", region_name="ap-northeast-1")


def series(ns, name, dims):
    r = cw.get_metric_statistics(Namespace=ns, MetricName=name, Dimensions=dims, StartTime=START, EndTime=END,
                                 Period=60, Statistics=["Sum"])
    return sorted(({"t": p["Timestamp"].isoformat(), "sum": p["Sum"]} for p in r["Datapoints"]), key=lambda x: x["t"])


if __name__ == "__main__":
    out = {"window": [START.isoformat(), END.isoformat()], "bedrock": {}, "guardrails": {}}
    model = [{"Name": "ModelId", "Value": "global.anthropic.claude-sonnet-4-6"}]
    for m in ("InputTokenCount", "OutputTokenCount", "Invocations"):
        out["bedrock"][m] = series("AWS/Bedrock", m, model)
    for pt in ("ContentPolicy", "TopicPolicy", "SensitiveInformationPolicy", "WordPolicy"):
        out["guardrails"][pt] = series("AWS/Bedrock/Guardrails", "TextUnitCount",
                                       [{"Name": "GuardrailPolicyType", "Value": pt}, {"Name": "Operation", "Value": "ApplyGuardrail"}])
    (HERE / "bedrock_metrics.json").write_text(json.dumps(out, indent=1))
    print({k: sum(p["sum"] for p in v) for k, v in {**out["bedrock"], **out["guardrails"]}.items()})
