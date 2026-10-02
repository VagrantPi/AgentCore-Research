# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""#5、#8：模擬一位使用者每天的用量。用法：uv run cost_day.py [天數，預設 1]

每天：
- Memory：actor wp5-user-cost 寫 100 個 event（每個間隔 1 秒，避免 LTM_RATE_EXCEEDED）、做 20 次檢索（自己計數）
- Runtime：wp0_min 上一個 session，session ID 以使用者開頭（wp5-cost-<user>-...），
  每 5 分鐘呼叫一次共 105 分鐘，之後放著讓 15 分鐘閒置逾時 → 在線約 2 小時
- Browser 10 分鐘不實跑，用官網單價估算（瀏覽器改由自家 MCP server 開，見 WP2）
多天時，第 N 天在第 1 天開始後 24×(N-1) 小時開始。每天的時間與 session ID 記在 state.json 的 costDays。

最後一個 session 結束 1 小時後用 cost_report.py 換算月費。
"""
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from common import ACCOUNT, REGION, TOPICS, client, load_state, save_state

ACTOR = os.environ.get("WP5_COST_ACTOR", "wp5-user-cost")   # 3 天版在 EC2 上用 wp5-user-cost3d
RUNTIME = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:runtime/wp0_min-HsBwOc6VWU"


def run_day(day, dp, st):
    started = datetime.now(timezone.utc)
    for i in range(100):
        dp.create_event(memoryId=st["memoryId"], actorId=ACTOR, sessionId=f"wp5-cost-d{day}-s{i // 20}",
                        eventTimestamp=datetime.now(timezone.utc),
                        payload=[{"conversational": {"role": "USER", "content": {"text": TOPICS["A"][1][i % 5]}}}])
        time.sleep(1)
    print(f"day {day} events 100", flush=True)
    sid_sem = st["strategies"]["wp5_semantic"]
    for i in range(20):
        dp.retrieve_memory_records(memoryId=st["memoryId"], namespace=f"/strategy/{sid_sem}/actor/{ACTOR}/",
                                   searchCriteria={"searchQuery": "旅遊", "topK": 5})
    print(f"day {day} retrievals 20", flush=True)
    session = f"wp5-cost-{ACTOR}-d{day}-{uuid.uuid4().hex}"
    print(f"day {day} runtime session {session}", flush=True)
    for i in range(22):   # 0, 5, …, 105 分鐘
        dp.invoke_agent_runtime(agentRuntimeArn=RUNTIME, runtimeSessionId=session,
                                payload=b'{"prompt":"ping"}')["response"].read()
        print(f"day {day} invoke {i} {datetime.now(timezone.utc):%m-%d %H:%M:%S}", flush=True)
        if i < 21:
            time.sleep(300)
    return {"day": day, "startedAt": started.isoformat(), "session": session,
            "lastInvokeAt": datetime.now(timezone.utc).isoformat()}


days = int(sys.argv[1]) if len(sys.argv) > 1 else 1
st = load_state()
dp = client("bedrock-agentcore")
first = datetime.now(timezone.utc)
done = []
for day in range(1, days + 1):
    wait = (first + timedelta(hours=24 * (day - 1)) - datetime.now(timezone.utc)).total_seconds()
    if wait > 0:
        print(f"等到第 {day} 天開始：{first + timedelta(hours=24 * (day - 1)):%m-%d %H:%M} UTC", flush=True)
        time.sleep(wait)
    done.append(run_day(day, dp, st))
    save_state(costDays=done, costActor=ACTOR)
print("done; 最後一個 session 會在 15 分鐘後閒置逾時", flush=True)
