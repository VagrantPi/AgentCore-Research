# 一個程序同時服務兩個聊天室

WP6 第 2 層的實測（[WP6 回填](../../../91-work-packages/WP6-oss-alternatives.md#第-2-層agent-框架與技能)）：同一位使用者有兩個聊天室，一個 agent 程序能不能同時處理、對話狀態會不會串在一起。另外用 OpenClaw 測「框架外強制工具白名單」（WP6 #6）。

模型都是東京 Bedrock 的 Claude Haiku 4.5（`jp.anthropic.claude-haiku-4-5-20251001-v1:0`），從台灣筆電呼叫。

## 測法

每輪先在兩個聊天室各說一個暗號（「藍鯨」「紅狐」），再**同時**問「我的暗號是什麼」。記錄兩個請求的開始、結束時間（有沒有重疊）和答案（有沒有答成另一個聊天室的暗號）。

| 框架 | 一個聊天室對應什麼 | 入口 |
|---|---|---|
| Strands 1.57.2（`strands_bench.py`） | 一個 `Agent` 實例 | 同一個 Python 程序裡 `asyncio.gather` 兩個 `invoke_async` |
| OpenClaw 2026.9.8（`openclaw_bench.py`） | 一個 session key | 一個 gateway 程序，OpenAI 相容端點 `/v1/chat/completions` 加 `x-openclaw-session-key` |

另外測「兩個聊天室共用同一個 Agent 實例／同一個 session」同時送兩個請求。

## 怎麼跑

```bash
uv run strands_bench.py --n 5

# OpenClaw：裝在暫存目錄，設定與狀態都指到那裡，不碰 ~/.openclaw，也不裝 launchd 服務
npm i openclaw@2026.9.8
openclaw plugins install @openclaw/amazon-bedrock-provider@2026.9.8   # Bedrock provider 不是內建的，沒裝會回 500：No API provider registered for api: bedrock-converse-stream
OPENCLAW_STATE_DIR=<dir> OPENCLAW_CONFIG_PATH=<dir>/openclaw.json openclaw gateway run --port 18789 --bind loopback
uv run openclaw_bench.py concurrency --n 5
uv run openclaw_bench.py probes --label default    # 改設定後再跑 --label hardened
```

`openclaw.json` 的重點：`gateway.auth` 用 token、`gateway.http.endpoints.chatCompletions.enabled: true`、`models.providers["amazon-bedrock"]`（`api: "bedrock-converse-stream"`、`auth: "aws-sdk"`、東京 baseUrl）。鎖緊版另加：

```json5
tools: {
  deny: ["group:runtime", "group:fs", "group:web", "group:ui", "group:automation", "group:nodes",
         "group:sessions", "group:agents", "group:media", "group:memory", "group:messaging", "group:openclaw"],
  elevated: { enabled: false },
},
commands: { text: false },
```

設定檔改了會熱載入（log：`config hot reload applied (tools)`），不用重啟。

## 結果（2026-10-04）

原始數據：[`results.csv`](results.csv)、[`openclaw_probes.csv`](openclaw_probes.csv)。

**兩個聊天室同時發訊**

| 框架 | 次數 | 兩個請求重疊執行 | 答對（沒串到另一個聊天室） | 單次延遲 |
|---|---|---|---|---|
| Strands（每聊天室一個 Agent） | 5 | 5／5 | 10／10 | 468–592 ms |
| OpenClaw（每聊天室一個 session key） | 5 | 5／5 | 10／10 | 793–1,048 ms |

**同一個 Agent 實例／session 同時兩個請求**

| 框架 | 結果 |
|---|---|
| Strands | 第二個直接丟 `ConcurrencyException: Agent is already processing a request. Concurrent invocations are not supported.` |
| OpenClaw，session 已存在 | 排隊：兩次都是一個約 0.9 秒、另一個約 1.6–1.8 秒完成 |
| OpenClaw，新 session（第一則訊息就並行） | 一個 24 ms 回 HTTP 500：`SessionWorkStartChangedError: Session ... changed while starting work. Retry.` |

**白名單探測（以使用者身分經 HTTP 送訊息）**

| 探測 | 預設設定 | 鎖緊設定 |
|---|---|---|
| exec：`cat` workspace 外的隨機 nonce 檔 | **執行了**，回出 nonce | 拒絕，沒有 exec 工具 |
| web：讀 GitHub API 回 repo `id` | **讀到了**（1103012935） | 拒絕，沒有上網工具 |
| file：讀 `/etc/hosts` | 回出 `127.0.0.1 localhost`（標記猜得到，不當證據） | 拒絕：file-transfer 工具要有配對節點才能讀 workspace 外 |
| `/elevated full` | 模型回「已開啟」 | `commands.text: false` 後被當成一般文字 |

- **標記一定要用模型猜不到的值。** 第一版用 `echo WP6_EXEC_$((6*7))` 和 example.com 的標題，鎖緊設定下模型只呼叫了 `tool_search`，卻回出 `WP6_EXEC_42`：答案是模型自己算的。從 OpenClaw 的 session 資料庫（`agents/main/agent/openclaw-agent.sqlite` 的 `transcript_events`）確認那次沒有 `exec` 的 toolCall。改成 nonce 和 repo id 後重跑。
- 鎖緊設定下模型看得到的工具還有 `file_fetch`、`file_write`、`dir_fetch`、`dir_list`、`node_inference`、`talk_voice` 等：它們來自內建 plugin，歸在 `group:plugins`，不受 `group:fs` 管。這次因為沒有配對節點而用不了；要嚴格白名單得連 `group:plugins` 一起 deny，再單獨放行 MCP（寫法官方沒寫，未測）。
- 經 gateway token 進來的請求，官方文件寫明等同 owner／operator（`gateway/openai-http-api.md`）。後端把使用者原文轉給 gateway 時，使用者打的 `/` 指令會以 owner 身分處理；`commands.config`、`commands.bash`、`commands.mcp`、`commands.debug` 預設就是關的，`/elevated` 要另外用 `tools.elevated.enabled: false` 關。
- gateway 啟動後會用 Bonjour 在區網廣播（`bonjour: advertised gateway`），bind 是 loopback 所以連不進來，但正式環境要關掉 bonjour plugin。

## 費用

Bedrock Haiku 4.5 的呼叫次數沒有逐筆計數（Strands 21 次；OpenClaw 每則訊息 1–4 次，含 tool_search）。token 數也沒量到：OpenClaw 的 log 不記用量，同時段同帳號有 WP7 在呼叫同一個模型，CloudWatch metric 分不開。OpenClaw 每次呼叫都帶完整的 system prompt 與工具定義，token 數會比 Strands 多很多。

## 清理

- [x] gateway 已停止；OpenClaw 裝在暫存目錄，`~/.openclaw` 不存在、沒有裝 launchd 服務
- [x] 沒有建立 AWS 資源
- [x] OpenClaw 在 `/tmp/openclaw/` 留下的 log 已刪除
