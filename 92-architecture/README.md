# 對話 agent 架構設計

> 依 [91 技術選型調研工作包](../91-work-packages/) 的實測結果（2026-10-02～10-05，東京）定下的設計，給開發團隊照著實作。
>
> 寫法：每個事實附 WP 或實驗的連結；研究沒驗證的標「未驗證」；研究沒寫、由本文件補的標「建議」。

## 一、選型決定

| 決定 | 理由與證據 | 不採用 |
|---|---|---|
| **方案 B：AgentCore Runtime 跑自寫 agent** | 三個方案都沒有阻斷項；方案 B 每人每月含模型約 $3.4–4.2（Haiku 4.5），能力邊界與資料隔離都已實證（[決策矩陣](../91-work-packages/README.md#決策矩陣全部回填後匯整)） | 方案 A（OpenClaw 跑在 AgentCore）：每人約 $20.7，模型佔 94%，另有網路固定費（[WP7](../91-work-packages/WP7-openclaw-on-agentcore.md#回填)）。方案 C（自架）：沒有比方案 B 便宜的人數門檻，維運約 60 點（[WP6](../91-work-packages/WP6-oss-alternatives.md#8-門檻方案-c-比方案-b-便宜的使用者規模)） |
| **主 agent 用 Runtime，不用 Harness** | 預喚醒後首句 p50 170–196 ms（[WP1](../91-work-packages/WP1-runtime-session.md#回填)） | Harness 也可行，但第一次呼叫約 38 秒、使用者 token 要由後端明文組進 `tools` 參數（[skill-gating](../08-policy/experiments/skill-gating/README.md)） |
| **Runtime V1＋小 image＋預喚醒** | 小 image 時 V2 只差不到 2 秒，不值得 V2 的限制（[WP1](../91-work-packages/WP1-runtime-session.md#回填)） | V2：只有「大 image＋突發流量」才值得 |
| **一位使用者一個 session，多個聊天室共用** | 並行請求不會卡 `/ping`，前提是 handler 為 async 或多執行緒（[WP1](../91-work-packages/WP1-runtime-session.md#回填)） | 一個聊天室一個 session：不需要 |
| **部署用固定版本的 endpoint** | 透過 DEFAULT 恢復時，換版本會清空 session storage；固定版本的 endpoint 不會（[WP1](../91-work-packages/WP1-runtime-session.md#回填)） | DEFAULT endpoint |
| **技能授權只放在自家 MCP server（HephAgora），不用 Gateway** | `tools/list` 過濾、未購買呼叫被拒、身分從 Runtime 帶到 server 都通過（[WP2](../91-work-packages/WP2-capability-boundary.md#回填)） | Gateway＋Policy：server 本來就要自己驗使用者，再加等於做兩次；MCP target 不能轉傳使用者 token。授權函式庫（Cedar、OPA）省不了程式碼（[WP6](../91-work-packages/WP6-oss-alternatives.md#第-3-層工具閘道與授權)） |
| **Browser 包成 HephAgora 的技能，VM 開不了 Browser** | execution role 呼叫 `StartBrowserSession` 被拒；白名單外的網址被 MANAGED 政策擋下（[WP2](../91-work-packages/WP2-capability-boundary.md#回填)） | agent 直接開 Browser |
| **接手登入由 server 主導，同步等待** | 在 iOS 模擬器走完全程，agent 拿不到 Live View URL（[takeover](../08-policy/experiments/skill-gating/takeover/README.md)） | 非同步通知（實驗報告建議，未驗證） |
| **Runtime 放在沒有 NAT 的 VPC，用 VPC peering 連 HephAgora** | 擋得住外網，仍連得到自家 server（[WP3](../91-work-packages/WP3-sandbox-egress.md#回填)） | NAT：多一筆固定費且放行外網 |
| **Code Interpreter 用 Sandbox 模式** | 擋得住一般外網（[WP3](../91-work-packages/WP3-sandbox-egress.md#回填)）；缺口見「六」 | Public 模式 |
| **模型是設定值，預設 Haiku 4.5** | 模型費每人每月約 $0.9–1.4；品質不夠時改設定換 Sonnet 4.6（約 $2.9–3.4）（[token-cost](../90-integrations/experiments/token-cost/README.md)） | — |
| **區域：東京 `ap-northeast-1`** | 公司機器與 HephAgora 都在東京 | — |

## 二、元件與責任

| 元件 | 要做 | 不能做 |
|---|---|---|
| **App** | 帶 user token 呼叫後端；收到推播後開 Live View viewer，讓使用者接手、交還 | — |
| **後端** | 驗身分、查已購買的能力、查或分配 runtime session（對照表）、範圍外的請求先擋；每次呼叫 Runtime 前簽 60 秒的 actor JWT；需要時發範圍縮小的臨時憑證；session ID 要對得回使用者（以使用者 ID 開頭或保留對照表）；Memory 的 actorId 用不透明 ID，對照表放自家 DB（[WP5](../91-work-packages/WP5-user-state-isolation.md#回填)） | 不該有 `InvokeAgentRuntimeCommand` 權限（[WP5](../91-work-packages/WP5-user-state-isolation.md#回填)） |
| **Runtime agent** | 每個請求用 payload 裡的 actor JWT 連 HephAgora `/mcp`，工具清單完全由 HephAgora 決定；handler 為 async；長任務期間 `/ping` 回 `HealthyBusy`（[WP1](../91-work-packages/WP1-runtime-session.md#回填)） | 不自己把 prompt 或臨時憑證寫進 log |
| **HephAgora** | 驗 actor JWT；依 `skill_entitlements` 過濾 `tools/list`；`tools/call` 檢查購買（403）、每小時上限（429）、寫調用帳本 `tool_invocations`；一律依 actor 取資料（[skill-gating](../08-policy/experiments/skill-gating/README.md)） | 不信任工具參數裡的使用者 ID（[WP5 #10](../91-work-packages/WP5-user-state-isolation.md#回填)）；錯誤時不把內部 server 位址回給 agent（[takeover](../08-policy/experiments/skill-gating/takeover/README.md)） |
| **Browser 技能 server** | 用自己的 AWS 憑證開 Browser；操作完一定 `StopBrowserSession`；只回結構化結果；保證 A 的請求只拿 A 的 Browser profile | 不把 Live View URL 回給 HephAgora 或 agent |
| **Code Interpreter** | Sandbox 模式；套件預先打包成 wheel 送進沙箱（aarch64、Python 3.12），因為 PyPI 不通（[WP3](../91-work-packages/WP3-sandbox-egress.md#回填)） | 處理使用者資料時不用 Public 模式 |
| **Memory** | event 用 `actorId`、record 用 `namespace`／`namespacePath` 限制，每位使用者一個 principal；reflection 設在 actor 層級；控制寫入速率，避免 `LTM_RATE_EXCEEDED`（[WP5](../91-work-packages/WP5-user-state-isolation.md#回填)） | — |

**IAM 角色**

| 角色 | 權限 | 禁止 |
|---|---|---|
| Runtime execution role | 拉映像、寫 log、呼叫模型 | **任何 Browser 動作**；Code Interpreter 的 execution role 要零權限，因為沙箱裡讀得到它的憑證（[WP3](../91-work-packages/WP3-sandbox-egress.md#回填)） |
| Browser 技能 server 的角色 | 只能操作指定的 Browser ARN 與 profile | — |
| 使用者資料用的角色（供後端 AssumeRole） | 由 session policy 縮到單一使用者 | **trust 只寫後端**。實測 trust 寫了 execution role 時，VM 不需要 `sts:AssumeRole` 權限就能自己 assume、讀到別人的資料（[WP5 #4](../91-work-packages/WP5-user-state-isolation.md#回填)） |

## 三、串接流程

### 1. 一則訊息：從發出到收到回覆

```mermaid
sequenceDiagram
    participant App
    participant BE as 後端
    participant RT as Runtime agent
    participant HA as HephAgora
    App->>BE: 訊息（user token）
    BE->>BE: 驗身分、查購買、查或分配 session
    BE->>BE: 簽 60 秒 actor JWT
    BE->>RT: InvokeAgentRuntime（session ID、payload 帶 actor JWT）
    RT->>HA: POST /mcp tools/list（Bearer actor JWT）
    HA-->>RT: 只有已購買的工具
    RT->>HA: tools/call
    HA->>HA: 購買檢查（403）、每小時上限（429）、寫帳本
    HA-->>RT: 工具結果
    RT-->>BE: 回覆
    BE-->>App: 回覆
```

- **預喚醒**：使用者打開聊天室時，後端先對該 session 送一個空請求，不必等回應（[WP1](../91-work-packages/WP1-runtime-session.md#回填)）。
- **延遲**：MCP 一般工具 p50 約 21 ms；一次對話約 3–4.5 秒，大部分是模型（[skill-gating](../08-policy/experiments/skill-gating/README.md)）。
- **token 外洩的最大損害**：A 本人在 60 秒內能做的事（[WP5 #10](../91-work-packages/WP5-user-state-isolation.md#回填)）。
- **看不到的工具**一律回 `Unknown tool`。

### 2. 需要瀏覽器的技能

```mermaid
sequenceDiagram
    participant RT as Runtime agent
    participant HA as HephAgora
    participant BS as Browser 技能 server
    participant BR as AgentCore Browser（自訂，MANAGED 白名單）
    RT->>HA: tools/call
    HA->>BS: binding（mcp_server）
    BS->>BR: StartBrowserSession（server 自己的角色）
    BS->>BR: SigV4 簽 automation WebSocket，Playwright 操作
    BS->>BR: StopBrowserSession
    BS-->>HA: 結構化結果
    HA-->>RT: 工具結果
```

- 端到端 p50 約 5.8 秒，大多是開 session；每次呼叫約 $0.00016（[WP2](../91-work-packages/WP2-capability-boundary.md#回填)）。
- 實驗用固定流程的 Playwright，不是瀏覽子 agent；「子 agent 自己亂逛」未驗證。

### 3. 接手登入（server 主導，同步）

```mermaid
sequenceDiagram
    participant RT as Runtime agent
    participant HA as HephAgora
    participant BS as Browser 技能 server
    participant App
    RT->>HA: tools/call（需要登入的技能）
    HA->>BS: binding
    BS->>BS: 偵測到登入頁 → take_control → 一次性 viewer ticket
    BS->>App: 推播 viewer 連結（URL 只走這條路）
    App->>BS: 使用者在 viewer 登入，按「交還」
    BS->>BS: release_control → 重連 CDP → 讀結果
    BS-->>HA: {status, message}
    HA-->>RT: 工具結果
```

- 實測：偵測登入頁到推播 5.7 秒；開連結到 Live View 第一個畫面 2.4 秒；交還後 1.5–3.6 秒拿到結果（[takeover](../08-policy/experiments/skill-gating/takeover/README.md)）。
- **逾時**：工具從開始算最多 270 秒，比 binding 的 `timeout_ms`（300 秒）早結束；使用者沒交還時回 `user_did_not_complete_login`，server 照常 release、停 session。agent 端 MCP 的 HTTP 逾時也要拉長。
- 接手會切斷原本的 CDP 連線，交還後要重連；每個 CDP 指令設逾時，逾時就重連重試（[WP6](../91-work-packages/WP6-oss-alternatives.md#第-4-層雲端瀏覽器與接手)）。
- viewer 要自己加 HTML 輸入框轉送按鍵，Safari 點 DCV 畫面不會叫出鍵盤；中文逐字送時每個事件間隔 30 ms（[WP6](../91-work-packages/WP6-oss-alternatives.md#第-4-層雲端瀏覽器與接手)）。
- Browser 政策要加 `PasswordManagerEnabled: false`，否則雲端 Chrome 會想存使用者輸入的密碼。

### 4. VM 存取使用者資料

1. 後端 `AssumeRole`，帶 session policy（例如 S3 只允許 `users/<A>/*`），把臨時憑證放進呼叫 Runtime 的 payload。實測讀 A 成功、讀 B 被拒（[WP5 #3](../91-work-packages/WP5-user-state-isolation.md#回填)）。
2. 該角色的 trust 只寫後端（範本 [`trust-backend.json`](../02-memory/experiments/tenant-guard/aws/iam/trust-backend.json)）。
3. STS 有速率上限，憑證要快取到過期前。

## 四、網路與部署

- **VPC**：Runtime 放 private subnet，無 NAT、無 IGW；VPC 模式在東京只支援 az1、az2、az4。用 VPC peering 連 HephAgora 所在的 VPC，peering 沒有每小時費（[WP3](../91-work-packages/WP3-sandbox-egress.md#回填)）。VPC 模式不增加冷啟動（[WP1 #11](../91-work-packages/WP1-runtime-session.md#回填)）。
- **必要的 VPC endpoint**（[WP3](../91-work-packages/WP3-sandbox-egress.md#回填)）：
  - Interface：ECR `api`、ECR `dkr`、CloudWatch Logs、Bedrock runtime，單 AZ $40.88／月、雙 AZ $81.76／月。缺 ECR 時 Runtime 建得起來但呼叫回 502；缺 Logs 時照常運作但收不到 log。
  - S3 gateway endpoint（免費），政策用「全允許＋拒絕匿名請求」；照官方文件只放行 ECR 層 bucket 會拉不到映像。
- **閒置逾時**：預設 900 秒，可設 60–28,800 秒；費用跟 session 活著的秒數成正比，九成以上是記憶體。最後一次使用後主動 `StopRuntimeSession` 可省掉閒置的 21%（[WP1](../91-work-packages/WP1-runtime-session.md#回填)）。
- **成本分攤**：`USAGE_LOGS` 依 session 加總即得每位使用者的用量，與 metric 差 0%；同一個 log group 會混到其他 runtime，要依 `agent.name` 過濾（[WP5 #5](../91-work-packages/WP5-user-state-isolation.md#回填)）。
- **tag**：每個資源加 `project=hyfai` 與負責人。

## 五、上架新能力

前提：HephAgora 的一次性改動已上線（授權約 70 行、MCP 入口約 150 行、Browser server 約 200 行，開關 `HEPHAGORA_REQUIRE_ACTOR=1`、`HEPHAGORA_MCP_FACADE=1`）。之後**每新增一個技能，不改 HephAgora 程式碼**，只動資料與設定；agent 端也不用改，因為每次都從 `/mcp` 動態拿工具清單（[skill-gating #12](../08-policy/experiments/skill-gating/README.md)）。

### 一般技能

| # | 步驟 | 誰做 | 說明 |
|---|---|---|---|
| 1 | 寫技能後端（HTTP adapter 或 MCP server） | 技能開發者 | — |
| 2 | Service manifest：能力名稱、描述、`input_schema`、binding | 技能開發者 | `PUT /v1/registry/services/{id}` → 送審 → 審核 → 發布。描述要含使用者會講的詞（BM25 檢索）。MCP 工具名自動產生：`<service_id 點換底線>__<capability>` |
| 3 | 標成付費：`skill_products` 加一筆，含 `max_calls_per_hour` | 營運 | 目前沒有管理介面 |
| 4 | 購買紀錄寫進 `skill_entitlements` | 購買流程 | 資料來源待決，見「六」 |
| 5 | OAuth 類技能：manifest 的 `oauth_scopes`、client 憑證環境變數 | 技能開發者＋維運 | 未驗證 |
| 6 | 上架驗收（見下方） | 技能開發者 | — |

### 需要瀏覽器的技能，另外要做

| # | 步驟 | 說明 |
|---|---|---|
| 1 | MANAGED 政策檔放 S3：`URLBlocklist *`、`URLAllowlist <技能的網域>`、`PasswordManagerEnabled: false` | 每個技能（或每組白名單）一個 |
| 2 | 建自訂 Browser，指向該政策檔 | 政策只在 CreateBrowser 時讀取，**改白名單要重建 Browser** |
| 3 | Browser 技能 server 的角色加該 Browser ARN 的權限 | execution role 不加 |
| 4 | manifest 的 `mcp_server` binding 指向 Browser 技能 server | 會接手登入的技能，`timeout_ms` 要比工具總預算長（例如 300 秒 vs 270 秒） |
| 5 | 要保存登入狀態時，profile 依「使用者 × 網站」建立並加 tag，只給 server 的角色權限 | [WP5 #11](../91-work-packages/WP5-user-state-isolation.md#回填) |

### 上架驗收清單（建議）

研究只有實驗腳本（`check.sh`、`authz_check.sh`），以下依實驗檢查項整理成正式清單：

- [ ] 沒買的使用者 `tools/list` 看不到這個工具
- [ ] 沒買的使用者直接 `tools/call` 回 `Unknown tool` 或 403
- [ ] 有買的使用者呼叫成功，調用帳本記成該使用者
- [ ] 超過 `max_calls_per_hour` 回 429
- [ ] （瀏覽器技能）白名單外的網址回 `ERR_BLOCKED_BY_ADMINISTRATOR`
- [ ] （瀏覽器技能）agent 對話、HephAgora log、帳本裡搜不到 Live View URL
- [ ] （接手登入）使用者不交還時，270 秒內收掉並回明確狀態；接手時輸入的帳密沒有被保存

## 六、待決與上線前必做

| 項目 | 現況 | 下一步 |
|---|---|---|
| **購買資料來源** | 待決：從 `ai_family_backend` 的購買紀錄同步進 `skill_entitlements`，或 HephAgora 每次回查 | 由負責計費的人決定。同步：查詢快、資料兩份；回查：資料一份、每次 `tools/list`／`tools/call` 多一次呼叫 |
| **接手登入的真機驗證** | 只在 iOS 模擬器通過；真 iPhone、Android 沒測；iOS 鍵盤開著時點擊偶爾偏移；有 CAPTCHA、OTP、跨站 SSO 的網站沒測 | 真機驗證；有問題時的替代方案（電腦接手、App 原生登入表單、網站的委派授權）見 [WP2 #8](../91-work-packages/WP2-capability-boundary.md#回填) |
| **HephAgora 呼叫外部 MCP server 時不帶 actor** | Browser 技能 server 不知道要推播給誰 | HephAgora 把 actor 傳給 binding（約 5 行），或改由 HephAgora 自己推播 |
| **限流不是原子操作** | 先數再放行，大量並發時可能多放行 | 改成 `UPDATE … WHERE count < limit RETURNING` 或 Redis `INCR`（[WP6](../91-work-packages/WP6-oss-alternatives.md#第-3-層工具閘道與授權)） |
| **正式 agent 的成本重算** | 目前數字來自短 system prompt、stub 工具；每次呼叫多 1,000 個固定 token，每人每月 Haiku +$0.43、Sonnet +$1.17 | 上線後用 `USAGE_LOGS` 與 Bedrock 用量重算 |
| **閒置逾時的值** | 未定 | 依使用者回訪間隔決定；越短越省，但冷啟動機率越高 |
| **Code Interpreter Sandbox 放行同區域任意 S3** | 可能被拿來用匿名寫入外送資料，要第二個帳號實證 | 處理敏感資料時改用 VPC 模式加 S3 gateway endpoint 政策（[WP3](../91-work-packages/WP3-sandbox-egress.md#回填)） |
| **span 是否含對話內容** | 決定不驗 | 正式開 tracing 前先確認；在那之前假設含對話，設短保留期並限縮讀取權限 |
