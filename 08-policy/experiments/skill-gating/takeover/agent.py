# /// script
# requires-python = ">=3.12"
# dependencies = ["strands-agents", "mcp<2", "boto3"]
# ///
"""WP2 #8 的 agent 端：Strands＋Haiku 4.5，帶使用者的 actor JWT 經 MCP 連 HephAgora。

agent 只看得到 HephAgora 依購買過濾後的工具；接手登入整段在 server 端完成，
跑完把完整對話（含工具回傳）寫到 transcript.json，用來檢查裡面沒有 Live View URL。

用法：uv run agent.py --user userB [--prompt "..."]
"""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

HERE = Path(__file__).parent
HEPHAGORA = Path.home() / "WS/HephAgora"
HA = "http://localhost:13000/mcp"
MODEL_ID = "jp.anthropic.claude-haiku-4-5-20251001-v1:0"
# 接手要等使用者登入（server 最多等 240 秒），HTTP 逾時要比它長
HTTP_TIMEOUT = 400


def actor_jwt(user: str) -> str:
    return subprocess.run(["node", "scripts/wp2/sign-actor-jwt.mjs"], cwd=HEPHAGORA, env={**os.environ, "SUB": user},
                          capture_output=True, text=True, check=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="userB")
    ap.add_argument("--prompt", default="幫我登入測試網站，然後告訴我登入結果。")
    ap.add_argument("--out", default="transcript.json")
    a = ap.parse_args()
    token = actor_jwt(a.user)
    client = MCPClient(lambda: streamablehttp_client(HA, headers={"Authorization": f"Bearer {token}"},
                                                     timeout=HTTP_TIMEOUT, sse_read_timeout=HTTP_TIMEOUT))
    t0 = time.time()
    with client:
        tools = client.list_tools_sync()
        print("tools:", [t.tool_name for t in tools], flush=True)
        agent = Agent(model=BedrockModel(model_id=MODEL_ID, region_name="ap-northeast-1"), tools=tools,
                      system_prompt="你是使用者的助理。用繁體中文簡短回答。", callback_handler=None)
        result = agent(a.prompt)
        print(f"reply ({time.time() - t0:.1f}s):", str(result).strip(), flush=True)
        (HERE / a.out).write_text(json.dumps({"user": a.user, "prompt": a.prompt, "tools": [t.tool_name for t in tools],
                                              "messages": agent.messages, "reply": str(result)}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
