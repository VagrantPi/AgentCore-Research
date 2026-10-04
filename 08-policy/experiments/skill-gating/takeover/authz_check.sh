#!/usr/bin/env bash
# 新的 com.wp2.login-web 也受 HephAgora 技能授權管：A 沒買看不到、直打被拒；B 看得到。
#   HEPHAGORA=~/WS/HephAgora HA=http://localhost:13000 bash authz_check.sh
set -uo pipefail
HEPHAGORA=${HEPHAGORA:-$HOME/WS/HephAgora}
HA=${HA:-http://localhost:13000}
TOOL=com_wp2_login-web__login_and_check
tok() { (cd "$HEPHAGORA" && SUB=$1 node scripts/wp2/sign-actor-jwt.mjs); }
mcp() {
  curl -s -H "Authorization: Bearer $1" -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
    "$HA/mcp" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":$3}"
}
fail=0
check() { if grep -q -- "$3" <<<"$2"; then echo "PASS $1"; else echo "FAIL $1：$(head -c 200 <<<"$2")"; fail=1; fi; }
A=$(tok userA); B=$(tok userB)
la=$(mcp "$A" tools/list '{}'); lb=$(mcp "$B" tools/list '{}')
check "B tools/list 有 $TOOL" "$lb" "$TOOL"
check "A tools/list 沒有 $TOOL" "$(grep -c "$TOOL" <<<"$la" | sed 's/^0$/none/')" '^none$'
check "A 直接呼叫 → 被拒" "$(mcp "$A" tools/call "{\"name\":\"$TOOL\",\"arguments\":{}}")" 'Unknown tool'
exit $fail
