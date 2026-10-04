# WP2 能力邊界：自家 MCP server 依技能授權

> 回答：「使用者只能用買到的技能」能不能由**自家的 MCP server** 強制執行，而且 agent 繞不過？Browser 這類需要 AWS 權限的內建工具，包進自家 MCP server 之後還能不能正常運作（含使用者接手登入）？Gateway 還需不需要？
>
> 估點：8。優先序：1（風險高、價值高）。前置：WP0、自家 MCP server 的測試環境。分群：B。

## 設計變更背景

原本的設計是用 AgentCore Gateway + Policy 擋沒買的技能。後來確認：

- 公司**已經有自家的 MCP server**，技能和「誰買了什麼」的資料都在自家。
- Gateway 呼叫後端時用的是所有 target 共用的身分，自家 server 不能無條件信任來自 Gateway 的請求，**本來就要自己驗證使用者**。再加 Gateway 的 Policy，等於同一件事做兩次。
- MCP server 類型的 target **不支援直接轉傳使用者 token**，只能用 OBO 換發或 interceptor 注入身分（研究庫 [03 Gateway outbound 表](../03-gateway/README.md)）。
- **Browser、Code Interpreter 不經過 Gateway**：agent 是用 execution role 直接呼叫的。execution role 是所有使用者共用的，而且 VM 裡的程式讀得到它的憑證，IAM 沒辦法依使用者擋。

新設計：

```
Agent（Runtime VM；execution role 沒有 Browser 權限）
   │  帶著「這位使用者」的短效 token
   ▼
自家 MCP server（唯一的技能授權點）
   ├─ 驗證使用者 token → 查已購買的技能 → 過濾 tools/list、檢查 tools/call、限流、計量
   ├─ 一般技能（Todo…）：自己的業務邏輯
   └─ 需要瀏覽器的技能：server 用自己的 AWS 憑證開 AgentCore Browser
        （技能專屬的 Browser 資源有網域白名單）→ server 端的瀏覽子 agent 操作
        → 只回傳結構化結果；遇到登入頁時，Live View URL 由 server 直接推給 App
```

Gateway 降為**選配**：只有在需要 AWS connector（例如 Web Search）、聚合很多非自家後端、或要 Cedar 形式驗證與 Guardrails 時才加在前面。選配的檢核點放在本檔最後。

## 前提

| 前提 | 來源等級 | 出處 |
|---|---|---|
| 自家 MCP server 能依使用者身分過濾 `tools/list`、拒絕未購買工具的 `tools/call` | `[推測]`（要看自家 server 的現況，見步驟 0） | — |
| MCP 規格的授權機制是 OAuth：MCP server 當 resource server，驗證每個請求帶的 token | `[官方已寫]`（MCP 規格） | [MCP Authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) |
| Runtime 裡自己寫的 agent（例如 Strands 的 MCP client）可以在連線時帶入每位使用者不同的 header | `[推測]` | — |
| Harness 的 `remote_mcp` header 可以引用 Identity token vault 的 ARN；**能不能每次呼叫帶入不同使用者的 token，沒有文件** | `[推測]` | [00 Harness vs Runtime](../00-overview/harness-vs-runtime.md) |
| `InvokeHarness` 可以在呼叫時覆寫 `allowedTools` | `[官方已寫]`，未實證 | 同上 |
| Browser 由 agent 用 IAM 直接呼叫，不經過 Gateway；任何有 IAM 憑證的程式都能開 Browser session（不限於 Runtime 內） | `[官方已寫]` / `[推測]`（後半句是依 API 呼叫方式推論） | [05 內建工具](../05-built-in-tools/README.md) |
| Browser 企業政策 MANAGED 的 `URLAllowlist` 無法被 session 覆寫 | `[官方已寫]` | [browser-reliability-security.md](../05-built-in-tools/browser-reliability-security.md) |
| Live View URL 等於瀏覽器的操作權限，最長 300 秒 | `[官方已寫]` / `[推測]` | 同上 |

## 步驟

0. **盤點自家 MCP server 的現況（先做，決定後面的工作量）：**
   - 目前有沒有驗證使用者身分（OAuth / JWT）？如果沒有，在測試環境先補上最小的 JWT 驗證（例如驗 Cognito 發的 token），這會是本 WP 最大的工作項目。
   - 「使用者買了哪些技能」存在哪裡、server 能不能在每次請求時查到。
   - 部署一份**測試用的 server 執行個體**，資源加 tag `wp=WP2`、`owner`、`project=hyfai`，不要直接用正式環境。
1. **兩位測試使用者：** 用 Cognito 發 JWT。使用者 A 只買 `todo`；使用者 B 買了 `todo` 和 `flight`。
2. **在自家 server 實作技能授權：** `tools/list` 只回傳該使用者買的技能所屬的工具；`tools/call` 再檢查一次。用 A、B 的 token 各自呼叫，記錄回應。
3. **繞過測試：** 用 A 的 token 直接呼叫 `flight` 技能的工具（假裝知道工具名稱），應該被拒。
4. **身分從 agent 帶到 server（Runtime）：** 在 Runtime 裡寫一個最小的 agent，後端把使用者的短效 token 放進呼叫內容，agent 連 MCP server 時帶上。分別用 A、B 呼叫，確認 server 收到的是正確的使用者。
5. **身分從 agent 帶到 server（Harness）：** 建一個 Harness，用 `remote_mcp` 接自家 server。試試看能不能在每次 `InvokeHarness` 時帶入不同使用者的 token（覆寫 `tools` 裡的 header，或其他方式）。做不到就記錄下來，這會是「必須用 Runtime」的理由。同時驗證 `allowedTools` 覆寫的效果。
6. **Execution role 沒有 Browser 權限：** Runtime 的 execution role 不給任何 `bedrock-agentcore` Browser 相關權限。在 VM 裡用程式直接呼叫 `StartBrowserSession`，應收到 `AccessDenied`。
7. **把 Browser 包成自家 server 的工具：**
   - 建一個 Browser 資源，企業政策用 MANAGED：`URLBlocklist: ["*"]` 加上測試站的 `URLAllowlist`。
   - 在自家 server 加一個工具（例如 `flight_search_on_web`）：server 用自己的 AWS 憑證開 Browser session，由 server 端的瀏覽子 agent（browser-use 或 Nova Act）操作測試站，只回傳結構化結果。
   - 用 B 呼叫成功；用 A 呼叫被拒。再讓子 agent 嘗試開白名單以外的網址，應被擋。
8. **使用者接手登入改由 server 主導：** 測試站需要登入時，server 端子 agent 先停止 → `take_control` → server 把 Live View URL **直接推給 App**（用一個簡單的推播端點模擬）→ 使用者登入、交還 → `release_control` → 繼續。檢查 agent 的對話內容和 trace 裡**沒有出現 Live View URL**。
   - 這一步可以沿用 [WP4](WP4-browser-takeover.md)（已由其他工程師完成）的程式，只是把呼叫位置從 agent 搬到 server。
9. **限流與計量：** 在自家 server 對 `flight` 技能設「每小時最多 30 次」，用 B 連打 35 次，確認第 31 次被擋，並有計量紀錄。
10. **延遲：** 量測 agent → 自家 server 一般工具的 p50；以及包了 Browser 的工具，從呼叫到拿到結果的端到端時間。
11. **成本：** 呼叫包了 Browser 的工具 20 次，隔天用 WP0 的腳本拉 Browser 費用；另外記錄測試用 server 的基礎設施費用。

## 檢核點

| # | 檢核點 | 來源等級 | 判定 |
|---|---|---|---|
| 0 | 自家 MCP server 目前有沒有依使用者驗證身分；沒有的話補上最小驗證的範圍 | — | 有 / 沒有；補上的內容 |
| 1 | A 的 `tools/list` 沒有 `flight` 的工具；B 的有 | `[推測]` | 是 / 否 |
| 2 | A 直接呼叫 `flight` 的工具被拒 | `[推測]` | 是 / 否；貼錯誤回應 |
| 3 | Runtime 的 agent 能把每位使用者的 token 帶到 server，server 收到的身分正確 | `[推測]` | 是 / 否 |
| 4 | Harness 的 `remote_mcp` 能不能每次呼叫帶不同使用者的 token | `[推測]` | 能 / 不能；不能就記錄為「必須用 Runtime」 |
| 5 | Harness 覆寫 `allowedTools` 後，模型不知道被排除的工具 | `[官方已寫]`，未實證 | 是 / 否；貼模型回應 |
| 6 | VM 裡直接呼叫 `StartBrowserSession` 收到 `AccessDenied` | `[官方已寫]`（IAM 行為） | 是 / 否 |
| 7 | 包成自家工具的 Browser：B 成功、A 被拒、白名單以外的網址被擋 | `[推測]` | 三個是 / 否 |
| 8 | 接手登入由 server 主導可以走完；agent 的對話與 trace 裡沒有 Live View URL | `[推測]` | 是 / 否 |
| 9 | 自家 server 的技能限流與計量生效 | 自家實作 | 是 / 否 |
| 10 | 一般工具呼叫的延遲 p50；包了 Browser 的工具端到端時間 | — | 毫秒 / 秒 |
| 11 | 20 次 Browser 工具呼叫的實際費用；測試 server 的費用 | 成本 | USD |
| 12 | 「新增一個技能」實際要碰的東西清單（Skill 檔、server 的工具與授權設定、Browser 資源） | — | 清單 |

**阻斷級（先做）：** #0、#1、#2、#3、#6、#7。

## 判定對選型的影響

- #1、#2、#3 都通過 → 技能授權放在自家 MCP server 可行，**不需要 Gateway**。
- #4 是「不能」→ 主 agent 必須用 Runtime，不能用 Harness。
- #6、#7 都通過 → Browser 依技能收費可行，VM 碰不到 Browser。
- #7 的白名單沒有擋住 → 改用 VPC + Network Firewall 當硬邊界（研究庫 [browser-reliability-security.md](../05-built-in-tools/browser-reliability-security.md) 的建議）。
- #12 的清單就是之後技能上架的 SOP 草稿。

## 選配：保留 Gateway 時才做

只有在決定把 Gateway 放在自家 MCP server 前面時才做。

| # | 檢核點 | 來源等級 |
|---|---|---|
| G1 | Gateway 以「MCP server」類型的 target 接自家 server，工具清單同步正常；新增工具後要呼叫 `SynchronizeGatewayTargets` 才看得到 | `[官方已寫]` |
| G2 | 使用者身分怎麼帶到自家 server：OBO 換發（IdP 要支援 token exchange）或 REQUEST interceptor 注入，哪一種可行、各多出多少延遲 | `[推測]` |
| G3 | Policy `ENFORCE` 下依 JWT claim 過濾 `tools/list`；陣列型 claim 的三種寫法哪一種能用 | `[官方已寫]` / `[推測]` |
| G4 | Dogwood `count` 限制生效；是否需要呼叫端帶 session ID | `[矛盾]` |
| G5 | `UpdatePolicy` 切 `LOG_ONLY` 後 policy 失效，以及怎麼用 IAM 鎖住 | `[官方已寫]` |
| G6 | 1,000 次呼叫的 Gateway + Policy 實際費用 | 成本 |

Cedar 規則可以先用 [`08-policy/experiments/prompt-to-policy/`](../08-policy/experiments/prompt-to-policy/) 在本機驗證。

## 交付

- 測試用自家 MCP server 的授權實作、Browser 工具的實作、Runtime agent 的範例，放在 `08-policy/experiments/skill-gating/`（若含自家 server 的程式碼不便放進研究庫，只放設定與說明，並註明程式碼位置）。
- 本檔案下方的回填區。

## 關聯

- 研究庫：[03 Gateway](../03-gateway/README.md)（outbound 表、MCP server target）、[05 內建工具](../05-built-in-tools/README.md)、[browser-reliability-security.md](../05-built-in-tools/browser-reliability-security.md)、[00 Harness vs Runtime](../00-overview/harness-vs-runtime.md)、[01 Runtime：安全要點](../01-runtime/README.md#安全要點)、[08 Policy](../08-policy/README.md)
- 相關 WP：[WP3](WP3-sandbox-egress.md)（VM 不能上網時連得到自家 server 嗎）、[WP4](WP4-browser-takeover.md)（接手登入的既有實作）、[WP5](WP5-user-state-isolation.md)（使用者 token 在 VM 裡被濫用的影響範圍）
- 既有腳本：[`05-built-in-tools/experiments/url-guard/`](../05-built-in-tools/experiments/url-guard/)（導覽白名單檢查）

## 回填

### 本機部分（#0、#1、#2、#9、#12）

- 負責人：RomanChen
- 執行日期：2026-10-02
- 區域：本機（HephAgora 以 docker compose 跑在開發機，資料庫為本機 Postgres）；AWS 部分預定東京 `ap-northeast-1`
- 資源 tag：本機部分未建 AWS 資源
- 使用的 AWS 帳號：本機部分未使用
- 自家 MCP server：**HephAgora**（`hephai/HephAgora`），實驗分支 `wp2/skill-gating`
- 實作、重現步驟、#12 清單：[`08-policy/experiments/skill-gating/`](../08-policy/experiments/skill-gating/README.md)

#### 結論（三句內）

1. **HephAgora 有依使用者驗身分的機制但不強制**：actor JWT（`ai_family_backend` 簽、60 秒）已有，但 `/v1/discover`、`/v1/invoke` 不帶 token 也放行；本機加一個開關改成必帶。
2. **「只能用買到的技能」在 server 端做得到，而且改動小**：加兩張表（付費技能、購買紀錄），discover 不列未購買的、invoke 未購買回 403、每小時上限超過回 429；一次性約 70 行，之後新增技能只動資料、不改程式。
3. **但還沒有證明 agent 繞不過**：本次測的是 HephAgora 自己的 HTTP API，不是標準 MCP；HephAgora 對外也不是 MCP server，agent 要接得先包一層 MCP 轉接。真正的 agent 要等 AgentCore 權限後做 #3–#8。

#### 檢核表

| # | 檢核點 | 來源等級 | 結果 | 證據 | 對選型的影響 |
|---|---|---|---|---|---|
| 0 | 自家 server 有沒有依使用者驗證身分 | — | **有，但不強制**。補上：開關 `HEPHAGORA_REQUIRE_ACTOR=1` 讓 discover / invoke 必帶（4 檔約 20 行） | 不帶 token：改前 200、改後 401；壞 token 401；帶 A、B 的 token 200，調用帳本分別記成 `user-a`、`user-b` | 身分驗證不是 WP2 最大的工作量，現有 actor JWT 可沿用 |
| 1 | A 的工具清單沒有 flight；B 的有 | `[推測]` | 通過（以 `/v1/discover` 代替 `tools/list`） | `check.sh`：A 查「機票」無結果、B 有 `com.wp2.flight`；A 自帶白名單指定 flight 仍無 | 過濾由 server 決定，caller 的白名單只能縮小 |
| 2 | A 直接呼叫 flight 被拒 | `[推測]` | 通過 | `403 {"error":"skill not purchased","service_id":"com.wp2.flight"}`；B 呼叫 200；免費技能不受影響 | — |
| 3 | Runtime 的 agent 把使用者 token 帶到 server | `[推測]` | 未做 | — | 待 AgentCore 權限；HephAgora 測試版要放上 AWS |
| 4 | Harness `remote_mcp` 每次帶不同使用者 token | `[推測]` | 未做 | — | 同上 |
| 5 | Harness 覆寫 `allowedTools` 後模型不知道被排除的工具 | `[官方已寫]`，未實證 | 未做 | — | 同上 |
| 6 | VM 裡 `StartBrowserSession` 收到 `AccessDenied` | `[官方已寫]` | 未做 | — | 同上 |
| 7 | Browser 包成自家工具：B 成功、A 被拒、白名單外被擋 | `[推測]` | 未做 | — | 同上 |
| 8 | 接手登入由 server 主導 | `[推測]` | 未做 | — | 同上 |
| 9 | 技能限流與計量 | 自家實作 | 通過 | `check-rate.sh`：35 次中第 1–30 次 200、第 31–35 次 429；帳本 `ok` 30、`http_429` 5 | 計數沿用既有調用帳本，不必另建計數器；先數再放行非原子，並發可能多放行（未測） |
| 10 | 延遲 | — | 未做 | — | 待 AgentCore 權限 |
| 11 | 費用 | 成本 | 未做 | — | 同上 |
| 12 | 新增一個技能要碰的東西 | — | 完成 | [清單](../08-policy/experiments/skill-gating/README.md#12-新增一個技能要碰的東西) | 未決：購買紀錄的來源（`ai_family_backend` 同步或回查）、Browser 技能、agent 端 Skill 檔、MCP 轉接 |

- #9 用的不是 B 本人：B 在 #1、#2 已用掉額度，改用和 B 買一樣東西的新使用者，才能從 0 驗「第 31 次被擋」。

#### 實際費用

| 資源 | 用量 | 用量來源 | 單價 | 估算金額（USD） |
|---|---|---|---|---|
| 本機 docker | — | — | — | 0 |

#### 否定項目的替代方案

本機部分沒有否定項目。

#### 清理確認

- [x] 本機部分未建任何 AWS 資源
- [ ] 本機 docker（HephAgora、Postgres）保留，給後續檢核點沿用

#### 要更正研究庫的段落

| 檔案:行號 | 原本寫的 | 實測結果 |
|---|---|---|
| `91-work-packages/WP2-capability-boundary.md:36` | 自家 MCP server 能依使用者身分過濾、拒絕未購買工具：`[推測]` | 本機實證可行（HephAgora，需上述改動）；agent 端未驗 |
| `91-work-packages/README.md:171` | 同上：`[推測]` | 同上 |

### AWS 部分（#3–#7、#10、#11）

- 負責人：RomanChen
- 執行日期：2026-10-02（資源當天建、當天刪）
- 區域：ap-northeast-1（東京）
- 資源 tag：`wp=WP2`、`owner=roman`、`project=hyfai`
- 使用的 AWS 帳號：050571774557（IAM user `RomanChen`，加掛 inline policy `wp-roman-agentcore`：`bedrock-agentcore:*`、`cognito-idp:*`，限東京；B 群全部做完後移除）
- 架構、資源清單、重現步驟：[`08-policy/experiments/skill-gating/`](../08-policy/experiments/skill-gating/README.md)

#### 結論（三句內）

1. **agent 繞不過自家 server 的技能授權**：Runtime 與 Harness 的 agent 都帶使用者 token 經標準 MCP 連 HephAgora，模型只看得到該使用者買過的工具；VM 的 execution role 開不了 Browser，Browser 只能經 server 代開，白名單外的網址被 MANAGED 政策擋下。**不需要 Gateway。**
2. **Harness 也能用**：`InvokeHarness` 每次覆寫 `tools` 就能帶不同使用者的 token，`allowedTools` 覆寫後模型確實不知道被排除的工具；代價是第一次呼叫約 38 秒冷啟動，且 token 由後端明文組進呼叫參數。
3. **延遲與費用都小**：agent → 自家 server 一般工具 p50 約 21 ms；Browser 工具端到端約 5.8 秒，大部分是開 session。費用見下方。

#### 檢核表

| # | 檢核點 | 來源等級 | 結果 | 證據 | 對選型的影響 |
|---|---|---|---|---|---|
| 3 | Runtime 的 agent 把每位使用者的 token 帶到 server，身分正確 | `[推測]` | 通過 | EC2 帳本：`user-a` todo_add、`user-b` flight_search；A 的工具清單無 flight | 技能授權放自家 server 可行 |
| 4 | Harness 的 `remote_mcp` 能不能每次帶不同使用者的 token | `[推測]` | **能** | `InvokeHarness` 覆寫 `tools` 的 headers；帳本 `user-a` todo_add、`user-b` flight_search | 主 agent 不必限定 Runtime；但 token 要由後端每次組進參數 |
| 5 | Harness 覆寫 `allowedTools` 後模型不知道被排除的工具 | `[官方已寫]`，未實證 | 通過 | B 帶 `["@ha/com_wp2_todo__*"]`：「我目前沒有查詢機票的能力」；列工具只列 2 個 todo 工具 | 可當第二層防線；第一層仍是 server |
| 6 | VM 裡直接呼叫 `StartBrowserSession` 收到 `AccessDenied` | `[官方已寫]` | 通過 | `wp2-agent-exec` 對自訂 browser 與 `aws.browser.v1` 皆 `AccessDeniedException` | VM 碰不到 Browser |
| 7 | 包成自家工具的 Browser：B 成功、A 被拒、白名單外被擋 | `[推測]` | 通過 | B：Example Domain；A：工具不可見，直打 `/v1/invoke` 403；B 開 google.com：`ERR_BLOCKED_BY_ADMINISTRATOR` | Browser 依技能收費可行 |
| 8 | 接手登入由 server 主導 | `[推測]` | 未做（改天） | — | 要另測手機能否開 Live View（DCV 網頁客戶端官方不支援 iOS／Android） |
| 10 | 一般工具延遲 p50；Browser 工具端到端 | — | 21 ms（p90 23 ms，n=20）；5.8 s（n=3） | Runtime 內 `probe=mcp_latency` | — |
| 11 | Browser 工具費用；測試 server 費用 | 成本 | Browser 每次呼叫約 **$0.00016**（實跑 5 次、計費約 5–6 秒／次），20 次換算約 $0.003；測試 server（EC2 27 分鐘）約 $0.024 | `USAGE_LOGS` → `usage_cost.py`（10:06 UTC，最後 session 結束後 1 小時）；EC2 用量×官網價 | Browser 依次計費、極便宜；Harness 一個 session 約是自寫 Runtime 的 5 倍（記憶體大） |

- 與文件的差異：server 端操作網頁用固定流程的 Playwright，不是瀏覽子 agent（browser-use／Nova Act）；沒測子 agent 自己亂逛。

#### 實際費用

| 資源 | 用量 | 用量來源 | 單價（官網） | 估算金額（USD） |
|---|---|---|---|---|
| Runtime `wp2_agent`，9 個 session（各 1–3 次呼叫＋5 分鐘閒置） | 0.029106 vCPU-h、1.372662 GB-h | `USAGE_LOGS` | $0.0895／vCPU-h、$0.00945／GB-h | 0.015578 |
| Harness `wp2_harness`（底層 Runtime），4 個 session | 0.070659 vCPU-h、3.042300 GB-h | `USAGE_LOGS` | 同上 | 0.035073 |
| Browser `wp2_browser`，5 個 session | 0.005707 vCPU-h、0.029116 GB-h（共 28 秒） | `USAGE_LOGS` | 同上 | 0.000786 |
| EC2 `t4g.medium`（HephAgora 測試版） | 0.456 h（08:33:29–09:00:51 UTC） | 啟動／終止時間 | $0.0432／h | 0.0197 |
| EBS 30 GB gp3 | 0.456 h | 同上 | $0.096／GB-月 | 0.0018 |
| 公網 IPv4 | 0.456 h | 同上 | $0.005／h | 0.0023 |
| **合計** | | | | **約 0.076** |

- 不含 Haiku 4.5 的 token 費（未量）、ECR／S3 儲存、CloudWatch Logs（量很小）。
- Browser 只記到 5 個 session：本機開發時在建立投遞前開的 2 個沒有補送（Code Interpreter 會補送，Browser 沒有）。
- 文件要求 20 次 Browser 呼叫，本次實跑 7 次（記到 5 次），20 次以每次 $0.00016 換算。
- Harness 每個 session 的 GB-h 約是 `wp2_agent` 的 5 倍（約 0.76 vs 0.15），同樣 5 分鐘閒置下單次約 $0.0087 vs $0.0017。

#### 否定項目的替代方案

AWS 部分沒有否定項目。

#### 清理確認

- [x] Runtime `wp2_agent`、Harness `wp2_harness`（含底層 Runtime）已刪除
- [x] Browser `wp2_browser` 已刪除；session 都已主動關閉，無殘留
- [x] EC2、EBS、VPC、子網路、IGW、路由表、安全群組已刪除（2026-10-02 09:00 UTC）
- [x] `USAGE_LOGS` 投遞（WP2 的 3 個 source／delivery）已刪除
- [x] IAM 角色 `/wp/wp2-hephagora-ec2`（含 instance profile）、`/wp/wp2-harness-exec` 已刪除
- [x] ECR `wp2-hephagora`、`wp2-agent`、角色 `/wp/wp2-agent-exec`、S3 `wp2-roman-browser-policy-…`、log group `wp2-usage`：與 WP3 一起刪除（11:00 UTC）
- [ ] IAM user `RomanChen` 的 `wp-roman-agentcore`：B 群全部做完後移除

#### 要更正研究庫的段落

| 檔案:行號 | 原本寫的 | 實測結果 |
|---|---|---|
| `91-work-packages/README.md:171`–`:174` | 自家 server 過濾、token 帶到 server、Browser 包裝、`allowedTools` 覆寫：`[推測]` / 未實證 | 已實證；#8 接手登入未做 |
| `00-overview/harness-vs-runtime.md:29` | `remote_mcp` 的 header 引用 token vault；每次呼叫能不能帶不同使用者的 token 沒寫 | 每次 `InvokeHarness` 覆寫 `tools` 就能帶不同使用者的 header（token 由後端明文組進參數） |
| `00-overview/harness-vs-runtime.md:36` | `allowedTools` 可以限制模型能看到的工具 | 實證：覆寫後模型不知道被排除的工具；`remote_mcp` 的工具寫成 `@<server 名>/<工具名>` |

### #8 接手登入改由 server 主導（2026-10-04）：無法驗證（阻斷）

- 負責人：Kais
- 執行日期：2026-10-04（只確認前提，沒有建資源）
- 區域：ap-northeast-1
- 資源 tag：`wp=WP2`、`owner=kais`、`project=hyfai`（本節沒有建任何資源）
- 使用的 AWS 帳號：050571774557（IAM user `KaisLinCli`）

#### 結論（三句內）

1. **#8 沒有做，兩個前提都不成立**：
   - 步驟 8 寫的「沿用 WP4 的程式」不存在。[WP4 回填](WP4-browser-takeover.md#回填)是空的，`05-built-in-tools/experiments/takeover-demo/` 從沒建立。
   - WP2 的 HephAgora 分支 `wp2/skill-gating` 沒有推上 GitLab。
2. HephAgora 已由 Kais 重建，用來做 WP5 #10、#11。重建版**不含** Browser MCP server，也沒有 `take_control`、Live View、推播端點。
3. **手機開 Live View 官方有支援**：[DCV Web Client SDK release notes](https://docs.aws.amazon.com/dcv/latest/websdkguide/doc-history-release-notes.html) 1.10.1（2025-10-22）起支援 iOS Safari／Chrome、Android Chrome 與觸控 `[官方已寫]`。
   - WP6 已在 iOS 模擬器的 Mobile Safari 實測：Live View 顯示、點擊、`take_control`／`release_control` 都成功。打字要在 viewer 加 HTML 輸入框轉送按鍵。結果在 `05-built-in-tools/experiments/mobile-takeover/`（MR !10，2026-10-04 時尚未合併）。
   - #8 剩下要驗的是：server 主導的流程、URL 不經 agent，以及真機。
   - 本節初版寫「DCV 網頁客戶端官方不支援 iOS／Android」，是照任務說明寫、沒有查證，已更正。

#### 檢核表

| # | 檢核點 | 來源等級 | 結果 | 證據 | 對選型的影響 |
|---|---|---|---|---|---|
| 8 | 接手登入由 server 主導可以走完；agent 的對話與 trace 裡沒有 Live View URL | `[推測]` | **無法驗證**（前提不存在） | `glab api projects/hephai%2FHephAgora/repository/branches?search=wp2` 回 `[]`（2026-10-04）；repo 內沒有 `take_control`／Live View 的程式 | 「使用者接手登入」仍沒有實證。選型時當作未知數；有網站需要登入的技能，先排在 #8 驗完之後 |

#### 要補做 #8 需要的東西

1. HephAgora 的 Browser MCP server（WP2 原本有，重建版沒做），加上：
   - 偵測到登入頁就停止自動操作。
   - `UpdateBrowserStream` 關閉自動化串流（`take_control`）。
   - 產生 Live View 預簽 URL（最長 300 秒）。
   - 推到模擬的 App 推播端點。
   - 等使用者交還後 `release_control`，再繼續。
2. 一個嵌入 DCV 網頁客戶端（`BrowserLiveView`）的頁面，讓手機打開推播帶的連結。可以沿用 WP6 mobile-takeover 的 viewer，含「HTML 輸入框轉送按鍵」的作法。
3. 一支真的 iOS 和一支 Android 手機，由人實際操作登入。WP6 只測過模擬器。
4. 先看 WP6 正在查的「開著 Live View 時自動化偶爾卡住」有沒有結論，卡住會直接影響「交還後繼續」。
5. 估計工時：程式 3–5 小時，加上 AWS 一個時段約 1 小時。

#### 真機若有問題時的替代方案（未驗證，供補做時比較）

| 方案 | 做法 | 代價 |
|---|---|---|
| 改用電腦接手 | 推播只通知，Live View 連結在電腦瀏覽器開 | 使用者要離開手機 |
| App 原生登入表單 | server 偵測到登入頁時，請 App 用原生表單收帳密／OTP，再由 server 填入 | 帳密會經過自家 server，資安責任和合規要另外評估 |
| 網站支援的委派授權 | 有 OAuth／裝置碼流程的網站改走授權，不操作登入頁 | 只適用部分網站 |

#### 清理確認

- [x] 本節沒有建立任何 AWS 資源
