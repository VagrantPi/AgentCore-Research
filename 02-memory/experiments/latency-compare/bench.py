# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3", "psycopg[binary]", "pgvector", "mem0ai", "psycopg2-binary"]
# ///
"""同一則訊息寫進三種記憶後端，量寫入、搜尋、寫入到搜得到的延遲。

每次試驗用新的 user_id，搜尋時只會找到這次寫入的東西，所以「有任何結果」就算命中。
pgvector、Mem0 要先開本機容器（見 README）；AgentCore 會自己建暫時 memory，結束時刪掉。

用法：
  uv run bench.py pgvector --n 10
  uv run bench.py mem0 --n 10
  uv run bench.py agentcore --n 5
"""
import argparse
import csv
import datetime as dt
import json
import statistics
import time
import uuid
from pathlib import Path

import boto3

REGION = "ap-northeast-1"
EMBED_MODEL = "amazon.titan-embed-text-v2:0"
# mem0ai 2.2.1 的 Nova 路徑把 system 字串當 message 塞進 Converse，參數驗證就失敗，所以改用 Haiku 4.5
LLM_MODEL = "jp.anthropic.claude-haiku-4-5-20251001-v1:0"
MESSAGES = [{"role": "user", "content": "我對花生過敏，平常住在台中。"},
            {"role": "assistant", "content": "好的，我記住了。"}]
QUERY = "使用者有什麼食物過敏？"
PG = dict(host="localhost", port=5433, user="postgres", password="postgres", dbname="postgres")
TAGS = {"wp": "WP6", "owner": "kais", "project": "hyfai"}
OUT = Path(__file__).with_name("results.csv")


def ms(t0):
    return round((time.perf_counter() - t0) * 1000, 1)


def trial(write, search, timeout, interval):
    """回傳 write_ms、第一次 search_ms、visible_ms（從寫入開始到第一次命中）、輪詢次數、命中內容。"""
    t0 = time.perf_counter()
    write()
    write_ms = ms(t0)
    first_search_ms, polls = None, 0
    while True:
        t1 = time.perf_counter()
        hits = search()
        polls += 1
        first_search_ms = first_search_ms or ms(t1)
        if hits:
            return write_ms, first_search_ms, ms(t0), polls, hits[0]
        if time.perf_counter() - t0 > timeout:
            return write_ms, first_search_ms, None, polls, ""
        time.sleep(interval)


def embedder():
    br = boto3.client("bedrock-runtime", region_name=REGION)

    def embed(text):
        body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})
        return json.loads(br.invoke_model(modelId=EMBED_MODEL, body=body)["body"].read())["embedding"]
    return embed


def run_pgvector(n):
    import numpy as np
    import psycopg
    from pgvector.psycopg import register_vector
    conn = psycopg.connect(**PG, autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS wp6_facts (user_id text, text text, emb vector(1024))")
    embed = embedder()
    text = MESSAGES[0]["content"]
    for i in range(n):
        u = f"pg-{uuid.uuid4().hex[:8]}"
        write = lambda: conn.execute("INSERT INTO wp6_facts VALUES (%s, %s, %s)", (u, text, np.array(embed(text))))
        search = lambda: [r[0] for r in conn.execute(
            "SELECT text FROM wp6_facts WHERE user_id = %s ORDER BY emb <=> %s LIMIT 5",
            (u, np.array(embed(QUERY)))).fetchall()]
        yield i, trial(write, search, timeout=10, interval=0.2)
    conn.execute("DROP TABLE wp6_facts")


def run_mem0(n):
    import os
    os.environ.setdefault("AWS_REGION", REGION)
    os.environ["MEM0_TELEMETRY"] = "False"   # 不送使用資料到 PostHog；要在 import mem0 之前設
    from mem0 import Memory
    # 帳號層級的 CloudWatch 會混到別人的呼叫，所以直接從 Converse 回應累計這支程式自己的 token
    usage = {"calls": 0, "inputTokens": 0, "outputTokens": 0}

    def count(parsed, **_):
        usage["calls"] += 1
        for k in ("inputTokens", "outputTokens"):
            usage[k] += parsed.get("usage", {}).get(k, 0)
    boto3.setup_default_session()
    boto3.DEFAULT_SESSION.events.register("after-call.bedrock-runtime.Converse", count)
    m = Memory.from_config({
        "llm": {"provider": "aws_bedrock", "config": {"model": LLM_MODEL, "temperature": 0.1, "max_tokens": 2000}},
        "embedder": {"provider": "aws_bedrock", "config": {"model": EMBED_MODEL}},
        "vector_store": {"provider": "pgvector", "config": {**PG, "collection_name": "wp6_mem0", "embedding_model_dims": 1024}},
    })
    for i in range(n):
        u = f"mem0-{uuid.uuid4().hex[:8]}"
        write = lambda: m.add(MESSAGES, user_id=u)
        search = lambda: [r["memory"] for r in m.search(QUERY, filters={"user_id": u})["results"]]
        yield i, trial(write, search, timeout=30, interval=0.5)
        m.delete_all(user_id=u)
    print(f"LLM 用量（{n} 次 add）：{usage}")


def run_agentcore(n):
    c = boto3.client("bedrock-agentcore-control", region_name=REGION)
    d = boto3.client("bedrock-agentcore", region_name=REGION)
    mem = c.create_memory(name=f"wp6_latency_{int(time.time())}", eventExpiryDuration=7, tags=TAGS,
                          memoryStrategies=[{"semanticMemoryStrategy": {"name": "Semantic",
                                                                        "namespaceTemplates": ["/wp6/{actorId}/"]}}])["memory"]
    try:
        while (status := c.get_memory(memoryId=mem["id"])["memory"]["status"]) != "ACTIVE":
            print("waiting for memory:", status); time.sleep(10)
        for i in range(n):
            u = f"ac-{uuid.uuid4().hex[:8]}"
            payload = [{"conversational": {"role": m["role"].upper(), "content": {"text": m["content"]}}} for m in MESSAGES]
            write = lambda: d.create_event(memoryId=mem["id"], actorId=u, sessionId=f"s-{u}",
                                           eventTimestamp=dt.datetime.now(dt.timezone.utc), payload=payload)
            search = lambda: [r["content"]["text"] for r in d.retrieve_memory_records(
                memoryId=mem["id"], namespace=f"/wp6/{u}/",
                searchCriteria={"searchQuery": QUERY, "topK": 5})["memoryRecordSummaries"]]
            yield i, trial(write, search, timeout=300, interval=2)   # RetrieveMemoryRecords 上限 30 TPS
    finally:
        c.delete_memory(memoryId=mem["id"])
        print("deleted memory", mem["id"])


def rtt_baseline():
    """東京 STS 往返時間中位數，當成「台灣 → 東京」一次 API 呼叫的底。"""
    sts = boto3.client("sts", region_name=REGION, endpoint_url=f"https://sts.{REGION}.amazonaws.com")
    sts.get_caller_identity()
    samples = []
    for _ in range(5):
        t0 = time.perf_counter(); sts.get_caller_identity(); samples.append(ms(t0))
    return statistics.median(samples)


def p(xs, q):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, round(q * (len(xs) - 1)))] if xs else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate", choices=["pgvector", "mem0", "agentcore"])
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()
    rtt = rtt_baseline()
    print(f"STS 東京 RTT 中位數 {rtt} ms")
    rows = []
    run = {"pgvector": run_pgvector, "mem0": run_mem0, "agentcore": run_agentcore}[a.candidate]
    new = not OUT.exists()
    with OUT.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "candidate", "trial", "write_ms", "search_ms", "visible_ms", "polls", "rtt_ms", "hit"]); f.flush()
        for i, (wm, sm, vm, polls, hit) in run(a.n):
            row = [dt.datetime.now().isoformat(timespec="seconds"), a.candidate, i, wm, sm, vm, polls, rtt, hit]
            w.writerow(row); f.flush(); rows.append(row)
            print(row)
    for name, col in [("write_ms", 3), ("search_ms", 4), ("visible_ms", 5)]:
        vals = [r[col] for r in rows]
        print(f"{name}: p50={p(vals, .5)} p90={p(vals, .9)} miss={vals.count(None)}")
