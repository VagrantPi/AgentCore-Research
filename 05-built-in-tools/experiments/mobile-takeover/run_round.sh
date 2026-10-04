#!/bin/bash
# 一輪：4 個條件同時跑（視窗 × Live View）。用法：bash run_round.sh <round>
# Live View 用兩台已開機的模擬器：PRO、PROMAX（UDID 依自己的機器改）
set -u
cd "$(dirname "$0")"
R=$1
PRO=9BF134DA-2D10-4321-AEDA-E3004E24C0F2
PROMAX=E6CFCF6D-229B-46E2-8676-48825D8F236E
uv run viewport_cost.py run --round "$R" --viewport 1280x720 &
uv run viewport_cost.py run --round "$R" --viewport 390x844 &
uv run viewport_cost.py run --round "$R" --viewport 1280x720 --liveview "$PRO" --port 8771 &
uv run viewport_cost.py run --round "$R" --viewport 390x844 --liveview "$PROMAX" --port 8772 &
wait
