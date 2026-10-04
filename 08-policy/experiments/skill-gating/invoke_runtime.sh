#!/usr/bin/env bash
# 呼叫 wp2_agent Runtime。用法：invoke_runtime.sh <session_id（≥33 字元）> '<payload JSON>'
# payload 的 "__TOKEN_<user>__" 會被換成當下現簽的 actor JWT（60 秒有效，所以每次呼叫前才簽）。
# 簽章用 HephAgora repo 的本機 app 容器與 .wp2-keys/（私鑰只在開發機）。
set -euo pipefail
: "${AWS_PROFILE:=roman}" "${AWS_REGION:=ap-northeast-1}"; export AWS_PROFILE AWS_REGION
RUNTIME_ARN="${RUNTIME_ARN:-arn:aws:bedrock-agentcore:ap-northeast-1:050571774557:runtime/wp2_agent-3CtxOI8mwx}"
HA_REPO="${HA_REPO:-$HOME/Work/HephAgora}"
AUD="${AUD:-http://wp2-hephagora.test}"
SESSION="$1"; PAYLOAD="$2"
while [[ "$PAYLOAD" =~ __TOKEN_([a-z0-9-]+)__ ]]; do
  user="${BASH_REMATCH[1]}"
  tok=$(cd "$HA_REPO" && docker compose exec -T -e SUB="$user" -e KEY_PEM="$(cat .wp2-keys/wp2-test.key.pem)" \
        -e HEPHAGORA_PUBLIC_BASE="$AUD" app node --input-type=module - < scripts/wp2/sign-actor-jwt.mjs)
  PAYLOAD="${PAYLOAD//__TOKEN_${user}__/$tok}"
done
out=$(mktemp)
t0=$(python3 -c 'import time;print(time.time())')
aws bedrock-agentcore invoke-agent-runtime --agent-runtime-arn "$RUNTIME_ARN" --runtime-session-id "$SESSION" \
  --payload "$PAYLOAD" --cli-binary-format raw-in-base64-out --cli-read-timeout 300 "$out" >/dev/null
python3 - "$out" "$t0" <<'PY'
import json, sys, time
body = json.load(open(sys.argv[1]))
body["client_roundtrip_ms"] = round((time.time() - float(sys.argv[2])) * 1000)
print(json.dumps(body, ensure_ascii=False, indent=1))
PY
rm -f "$out"
