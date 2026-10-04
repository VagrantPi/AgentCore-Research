# WP7 OpenClaw on AgentCore 官方範例實跑

> 回答：方案 A（OpenClaw 跑在 AgentCore Runtime）的真實延遲和成本是多少？拿來當 WP1（方案 B）和 WP6（方案 C）的對照組。
>
> 估點：3。優先序：7（風險低、價值低）。前置：WP0、WP3 建好的不開 NAT VPC（能力邊界測試用）。分群：B。

## 目標

部署 AWS 官方範例，拿到四個數字，並確認它的能力邊界能不能收緊。

## 前提

| 前提 | 來源等級 | 出處 |
|---|---|---|
| 官方範例：每位使用者一個 session；輕量替身 agent 約 23 秒先回、完整 OpenClaw 回覆約 70 秒；工作區 `~/.openclaw/` 鏡像到 session storage 並備份到 S3；cron 用 EventBridge 叫醒；預設 idle 30 分鐘、最長 8 小時 | 外部資料（範例 README 自述，未經本團隊實測） | [aws-samples/sample-host-openclaw-on-amazon-bedrock-agentcore](https://github.com/aws-samples/sample-host-openclaw-on-amazon-bedrock-agentcore) |
| 範例停用了 `read` 工具、channel 工具；`exec` 保留；Bedrock proxy 綁在 loopback | 外部資料 | 同上 |
| 大工作區（約 1,000 個檔案）還原要 80–115 秒 | 外部資料 | 同上 |

## 步驟

1. 照範例 README 部署（Telegram 或 Slack 任選一個 channel），資源加 tag `wp=WP7`、`owner`、`project=hyfai`。
2. 新使用者第一次發訊：記錄首則回覆、完整回覆的時間。
3. 等 idle 逾時後再發訊：記錄工作區還原時間（先在工作區塞 500 個小檔案）。
4. 模擬 10 位使用者各聊 10 輪，用 WP0 的方法估算費用。
5. **能力邊界測試：** 以使用者身分要求「查今天的新聞」「幫我寫一支爬蟲抓某網站」，看 OpenClaw 會不會做（預期會，因為範例保留 `exec` 和上網）。再嘗試把 Runtime 改成 VPC 無 NAT（可借用 WP3 的 VPC），看 OpenClaw 還能不能啟動和回話。

## 檢核點

| # | 檢核點 | 來源等級 | 判定 |
|---|---|---|---|
| 1 | 首則回覆延遲（冷啟動） | 外部資料 | 秒 |
| 2 | 完整 OpenClaw 回覆延遲 | 外部資料 | 秒 |
| 3 | 500 個檔案的工作區還原時間 | 外部資料 | 秒 |
| 4 | 10 位使用者各 10 輪的實際費用，換算每位使用者月費 | 成本 | USD |
| 5 | 預設設定下，使用者能不能叫它做範圍外的事（上網、寫爬蟲） | `[推測]` | 是 / 否 |
| 6 | VPC 無 NAT 下 OpenClaw 能否啟動與回話 | `[推測]` | 是 / 否 |

## 判定對選型的影響

- 檢核點 1、2 和 WP1 的數字並列：方案 A 的首句延遲是方案 B 的幾倍。
- 檢核點 5 是「是」、6 是「否」→ 方案 A 的能力邊界無法在不拆 OpenClaw 的前提下收緊，列為阻斷項。

## 交付

- 本檔案下方的回填區。

## 關聯

- 研究庫：[01 Runtime](../01-runtime/README.md)（session storage、idle）、[90 框架整合](../90-integrations/README.md)
- 外部：[aws-samples/sample-host-openclaw-on-amazon-bedrock-agentcore](https://github.com/aws-samples/sample-host-openclaw-on-amazon-bedrock-agentcore)

## 回填

- 負責人：kais
- 執行日期：2026-10-04（02:41–04:08 UTC 實測；VPC 本體隔天刪）
- 區域：ap-northeast-1（private subnet 在 `apne1-az4`、`apne1-az1`）
- 資源 tag：`wp=WP7`、`owner=kais`、`project=hyfai`
- 使用的 AWS 帳號：050571774557（IAM user `KaisLinCli`）
- 範例版本：`b0c427f`（2026-09-28，OpenClaw 2026.9.5），模型 `global.anthropic.claude-sonnet-4-6`
- 腳本與原始資料：[`90-integrations/experiments/openclaw-wp7/`](../90-integrations/experiments/openclaw-wp7/README.md)

**跟範例不同的地方：** `KaisLinCli` 沒有 CloudFormation、DynamoDB、Cognito 權限，範例的 CDK 部署不了。所以只部署 Runtime 容器（網路、guardrail、execution role 照範例設定），用 boto3 直接呼叫 `InvokeAgentRuntime` 取代 Router Lambda。沒有 Telegram、API Gateway、DynamoDB、Cognito、Cron、Browser、KMS。因此 #1、#2 **不含** Telegram → API Gateway → Lambda 那一段，範例 README 的 23 秒、70 秒是從 webhook 算起。呼叫端是台灣的筆電。

### 結論（三句內）

1. **延遲：** 首則回覆（輕量替身 agent）從預熱池拿 VM 約 4.6 秒，池子用光後 16.7–20.7 秒；完整 OpenClaw 從第一則訊息算起約 20 秒接手，之後每則約 4.7 秒（方案 B 的 WP1 預喚醒後首句 0.17 秒、暖機約 0.2 秒，不含模型）。
2. **成本：** 完整 OpenClaw 每輪送約 2.6 萬個輸入 token（系統提示加 35 個工具定義，沒有 prompt cache），模型費每輪約 $0.065，佔每位使用者成本的絕大部分。
3. **能力邊界：** 預設設定下會上網、會執行程式（#5 是）。照範例只拔掉 NAT 會回不了話；但只要再打開 `bedrock-runtime` endpoint 的 private DNS、加 STS endpoint，就能正常回話而且上不了網（#6 是）。**不必改 OpenClaw，因此不列為阻斷項**。

### 檢核表

| # | 檢核點 | 來源等級 | 結果 | 證據 | 對選型的影響 |
|---|---|---|---|---|---|
| 1 | 首則回覆延遲（冷啟動） | 外部資料 | **從預熱池 p50 4.6 秒**（7 位依序的新使用者 4.0–6.6 秒）；**池子用光後 16.7–20.7 秒**（20 人同時發訊，10 人落在池子 3.9–4.9 秒，另外 10 人 16.7–20.7 秒；部署後第一個 session 17.4 秒） | `first.csv`、`burst.csv` | 首則是輕量替身 agent 回的（log `Routing via lightweight agent`），內容會附「Warm-up mode」字樣。比 WP1 方案 B 的 V1 真冷啟動（小 image 3.6 秒、1 GB 17.8 秒）慢，主因是 1.45 GB 的映像 |
| 2 | 完整 OpenClaw 回覆延遲 | 外部資料 | **從第一則訊息算起 p50 19.8 秒**（OpenClaw 約 15 秒 ready，再回一句 4.7 秒）；之後每則 p50 約 5.0 秒、p90 7.3 秒（#4 的 100 輪） | `first.csv`、`load.csv`；log `OpenClaw ready — switching` | 範例 README 的 70 秒大多是等 S3 還原（新使用者沒有檔案時約 10 秒就 ready）。**完整 OpenClaw 不知道替身 agent 剛剛說過什麼**（問「你剛剛說了什麼」，回「這是我們對話的開頭」） |
| 3 | 500 個檔案的工作區還原時間 | 外部資料 | **新 session：S3 還原 14.4–14.8 秒**（3 次），還原後 10 秒 OpenClaw ready，從第一則訊息算起 28.4 秒。**同一個 session 閒置 31 分鐘後再發訊：** session storage 還留著 502 個檔案，只比對 S3 花 2 秒，14.5 秒 ready，首則回覆 9.1 秒 | `restore.csv`；`logs_excerpt.txt` 的 `Restoring workspace` → `Restored 500 file(s)` | 還原是逐檔 GetObject，約 30 ms／檔，跟檔案數成正比。範例 Router 換新 session ID 時才會從 S3 全量還原 |
| 4 | 10 位使用者各 10 輪的實際費用，換算每位使用者月費 | 成本 | 見下方「實際費用」：100 輪模型費 **$6.52**（每輪 $0.065）；**待補：Runtime 費用與每位使用者月費** | `load.csv`；proxy log 與 CloudWatch `AWS/Bedrock` 的 token 數完全一致（輸入 2,093,655、輸出 15,788） | 方案 A 的成本由模型 token 主導，每輪送整份系統提示與 35 個工具定義 |
| 5 | 預設設定下，使用者能不能叫它做範圍外的事（上網、寫爬蟲） | `[推測]` | **是。** 「查今天的新聞」：`web_search` 因沒設定搜尋供應商而失敗，agent 自己改用 `web_fetch` 抓 Google News RSS 成功，最後回覆被 guardrail 的輸出過濾擋掉。「寫爬蟲並執行」：`exec` 實際跑 Python，從外網抓回 `Example Domain` | `boundary.jsonl`（tag `nat`）；`logs_excerpt.txt` 的 `tool=web_search`、`tool=web_fetch`、`tool=exec` | guardrail 只過濾內容，不限制工具；範例保留的 `exec`、`web_fetch` 都能連外 |
| 6 | VPC 無 NAT 下 OpenClaw 能否啟動與回話 | `[推測]` | **照範例原樣：否**（能啟動，回不了話）。拔掉 NAT 後容器正常啟動、`/ping` 正常、OpenClaw 宣告 ready，但打 Bedrock 逾時：範例刻意把 `bedrock-runtime` endpoint 的 private DNS 關掉，讓 `global.*` profile 走 NAT。**改兩個設定後：是。** 打開 private DNS 後能回話，但建 scoped 憑證時連 STS 要 2.2–6.6 分鐘才逾時（之後退回用完整 role）；再加 STS interface endpoint，首則 4.6–5.2 秒、到完整回覆約 20 秒，跟有 NAT 時一樣。這時 `web_search`、`web_fetch`（example.com 連線逾時）都失敗，clawhub.ai、catalog.openclaw.ai 也連不到 | `first.csv`（n01–n06）、`boundary.jsonl`（tag `nonat-dns-sts`）、`logs_excerpt.txt` 的 `Proxy call failed`、`connect ETIMEDOUT`、`Scoped credentials failed` | 方案 A 的能力邊界可以在網路層收緊，不用拆 OpenClaw。代價：多 STS endpoint；技能不能從 ClawHub 線上安裝；`web_*` 工具仍出現在模型的工具清單裡，只是會失敗 |

- #6 用的 `global.anthropic.claude-sonnet-4-6` 在 private DNS 打開後仍可呼叫（跨區路由在 Bedrock 端完成）。範例 `vpc_stack.py` 註解說要關 private DNS 才能用 `global.*`，在東京不成立。
- 其他觀察：
  - guardrail 的輸出過濾有誤擋：100 輪裡「幫我想三個晚餐的點子」被擋 1 次。
  - guardrail 每次呼叫只檢查最後一則使用者訊息與回覆，不是整份 prompt。100 輪約 1,100 個 text unit。
  - 預熱池約 10 台：burst 20 人時剛好 10 人落在池子。

### 實際費用

**待補（session 結束滿 1 小時後跑 `usage_cost.py`）。**

### 否定項目的替代方案

| 被否定的檢核點 | 替代方案 | 多出的成本或限制 |
|---|---|---|
| #6 照範例只拔 NAT 能回話（否定） | 打開 `bedrock-runtime` endpoint 的 private DNS，加 STS interface endpoint | STS endpoint 單 AZ $10.22／月；ClawHub 線上安裝技能、`web_*` 工具都不能用 |

### 清理確認

**待補。**

### 要更正研究庫的段落

| 檔案:行號 | 原本寫的 | 實測結果 |
|---|---|---|
| `91-work-packages/WP7-openclaw-on-agentcore.md` 前提 | 替身 agent 約 23 秒先回、完整 OpenClaw 約 70 秒 | 不含 Telegram 與 Lambda 時，從預熱池 4.6 秒、完整約 20 秒；70 秒主要是 S3 還原等待 |
| `91-work-packages/WP7-openclaw-on-agentcore.md` 前提 | 大工作區（約 1,000 個檔案）還原要 80–115 秒 | 500 個小檔 14.5 秒（逐檔約 30 ms），與檔案數成正比 |
