"""WP2 能力邊界實驗的 agent：跑在 AgentCore Runtime，帶「這位使用者」的 token 呼叫自家 MCP server（HephAgora）。

請求 payload：
- prompt：使用者訊息
- actor_token：使用者的短效 actor JWT（實際架構由後端簽發後放進呼叫內容；本實驗由測試腳本簽）

agent 每個請求：用 actor_token 連 HephAgora 的 /mcp → 拿到「這位使用者看得到的工具」→ 交給模型。
所以模型能用哪些工具完全由 HephAgora 決定，agent 本身不寫任何白名單。

量測入口（payload.probe，WP2 #6、#10 用，不經模型）：
- probe=browser：在 VM 裡直接呼叫 StartBrowserSession（browser_ids），預期 AccessDenied
- probe=mcp_latency：帶 actor_token 直接用 MCP 連續呼叫 tool n 次，回傳 p50／p90
- probe=egress：VM 能連到哪裡（外網、S3、STS、自家 MCP server），WP3 #8 用
- probe=abuse：WP5 #10，VM 裡拿 A 的 token 試讀 victim 的 todo、呼叫沒買的技能，等過期再打一次
- probe=profile：WP5 #11，用 execution role 讀 Browser profile（profile_ids），預期 AccessDenied

回傳 answer 以外的證據欄位：
- tools_visible：這次 MCP tools/list 拿到的工具名
- tool_calls：模型實際呼叫的工具與結果（是否錯誤、前 120 字）

環境變數：HA_MCP_URL（HephAgora 的 /mcp）、MODEL_ID（預設 Haiku 4.5 的 jp. inference profile）、AWS_REGION。

handler 是 async，實際工作丟到 thread：WP1 #8 實測，同一 session 並行請求時 handler 必須 async 或多執行緒，
否則請求排隊、/ping 被卡住。
"""

import asyncio
import os
import time

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

HA_MCP_URL = os.environ["HA_MCP_URL"]
MODEL_ID = os.environ.get("MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")
REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
SYSTEM_PROMPT = (
    "你是聊天 App 裡的助理。只能用提供給你的工具完成使用者的要求；"
    "沒有對應工具時，直接告訴使用者你目前沒有這個能力，不要假裝做到。回答用繁體中文。"
)

app = BedrockAgentCoreApp()


def _tool_calls(agent: Agent) -> list[dict]:
    """從對話紀錄抽出模型實際呼叫的工具與結果。"""
    calls, results = {}, {}
    for msg in agent.messages:
        for block in msg.get("content", []):
            if "toolUse" in block:
                u = block["toolUse"]
                calls[u["toolUseId"]] = {"name": u["name"], "input": u.get("input")}
            if "toolResult" in block:
                r = block["toolResult"]
                text = "".join(c.get("text", "") for c in r.get("content", []))
                results[r["toolUseId"]] = {"status": r.get("status"), "text": text[:120]}
    return [{**c, **results.get(i, {})} for i, c in calls.items()]


def _run(prompt: str, actor_token: str) -> dict:
    t0 = time.time()
    mcp = MCPClient(url=HA_MCP_URL, headers={"Authorization": f"Bearer {actor_token}"})
    with mcp:
        t_conn = time.time()
        tools = mcp.list_tools_sync()
        t_list = time.time()
        agent = Agent(
            model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
            callback_handler=None,
        )
        result = agent(prompt)
        t_done = time.time()
    return {
        "answer": str(result).strip(),
        "tools_visible": [t.tool_name for t in tools],
        "tool_calls": _tool_calls(agent),
        "timing_ms": {
            "mcp_connect": round((t_conn - t0) * 1000),
            "mcp_list_tools": round((t_list - t_conn) * 1000),
            "agent_total": round((t_done - t_list) * 1000),
        },
    }


def _probe_browser(browser_ids: list[str]) -> dict:
    """WP2 #6：在 VM 裡用 execution role 直接呼叫 StartBrowserSession，預期 AccessDenied。
    萬一成功開了 session，立刻關掉（避免空轉計費），並如實回報。"""
    import boto3
    from botocore.exceptions import ClientError

    out = {"caller": boto3.client("sts", region_name=REGION).get_caller_identity()["Arn"]}
    client = boto3.client("bedrock-agentcore", region_name=REGION)
    for bid in browser_ids:
        try:
            r = client.start_browser_session(browserIdentifier=bid, name="wp2-probe", sessionTimeoutSeconds=60)
            client.stop_browser_session(browserIdentifier=bid, sessionId=r["sessionId"])
            out[bid] = {"result": "SESSION_STARTED (unexpected)", "session_id": r["sessionId"]}
        except ClientError as e:
            out[bid] = {"result": e.response["Error"]["Code"], "message": e.response["Error"]["Message"][:200]}
    return out


def _probe_mcp_latency(actor_token: str, tool: str, args: dict, n: int) -> dict:
    """WP2 #10：agent → 自家 server 一般工具的延遲。不經模型，直接用 MCP 連續呼叫 n 次。"""
    mcp = MCPClient(url=HA_MCP_URL, headers={"Authorization": f"Bearer {actor_token}"})
    samples, errors = [], 0
    with mcp:
        for i in range(n):
            t = time.perf_counter()
            r = mcp.call_tool_sync(tool_use_id=f"wp2-{i}", name=tool, arguments=args)
            samples.append(round((time.perf_counter() - t) * 1000, 1))
            errors += r.get("status") != "success"
    s = sorted(samples)
    return {"tool": tool, "n": n, "errors": errors, "p50_ms": s[len(s) // 2], "p90_ms": s[int(len(s) * 0.9) - 1],
            "min_ms": s[0], "max_ms": s[-1], "samples_ms": samples}


def _probe_egress(actor_token: str | None) -> dict:
    """WP3 #8：VM 能連到哪裡。HTTPS 一律不跟轉址（S3 根目錄會 307 到外網，跟了會誤判）。"""
    import http.client
    import socket
    import ssl
    from urllib.parse import urlparse

    def https(host: str, path: str = "/", t: int = 6) -> str:
        try:
            c = http.client.HTTPSConnection(host, timeout=t, context=ssl.create_default_context())
            c.request("GET", path)
            r = c.getresponse()
            return f"ok HTTP {r.status}"
        except Exception as e:
            return f"fail {type(e).__name__}"

    # 先做帶 token 的 MCP（actor JWT 只活 60 秒，冷啟動加上後面幾個要等逾時的目標會超過）
    out = {}
    u = urlparse(HA_MCP_URL)
    try:
        socket.create_connection((u.hostname, u.port or 80), timeout=5).close()
        out["tcp 自家 MCP server"] = "ok"
    except Exception as e:
        out["tcp 自家 MCP server"] = f"fail {type(e).__name__}"
    if actor_token:
        try:
            with MCPClient(url=HA_MCP_URL, headers={"Authorization": f"Bearer {actor_token}"}) as mcp:
                out["mcp tools/list（帶使用者 token）"] = [t.tool_name for t in mcp.list_tools_sync()]
        except Exception as e:
            out["mcp tools/list（帶使用者 token）"] = f"fail {type(e).__name__}: {e}"[:200]
    out |= {
        "https example.com": https("example.com"),
        "https pypi.org": https("pypi.org", "/simple/"),
        "https s3.ap-northeast-1（同區域）": https("s3.ap-northeast-1.amazonaws.com"),
        "https s3.us-east-1（其他區域）": https("s3.us-east-1.amazonaws.com"),
        "https sts.ap-northeast-1": https("sts.ap-northeast-1.amazonaws.com"),
    }
    return out


def _probe_abuse(actor_token: str, victim: str) -> dict:
    """WP5 #10：VM 裡拿到 A 的 token，能做到多少事。直接打 HTTP（不經 MCP client／模型），
    每一步留狀態碼與回應前 300 字。最後等 token 過期再打一次。"""
    import base64
    import json
    import urllib.error
    import urllib.request

    base = HA_MCP_URL.rsplit("/mcp", 1)[0]

    def post(path: str, body: dict) -> dict:
        req = urllib.request.Request(
            base + path, data=json.dumps(body).encode(), method="POST",
            headers={"authorization": f"Bearer {actor_token}", "content-type": "application/json",
                     "accept": "application/json, text/event-stream"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return {"http": r.status, "body": r.read().decode()[:300]}
        except urllib.error.HTTPError as e:
            return {"http": e.code, "body": e.read().decode()[:300]}

    def mcp(method: str, params: dict) -> dict:
        return post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})

    def invoke(service: str, cap: str, args: dict) -> dict:
        return post("/v1/invoke", {"ref": {"service_id": service, "capability": cap}, "arguments": args})

    out = {"steps": {}}
    s = out["steps"]
    s["1 /mcp tools/list"] = mcp("tools/list", {})
    s["2 /mcp todo 帶 user_id=被害者"] = mcp("tools/call", {"name": "com_wp2_todo__list_todos", "arguments": {"user_id": victim}})
    s["3 /v1/invoke todo 帶 user_id=被害者"] = invoke("com.wp2.todo", "list_todos", {"user_id": victim})
    s["4 /mcp 呼叫沒買的 flight"] = mcp("tools/call", {"name": "com_wp2_flight__search_flights", "arguments": {"from": "TPE", "to": "NRT"}})
    s["5 /v1/invoke 呼叫沒買的 flight"] = invoke("com.wp2.flight", "search_flights", {"from": "TPE", "to": "NRT"})

    # 等到 exp 過後 10 秒（server 容許 5 秒時鐘誤差）
    exp = json.loads(base64.urlsafe_b64decode(actor_token.split(".")[1] + "=="))["exp"]
    wait = max(0, exp + 10 - time.time())
    time.sleep(wait)
    out["waited_s"] = round(wait, 1)
    s["6 過期後 /mcp tools/list"] = mcp("tools/list", {})
    s["7 過期後 /v1/invoke todo"] = invoke("com.wp2.todo", "list_todos", {})
    return out


def _probe_profile(profile_ids: list[str]) -> dict:
    """WP5 #11：用 Runtime 的 execution role 讀 Browser profile，預期全部 AccessDenied。"""
    import boto3
    from botocore.exceptions import ClientError

    out = {"caller": boto3.client("sts", region_name=REGION).get_caller_identity()["Arn"]}
    ctl = boto3.client("bedrock-agentcore-control", region_name=REGION)
    calls = {"ListBrowserProfiles": lambda: ctl.list_browser_profiles()}
    for pid in profile_ids:
        calls[f"GetBrowserProfile {pid}"] = lambda pid=pid: ctl.get_browser_profile(profileId=pid)
    for name, fn in calls.items():
        try:
            r = fn()
            r.pop("ResponseMetadata", None)
            out[name] = {"result": "ALLOWED (unexpected)", "response": str(r)[:200]}
        except ClientError as e:
            out[name] = {"result": e.response["Error"]["Code"], "message": e.response["Error"]["Message"][:200]}
    return out


@app.entrypoint
async def invoke(payload: dict) -> dict:
    probe = payload.get("probe")
    if probe == "abuse":
        return await asyncio.to_thread(_probe_abuse, payload["actor_token"], payload.get("victim", "userB"))
    if probe == "profile":
        return await asyncio.to_thread(_probe_profile, payload.get("profile_ids", []))
    if probe == "egress":
        return await asyncio.to_thread(_probe_egress, payload.get("actor_token"))
    if probe == "browser":
        return await asyncio.to_thread(_probe_browser, payload.get("browser_ids", []))
    if probe == "mcp_latency":
        return await asyncio.to_thread(
            _probe_mcp_latency, payload["actor_token"], payload["tool"], payload.get("args", {}), int(payload.get("n", 20))
        )
    prompt = payload.get("prompt")
    token = payload.get("actor_token")
    if not prompt or not token:
        return {"error": "prompt and actor_token required"}
    try:
        return await asyncio.to_thread(_run, prompt, token)
    except Exception as e:  # 連不上 HA、token 過期被 401 等，原樣回報當證據
        return {"error": f"{type(e).__name__}: {e}"[:500]}


if __name__ == "__main__":
    app.run()
