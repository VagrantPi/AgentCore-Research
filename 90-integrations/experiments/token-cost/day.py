# /// script
# requires-python = ">=3.12"
# dependencies = ["strands-agents", "mcp<2", "boto3"]
# ///
"""方案 B 的模型 token 用量：一個聊天室一天 10 輪，agent 形狀同 WP2（Strands＋經 HephAgora MCP 的工具）。

依序跑 TURNS 的 10 句，對話歷史一路帶下去。每輪記下
輸入、輸出、cache 讀／寫 token、模型呼叫次數、工具呼叫，寫到 turns.csv。

用法（本機 HephAgora 要先起來，見 README）：
  uv run day.py --model haiku --cache off
  uv run day.py --model sonnet --cache auto
"""
import argparse
import csv
import datetime as dt
import os
import subprocess
import time
import uuid
from pathlib import Path

from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.models.bedrock import CacheConfig
from strands.tools.mcp import MCPClient

HERE = Path(__file__).parent
HEPHAGORA = Path.home() / "WS/HephAgora"
HA = "http://localhost:13000/mcp"
MODELS = {
    "haiku": "jp.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet": "global.anthropic.claude-sonnet-4-6",
}
SYSTEM = "你是使用者的個人助理。用繁體中文回答，簡潔但完整。需要資料時使用工具，不要自己編造。"
TURNS = [
    "早安，我今天有什麼待辦？",
    "幫我查下週五台北飛東京的機票。",
    "哪一班最便宜？",
    "東京三月天氣大概怎樣？要帶什麼衣服？",
    "那再幫我查台北飛大阪。",
    "東京跟大阪的機票比較一下。",
    "我還有哪些待辦沒做？",
    "幫我寫一段訊息跟主管說我要請假出差。",
    "改得正式一點。",
    "幫我總結今天聊了什麼。",
]
FIELDS = ["inputTokens", "outputTokens", "cacheReadInputTokens", "cacheWriteInputTokens"]


def actor_jwt(user: str) -> str:
    return subprocess.run(["node", "scripts/wp2/sign-actor-jwt.mjs"], cwd=HEPHAGORA, env={**os.environ, "SUB": user},
                          capture_output=True, text=True, check=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=MODELS, required=True)
    ap.add_argument("--cache", choices=["off", "auto"], required=True)
    a = ap.parse_args()
    run = f"{a.model}-{a.cache}-{uuid.uuid4().hex[:6]}"
    model = BedrockModel(model_id=MODELS[a.model], region_name="ap-northeast-1",
                         **({"cache_config": CacheConfig(strategy="auto")} if a.cache == "auto" else {}))
    history = []
    out = HERE / "turns.csv"
    new = not out.exists()
    with out.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "run", "model", "cache", "turn", "prompt", *FIELDS, "model_calls", "tool_calls", "seconds", "reply_chars"])
        for i, prompt in enumerate(TURNS, 1):
            # actor JWT 只有 60 秒：每輪重新簽、重新連 MCP，開新的 Agent 並帶入前面的對話歷史
            token = actor_jwt("userB")
            client = MCPClient(lambda: streamablehttp_client(HA, headers={"Authorization": f"Bearer {token}"}))
            with client:
                agent = Agent(model=model, tools=client.list_tools_sync(), system_prompt=SYSTEM,
                              messages=history, callback_handler=None)
                t0 = time.time()
                reply = str(agent(prompt)).strip()
                history = agent.messages
            m = agent.event_loop_metrics
            used = [m.accumulated_usage.get(k, 0) for k in FIELDS]
            tool_calls = {name: t.call_count for name, t in m.tool_metrics.items() if t.call_count}
            w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), run, a.model, a.cache, i, prompt, *used,
                        m.cycle_count, ";".join(f"{k}x{v}" for k, v in tool_calls.items()),
                        round(time.time() - t0, 1), len(reply)])
            f.flush()
            print(f"{run} #{i} in={used[0]} out={used[1]} cr={used[2]} cw={used[3]} calls={m.cycle_count} tools={tool_calls} | {reply[:60]!r}", flush=True)


if __name__ == "__main__":
    main()
