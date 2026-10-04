#!/bin/bash
# 兩台模擬器各自重複跑 lv_hang.py，任一邊抓到卡住就停。用法：bash hang_batch.sh [次數] [額外參數…]
set -u
cd "$(dirname "$0")"
N=${1:-6}
shift || true
PRO=9BF134DA-2D10-4321-AEDA-E3004E24C0F2
PROMAX=E6CFCF6D-229B-46E2-8676-48825D8F236E
LOG=hang_batch.log
: > "$LOG"
lane() {
  local sim=$1 port=$2
  shift 2
  for i in $(seq 1 "$N"); do
    grep -q 'RESULT HANG' "$LOG" && return
    uv run lv_hang.py --sim "$sim" --port "$port" "$@" 2>&1 | sed "s/^/[$port #$i] /" >> "$LOG"
  done
}
lane "$PRO" 8771 "$@" &
lane "$PROMAX" 8772 "$@" &
wait
grep -E 'RESULT|STALL' "$LOG"
