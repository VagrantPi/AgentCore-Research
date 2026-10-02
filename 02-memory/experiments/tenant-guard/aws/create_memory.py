# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""步驟 1：建 Memory（semantic + user preference + episodic，reflection 設在 actor 層級），等到 ACTIVE。

用法：uv run create_memory.py [名稱，預設 wp5_mem]（成本 3 天版用 wp5_cost3d）
"""
import sys
import time

from common import TAGS, client, save_state

ACTOR_NS = "/strategy/{memoryStrategyId}/actor/{actorId}/"

ctl = client("bedrock-agentcore-control")
m = ctl.create_memory(
    name=sys.argv[1] if len(sys.argv) > 1 else "wp5_mem", eventExpiryDuration=7, tags=TAGS,
    memoryStrategies=[
        {"semanticMemoryStrategy": {"name": "wp5_semantic", "namespaces": [ACTOR_NS]}},
        {"userPreferenceMemoryStrategy": {"name": "wp5_pref", "namespaces": [ACTOR_NS]}},
        {"episodicMemoryStrategy": {
            "name": "wp5_episodic",
            "namespaces": [ACTOR_NS + "session/{sessionId}/"],
            "reflectionConfiguration": {"namespaces": [ACTOR_NS]},   # actor 層級，不是 /strategy/{id}/
        }},
    ],
)["memory"]
mid = m["id"]
print("memoryId", mid)
while (m := ctl.get_memory(memoryId=mid)["memory"])["status"] == "CREATING":
    time.sleep(10)
print("status", m["status"])
strategies = {s["name"]: s["strategyId"] for s in m["strategies"]}
for s in m["strategies"]:
    print(s["name"], s["strategyId"], s.get("namespaces"), s.get("configuration"))
save_state(memoryId=mid, memoryArn=m["arn"], strategies=strategies)
