# 延伸：技能授權改由自家系統負責，不用 AgentCore Policy

> 接續 [08-policy](README.md) 與 [WP2](../91-work-packages/WP2-capability-boundary.md)。原計畫用 Gateway + Policy 擋下「沒買的技能」；後來確定要接自家的工具市集 HephAgora，這篇回答：Policy 這段還要不要用 AWS 的？不用的話自己要做什麼？
>
> 資料查核日期：2026-10-04。依據是三個自家 repo 的 `main` 分支原始碼（`~/WS/ai_family_backend`、`~/WS/hephmind`、`~/WS/HephAgora`），**只讀程式碼，沒有實跑**。標示「推論」的部分是由程式碼推導、還沒驗證的。

## 結論先講

- **不用 AgentCore Policy。** 「誰買了什麼」記在 `ai_family_backend`，而且三個系統已經串好一條檢查鏈；加 Gateway + Policy 等於同一件事做兩次，還會讓使用者身分傳不到 HephAgora。
- **現在的檢查鏈已經擋得住模型：** backend 算白名單 → HephAgora 的 discover 依白名單過濾 → hephmind 只執行這一輪 discover 拿到的工具。最後一步是程式邏輯，模型被 prompt injection 也繞不過。
- **剩下一個缺口：** HephAgora 的 `/v1/invoke` 不檢查白名單，而且白名單放在請求內容裡、由呼叫端自己帶。只有在「跑 agent 的同一台 VM 裡有不受信任的程式」時，這個缺口才能被利用。
- **建議補一層便宜的保險（約半天）：** 白名單綁在 backend 建立的 HephAgora session 上，discover 與 invoke 都依 session 上的名單檢查。hephmind 不用改。

## 三個系統的角色

| 系統 | 角色 | 跟技能授權有關的部分 |
|---|---|---|
| `ai_family_backend` | 身分與購買資料的權威 | 算出這一輪可以用的技能（白名單）；簽發使用者身分憑證；依工具使用紀錄扣電 |
| `hephmind` | 對話 agent（呼叫 LLM、執行工具） | 把身分憑證與白名單原樣轉給 HephAgora；只執行 discover 拿到的工具 |
| `HephAgora` | 工具市集，對 agent 開 REST API | `/v1/discover` 依白名單過濾；`/v1/invoke` 呼叫下游 MCP server |

用詞提醒：研究庫裡一直說「自家 MCP server」。實際上 HephAgora 對 agent 開的是 REST（`/v1/discover`、`/v1/invoke`），在 `main` 分支上沒有對外的 MCP 端點；它本身是去呼叫下游 MCP server 的 client（`src/execution/mcp.ts`）。WP2 裡「過濾 `tools/list`」對應到 HephAgora 就是「過濾 `/v1/discover` 的結果」。

## 現在的檢查鏈

```
App
 │
 ▼
ai_family_backend
 │  1. listMountable() 算白名單：已解鎖 ∧ 在期間內 ∧ 適用這個角色 ∧ 角色沒停用 ∧ 電力 > 0
 │  2. /chat 請求內容帶 allowed_service_ids；header 帶 X-HephAgora-Actor（session 或 actor JWT）
 ▼
hephmind
 │  3. discover：白名單轉成 hints.service_ids
 │  5. 只執行這一輪 discover 拿到的工具名稱，其他略過
 ▼
HephAgora
    4. /v1/discover 依 hints.service_ids 過濾 → 模型只看得到買過的工具
    6. /v1/invoke 驗身分、查 OAuth 安裝、呼叫下游 MCP server（不檢查白名單）
```

| 步驟 | 位置 |
|---|---|
| 1 算白名單 | `ai_family_backend/backend/src/services/chat-capability.service.ts:43`（`listMountable`） |
| 2 帶白名單給 hephmind | `ai_family_backend/backend/src/services/chat-message.service.ts:344` |
| 2 身分憑證 | `ai_family_backend/backend/src/services/hephmind-chat.service.ts:21`（優先用 30 分鐘的 HephAgora session，換不到才用 60 秒的 actor JWT） |
| 3 轉成 `hints.service_ids` | `hephmind/internal/adapter/gateway/hephagora/client_discover.go:64` |
| 4 discover 過濾 | `HephAgora/src/discovery/routes.ts:40` |
| 5 只執行 discover 拿到的工具 | `hephmind/internal/adapter/http/handler/playground_chat_hephagora_hop.go:297`（`p.haRefs[tc.Name]`，查不到就略過） |
| 6 invoke 的檢查 | `HephAgora/src/execution/routes.ts:144`（`requireConsumerKey`、`optionalActor`）、`:180`（OAuth 安裝） |
| 扣電 | `ai_family_backend/backend/src/services/chat-capability.service.ts:62`（`chargeToolUsages`）；依據的 `tools_used` 由 hephmind 在實際 invoke 時記錄，不是模型自己回報 |

白名單的三種狀態在 hephmind 與 HephAgora 兩邊都有處理：`nil` 是不限縮，空陣列是一個都不准，非空陣列是只准這些。hephmind 特別避開 `omitempty`，以免空陣列被省略後變成不限縮。

## 為什麼不用 AgentCore Policy

1. **白名單每一輪都在變。** 名單取決於角色與當下的電力。Policy 只能從 JWT claim 讀名單，等於每一輪都要重簽 token 給 Gateway。陣列型 claim 能不能用也還沒驗證（WP2 G3）。
2. **身分傳不到 HephAgora。** HephAgora 依使用者身分查 OAuth 安裝與 session。Gateway 的 MCP server 與 OpenAPI 兩種 target 都不支援直接轉傳 token（[03 Gateway outbound 表](../03-gateway/README.md)），要多做 OBO 換發或 interceptor。
3. **Policy 看不到 discover 結果裡的每一筆。** HephAgora 掛在 Gateway 後面，Gateway 看到的只是 `discover`、`invoke` 幾支工具；真正的技能在參數 `ref.service_id` 裡，而 discover 回傳的語意搜尋結果無法逐筆過濾。
4. **限流擋不住。** Policy 的 `count` 依呼叫端自帶的 session ID 計數，換一個 ID 就重新算（見 [08 本文](README.md)）。

AgentCore Policy 只有在之後為了 AWS connector（例如 Web Search）另外加 Gateway 時，才用來管那些經過 Gateway 的工具。

## 剩下的缺口

| 缺口 | 什麼情況下會被利用 |
|---|---|
| `/v1/invoke` 不檢查白名單 | 有程式拿到身分憑證後直接打 invoke，跳過 hephmind 的第 5 步 |
| 白名單是請求內容的 `hints.service_ids`，由呼叫端提供 | 有程式改掉或拿掉這個欄位，discover 就回傳整個貨架 |
| invoke 用 `optionalActor`，免費服務可以不帶身分 | 同上，加上無法歸戶 |
| 限流依 IP（`HephAgora/src/http/rate-limit.ts:90`） | 同一個 IP 背後的所有使用者共用額度；無法依技能限次 |

這些缺口的前提都是「**有不受信任的程式拿到身分憑證**」。現在 hephmind 跑在自家伺服器上，這個前提不成立。搬進 AgentCore Runtime 之後（推論）：

- VM 裡只跑 hephmind 自己的程式、寫程式交給另一個沙箱 Code Interpreter 時，前提仍不成立，現在的檢查鏈就夠用。
- 若 agent 能在同一台 VM 裡執行程式，或用了被污染的套件，前提就成立。[WP5](../91-work-packages/WP5-user-state-isolation.md) #10（VM 裡的使用者 token 被濫用的影響範圍）測的就是這件事。

## 建議補強

讓上面的缺口即使 VM 被突破也成立不了。hephmind 不用改。

1. **backend 建立 session 時一起送白名單：** `POST /v1/sessions/create`（只有 backend 能呼叫，用 HMAC 保護，見 `HephAgora/src/auth/sessions.ts`）多收 `allowed_service_ids`，存在 session 上。actor JWT 路徑則加同名 claim。
2. **discover 改用 session 上的名單**，不再相信請求裡的 `hints.service_ids`。
3. **invoke 檢查 `service_id` 在不在名單內**，不在就回 403。來自 Runtime 的 consumer 一律要帶身分。
4. （可之後再做）限流改依「使用者＋技能」計數；扣電改依 HephAgora 的 invoke 帳本（已經依使用者記錄每次呼叫）。

### 待決定：session 的範圍

白名單會隨角色與每一輪的電力改變，但 session 一次有效 30 分鐘。

| 做法 | 優點 | 代價 |
|---|---|---|
| **每一輪換一次 session**（建議） | 名單永遠是最新的；做法最單純 | 每一輪多一次 backend → HephAgora 的呼叫 |
| session 綁「使用者＋角色」 | 呼叫次數少 | 購買、停用、電力歸零時要主動作廢或更新 session |

## 對 WP2 的影響

- **#0 已有答案：** HephAgora 有依使用者驗證身分（actor JWT 與 session），購買資料在 backend，白名單已經算好並傳到 discover。
- **#1 改成**「A、B 的 `/v1/discover` 結果依白名單不同」；**#2 改成**「A 直接打 `/v1/invoke` 呼叫 `flight` 被拒」。目前 #2 會**失敗**，要等上面的補強做完。
- **#3** 要確認 Runtime 裡的 hephmind 拿得到 backend 傳來的 `X-HephAgora-Actor` 與白名單。
- **選配 G1–G6** 可以標成不做。
- 研究庫裡「自家 MCP server」「`tools/list`」的用詞，之後改成 HephAgora 的 REST 端點。
