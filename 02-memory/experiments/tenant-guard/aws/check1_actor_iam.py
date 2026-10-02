# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""#1：IAM 依 actorId／namespace 限制 Memory 存取。

用法：uv run check1_actor_iam.py namespace|namespacePath
  建（或更新）/wp/wp5-mem-user-a、-b，套上 iam/mem-user-<版本>.json，assume A 的 role 做存取矩陣。
"""
import json
import pathlib
import sys
import time

from botocore.exceptions import ClientError

from common import ACCOUNT, ACTORS, TAGS, client, load_state

HERE = pathlib.Path(__file__).parent
version = sys.argv[1]
st = load_state()
mid = st["memoryId"]
iam, sts = client("iam"), client("sts")

for user, actor in ACTORS.items():
    name = f"wp5-mem-user-{user.lower()}"
    try:
        iam.create_role(RoleName=name, Path="/wp/", AssumeRolePolicyDocument=(HERE / "iam/trust-backend.json").read_text(),
                        Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()], MaxSessionDuration=3600)
        print("建立", name)
    except iam.exceptions.EntityAlreadyExistsException:
        pass
    doc = (HERE / f"iam/mem-user-{version}.json").read_text().replace("MEMORY_ID", mid).replace("ACTOR_ID", actor)
    iam.put_role_policy(RoleName=name, PolicyName="wp5-memory", PolicyDocument=doc)
print("等 IAM 傳播 15 秒"); time.sleep(15)

for attempt in range(6):   # 新建的 role 可能還不能 assume
    try:
        creds = sts.assume_role(RoleArn=f"arn:aws:iam::{ACCOUNT}:role/wp/wp5-mem-user-a",
                                RoleSessionName="wp5-check1")["Credentials"]
        break
    except ClientError as e:
        print("assume 失敗，重試：", e.response["Error"]["Code"], e.response["Error"]["Message"][:150])
        time.sleep(10)
else:
    sys.exit("assume role 失敗，可能需要 KaisLinCli 的 sts:AssumeRole 權限")

admin, a = client("bedrock-agentcore"), client("bedrock-agentcore", creds)
b_event = admin.list_events(memoryId=mid, actorId=ACTORS["B"], sessionId="wp5-b-s0", maxResults=1)["events"][0]["eventId"]
a_event = admin.list_events(memoryId=mid, actorId=ACTORS["A"], sessionId="wp5-a-s0", maxResults=1)["events"][0]["eventId"]
ns = {u: {k: f"/strategy/{sid}/actor/{act}/" for k, sid in st["strategies"].items()} for u, act in ACTORS.items()}
payload = [{"conversational": {"role": "USER", "content": {"text": "wp5 check1 寫入測試"}}}]
from datetime import datetime, timezone

cases = []
for u in "AB":
    act = ACTORS[u]
    cases += [
        (u, "ListSessions", lambda act=act: a.list_sessions(memoryId=mid, actorId=act)),
        (u, "ListEvents", lambda act=act, u=u: a.list_events(memoryId=mid, actorId=act, sessionId=f"wp5-{u.lower()}-s0")),
        (u, "GetEvent", lambda act=act, u=u: a.get_event(memoryId=mid, actorId=act, sessionId=f"wp5-{u.lower()}-s0",
                                                          eventId=a_event if u == "A" else b_event)),
        (u, "CreateEvent", lambda act=act, u=u: a.create_event(memoryId=mid, actorId=act, sessionId=f"wp5-{u.lower()}-check1",
                                                                eventTimestamp=datetime.now(timezone.utc), payload=payload)),
        (u, "ListMemoryRecords(semantic)", lambda u=u: a.list_memory_records(memoryId=mid, namespace=ns[u]["wp5_semantic"])),
        (u, "RetrieveMemoryRecords(semantic)", lambda u=u: a.retrieve_memory_records(
            memoryId=mid, namespace=ns[u]["wp5_semantic"], searchCriteria={"searchQuery": "旅遊", "topK": 3})),
        # 同一個 namespace 改用 namespacePath 參數傳（API 二擇一）
        (u, "ListMemoryRecords(namespacePath=semantic)", lambda u=u: a.list_memory_records(
            memoryId=mid, namespacePath=ns[u]["wp5_semantic"])),
        (u, "RetrieveMemoryRecords(namespacePath=semantic)", lambda u=u: a.retrieve_memory_records(
            memoryId=mid, namespacePath=ns[u]["wp5_semantic"], searchCriteria={"searchQuery": "旅遊", "topK": 3})),
    ]
cases += [
    ("*", "ListMemoryRecords(/strategy/ 前綴)", lambda: a.list_memory_records(memoryId=mid, namespace="/strategy/")),
    ("*", "ListMemoryRecords(/ 根)", lambda: a.list_memory_records(memoryId=mid, namespace="/")),
    ("*", "ListActors", lambda: a.list_actors(memoryId=mid)),
]
results = []
for target, op, fn in cases:
    try:
        r = fn()
        n = len(r.get("events") or r.get("sessionSummaries") or r.get("memoryRecordSummaries") or r.get("actorSummaries") or [])
        out = f"允許（{n} 筆）" if not r.get("event") else "允許"
        leaked = {ns_ for rec in r.get("memoryRecordSummaries", []) for ns_ in rec["namespaces"]
                  if ACTORS["A"] not in ns_}
        if leaked:
            out += f" ⚠️ 含別人的 namespace：{sorted(leaked)}"
    except ClientError as e:
        out = f"{e.response['Error']['Code']}: {e.response['Error']['Message'][:120]}"
    results.append((target, op, out))
    print(f"[{version}] role A → {target} {op}: {out}")
(HERE / f"results/check1-{version}.json").parent.mkdir(exist_ok=True)
(HERE / f"results/check1-{version}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
