"""WP2 #4、#5：呼叫 wp2_harness，每次覆寫 remote_mcp 的 Authorization header（帶不同使用者的 actor JWT），
必要時覆寫 allowedTools。輸出模型看到的工具呼叫與回答。

用法（環境變數）：
  TOKEN          這次要帶的 actor JWT（60 秒有效，呼叫前才簽）
  PROMPT         使用者訊息
  ALLOWED_TOOLS  選填，JSON 陣列，例如 ["@ha/com_wp2_todo__*"]；不給就用 harness 預設（["@ha"]）
  HARNESS_ARN、HA_MCP_URL、AWS_REGION

在 skill-gating/agent 的映像裡跑（裡面有 boto3）：
  docker run --rm -v ~/.aws:/root/.aws:ro -e AWS_PROFILE=roman -e TOKEN=... -e PROMPT=... \
    -v $PWD/harness_check.py:/app/harness_check.py wp2-agent:local python harness_check.py
"""

import json
import os
import time
import uuid

import boto3

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
HARNESS_ARN = os.environ.get(
    "HARNESS_ARN", "arn:aws:bedrock-agentcore:ap-northeast-1:050571774557:harness/wp2_harness-SjPFM5dhUu"
)
HA_MCP_URL = os.environ.get("HA_MCP_URL", "http://18.181.169.251:13000/mcp")

kwargs = {
    "harnessArn": HARNESS_ARN,
    "runtimeSessionId": str(uuid.uuid4()),
    # #4：每次呼叫覆寫 tools，把「這位使用者」的 token 放進 remote_mcp header
    "tools": [
        {
            "type": "remote_mcp",
            "name": "ha",
            "config": {"remoteMcp": {"url": HA_MCP_URL, "headers": {"Authorization": f"Bearer {os.environ['TOKEN']}"}}},
        }
    ],
    "messages": [{"role": "user", "content": [{"text": os.environ["PROMPT"]}]}],
}
if os.environ.get("ALLOWED_TOOLS"):
    kwargs["allowedTools"] = json.loads(os.environ["ALLOWED_TOOLS"])  # #5

t0 = time.time()
resp = boto3.client("bedrock-agentcore", region_name=REGION).invoke_harness(**kwargs)
text, tool_uses, results, stop = [], [], [], None
for ev in resp["stream"]:
    if "contentBlockStart" in ev and "toolUse" in ev["contentBlockStart"].get("start", {}):
        tool_uses.append(ev["contentBlockStart"]["start"]["toolUse"].get("name"))
    if "contentBlockDelta" in ev:
        d = ev["contentBlockDelta"].get("delta", {})
        if "text" in d:
            text.append(d["text"])
        if "toolResult" in d:
            results.append(str(d["toolResult"])[:160])
    if "messageStop" in ev:
        stop = ev["messageStop"].get("stopReason")
    for k in ev:
        if k.endswith("Exception"):
            text.append(f"[{k}] {ev[k]}")
print(
    json.dumps(
        {
            "allowed_tools": kwargs.get("allowedTools", "(harness 預設 @ha)"),
            "tool_uses": tool_uses,
            "tool_results": results,
            "stop_reason": stop,
            "answer": "".join(text).strip(),
            "elapsed_ms": round((time.time() - t0) * 1000),
        },
        ensure_ascii=False,
        indent=1,
    )
)
