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
2. **成本：** 完整 OpenClaw 每輪送約 2.6 萬個輸入 token（系統提示加 35 個工具定義，沒有 prompt cache），模型費每輪約 $0.065。每位使用者每天聊 10 輪，月費約 $20.7，其中模型佔 94%；另有範例網路固定費約 $188／月。
3. **能力邊界：** 預設設定下會上網、會執行程式（#5 是）。照範例只拔掉 NAT 會回不了話；但只要再打開 `bedrock-runtime` endpoint 的 private DNS、加 STS endpoint，就能正常回話而且上不了網（#6 是）。**不必改 OpenClaw，因此不列為阻斷項**。

### 檢核表

| # | 檢核點 | 來源等級 | 結果 | 證據 | 對選型的影響 |
|---|---|---|---|---|---|
| 1 | 首則回覆延遲（冷啟動） | 外部資料 | **從預熱池 p50 4.6 秒**（7 位依序的新使用者 4.0–6.6 秒）；**池子用光後 16.7–20.7 秒**（20 人同時發訊，10 人落在池子 3.9–4.9 秒，另外 10 人 16.7–20.7 秒；部署後第一個 session 17.4 秒） | `first.csv`、`burst.csv` | 首則是輕量替身 agent 回的（log `Routing via lightweight agent`），內容會附「Warm-up mode」字樣。比 WP1 方案 B 的 V1 真冷啟動（小 image 3.6 秒、1 GB 17.8 秒）慢，主因是 1.45 GB 的映像 |
| 2 | 完整 OpenClaw 回覆延遲 | 外部資料 | **從第一則訊息算起 p50 19.8 秒**（OpenClaw 約 15 秒 ready，再回一句 4.7 秒）；之後每則 p50 約 5.0 秒、p90 7.3 秒（#4 的 100 輪） | `first.csv`、`load.csv`；log `OpenClaw ready — switching` | 範例 README 的 70 秒大多是等 S3 還原（新使用者沒有檔案時約 10 秒就 ready）。**完整 OpenClaw 不知道替身 agent 剛剛說過什麼**（問「你剛剛說了什麼」，回「這是我們對話的開頭」） |
| 3 | 500 個檔案的工作區還原時間 | 外部資料 | **新 session：S3 還原 14.4–14.8 秒**（3 次），還原後 10 秒 OpenClaw ready，從第一則訊息算起 28.4 秒。**同一個 session 閒置 31 分鐘後再發訊：** session storage 還留著 502 個檔案，只比對 S3 花 2 秒，14.5 秒 ready，首則回覆 9.1 秒 | `restore.csv`；`logs_excerpt.txt` 的 `Restoring workspace` → `Restored 500 file(s)` | 還原是逐檔 GetObject，約 30 ms／檔，跟檔案數成正比。範例 Router 換新 session ID 時才會從 S3 全量還原 |
| 4 | 10 位使用者各 10 輪的實際費用，換算每位使用者月費 | 成本 | 100 輪合計 **$6.66**：模型 $6.52、guardrail ≤ $0.11、Runtime $0.03（每輪 $0.067）。**每位使用者月費約 $20.7**（每天 1 次 10 輪 × 30 天，含範例預設的閒置 30 分鐘；用完立刻停 session 是 $20.0）。**模型費佔 94%**。另有範例網路固定費約 $188／月（NAT＋7 個 interface endpoint × 2 AZ），100 人分攤每人 $1.9 | 見下方「實際費用」 | `load.csv`；proxy log 與 CloudWatch `AWS/Bedrock` 的 token 數完全一致（輸入 2,093,655、輸出 15,788） | 方案 A 的成本由模型 token 主導，每輪送整份系統提示與 35 個工具定義 |
| 5 | 預設設定下，使用者能不能叫它做範圍外的事（上網、寫爬蟲） | `[推測]` | **是。** 「查今天的新聞」：`web_search` 因沒設定搜尋供應商而失敗，agent 自己改用 `web_fetch` 抓 Google News RSS 成功，最後回覆被 guardrail 的輸出過濾擋掉。「寫爬蟲並執行」：`exec` 實際跑 Python，從外網抓回 `Example Domain` | `boundary.jsonl`（tag `nat`）；`logs_excerpt.txt` 的 `tool=web_search`、`tool=web_fetch`、`tool=exec` | guardrail 只過濾內容，不限制工具；範例保留的 `exec`、`web_fetch` 都能連外 |
| 6 | VPC 無 NAT 下 OpenClaw 能否啟動與回話 | `[推測]` | **照範例原樣：否**（能啟動，回不了話）。拔掉 NAT 後容器正常啟動、`/ping` 正常、OpenClaw 宣告 ready，但打 Bedrock 逾時：範例刻意把 `bedrock-runtime` endpoint 的 private DNS 關掉，讓 `global.*` profile 走 NAT。**改兩個設定後：是。** 打開 private DNS 後能回話，但建 scoped 憑證時連 STS 要 2.2–6.6 分鐘才逾時（之後退回用完整 role）；再加 STS interface endpoint，首則 4.6–5.2 秒、到完整回覆約 20 秒，跟有 NAT 時一樣。這時 `web_search`、`web_fetch`（example.com 連線逾時）都失敗，clawhub.ai、catalog.openclaw.ai 也連不到 | `first.csv`（n01–n06）、`boundary.jsonl`（tag `nonat-dns-sts`）、`logs_excerpt.txt` 的 `Proxy call failed`、`connect ETIMEDOUT`、`Scoped credentials failed` | 方案 A 的能力邊界可以在網路層收緊，不用拆 OpenClaw。代價：多 STS endpoint；技能不能從 ClawHub 線上安裝；`web_*` 工具仍出現在模型的工具清單裡，只是會失敗 |

- #6 用的 `global.anthropic.claude-sonnet-4-6` 在 private DNS 打開後仍可呼叫（跨區路由在 Bedrock 端完成）。範例 `vpc_stack.py` 註解說要關 private DNS 才能用 `global.*`，在東京不成立。
- 其他觀察：
  - guardrail 的輸出過濾有誤擋：100 輪裡「幫我想三個晚餐的點子」被擋 1 次。
  - guardrail 每次呼叫只檢查最後一則使用者訊息與回覆，不是整份 prompt。100 輪約 1,100 個 text unit。
  - 預熱池約 10 台：burst 20 人時剛好 10 人落在池子。

### 實際費用

單價（官網公開價目檔，東京）：
- Runtime：$0.0895／vCPU-h、$0.00945／GB-h（`usage_cost.py`）。
- Sonnet 4.6 Global：輸入 $3／百萬 token、輸出 $15／百萬 token（AmazonBedrockFoundationModels，2026-09-30）。
- Guardrail：content、topic 各 $0.15／千 text unit；sensitive information 最多 $0.10／千；word 免費（AmazonBedrock，2026-10-03）。
- Interface endpoint：$0.014／小時／AZ（AmazonVPC，2026-09-17）。
- NAT：$0.062／小時＋$0.062／GB；公網 IPv4：$0.005／小時（AmazonEC2，2026-09-25）。

**#4：10 位使用者各 10 輪**（03:03–03:06 UTC，每位使用者一個新 session，最後一輪後立刻 `StopRuntimeSession`）

| 資源 | 用量 | 用量來源 | 算式 | 估算金額（USD） |
|---|---|---|---|---|
| Runtime（10 個 session） | 1,352 秒；0.129548 vCPU-h、1.977986 GB-h | `USAGE_LOGS` → `usage_cost.py`（07:18 UTC 跑兩次，結果相同） | 0.129548 × 0.0895 + 1.977986 × 0.00945 | 0.0303 |
| 模型輸入 | 2,093,655 token（110 次呼叫） | proxy log `[proxy] ... in/out tokens`，與 CloudWatch `AWS/Bedrock` `InputTokenCount` 完全一致 | 2.093655 × 3 | 6.2810 |
| 模型輸出 | 15,788 token | 同上（`OutputTokenCount`） | 0.015788 × 15 | 0.2368 |
| Guardrail | content 220、topic 220、sensitive 440、word 220 text unit | CloudWatch `AWS/Bedrock/Guardrails` `TextUnitCount` | (220 + 220) × 0.00015 + 440 × 0.0001（上限） | ≤ 0.1100 |
| **合計** | | | | **6.658** |

- 每個 session 平均活 135 秒，平均約 0.34 vCPU、**5.3 GB 記憶體**（WP1 的最小 agent 約 1.1 GB）。
- **閒置 30 分鐘的費用**：範例預設 idle 1800 秒，Router 不主動停 session。用 #3 的 idle 對照組估算：i01 共 1,961 秒，0.033852 vCPU-h、2.470044 GB-h。扣掉一般 session 的活躍部分（約 0.0123 vCPU-h、0.174 GB-h）後，閒置 30 分鐘約 0.0216 vCPU-h、2.296 GB-h，即 **$0.0236**。
- **每位使用者月費**：每天 1 次、10 輪，30 天。
  - 用完立刻停 session：$0.6658 × 30 = **$19.97**
  - 範例預設（閒置 30 分鐘才結束）：($0.6658 + $0.0236) × 30 = **$20.68**
  - 其中模型 $19.55（94%）、guardrail ≤ $0.33、Runtime $0.09（立刻停）到 $0.80（閒置 30 分鐘）。
- **網路固定費**（與人數無關，不含資料處理費）：
  - 範例架構：NAT $0.062 × 730 = $45.26，加 7 個 interface endpoint × 2 AZ × $0.014 × 730 = $143.08，合計 **$188.34／月**，100 人分攤每人 $1.88。
  - #6 收緊後（無 NAT）：要再加 STS endpoint。
- 模型費的假設：一般閒聊、每輪都只有使用者一句話。完整 OpenClaw 每次呼叫基本就是約 2.6 萬個輸入 token，這次輸出很短，用工具的回合會呼叫好幾次（#5 一題用了 3–4 次）。

**本次實測合計**

| 資源 | 用量 | 用量來源 | 算式 | 估算金額（USD） |
|---|---|---|---|---|
| Runtime `wp7_openclaw`（49 個 session，含 #1–#6） | 0.544999 vCPU-h、14.021383 GB-h | `USAGE_LOGS` → `usage_cost.py` | 0.544999 × 0.0895 + 14.021383 × 0.00945 | 0.1813 |
| 模型（02:45–04:10，218 次呼叫） | 輸入 3,221,532、輸出 22,679 token | proxy log，與 CloudWatch 一致 | 3.221532 × 3 + 0.022679 × 15 | 10.0048 |
| Guardrail | content 431、topic 431、sensitive 862 text unit | CloudWatch | 862 × 0.00015 + 862 × 0.0001（上限） | ≤ 0.2155 |
| Interface endpoint × 8（02:41–04:04，各 2 AZ） | 每個 1.38 h × 2 AZ | `infra.json` 建立／刪除時間 | 8 × 1.384 × 2 × 0.014 | 0.3100 |
| STS endpoint（#6b 追加，03:57–04:04） | 0.110 h × 2 AZ | 同上 | 0.110 × 2 × 0.014 | 0.0031 |
| NAT（02:41–03:31） | 0.833 h | 同上 | 0.833 × 0.062 | 0.0517 |
| NAT 的公網 IPv4 | 0.834 h | 同上 | 0.834 × 0.005 | 0.0042 |
| **合計** | | | | **約 10.77** |

- 本帳號拿不到帳單，全部是估算，算法見 [WP0](WP0-cost-baseline.md)。
- 不含：NAT 與 endpoint 的資料處理費（$0.062／GB、$0.01／GB；資料量沒量，主要是 1.45 GB 映像經 ECR endpoint 拉了幾次）、ECR 儲存（1.45 GB 存放約 4.5 小時，不到 $0.01）、S3 請求費（約 2,000 次 PUT／GET，不到 $0.02）。

### 否定項目的替代方案

| 被否定的檢核點 | 替代方案 | 多出的成本或限制 |
|---|---|---|
| #6 照範例只拔 NAT 能回話（否定） | 打開 `bedrock-runtime` endpoint 的 private DNS，加 STS interface endpoint | STS endpoint 單 AZ $10.22／月；ClawHub 線上安裝技能、`web_*` 工具都不能用 |

### 清理確認

- [x] Runtime `wp7_openclaw`、`USAGE_LOGS` 投遞 `wp7_openclaw-usage-src`、ECR repo `wp7-openclaw`、role `/wp/wp7-openclaw-exec` 已刪除（2026-10-04 07:19 UTC）
- [x] Guardrail `wp7_openclaw_content_guardrail`、secret `wp7/openclaw/gateway-token`（不保留復原期）、S3 bucket `wp7-openclaw-050571774557` 已刪除（06:33 UTC）
- [x] Runtime log group 已刪除；`/openclaw/container` 是帳號裡另一套 openclaw 部署的 log group，只刪了我們寫的 50 個 `test_*` stream
- [x] NAT gateway、EIP、IGW、public subnet 已刪除（03:31 UTC）；interface endpoint × 9、S3 gateway endpoint、endpoint 安全群組已刪除（04:08 UTC）
- [x] Browser、Gateway、Policy、Memory：沒有建立
- [ ] VPC `wp7-vpc`（private subnet × 2、路由表、`wp7-runtime-sg`）：等 AgentCore 網卡自動清掉，隔天刪；也給 WP1 #11 用
- [ ] 服務連結角色 `AWSServiceRoleForBedrockAgentCoreNetwork`：確認東京沒有 VPC 模式的 AgentCore 資源後刪
- [ ] 隔天確認 Runtime 沒有仍在跑的資源（`list-agent-runtimes`）
- 帳號裡另一套 openclaw 部署（Runtime `openclaw_agent`、`openclaw/*` secret，2026-09-13 建立、沒有 tag）不是本次建立的，沒有動。

### 要更正研究庫的段落

| 檔案:行號 | 原本寫的 | 實測結果 |
|---|---|---|
| `91-work-packages/WP7-openclaw-on-agentcore.md` 前提 | 替身 agent 約 23 秒先回、完整 OpenClaw 約 70 秒 | 不含 Telegram 與 Lambda 時，從預熱池 4.6 秒、完整約 20 秒；70 秒主要是 S3 還原等待 |
| `91-work-packages/WP7-openclaw-on-agentcore.md` 前提 | 大工作區（約 1,000 個檔案）還原要 80–115 秒 | 500 個小檔 14.5 秒（逐檔約 30 ms），與檔案數成正比 |
