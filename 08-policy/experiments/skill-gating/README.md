# 技能授權實驗：自家 MCP server（HephAgora）依購買強制

[WP2](../../../91-work-packages/WP2-capability-boundary.md) 的交付物。驗證「使用者只能用買到的技能」能不能由自家 server 強制，而不是靠 agent 或 prompt；以及 Browser 包成自家技能後能不能正常運作。

- 自家 MCP server＝**HephAgora**（`hephai/HephAgora`）。
- HephAgora 的改動在它的分支 `wp2/skill-gating`。原分支（RomanChen，2026-10-02）一直沒有推上 GitLab，2026-10-04 由 Kais 依本文件重建同名分支，用來做 WP5 #10、#11：[hephai/HephAgora `wp2/skill-gating`](https://gitlab.hephaistudio.dscloud.biz:49156/hephai/HephAgora/-/tree/wp2/skill-gating)（`de3df3d6`）。重建版和原版的差異：
  - 沒有 Browser MCP server（`wp2-browser-server.ts`），所以 #6、#7、#8 不能用重建版重現。
  - migration 合成 `036_wp2_skill_entitlements.sql`。
  - `com.wp2.todo` 改成每人一份資料（`src/wp2/todo.ts`）。
  - 本機驗收改成 `scripts/wp2/check.sh`，compose 檔用 `docker-compose.wp2-local.yml`，project 名 `hephagora-wp2`、port 13100。
- 本目錄放 agent、呼叫腳本與說明。
- 已完成：本機 #0、#1、#2、#9、#12；AWS（東京）#3、#4、#5、#6、#7、#10。#8 於 2026-10-05 補做，見 [`takeover/`](takeover/README.md)；#11 見 WP2 回填。

## 架構

```
測試腳本（扮演後端：用測試 consumer 私鑰簽 60 秒 actor JWT）
   │ InvokeAgentRuntime / InvokeHarness（payload 或 remote_mcp header 帶 actor JWT）
   ▼
AgentCore Runtime wp2_agent（Strands＋Haiku 4.5）或 Harness wp2_harness
   │ execution role 沒有任何 Browser 權限
   │ MCP（streamable HTTP），Authorization: Bearer <actor JWT>
   ▼
EC2 上的 HephAgora 測試版：POST /mcp（標準 MCP 入口）
   ├─ 驗 actor JWT → 依 skill_entitlements 過濾 tools/list、invoke 未購買 403、每小時上限 429、寫調用帳本
   ├─ com.wp2.todo / com.wp2.flight：沒有 binding，走內建 stub
   └─ com.wp2.flight-web → wp2-browser（EC2 instance role）→ AgentCore Browser wp2_browser
                                                      （MANAGED：URLBlocklist *、URLAllowlist example.com）
```

## 實作摘要

| 改動 | 檔案（HephAgora） | 說明 |
|---|---|---|
| 必帶使用者身分 | `src/auth/jwt-verify.ts`、`src/discovery/routes.ts`、`src/execution/routes.ts` | `HEPHAGORA_REQUIRE_ACTOR=1` 時，`/v1/discover`、`/v1/invoke` 不帶 actor JWT 一律 401。未設時行為不變 |
| 已購買技能 | `migrations/036_wp2_skill_entitlements.sql`、`src/auth/skill-entitlement.ts` | `skill_products`（哪些 service 要買）、`skill_entitlements`（誰買了什麼）。discover 由 server 排除未購買的付費 service（caller 的 `hints.service_ids` 只能再縮小）；invoke 未購買回 403 |
| 每小時上限 | `migrations/037_wp2_skill_rate_limit.sql`、同上 | `skill_products.max_calls_per_hour`；計數用既有調用帳本 `tool_invocations`（該使用者、該 service、一小時內 `status='ok'`），超過回 429 |
| 標準 MCP 入口 | `src/mcp-facade/routes.ts`、`src/index.ts` | `HEPHAGORA_MCP_FACADE=1` → `POST /mcp`（stateless）。`tools/list` 用同一套購買過濾；`tools/call` 內部轉 `/v1/invoke`，購買檢查、限流、帳本全部沿用。工具名 `<service_id 點換底線>__<capability>`；看不到的工具一律回 Unknown tool |
| Browser 技能 | `src/mcp-servers/wp2-browser-server.ts`、`package.json` | 另一個 MCP server 容器：`StartBrowserSession` → SigV4 簽 automation WebSocket（照官方 TS SDK）→ `playwright-core` 開網址、讀標題與內文 → 一定 `StopBrowserSession`。新增依賴 `@aws-sdk/client-bedrock-agentcore`、`playwright-core` |

一次性改動：授權約 70 行、MCP 入口約 150 行、Browser server 約 200 行。表都空、開關都不開時，HephAgora 行為與原本相同。

## 本目錄

| 檔案 | 用途 |
|---|---|
| `agent/` | Runtime 用的 agent（`main.py`、`Dockerfile`、`requirements.txt`）。每個請求用 payload 的 `actor_token` 連 HephAgora `/mcp`，模型能用哪些工具完全由 HephAgora 決定。另有量測入口 `probe=browser`（#6）、`probe=mcp_latency`（#10），以及 WP5 用的 `probe=abuse`（WP5 #10）、`probe=profile`（WP5 #11） |
| `results/` | WP5 #10、#11 的原始輸出（2026-10-04） |
| `invoke_runtime.sh` | 呼叫 Runtime；payload 裡的 `__TOKEN_<user>__` 會換成當下現簽的 actor JWT |
| `harness_check.py` | 呼叫 Harness；每次覆寫 `tools`（remote_mcp header 帶 token），可選覆寫 `allowedTools` |

套件版本已鎖（`bedrock-agentcore` 1.24.0、`strands-agents` 1.57.2、`mcp` 2.1.1）。`mcp` 2.x 沒有 `streamablehttp_client`，改用 Strands `MCPClient(url=, headers=)`。

## 重現

**本機（HephAgora repo 根目錄）**

以下是 2026-10-04 重建版的步驟。原版另有 `check-rate.sh`、`check-mcp.sh`、`check-browser.sh`、`trim-demo-services.sql`，重建版已併進 `check.sh`、`seed.sql`；Browser（#7）沒有重建。

```bash
npm ci                                  # 簽 actor JWT 要用 repo 裡的 jose
# 獨立 project、port 13100，不碰日常開發的 DB；開關寫在 docker-compose.wp2-local.yml
APP_PORT=13100 docker compose -p hephagora-wp2 --profile localdb \
  -f docker-compose.yml -f docker-compose.wp2-local.yml up -d --build db app
export PSQL="docker compose -p hephagora-wp2 exec -T db psql -U hephagora -d hephagora"
bash scripts/wp2/setup-consumer.sh      # 測試 consumer wp2-test：產金鑰到 .wp2-keys/、公鑰寫進 DB
$PSQL -v ON_ERROR_STOP=1 < scripts/wp2/seed.sql   # wp2 服務、購買、每人 todo；其他 demo service 下架
RATE=1 bash scripts/wp2/check.sh        # #1、#2、/mcp 入口、過期 token；RATE=1 加跑 #9（把 userA 的 todo 打滿 30 次）
docker compose -p hephagora-wp2 down -v # 收掉（含測試 DB）
```

重跑 `RATE=1` 前，先清掉 userA 這一小時的帳：`$PSQL -c "DELETE FROM tool_invocations WHERE billed_consumer_id='wp2-test'"`。

**AWS（東京，2026-10-02 建、當天刪）**

| 資源 | 設定 |
|---|---|
| VPC＋公開子網路＋IGW＋安全群組 | 專用，只開 TCP 13000，不開 SSH |
| EC2 `t4g.medium` | AL2023 arm64、30 GB gp3 加密；user-data 跑 `scripts/wp2/ec2/run.sh`（docker run db／app／wp2-browser、匯入 seed、8 小時自動關機）；IMDSv2、hop limit 2（容器要拿 instance role） |
| IAM | `/wp/wp2-hephagora-ec2`（ECR 拉 `wp2-*`、讀 S3 `deploy/`、只能操作 `wp2_browser`、SSM）；`/wp/wp2-agent-exec`（拉 agent 映像、log、Haiku jp，**無 Browser**）；`/wp/wp2-harness-exec`（官方最小範例去掉 Browser／Code Interpreter／Memory） |
| ECR | `wp2-hephagora`、`wp2-agent`（映像在開發機 build，HephAgora 分支不用推 GitLab） |
| S3 | Browser 企業政策檔、EC2 部署檔（只含公鑰） |
| AgentCore | Browser `wp2_browser`（MANAGED 政策）；Runtime `wp2_agent`（PUBLIC、閒置 300 秒）；Harness `wp2_harness`（memory disabled、`allowedTools: ["@ha"]`）；`USAGE_LOGS` 投遞 |

模型：`jp.anthropic.claude-haiku-4-5-20251001-v1:0`。actor JWT 的 audience 在 EC2 版設成 `http://wp2-hephagora.test`。

## 結果（2026-10-02）

**本機**

| # | 檢核點 | 結果 | 證據 |
|---|---|---|---|
| 0 | 自家 server 有沒有依使用者驗證身分 | **有，但不強制**：actor JWT（`ai_family_backend` 簽、60 秒、RS256），但 discover / invoke 不帶也放行。補上：開關讓兩支必帶 | 不帶 token：改前 200、改後 401；壞 token 401；帶 A / B 的 token 200，帳本分別記成 `user-a`、`user-b` |
| 1 | A 的工具清單沒有 flight，B 的有 | 通過 | `check.sh`；A 自帶白名單指定 flight 仍無。`/mcp` 版（`check-mcp.sh`）也通過 |
| 2 | A 直接呼叫 flight 被拒 | 通過 | `403 {"error":"skill not purchased"}`；`/mcp` 版 A 猜工具名回 `Unknown tool` |
| 9 | 技能限流與計量 | 通過 | 35 次中第 1–30 次 200、第 31–35 次 429；帳本 `ok` 30、`http_429` 5 |

**AWS**

| # | 檢核點 | 結果 | 證據 |
|---|---|---|---|
| 3 | Runtime 的 agent 把使用者 token 帶到 server | 通過 | A、B 分別呼叫 `wp2_agent`；EC2 帳本記成 `user-a` todo_add、`user-b` flight_search。A 的工具清單沒有 flight，回答「目前沒有查詢機票的能力」 |
| 4 | Harness `remote_mcp` 每次帶不同使用者 token | **能** | 同一個 Harness，`InvokeHarness` 每次覆寫 `tools`（headers 帶各自 token）；帳本 `user-a` todo_add、`user-b` flight_search |
| 5 | 覆寫 `allowedTools` 後模型不知道被排除的工具 | 通過 | B（有買 flight）帶 `["@ha/com_wp2_todo__*"]`：問機票答「我目前沒有查詢機票的能力」；要它列出所有工具，只列 `ha_com_wp2_todo__todo_add`、`ha_com_wp2_todo__todo_list` |
| 6 | VM 裡 `StartBrowserSession` 收到 `AccessDenied` | 通過 | `wp2-agent-exec` 對 `wp2_browser` 與 `aws.browser.v1` 都 `AccessDeniedException` |
| 7 | Browser 包成自家工具：B 成功、A 被拒、白名單外被擋 | 通過 | 經 Runtime → HephAgora → wp2-browser：B 開 example.com 得到「Example Domain」；A 看不到工具，直接打 `/v1/invoke` 回 403；B 開 google.com 得到 `ERR_BLOCKED_BY_ADMINISTRATOR`，AI 回報被政策擋 |
| 10 | 延遲 | 一般工具 p50 **20.9 ms**（p90 23.4，n=20）；Browser 工具端到端 p50 **5.8 s**（n=3） | `probe=mcp_latency`（VM 內直接用 MCP 呼叫，不經模型）。Browser 時間大多是開 session（本機量到約 4.3 s） |

其他觀察：

- **Runtime 一次對話**：從呼叫到回答約 3–4.5 s，MCP 連線加列工具不到 0.1 s，其餘是模型。
- **Harness 冷啟動**：同一個 Harness 第一次呼叫約 38 s，之後約 3–4 s。
- **Harness 工具名會加伺服器前綴**（`ha_…`），`allowedTools` 則用 `@ha/<原工具名>`。
- **Harness 傳 token 的方式**：token 是明文放在每次 `InvokeHarness` 的 `tools` 參數，由後端組好。官方註明以 SigV4 呼叫時 Harness 不會往下游傳使用者身分（[harness-security](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-security.html)）。
- **CreateHarness 預設會建 Memory**：要明確設 `memory: {"disabled": {}}`。另外會自動建一個底層 Runtime（`harness_<name>-…`），刪 Harness 時一起刪。
- **與文件的差異**：server 端操作網頁用固定流程的 Playwright（開網址、讀標題與內文），不是文件寫的瀏覽子 agent（browser-use／Nova Act）。權限與白名單驗得到，但沒測「子 agent 自己亂逛」。
- **#9 用的不是 B 本人**：B 在 #1、#2 已用掉額度，改用和 B 買一樣東西的新使用者，才能從 0 驗「第 31 次被擋」。
- **#9 的計數不是原子操作**：先數再放行，大量並發時可能多放行幾次；本次為循序呼叫。

## #12 新增一個技能要碰的東西

前提：上面的一次性改動已經上線。之後**每新增一個技能，不用改 HephAgora 的程式碼**，只動資料與設定。

| # | 要碰的東西 | 誰做 | 現況 | 本次實驗怎麼做 |
|---|---|---|---|---|
| 1 | Service manifest（能力名稱、描述、`input_schema`、binding） | 技能開發者 | 現有流程：`PUT /v1/registry/services/{id}` → 送審 → 審核 → 發布（HephAgora `docs/api-registry.md` §15.2） | 捷徑：seed SQL 直接寫成 `published` |
| 2 | 技能後端（HTTP adapter、MCP server） | 技能開發者 | 現有 | todo、flight 走內建 stub；flight-web 走 `wp2-browser` |
| 3 | 檢索索引（description 進 BM25；有 Azure embedding 時發布即向量化） | HephAgora 自動 | 現有 | 沒設 embedding，純 BM25。description 要含使用者會講的詞 |
| 4 | 標成付費：`skill_products` 一筆（含每小時上限） | 營運 | **新增**（036、037）；目前沒有管理介面 | seed SQL |
| 5 | 購買紀錄：`skill_entitlements` | 購買流程 | **新增**；**資料來源未定**：從 `ai_family_backend` 的購買紀錄（能力包？）同步，還是 HephAgora 每次回查 | seed SQL |
| 6 | OAuth 類技能：manifest 的 `oauth_scopes`、client 憑證環境變數 | 技能開發者＋維運 | 現有（HephAgora §17） | 未測 |
| 7 | 需要瀏覽器的技能 | 維運＋技能開發者 | 每個技能（或每組白名單）一個自訂 Browser（MANAGED 政策檔放 S3，**只在 CreateBrowser 時讀，改白名單要重建 Browser**）；server 角色加該 Browser ARN 的權限；manifest 的 `mcp_server` binding 指向 browser server | 一個 `wp2_browser`、一個 `com.wp2.flight-web` |
| 8 | Agent 端的 Skill 檔 | — | **不需要**：Runtime agent 與 Harness 都是每次從 HephAgora `/mcp` 動態拿工具清單。Harness 的 `allowedTools` 若要再收窄，用 `@ha/<工具名>` | — |
| 9 | MCP 工具對應 | — | **自動**：MCP 入口依 manifest 產生，工具名 `<service_id 點換底線>__<capability>` | — |

使用者身分（actor JWT、consumer 金鑰註冊）是每個 consumer 一次性的設定，不是每個技能都要做。
