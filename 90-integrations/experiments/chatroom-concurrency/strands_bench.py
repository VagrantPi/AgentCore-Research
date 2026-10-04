# /// script
# requires-python = ">=3.12"
# dependencies = ["strands-agents", "boto3"]
# ///
"""一個 Python 程序同時服務同一位使用者的兩個聊天室（Strands）。

每個聊天室一個 Agent 實例。每輪先各自告訴 agent 一個暗號，再兩個聊天室同時問「我的暗號是什麼」，
記錄兩個請求有沒有重疊執行、各自答對沒有（沒有串到另一個聊天室的暗號）。
另外試一次「兩個聊天室共用同一個 Agent 實例」。

用法：uv run strands_bench.py --n 5
"""
import argparse
import asyncio
import csv
import datetime as dt
import importlib.metadata
import time
from pathlib import Path

from strands import Agent
from strands.models import BedrockModel

MODEL_ID = "jp.anthropic.claude-haiku-4-5-20251001-v1:0"
REGION = "ap-northeast-1"
OUT = Path(__file__).with_name("results.csv")
SYSTEM = "你是簡潔的助理。被問到暗號時，只回答暗號本身。"
ROOMS = {"room-1": "藍鯨", "room-2": "紅狐"}


def new_agent() -> Agent:
    return Agent(model=BedrockModel(model_id=MODEL_ID, region_name=REGION), system_prompt=SYSTEM, callback_handler=None)


async def ask(agent: Agent, room: str, text: str, t0: float) -> dict:
    start = time.perf_counter() - t0
    try:
        result = await agent.invoke_async(text)
        reply, err = str(result).strip(), ""
    except Exception as e:  # 共用實例時預期 ConcurrencyException
        reply, err = "", f"{type(e).__name__}: {e}"
    return {"room": room, "start_ms": round(start * 1000), "end_ms": round((time.perf_counter() - t0) * 1000), "reply": reply, "error": err}


async def trial_separate(i: int) -> list[dict]:
    agents = {room: new_agent() for room in ROOMS}
    t0 = time.perf_counter()
    await asyncio.gather(*(ask(agents[r], r, f"記住，我的暗號是「{w}」。只回「好」。", t0) for r, w in ROOMS.items()))
    t0 = time.perf_counter()
    rows = await asyncio.gather(*(ask(agents[r], r, "我的暗號是什麼？", t0) for r in ROOMS))
    for row in rows:
        row.update(trial=i, mode="separate", correct=ROOMS[row["room"]] in row["reply"] and not any(w in row["reply"] for r, w in ROOMS.items() if r != row["room"]))
    return rows


async def trial_shared(i: int) -> list[dict]:
    agent = new_agent()
    t0 = time.perf_counter()
    rows = await asyncio.gather(*(ask(agent, r, f"記住，我的暗號是「{w}」。只回「好」。", t0) for r, w in ROOMS.items()))
    for row in rows:
        row.update(trial=i, mode="shared", correct="")
    return rows


def overlap(rows: list[dict]) -> bool:
    a, b = rows
    return a["start_ms"] < b["end_ms"] and b["start_ms"] < a["end_ms"]


async def main(n: int) -> None:
    print("strands-agents", importlib.metadata.version("strands-agents"), "model", MODEL_ID)
    all_rows = []
    for i in range(n):
        rows = await trial_separate(i)
        print(f"separate #{i}: overlap={overlap(rows)}", [(r["room"], r["start_ms"], r["end_ms"], r["reply"], r["correct"]) for r in rows])
        all_rows += rows
    rows = await trial_shared(0)
    print("shared #0:", [(r["room"], r["reply"][:20], r["error"][:90]) for r in rows])
    all_rows += rows
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    fields = ["ts", "framework", "trial", "mode", "room", "start_ms", "end_ms", "reply", "correct", "error"]
    new = not OUT.exists()
    with OUT.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        for r in all_rows:
            w.writerow({"ts": now, "framework": "strands", **{k: r[k] for k in fields[2:]}})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=5)
    asyncio.run(main(p.parse_args().n))
