"""WP7 #4：用 CloudWatch metric 對帳模型 token 與 guardrail text unit（proxy log 是主要來源，這裡是交叉驗證）。

用法：uv run --with boto3 python metrics.py 2026-10-04T03:03 2026-10-04T03:07
"""

import json
import sys
from datetime import datetime, timezone

import boto3

from vpc import REGION, load

cw = boto3.client("cloudwatch", region_name=REGION)
MODEL = "global.anthropic.claude-sonnet-4-6"


def total(ns, name, dims, start, end):
    r = cw.get_metric_statistics(Namespace=ns, MetricName=name, Dimensions=dims, StartTime=start, EndTime=end,
                                 Period=60, Statistics=["Sum"])
    return sum(p["Sum"] for p in r["Datapoints"])


def main(since, until):
    start = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(until).replace(tzinfo=timezone.utc)
    g = load()["guardrail"]
    garn = f"arn:aws:bedrock:{REGION}:050571774557:guardrail/{g['id']}"
    out = {"since": since, "until": until}
    for m in ("InputTokenCount", "OutputTokenCount", "Invocations"):
        out[m] = total("AWS/Bedrock", m, [{"Name": "ModelId", "Value": MODEL}], start, end)
    # guardrail metric 的維度組合依 list_metrics 實際出現的為準
    for metric in cw.list_metrics(Namespace="AWS/Bedrock/Guardrails", MetricName="TextUnitCount")["Metrics"]:
        dims = metric["Dimensions"]
        d = {x["Name"]: x["Value"] for x in dims}
        if d.get("GuardrailArn", garn) != garn:
            continue
        key = "TextUnitCount[" + ",".join(f"{k}={v.rsplit('/', 1)[-1]}" for k, v in sorted(d.items())) + "]"
        v = total("AWS/Bedrock/Guardrails", "TextUnitCount", dims, start, end)
        if v:
            out[key] = v
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
