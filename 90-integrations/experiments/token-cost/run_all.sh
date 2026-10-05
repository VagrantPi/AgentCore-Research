#!/bin/bash
# 4 個組合（Haiku／Sonnet × cache 關／開）各跑 REPEAT 次一天份。用法：bash run_all.sh [REPEAT]
set -u
cd "$(dirname "$0")"
REPEAT=${1:-2}
for i in $(seq 1 "$REPEAT"); do
  for model in haiku sonnet; do
    for cache in off auto; do
      uv run day.py --model "$model" --cache "$cache" 2>&1 | grep -E '#10 |Traceback|Error'
    done
  done
done
