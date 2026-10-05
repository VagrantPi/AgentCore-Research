"""讀 turns.csv，依東京單價換算每輪、每天（10 輪）、每月（30 天）的模型費。

單價：AWS Price List 公開檔 AmazonBedrockFoundationModels／ap-northeast-1，publicationDate 2026-09-30，每百萬 token。
  Haiku 4.5 用 jp. 地區 profile（Regional）；Sonnet 4.6 用 global. profile（Global）；cache 寫是 5 分鐘 TTL 的價格。
用法：python3 cost.py
"""
import csv
import statistics
from collections import defaultdict
from pathlib import Path

PRICES = {  # 輸入、輸出、cache 讀、cache 寫（USD／百萬 token）
    "haiku": (1.10, 5.50, 0.11, 1.375),
    "sonnet": (3.00, 15.00, 0.30, 3.75),
}
DAYS = 30

rows = list(csv.DictReader((Path(__file__).parent / "turns.csv").open()))
runs = defaultdict(list)
for r in rows:
    runs[r["run"]].append(r)


def cost(r) -> float:
    p = PRICES[r["model"]]
    toks = [int(r[k]) for k in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheWriteInputTokens")]
    return sum(t * price for t, price in zip(toks, p)) / 1e6


print("run,turns,input,output,cache_read,cache_write,model_calls,usd_day,usd_month")
by_combo = defaultdict(list)
for run, rs in runs.items():
    if len(rs) != 10:
        print(f"{run},{len(rs)},不完整，略過")
        continue
    tot = {k: sum(int(r[k]) for r in rs) for k in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheWriteInputTokens", "model_calls")}
    day = sum(cost(r) for r in rs)
    by_combo[(rs[0]["model"], rs[0]["cache"])].append((day, tot))
    print(f"{run},10,{tot['inputTokens']},{tot['outputTokens']},{tot['cacheReadInputTokens']},{tot['cacheWriteInputTokens']},{tot['model_calls']},{day:.4f},{day * DAYS:.2f}")

print("\nmodel,cache,n,usd_month_mean,min,max,avg_input_per_turn,avg_output_per_turn,avg_cache_read_per_turn,model_calls_per_turn")
for (model, cache), items in sorted(by_combo.items()):
    months = [d * DAYS for d, _ in items]
    avg = lambda k: statistics.mean(t[k] for _, t in items) / 10
    print(f"{model},{cache},{len(items)},{statistics.mean(months):.2f},{min(months):.2f},{max(months):.2f},"
          f"{avg('inputTokens'):.0f},{avg('outputTokens'):.0f},{avg('cacheReadInputTokens'):.0f},{avg('model_calls'):.2f}")
