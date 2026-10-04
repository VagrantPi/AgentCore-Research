# WP5 使用者狀態與隔離、每使用者成本

> 回答：使用者的對話記憶、任務進度、檔案放在 VM 外面之後，A 讀不讀得到 B 的？每位使用者每月實際花多少？
>
> 估點：5。優先序：3（風險高、價值高）。前置：WP0、一個最小的 Runtime（WP1 步驟 1）。分群：A。

## 目標

用兩個使用者（A、B）實際驗證每一層的隔離，並估算「一位使用者一個月」的費用。

## 前提

| 前提 | 來源等級 | 出處 |
|---|---|---|
| Memory 用 `actorId` 隔離；IAM 能否依 actorId 限制，文件互相矛盾 | `[矛盾]` | [multi-tenant-isolation.md](../02-memory/multi-tenant-isolation.md) |
| Episodic 策略的 reflection 可能跨使用者彙整；設在 actor 層級可以避免 | `[官方已寫]` 風險 / `[推測]` 做法 | 同上、[02 Memory](../02-memory/README.md) |
| 刪除一位使用者的全部資料要先刪 event 再刪 record | `[推測]` | [multi-tenant-isolation.md](../02-memory/multi-tenant-isolation.md) |
| VM 內任何程式讀得到 execution role 憑證；用範圍縮小的 STS 臨時憑證可以限制 | `[官方已寫]` / `[推測]`（討論中的設計） | [01 Runtime：安全要點](../01-runtime/README.md#安全要點) |
| `USAGE_LOGS` 可以分攤到每個 session | `[官方已寫]`，WP0 會先驗 | [06 Observability](../06-observability/README.md) |
| `AWS_GENAI_CONTENT_EXTRACTION_OPT_OUT` 的名稱和實際行為看起來相反 | `[矛盾]` | 同上 |
| 定價：短期記憶每千個 event $0.25；長期儲存 built-in 每千筆每月 $0.75；檢索每千次 $0.50；`ListEvents` 等讀取操作定價頁沒列 | `[官方已寫]` / 無數字 | [read-write-cost.md](../02-memory/read-write-cost.md) |

## 步驟

1. **Memory：** 建一個 Memory，開 semantic + user preference + episodic 三種策略，episodic 的 reflection 設在 actor 層級。用 A、B 各寫 50 個 event（內容刻意有共通主題，例如都在聊「旅遊」）。
2. 用兩個 IAM role（只允許各自的 actorId；寫法參考研究庫 `multi-tenant-isolation.md` 列出的兩種 condition key，兩種都試）：用 A 的 role 讀 B 的 namespace，看是否被拒。
3. 等萃取完成（約 1–2 分鐘，episodic 更久），讀 reflection，看有沒有混到 B 的內容。
4. **範圍縮小憑證：** 後端用 `AssumeRole` 加 session policy（S3 只允許 `users/A/*`）產生臨時憑證，透過 payload 傳進 Runtime；在 VM 裡用這組憑證讀 `users/B/`，應被拒。再在 VM 裡用 execution role 自己 `AssumeRole`（不帶 session policy）讀 `users/B/`，預期**能讀到**，證明「不能讓 VM 自己 AssumeRole」。記錄要怎麼用 IAM trust policy 擋住後者。
5. **刪除：** 刪掉 A 的全部資料，記錄 API 順序、呼叫次數、耗時，再確認 reflection 裡沒有 A 的殘留。
6. **Observability：** 開 tracing，看 span 裡有沒有對話內容；設 `AWS_GENAI_CONTENT_EXTRACTION_OPT_OUT` 的兩種值各跑一次，記錄實際行為。
7. **使用者 token 在 VM 裡被濫用的範圍：** 設計上，使用者的短效 token 會進到 VM，讓 agent 呼叫自家 MCP server（見 [WP2](WP2-capability-boundary.md#設計變更背景)）。在 VM 裡用 A 的 token 呼叫自家 server，嘗試讀 B 的 Todo 資料、呼叫 A 沒買的技能，都應被拒；並確認 token 過期後無法再用。
8. **Browser profile 由自家 server 管理：** profile 依「使用者 × 網站」建立並加 tag；確認 Runtime 的 execution role 讀不到任何 profile，只有自家 server 的角色讀得到。
9. **成本情境：** 模擬一位使用者一天：100 個 Memory event、20 次檢索、Runtime 在線 2 小時（idle 30 分鐘）、Browser 10 分鐘。跑 3 天，用 WP0 的方法估算費用，換算成月費。Runtime 用量用 `USAGE_LOGS` 依使用者加總，和 `CPUUsed-vCPUHours` metric 比對。

## 檢核點

| # | 檢核點 | 來源等級 | 判定 |
|---|---|---|---|
| 1 | IAM 依 actorId 限制：哪一種 condition key 有效 | `[矛盾]` | 記錄有效的寫法 |
| 2 | Actor 層級的 reflection 沒有混到另一位使用者 | `[推測]` | 是 / 否；貼 reflection 內容 |
| 3 | 範圍縮小的臨時憑證在 VM 裡讀不到 B 的資料 | `[官方已寫]`（AWS 通用） | 是 / 否 |
| 4 | VM 自己 AssumeRole 能繞過；trust policy 能擋 | `[推測]` | 是 / 否；附 trust policy |
| 5 | `USAGE_LOGS` 能否依使用者分攤；與 metric 加總差多少 | `[官方已寫]` | 百分比 |
| 6 | Span 裡有沒有對話內容；opt-out 變數的實際行為 | `[矛盾]` | 記錄 |
| 7 | 刪除一位使用者資料的步驟與耗時；reflection 無殘留 | `[推測]` | 記錄 |
| 8 | 一位使用者一個月的實際費用（Memory、Runtime、Browser 分開列） | 成本 | USD |
| 9 | `ListEvents` / `GetMemoryRecord` 這類讀取操作是否計費（拿不到帳單，查官網定價頁；沒寫就填「無法驗證」） | 無數字 | 是 / 否 / 無法驗證 |
| 10 | VM 裡的 A token 讀不到 B 的資料、呼叫不了 A 沒買的技能；過期後失效 | `[推測]` | 三個是 / 否 |
| 11 | Runtime 的 execution role 讀不到 Browser profile，只有自家 server 讀得到 | `[推測]` | 是 / 否 |

## 判定對選型的影響

- 檢核點 1、2、3 任一否定 → 該層的隔離要改由自家後端做（例如 Memory 改成自管），成本和工時要加進方案 B。
- 檢核點 8 直接進決策矩陣，和 WP6、WP7 比較。
- 檢核點 6 決定正式環境 tracing 的設定與個資處理流程。

## 交付

- 兩個 IAM role 的 policy、trust policy 範本放在 `02-memory/experiments/tenant-guard/aws/`。
- 本檔案下方的回填區。

## 關聯

- 研究庫：[02 Memory](../02-memory/README.md)、[multi-tenant-isolation.md](../02-memory/multi-tenant-isolation.md)、[read-write-cost.md](../02-memory/read-write-cost.md)、[06 Observability](../06-observability/README.md)、[04 Identity：多租戶治理](../04-identity/multi-tenant-governance.md)
- 既有腳本：[`02-memory/experiments/tenant-guard/`](../02-memory/experiments/tenant-guard/)（`guard.py` 從 JWT 推導 actorId 與 namespace，假 client 驗證過，改成真 client 即可）、[`02-memory/experiments/cost-model/`](../02-memory/experiments/cost-model/)（月費試算，拿來和實際帳單對照）

## 回填

- 負責人：Kais
- 執行日期：2026-10-02
- 區域：ap-northeast-1
- 資源 tag：`wp=WP5`、`owner=kais`、`project=hyfai`
- 使用的 AWS 帳號：050571774557（IAM user `KaisLinCli`，沿用 [`iam/wp0-owner-policy.json`](iam/wp0-owner-policy.json)；本 WP 不需加權限）
- 腳本、IAM 範本與原始輸出：[`02-memory/experiments/tenant-guard/aws/`](../02-memory/experiments/tenant-guard/aws/)（逐項結果見該目錄的 [README](../02-memory/experiments/tenant-guard/aws/README.md#結果)）
- 使用者 A、B 用固定的 actorId `wp5-user-a`、`wp5-user-b`，沒有等 WP2 的 Cognito JWT

### 結論（三句內）

1. **每一層的使用者隔離都做得到，阻斷級沒有否定**：Memory 用每位使用者一個 IAM role（event 限 `actorId`、record 限 `namespace`／`namespacePath`）、reflection 設在 actor 層級、範圍縮小的臨時憑證、VM 裡的使用者 token（#10）、Browser profile（#11）都擋得住跨使用者存取。刪除時唯一刪不掉的是 actorId、sessionId，所以 actorId 要用不透明的 ID。
2. **VM 能自己 AssumeRole 是真的風險，但防線很單純**：execution role 本身不需要 `sts:AssumeRole` 權限，只要任何 role 的 trust policy 寫了它的 ARN，VM 裡的程式就能拿到那個 role；所有給使用者資料用的 role，trust 只能信任後端。
3. **每位使用者每月約 $2.53–2.84**（估算，不含模型 token）：Memory 約一半（event 寫入最貴），Runtime 幾乎全是閒置時的記憶體費用；`USAGE_LOGS` 依 session 加總能精確分攤到使用者，和 metric 差 0%。

### 檢核表

| # | 檢核點 | 來源等級 | 結果 | 證據 | 對選型的影響 |
|---|---|---|---|---|---|
| 1 | IAM 依 actorId 限制：哪一種 condition key 有效 | `[矛盾]` | **通過，兩種都有效**。event 用 `bedrock-agentcore:actorId`；record 的 `namespace` 與 `namespacePath` key **各自只認同名的請求參數**，用另一種參數呼叫一律被拒（fail-closed）。兩種都要用就各寫一條 Allow | [README #1](../02-memory/experiments/tenant-guard/aws/README.md#1-iam-依-actoridnamespace-限制role-a-的存取矩陣)、`results/check1-*.json`。只用 A 的 role 測（B 的 role 套同一份範本、只換 actorId，未對稱重跑） | IAM 可以當 Memory 的第 2 層防線，前提是每位使用者（或每個租戶）有自己的 principal。`[矛盾]` 的答案：[IAM 參考](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonbedrockagentcore.html)（列 `namespace`）與[開發指南](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/specify-long-term-memory-organization.html)（列 `namespacePath`）都對，`namespacePath` 是另一個請求參數的 key。另外 [`ListMemoryRecords` API 參考](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_ListMemoryRecords.html)說 `namespace` 是前綴，實測是完全比對，以實測為準 |
| 2 | Actor 層級的 reflection 沒有混到另一位使用者 | `[推測]` | **是** | A 2 筆、B 3 筆 reflection，episode 5 筆，semantic／preference 60 筆，用雙方特徵詞交叉比對，0 筆混到對方；reflection 原文見 README | reflection 一律設在 actor 層級。reflection **不是匿名的**（保留了 `BRAVO-4402`、「Iceland」），設在 strategy 層級會讓所有人讀到 |
| 3 | 範圍縮小的臨時憑證在 VM 裡讀不到 B 的資料 | `[官方已寫]` | **是** | 後端 `AssumeRole` + session policy（只 `users/A/*`），憑證送進 VM：讀 A 成功、讀 B `AccessDenied`。**和步驟 4 的偏差**：憑證不是經 `InvokeAgentRuntime` 的 payload 傳入，而是用 `InvokeAgentRuntimeCommand` 以環境變數帶進 VM（最小 agent 沒有 boto3，也不處理 payload）；VM 內拿到的是同一組憑證，結論不受影響 | 「後端發範圍縮小的憑證給 VM」可行。正式 agent 用 payload 傳入時，要避免憑證被寫進 log |
| 4 | VM 自己 AssumeRole 能繞過；trust policy 能擋 | `[推測]` | **是，能繞過；是，trust 能擋** | trust 寫了 execution role ARN 時，VM 內 `AssumeRole` 成功並讀到 B；改成只信任後端後 `AccessDenied`。execution role 的 identity policy **沒有** `sts:AssumeRole` 也能 assume（同帳號下 trust 寫出 ARN 就足夠） | 帳號裡任何 trust 寫了 execution role ARN 的 role 都等於交給 VM。上線前要掃整個帳號的 trust policy；範本 [`trust-backend.json`](../02-memory/experiments/tenant-guard/aws/iam/trust-backend.json) |
| 5 | `USAGE_LOGS` 能否依使用者分攤；與 metric 加總差多少 | `[官方已寫]` | **通過，差 0%** | 成本模擬的 session ID 以使用者開頭（`wp5-cost-wp5-user-cost-…`），`USAGE_LOGS` 依 session 加總即得該使用者的 Runtime 用量。同時段 `wp0_min` 5 個 session 的 log 加總：0.025731 vCPU-h、2.521397 GB-h，與 `CPUUsed-vCPUHours`、`MemoryUsed-GBHours` metric 完全相同（`results/cost-day.txt`） | session ID 要能對回使用者：以使用者 ID 開頭，或後端保留「session → 使用者」對照表。metric 只到 runtime 層級，分攤一定要用 log。同一個 log group 會混到其他 runtime（這次有 WP1 的 `wp1_cost_v1_img_pub`），要依 `agent.name` 過濾 |
| 6 | Span 裡有沒有對話內容；opt-out 變數的實際行為 | `[矛盾]` | **無法驗證（決定不驗）** | `KaisLinCli` 沒有 X-Ray 權限，帳號也沒開 CloudWatch Transaction Search（沒有 `aws/spans` log group）。開啟是全帳號設定，**Kais 決定（2026-10-02）不在公司帳號開啟**。補驗時所需的權限見 [`iam/wp5-xray-policy.json`](iam/wp5-xray-policy.json) | 不阻斷選型。在補驗之前，一律假設 span 含對話內容：`aws/spans` 與 agent log group 設短保留期、限縮讀取權限、加 CloudWatch 資料保護政策；agent 程式不自己把 prompt 寫進 log。**正式環境開 tracing 時補驗** |
| 7 | 刪除一位使用者資料的步驟與耗時；reflection 無殘留 | `[推測]` | **通過，但識別碼刪不掉** | `ListSessions` → 每個 session `ListEvents` → `DeleteEvent` ×64 → 每個 strategy `ListMemoryRecords(namespacePath)` → `BatchDeleteMemoryRecords`；共 79 次呼叫、11.2 秒。剛刪完 semantic 還列出 5 筆，5 分鐘後全部 0，reflection 無殘留。但 `ListActors`、`ListSessions` 仍列出 A 的 actorId 與 8 個空 session | 刪除作業要刪完等幾分鐘再掃。actorId 不能用 email 等個資。`namespace` 參數是**完全比對**（文件寫前綴），用它查會漏掉 session 層的 episode；`guard.forget_actor()` 已改用 `namespacePath` |
| 8 | 一位使用者一個月的實際費用（Memory、Runtime、Browser 分開列） | 成本 | **約 $2.53–2.84 / 人 / 月**（估算，3 天版與 1 天版）：Memory $1.16–1.48、Runtime $0.72–0.74、Browser $0.64（規格假設） | 見下方「實際費用」 | 進決策矩陣。Memory 占一半以上，其中 event 寫入最貴；Runtime 幾乎全是閒置的記憶體費用 |
| 9 | `ListEvents` / `GetMemoryRecord` 這類讀取操作是否計費 | 無數字 | **無法驗證** | [官網定價頁](https://aws.amazon.com/bedrock/agentcore/pricing/)（2026-10-02 查）只列「新 event」、「每月儲存的 record」、「record 檢索」三項，沒有提到 `ListEvents`、`GetEvent`、`ListMemoryRecords`、`GetMemoryRecord`；拿不到帳單無法實證 | 成本估算先當免費；上線後若能拿到帳單再對 |
| 10 | VM 裡的 A token 讀不到 B 的資料、呼叫不了 A 沒買的技能；過期後失效 | `[推測]` | **是、是、是**（2026-10-04） | Runtime `wp5_agent` 的 VM 裡拿 A 的 actor JWT（60 秒）直接打 EC2 上的 HephAgora：<br>① `/mcp`、`/v1/invoke` 都帶 `user_id=userB` 讀 todo → 只回 A 自己的 2 筆<br>② `/mcp` 呼叫 flight → `Unknown tool`；`/v1/invoke` → 403 `skill not purchased`<br>③ 等 66 秒後兩個入口都 401 `jwt expired`<br>原始輸出 [`results/wp5-10.json`](../08-policy/experiments/skill-gating/results/wp5-10.json)；細節見下方「#10、#11 補測」 | 使用者 token 可以交給 VM：外洩的最大損害＝A 本人在 60 秒內能做的事。前提是 server 一律依 actor 取資料、不信 caller 給的參數。token 在 60 秒內可重複使用（HephAgora 刻意不檢查 jti） |
| 11 | Runtime 的 execution role 讀不到 Browser profile，只有自家 server 讀得到 | `[推測]` | **是**（2026-10-04） | profile `userA__example_com`、`userB__example_com`（tag `user`、`site`）。<br>VM 內 execution role `/wp/wp5-agent-exec`：`ListBrowserProfiles`、`GetBrowserProfile` 全部 `AccessDeniedException`。<br>server 角色 `/wp/wp5-hephagora-ec2`（只多給這兩個 action）：列得到、也讀得到兩個 profile。<br>原始輸出 [`results/wp5-11-exec.json`](../08-policy/experiments/skill-gating/results/wp5-11-exec.json)、[`results/wp5-11-server.txt`](../08-policy/experiments/skill-gating/results/wp5-11-server.txt) | profile 權限只給 server 的角色，execution role 不給任何 Browser 動作。IAM 對 profile 只有 `aws:ResourceTag` 可用，「A 的請求只拿 A 的 profile」要由 server 自己保證 |

其他觀察：

- **短時間大量寫 event，長期記憶萃取會直接失敗**：連續寫 100 個 event（約 6 秒）後，`ListMemoryExtractionJobs` 出現 8 個 `FAILED`、原因 `LTM_RATE_EXCEEDED`，沒有自動重試。正式環境要控制寫入速率，或監控失敗的萃取工作並用 `StartMemoryExtractionJob` 重跑。
- **episodic 要「對話有結尾」才產出**：50 個重複提問超過 20 分鐘都沒有 episode；補寫有明確結尾（「謝謝，就這樣定案」）的對話後約 10 分鐘出現 episode 與 reflection。semantic、preference 則在寫入後幾分鐘內就有。
- **在 VM 裡執行程式**：用 `InvokeAgentRuntimeCommand`，不必另建 image。`command` **不經過 shell**，要自己包 `sh -c '...'`；PUBLIC 網路下 VM 裡可以 `pip install boto3`。這個 API 本身就能在任何 session 的 VM 裡下任意指令，正式環境的使用者與後端都不該有這個權限。

### 實際費用

情境：一位使用者一天 100 個 Memory event、20 次檢索、Runtime 在線 2 小時、Browser 10 分鐘。

**結論：約 $2.53–2.84 / 人 / 月**（估算，不含模型 token）。3 天版 $2.53、1 天版 $2.84，差別只在 Memory 長期儲存（見表下說明）；其餘各項兩版一致。

**原始資料**（都在 `02-memory/experiments/tenant-guard/aws/results/`，log 過期、資源刪除後仍可重算）：

| 檔案 | 內容 |
|---|---|
| `usage-logs-wp5.jsonl.gz` | `USAGE_LOGS` 裡所有 `wp5-` 開頭 session 的原始紀錄（30,536 筆，一筆 = 一個 session 的一秒），2026-10-04 用 `export_raw.py` 匯出 |
| `metrics-wp0_min.csv` | `wp0_min` 的 `CPUUsed-vCPUHours`、`MemoryUsed-GBHours`，5 分鐘一點（2026-10-02 06:00 – 10-04 13:00 UTC） |
| `cost-days.json` | 兩版每天的 session ID、開始與最後呼叫時間、3 天版的 record 數（`cost_report.py` 的輸入） |
| `cost-3day.txt`、`cost-day.txt` | `cost_report.py` 的輸出 |

**沒有留下的**：EC2 上的執行 log（`cost3d.log`，只記每次呼叫的時間，`USAGE_LOGS` 可以還原）在清理 S3 時一起刪掉，刪之前沒有存下來；兩個 Memory 的 record 內容（只留下數量）。

用原始資料重算（在 `91-work-packages/scripts/` 下執行，輸出和下表一致）：

```bash
python3 -c "import gzip, sys; from usage_cost import aggregate, write_csv; write_csv(aggregate(gzip.open('../../02-memory/experiments/tenant-guard/aws/results/usage-logs-wp5.jsonl.gz', 'rt').read().splitlines()), sys.stdout)"
```

#### 3 天版（2026-10-02 10:09 – 10-04 12:12 UTC）

在一台 EC2 `t4g.nano`（`i-06afed7f19deb7f4f`）上跑 `cost_day.py 3`（`ec2_runner.py launch`），Memory `wp5_cost3d-tc3SBsE1IR`、actor `wp5-user-cost3d`，每 24 小時跑一天。費用在最後一個 session 結束約 50 分鐘後算（2026-10-04 13:04 UTC），之後放寬時間窗重算（見下方「VM 開機的幾秒」）：3 個 session 各記到 7214／7224／7215 秒（預期約 7200 秒），log 加總與 metric 一致，判定已到齊。月費 = 3 天平均 × 30。

| 資源 | 用量（3 天合計） | 用量來源 | 單價（官網，2026-10-02 查） | 估算月費（USD） |
|---|---|---|---|---|
| Memory 短期（event） | 300 個 event | 自己計數 | $0.25 / 1,000 個新 event | 0.7500 |
| Memory 檢索 | 60 次 | 自己計數 | $0.50 / 1,000 次 | 0.3000 |
| Memory 長期儲存 | 3 天共 29 筆 record（semantic 7、preference 4、episodic 18），平均每天 9.7 筆 | `ListMemoryRecords` 實際列出 | $0.75 / 1,000 筆 / 月（built-in） | 0.1087 |
| Runtime（`wp0_min`，v1） | 21653 秒、0.062945 vCPU-h、7.183812 GB-h；每天 $0.023791／$0.024425／$0.025304 | `USAGE_LOGS`（與 metric 一致） | $0.0895 / vCPU-h、$0.00945 / GB-h | 0.7352 |
| Browser | 每天 10 分鐘（**未實跑**，假設 1 vCPU、4 GB） | 假設 | $0.0895 / vCPU-h、$0.00945 / GB-h | 0.6365 |
| **合計** | | | | **2.5304** |

- **長期儲存比 1 天版少很多**：每天寫的是同樣 5 句話，第 2、3 天的內容被合併進既有 record，沒有新增。真實使用者每天聊的不同，會更接近 1 天版的 38 筆／天。所以長期儲存取兩版的範圍（$0.11–0.43），這也是月費寫成範圍的原因。
- **Runtime 每天差異在 ±4% 內**；GB-h 每天略增（2.31 → 2.39 → 2.48），同一個 runtime 跑了 3 天，可能是 agent 程序記憶體慢慢變大，未深究。
- **VM 開機的幾秒記在 session 第一次呼叫之前**：每個 session（包括 #3、#4、#10、#11 的）都有約 7 秒、約 1 vCPU 的用量，時間戳在第一次呼叫前 6–43 分鐘，之後空白到第一次呼叫。看起來是 VM 從預先開好的池子分配，開機的用量算在後來拿到它的 session 頭上（呼應 WP0「呼叫前 VM 就開好了」）。每個 session 約 0.0011 vCPU-h（< $0.0001），不影響結論；但算費用的時間窗要往前多抓，`cost_report.py` 已從「開始前 5 分鐘」改成「開始前 60 分鐘」，第 1 天因此多了 6 秒、0.0011 vCPU-h。
- **萃取沒有失敗**：每個 event 間隔 1 秒寫入，3 天 0 個失敗的萃取工作（1 天版連續寫入時有 8 個 `LTM_RATE_EXCEEDED`）。
- 一開始在本機跑，因為筆電會移動、休眠會中斷，第 1 天跑到一半就停掉（actor `wp5-user-cost`，該 Runtime session 已手動 `StopRuntimeSession`，記到 330 秒，含開機的幾秒），不列入計算。
- 跑測試用的 EC2 是量測工具，不算進每人月費：`t4g.nano` 約 50 小時，估約 $0.57（$0.0054／h ≈ $0.27、8 GB gp3 ≈ $0.05、公有 IPv4 $0.005／h ≈ $0.25）。
- 原始輸出：`02-memory/experiments/tenant-guard/aws/results/cost-3day.txt`；算法：`cost_report.py`。

**和步驟 9 的偏差**（兩版相同）：Runtime 是 105 分鐘內每 5 分鐘呼叫一次，最後閒置 15 分鐘到逾時；規格的「idle 30 分鐘」沒有刻意做出來（呼叫之間本來就是閒置，`wp0_min` 不呼叫模型，CPU 幾乎全程閒置）。閒置時記憶體照算（WP0 #3），所以在線總時數相同時，閒置怎麼分布不影響費用。

#### 1 天版（2026-10-02 06:49 – 08:49 UTC，對照）

月費 = 1 天 × 30。費用在 session 結束約 45 分鐘後算：該 session 已記到 7216 秒（預期約 7200 秒），且 log 加總與 metric 一致，判定已到齊；1 小時後重查數字不變。2026-10-04 放寬時間窗重算，補上開機的 6 秒（見 3 天版「VM 開機的幾秒」），下表是重算後的數字。

| 資源 | 用量（1 天） | 用量來源 | 單價（官網，2026-10-02 查） | 估算月費（USD） |
|---|---|---|---|---|
| Memory 短期（event） | 100 個 event | 自己計數 | $0.25 / 1,000 個新 event | 0.7500 |
| Memory 檢索 | 20 次 | 自己計數 | $0.50 / 1,000 次 | 0.3000 |
| Memory 長期儲存 | 一天產生 38 筆 record（semantic 25、preference 5、episodic 8） | `ListMemoryRecords` 實際列出 | $0.75 / 1,000 筆 / 月（built-in） | 0.4275 |
| Runtime（`wp0_min`，v1） | 7222 秒、0.021319 vCPU-h、2.350839 GB-h → $0.024124 | `USAGE_LOGS`（與 metric 一致） | $0.0895 / vCPU-h、$0.00945 / GB-h | 0.7237 |
| Browser | 10 分鐘（**未實跑**，假設 1 vCPU、4 GB） | 假設 | $0.0895 / vCPU-h、$0.00945 / GB-h | 0.6365 |
| **合計** | | | | **2.8377** |

- 長期儲存的算法：record 一個月內線性累積，平均存量 = 月底的一半（38 × 30 ÷ 2 = 570 筆）。同主題的 record 會被合併，實際可能更少；但這次有 8 個萃取工作因 `LTM_RATE_EXCEEDED` 失敗，也可能低估。
- Runtime 用的是最小 agent（不呼叫模型、約 1 GB），**不含模型 token 費用**；真的 agent 記憶體更大，閒置費用會等比例增加。費用 92% 是記憶體（2.35 GB-h × $0.00945 = $0.0222），CPU 只占 8%。
- Browser 維持假設值（1 vCPU、4 GB）。[WP2 回填](WP2-capability-boundary.md)（AWS 部分的「實際費用」）已有實測：5 個 session 共 28 秒、0.005707 vCPU-h、0.029116 GB-h，平均約 0.73 vCPU、3.7 GB。
  - 套進「每天 10 分鐘」：(0.734 × 0.0895 + 3.74 × 0.00945) × 10/60 × 30 ≈ **$0.51／月**，比假設的 $0.64 低，每人月費會是約 $2.40–2.71。
  - 不直接採用：WP2 的 session 每個只有 5–6 秒（開頁讀內文就關），不一定代表 10 分鐘長 session 的資源用量。
  - WP4 的回填沒有費用數字。
- 原始輸出：`02-memory/experiments/tenant-guard/aws/results/cost-day.txt`（2026-10-02 當時的輸出，Runtime 是放寬時間窗前的 7216 秒；重算依據 `usage-logs-wp5.jsonl.gz`）。

### 否定項目的替代方案

| 被否定的檢核點 | 替代方案 | 多出的成本或限制 |
|---|---|---|
| （無阻斷級否定）#7 actorId、sessionId 刪不掉 | actorId 用後端產生的不透明 ID（例如 UUID），「ID → 使用者」的對照表放自家 DB，刪除使用者時刪對照表 | 要多維護一張對照表 |
| #4 VM 能自己 AssumeRole | 使用者資料用的 role，trust 只信任後端；後端發範圍縮小的臨時憑證給 VM | 每次請求多一次 `AssumeRole`（STS 有速率上限，需要快取到過期前） |

### 清理確認

- [x] IAM role `/wp/wp5-mem-user-a`、`/wp/wp5-mem-user-b`、`/wp/wp5-user-data` 已刪除
- [x] S3 bucket `wp5-isolation-59b47063` 已清空並刪除
- [x] Memory `wp5_mem-ah80eJAA2e` 已刪除（2026-10-02 09:36 UTC，狀態 `DELETING`）
- [x] Memory `wp5_cost3d-tc3SBsE1IR`（成本 3 天版）已刪除（2026-10-04 13:06 UTC，狀態 `DELETING`）
- [x] EC2 `i-06afed7f19deb7f4f` 跑完自行終止（2026-10-04 約 12:00 UTC）；S3 bucket `wp5-cost3d-6eaa8b19`、role 與 instance profile `/wp/wp5-cost-runner` 已刪除（2026-10-04 13:08 UTC，`/wp/` 只剩 WP0、WP3 保留的 role）
- [x] Runtime：沿用 WP0 的 `wp0_min-HsBwOc6VWU`（**保留**給 WP1）；`wp0-runtime-exec` 沒有改動
- [x] Browser、Gateway、Policy、VPC endpoint：未建立
- [ ] 隔天確認沒有仍在跑的 Runtime session — WP1 結束時一起確認

### 要更正研究庫的段落

| 檔案:行號 | 原本寫的 | 實測結果 |
|---|---|---|
| `02-memory/README.md:135` | `namespace`（完全相等）或 `namespacePath`（`StringLike`） | 兩個 key 都能用 `StringLike`（實測 `/strategy/*/actor/<id>/*`）；差別在各自只對應同名的請求參數 |
| `02-memory/multi-tenant-isolation.md:7` | 本機實作「用假的 client 測試」 | 已由 WP5 用真的 AWS client 實測，見 `experiments/tenant-guard/aws/` |
| `02-memory/multi-tenant-isolation.md:52` | 不要用 `namespacePath` 做前綴查詢 | `namespace` 參數是完全比對，要查子層（episodic 的 session 層 episode）只能用 `namespacePath`；結尾加 `/` 仍可避免比對到 `alice2` |
| `02-memory/multi-tenant-isolation.md:86` | `namespacePath`、`namespaceVariable` 只出現在開發指南，需實測 | `namespacePath` key 有效，但只對應 `namespacePath` 請求參數；`namespace` key 只對應 `namespace` 參數。`namespaceVariable` 未測 |
| `02-memory/multi-tenant-isolation.md:228` | 依 actor 的 namespace `ListMemoryRecords` | `namespace` 參數是完全比對，查不到子層的 episode；要用 `namespacePath`（`guard.forget_actor()` 已改） |
| `02-memory/multi-tenant-isolation.md:223`（被遺忘權） | 未提 actorId、sessionId 本身 | actorId、sessionId 刪不掉，會留在 `ListActors`／`ListSessions` |

### #10、#11 補測（2026-10-04）

- 負責人：Kais
- 執行日期：2026-10-04（09:10–09:27 UTC 建、測、刪；`USAGE_LOGS` 投遞在 10:30 UTC 算完費用後刪）
- 區域：ap-northeast-1
- 資源 tag：`wp=WP5`、`owner=kais`、`project=hyfai`（Browser profile 另加 `user`、`site`）
- 使用的 AWS 帳號：050571774557（IAM user `KaisLinCli`；EC2、VPC、ECR、S3、IAM 用既有的群組權限，沒有加權限）
- 自家 MCP server：WP2 的 HephAgora 分支 `wp2/skill-gating` 沒有推上 GitLab，由 Kais **依 [skill-gating README](../08-policy/experiments/skill-gating/README.md) 重建**（同名分支，[`de3df3d6`](https://gitlab.hephaistudio.dscloud.biz:49156/hephai/HephAgora/-/tree/wp2/skill-gating)）。和 WP2 版本的差異：
  - 沒有 Browser MCP server，這次用不到。
  - migration 合成一個 `036`。
  - todo 改成每人一份資料（`wp2_todos`），這樣 #10 才有「B 的資料」可以讀。
  - 先跑過 `scripts/wp2/check.sh`：本機 16 項（含每小時上限）、EC2 版 15 項（不跑每小時上限）全過。
- 架構：
  - EC2 `t4g.medium` 跑 HephAgora，開關為 `HEPHAGORA_REQUIRE_ACTOR=1`、`HEPHAGORA_MCP_FACADE=1`。
  - Runtime `wp5_agent`：PUBLIC 網路；execution role 只能拉映像、寫 log、呼叫 Haiku，沒有任何 Browser 權限。
  - agent 用 probe 直接打 HTTP，不經模型：`probe=abuse`（#10）、`probe=profile`（#11），見 [`agent/main.py`](../08-policy/experiments/skill-gating/agent/main.py)。
  - 使用者 A、B 是 actor JWT 的 `sub`（`userA`、`userB`），由開發機扮演後端簽發，沒有用 Cognito：HephAgora 認的就是 `sub`。

#### 結論（三句內）

1. **使用者 token 進 VM，能做的事不會超過使用者本人**：讀別人的資料、呼叫沒買的技能都被 server 擋下，過期後兩個入口都回 401。前提是 server 依 actor 取資料，不信任工具參數裡的使用者 ID。
2. **Browser profile 的存取可以只給 server**：execution role 不給權限就讀不到，server 角色加兩個 action 就讀得到。profile 不需要先建 Browser 就能建立。
3. 剩下的風險是 token 在 60 秒內可以重複使用，以及 profile 的 IAM 只能用 tag 區分。前者靠 60 秒效期控制；後者要由 server 自己檢查「這個請求的使用者 = profile 的 `user` tag」。

#### 費用

| 資源 | 用量 | 用量來源 | 單價（沿用 WP2 回填，官網 2026-10-02 查） | 估算金額（USD） |
|---|---|---|---|---|
| Runtime `wp5_agent`，3 個 session（含 1 次 token 沒換進去的失敗呼叫） | 0.005760 vCPU-h、0.640581 GB-h（共 998 秒，每個 session 含 5 分鐘閒置） | `USAGE_LOGS`（`usage_cost.py`，2026-10-04 10:28 UTC，最後 session 結束後 1 小時） | $0.0895／vCPU-h、$0.00945／GB-h | 0.0066 |
| EC2 `t4g.medium` | 0.1944 h（09:10:04–09:21:44 UTC，700 秒） | 啟動與終止時間 | $0.0432／h | 0.0084 |
| EBS gp3 30 GB | 0.1944 h | 同上 | $0.096／GB-月（÷730 h） | 0.0008 |
| 公有 IPv4 | 0.1944 h | 同上 | $0.005／h | 0.0010 |
| **合計** | | | | **≈ 0.0167** |

- 算式：Runtime 0.005760 × 0.0895 + 0.640581 × 0.00945 = 0.000516 + 0.006053；EC2 0.1944 × 0.0432；EBS 30 × 0.096 × 0.1944 ÷ 730；IPv4 0.1944 × 0.005。
- 不含 ECR、S3（存放約 20 分鐘，可忽略）與 CloudWatch Logs。這次沒有呼叫模型。

#### 否定項目的替代方案

無（#10、#11 都通過）。

#### 清理確認

- [x] Runtime `wp5_agent-db7UGyFQOS` 已刪除（09:27 UTC，session 都已閒置逾時）；log group `/aws/bedrock-agentcore/runtimes/wp5_agent-db7UGyFQOS-DEFAULT` 已刪除
- [x] Browser profile `userA__example_com-yxhNOKhfsC`、`userB__example_com-LX75w0kfGa` 已刪除；沒有開過 Browser session
- [x] EC2 `i-0aab33e1d4a2bcafb` 已終止（EBS 隨之刪除）；VPC `vpc-0e8771eab59450c50`、子網路、IGW、路由表、安全群組已刪除
- [x] ECR `wp5-hephagora`、`wp5-agent`（含映像），以及 S3 `wp5-kais-deploy-050571774557` 已刪除
- [x] IAM `/wp/wp5-hephagora-ec2`（含 instance profile）、`/wp/wp5-agent-exec` 已刪除
- [x] `USAGE_LOGS` delivery source `wp5_agent-usage-src` 與 delivery `3Crw3jaqmjkgsIMf` 已刪除（10:30 UTC，算完費用後）；destination `wp0-usage-dst` 是 WP0 的，保留
- [x] 用 `resourcegroupstaggingapi get-resources`（`wp=WP5`、`owner=kais`）複查：剩下的只有 3 天成本測試的 `wp5_cost3d`、`i-06afed7f19deb7f4f` 和它的 EBS、ENI、S3，不屬於本節
- [x] Gateway、Policy、Memory、VPC endpoint、NAT：未建立

#### 要更正研究庫的段落

| 檔案:行號 | 原本寫的 | 實測結果 |
|---|---|---|
| `91-work-packages/README.md:137` | 使用者 token（#10、#11）等 WP2 | #10、#11 都通過（2026-10-04，用重建的 HephAgora）。README 由 Kais 統一更新，本次不改 |
| `05-built-in-tools/browser-reliability-security.md:45` | 生命週期從 `CreateBrowserProfile` 開始，沒說要不要先建 Browser | `CreateBrowserProfile` 只需要 name（可加 tag），不依附任何 Browser；profile 和 Browser 是兩個獨立資源 |
| `08-policy/experiments/skill-gating/README.md:6` | HephAgora 分支「尚未推上 GitLab；推上後補連結」 | 原分支一直沒推，已由 Kais 重建同名分支；差異見本節開頭（README 已同步改） |

### 模型 token 費（補，2026-10-05）

上面 #8 的每人月費（約 $2.53–2.84）不含模型 token。補測方案 B agent 形狀（Strands＋經 HephAgora MCP 的工具）一天 10 輪的實際 token 數，細節與限制見 [`token-cost`](../90-integrations/experiments/token-cost/README.md)。

| 組合 | 每人每月（10 輪／天） | 每輪輸入／輸出 token |
|---|---|---|
| Haiku 4.5 `jp.` | **約 $0.9–1.4** | 約 2,000–2,600／200 |
| Sonnet 4.6 `global.`，不開 cache | **約 $2.9–3.4** | 約 2,500／190 |
| Sonnet 4.6，開 cache、輪與輪連續送 | 約 $2.1–2.4 | — |
| Sonnet 4.6，開 cache、輪與輪間隔超過 5 分鐘（最壞） | 約 $3.4–4.1（比不開還貴） | — |

- **含模型的每人每月：Haiku 約 $3.4–4.2、Sonnet 約 $5.4–6.3**（基礎設施 $2.53–2.84 ＋ 模型費）。
- Haiku 4.5 每個 cache 點至少 4,096 token，這次上下文不夠長，開了 cache 也沒作用；Sonnet 4.6 是 1,024。
- 這次的工具結果與 system prompt 都很短。每次呼叫多 1,000 個固定 token，每人每月 Haiku +$0.43、Sonnet +$1.17（不快取）。
- 單價：Price List 公開檔 `AmazonBedrockFoundationModels`／東京，publicationDate 2026-09-30。實驗模型費約 $0.54。

