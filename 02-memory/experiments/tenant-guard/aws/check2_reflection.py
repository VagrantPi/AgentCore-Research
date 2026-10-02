# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""#2：列出每個 strategy、每位使用者的 record，檢查有沒有混到對方的特徵詞（common.MARKERS）。

episode 在 .../actor/{actorId}/session/{sessionId}/，reflection 在 .../actor/{actorId}/（設定在 actor 層級）。
用 namespacePath 掃 /strategy/{id}/ 整棵樹（namespace 參數是完全比對，掃不到子層），確認沒有無法歸屬的 record。
"""
import json
import pathlib

from common import ACTORS, MARKERS, client, load_state

st = load_state()
dp = client("bedrock-agentcore")
OTHER = {"A": "B", "B": "A"}
OWNER = {a: u for u, a in ACTORS.items()}
out = {}


def list_all(**kw):
    recs, tok = [], None
    while True:
        r = dp.list_memory_records(memoryId=st["memoryId"], maxResults=100, **kw, **({"nextToken": tok} if tok else {}))
        recs += r["memoryRecordSummaries"]
        if not (tok := r.get("nextToken")):
            return recs


for name, sid in st["strategies"].items():
    by_ns = {}
    for r in list_all(namespacePath=f"/strategy/{sid}/"):
        for ns in r["namespaces"]:
            by_ns.setdefault(ns, []).append(r["content"]["text"])
    print(f"== {name}")
    for ns, texts in sorted(by_ns.items()):
        actor = ns.split("/actor/")[1].split("/")[0] if "/actor/" in ns else None
        owner = OWNER.get(actor)
        if actor and not owner:
            continue   # wp5-user-cost 等其他測試使用者
        if not owner:
            print(f"   ⚠️ 無法歸屬到使用者：{ns} {len(texts)} 筆")
            continue
        hits = [(m, t) for t in texts for m in MARKERS[OTHER[owner]] if m.lower() in t.lower()]
        own = sum(any(m.lower() in t.lower() for m in MARKERS[owner]) for t in texts)
        print(f"   {ns}  {len(texts)} 筆（含自己特徵詞 {own} 筆）  混到對方特徵詞：{len(hits)}")
        for m, t in hits:
            print(f"      ⚠️ {m}：{t[:200]}")
        if name == "wp5_episodic" and "/session/" not in ns:
            for t in texts:
                print(f"      reflection：{t[:400]}")
    out[name] = by_ns
pathlib.Path(__file__).with_name("results").mkdir(exist_ok=True)
pathlib.Path(__file__).with_name("results").joinpath("check2-records.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1))
