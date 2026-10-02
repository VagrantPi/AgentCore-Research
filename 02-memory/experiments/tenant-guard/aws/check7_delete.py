# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""#7：用 guard.forget_actor() 刪除使用者 A 的全部資料，記錄 API 呼叫次數與耗時，5 分鐘後重掃殘留。"""
import sys
import time
from collections import Counter

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from guard import forget_actor  # noqa: E402

from common import ACTORS, client, load_state  # noqa: E402

st = load_state()
mid, actor = st["memoryId"], ACTORS["A"]


class Counting:
    """包住 boto3 client，記錄每個 API 的呼叫順序與次數。"""
    def __init__(self, c):
        self.c, self.calls, self.order = c, Counter(), []

    def __getattr__(self, name):
        fn = getattr(self.c, name)

        def wrapped(**kw):
            self.calls[name] += 1
            if not self.order or self.order[-1] != name:
                self.order.append(name)
            return fn(**kw)
        return wrapped


def residue():
    dp = client("bedrock-agentcore")
    sess = dp.list_sessions(memoryId=mid, actorId=actor)["sessionSummaries"]
    recs = {n: len(dp.list_memory_records(memoryId=mid, namespacePath=f"/strategy/{sid}/actor/{actor}/")
                   ["memoryRecordSummaries"]) for n, sid in st["strategies"].items()}
    return len(sess), recs


print("刪除前：sessions、records =", residue())
c = Counting(client("bedrock-agentcore"))
t0 = time.time()
res = forget_actor(c, mid, actor, list(st["strategies"].values()))
print(f"forget_actor：{res}，耗時 {time.time() - t0:.1f} 秒")
print("API 順序：", " → ".join(c.order))
print("呼叫次數：", dict(c.calls))
print("刪除後立即：sessions、records =", residue())
time.sleep(300)
print("5 分鐘後：sessions、records =", residue())
