# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""步驟 1：A、B 各寫 50 個 event（5 個 session × 10 個 event，每個 event 一問一答）。"""
from datetime import datetime, timezone

from common import ACTORS, TOPICS, client, load_state, save_state

st = load_state()
dp = client("bedrock-agentcore")
for user, actor in ACTORS.items():
    place, lines = TOPICS[user]
    n = 0
    for s in range(5):
        sid = f"wp5-{user.lower()}-s{s}"
        for i in range(10):
            q = lines[(s + i) % len(lines)] + f"（第 {i + 1} 次問）"
            a = f"好的，我記下來了：你在規劃{place}的行程。{lines[(s + i) % len(lines)][:12]}……"
            dp.create_event(memoryId=st["memoryId"], actorId=actor, sessionId=sid,
                            eventTimestamp=datetime.now(timezone.utc),
                            payload=[{"conversational": {"role": "USER", "content": {"text": q}}},
                                     {"conversational": {"role": "ASSISTANT", "content": {"text": a}}}])
            n += 1
    print(user, actor, n, "events")
save_state(eventsWrittenAt=datetime.now(timezone.utc).isoformat())
