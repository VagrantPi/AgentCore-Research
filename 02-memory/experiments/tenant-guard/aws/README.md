# WP5 實測：Memory 與憑證的使用者隔離（東京，2026-10-02）

[WP5](../../../../91-work-packages/WP5-user-state-isolation.md) 的腳本與 IAM 範本。結論與費用見 WP5 回填區，這裡記腳本怎麼跑、範本怎麼用。

```bash
cd 02-memory/experiments/tenant-guard/aws
uv run create_memory.py                     # 步驟 1：建 Memory（三種策略，reflection 在 actor 層級）
uv run write_events.py                      # 步驟 1：A、B 各 50 個 event
uv run check1_actor_iam.py namespace        # #1：policy 用 bedrock-agentcore:namespace
uv run check1_actor_iam.py namespacePath    # #1：policy 用 bedrock-agentcore:namespacePath
uv run check34_scoped_creds.py setup        # #3、#4：bucket、users/A|B/note.txt、/wp/wp5-user-data
uv run check34_scoped_creds.py scoped       # #3
uv run check34_scoped_creds.py self unsafe  # #4：trust 信任 execution role
uv run check34_scoped_creds.py self safe    # #4：trust 只信任後端
uv run check2_reflection.py                 # #2
uv run check7_delete.py                     # #7
uv run cost_day.py                          # #5、#8（1 天版）
uv run cost_report.py                       # #5、#8：session 結束、log 到齊後換算月費
uv run ec2_runner.py launch|status|fetch|cleanup   # #8 3 天版：在 EC2 t4g.nano 上跑 cost_day.py 3
uv run export_raw.py                        # 把 USAGE_LOGS、metric、每天的 session 存進 results/（log 只保留 14 天）
uv run cleanup.py iam-s3 | memory           # 清理
```

`state.json` 存執行期的 memoryId、bucket 等，不 commit。`results/` 是各檢核點的原始輸出。

## IAM 範本（`iam/`）

| 檔案 | 用途 |
|---|---|
| `trust-backend.json` | **建議的 trust policy**：只信任後端的 principal。Memory 的使用者 role、資料 role 都用它 |
| `mem-user-namespace.json` | 使用者 role 的權限：event 用 `actorId` key；record 用 `namespace` key（呼叫時傳 `namespace` 參數） |
| `mem-user-namespacePath.json` | 同上，record 改用 `namespacePath` key（呼叫時傳 `namespacePath` 參數） |
| `user-data.json` | 後端用來發臨時憑證的 role：可讀 `users/*` |
| `session-policy-user.json` | 後端 `AssumeRole` 時帶的 session policy：只限 `users/<USER>/*` |
| `trust-backend-and-exec-UNSAFE.json` | **反例，不要用**：trust 同時信任 Runtime 的 execution role，VM 就能自己 assume |

`MEMORY_ID`、`ACTOR_ID`、`BUCKET`、`USER` 是佔位字串，腳本套用時替換。

### 使用者 role 的建議寫法

兩種 key 都有效，但**各自只認同名的請求參數**：policy 只寫 `namespace` 時，用 `namespacePath` 參數呼叫會被拒（反之亦然），兩邊都是 fail-closed。要讓程式兩種參數都能用，就兩個 key 各寫一條 Allow。

```json
{"Effect": "Allow",
 "Action": ["bedrock-agentcore:RetrieveMemoryRecords", "bedrock-agentcore:ListMemoryRecords"],
 "Resource": "arn:aws:bedrock-agentcore:ap-northeast-1:ACCOUNT:memory/MEMORY_ID",
 "Condition": {"StringLike": {"bedrock-agentcore:namespace": "/strategy/*/actor/ACTOR_ID/*"}}},
{"Effect": "Allow",
 "Action": ["bedrock-agentcore:RetrieveMemoryRecords", "bedrock-agentcore:ListMemoryRecords"],
 "Resource": "arn:aws:bedrock-agentcore:ap-northeast-1:ACCOUNT:memory/MEMORY_ID",
 "Condition": {"StringLike": {"bedrock-agentcore:namespacePath": "/strategy/*/actor/ACTOR_ID/*"}}}
```

- 樣式結尾的 `/*` 不能省：`/actor/wp5-user-a*` 會比對到 `wp5-user-a2`。
- `ListActors`、`GetMemoryRecord`、`DeleteMemoryRecord`、`BatchDeleteMemoryRecords` 沒有 condition key，使用者 role 不給。

## 結果

### #1 IAM 依 actorId／namespace 限制（role A 的存取矩陣）

| 呼叫（role A） | policy 用 `namespace` key | policy 用 `namespacePath` key |
|---|---|---|
| A 的 `ListSessions`／`ListEvents`／`GetEvent`／`CreateEvent` | 允許 | 允許 |
| B 的 `ListSessions`／`ListEvents`／`GetEvent`／`CreateEvent` | 拒絕 | 拒絕 |
| A 的 record，參數 `namespace=` | 允許（17 筆） | **拒絕** |
| A 的 record，參數 `namespacePath=` | **拒絕** | 允許（17 筆） |
| B 的 record（兩種參數） | 拒絕 | 拒絕 |
| `namespace=/strategy/`、`namespace=/` | 拒絕 | 拒絕 |
| `ListActors` | 拒絕（policy 沒給） | 拒絕 |

原始輸出：`results/check1-namespace.json`、`results/check1-namespacePath.json`。

**順帶發現：`namespace` 參數是完全比對，不是前綴。** `ListMemoryRecords(namespace="/strategy/<id>/")` 回 0 筆，`namespacePath` 同一個值回 41 筆（A 17 + B 24）。API 文件寫 `namespace` 是「namespace prefix」，與實測不符。影響：`guard.forget_actor()` 原本用 `namespace` 查，會漏掉 episodic 存在 `.../session/{sessionId}/` 底下的 episode，已改用 `namespacePath` 並補分頁。

### #3 範圍縮小的臨時憑證（VM 內）

後端（KaisLinCli）`AssumeRole /wp/wp5-user-data` 帶 `session-policy-user.json`（`USER=A`），憑證以環境變數送進 `InvokeAgentRuntimeCommand`：

```
read users/A: OK 'user A 的私人資料'
read users/B: DENIED AccessDenied: ... assumed-role/wp5-user-data/wp5-user-a is not authorized ...
```

### #4 VM 自己 AssumeRole

VM 內的身分是 `assumed-role/wp0-runtime-exec/BedrockAgentCore-<uuid>`。**execution role 的 identity policy 完全沒有 `sts:AssumeRole`**（只有 ECR、logs），但同帳號下 trust policy 直接寫出它的 ARN 就足夠：

| `wp5-user-data` 的 trust | VM 內 `AssumeRole`（不帶 session policy） | 讀 `users/B` |
|---|---|---|
| `trust-backend-and-exec-UNSAFE.json` | OK | **OK**（繞過成功） |
| `trust-backend.json` | AccessDenied | — |

所以防線**完全在被 assume 的那個 role 的 trust policy**，不在 execution role：帳號裡任何一個 trust 寫了 execution role ARN 的 role，VM 裡的程式都能拿到它的權限。審查時要掃整個帳號的 trust policy，不能只看 execution role。

### VM 內執行程式的方法

`InvokeAgentRuntimeCommand` 的 `command` **不經過 shell**，會直接拆成 argv 執行（`echo x | base64 -d` 變成把 `-d` 傳給前一個程式）。要自己包 `sh -c '...'`。PUBLIC 網路下 VM 裡可以 `pip install`，不必另建含 boto3 的 image。

### #2 actor 層級的 reflection 不混到另一位使用者

`write_events.py` 的 50 個重複提問一直沒被判定成「完成的 episode」（超過 20 分鐘沒有 episode）。`write_episodes.py` 補寫 A、B 各 2 段**有明確結尾**的對話（帶暗號 `ALPHA-7731`、`BRAVO-4402`）後約 10 分鐘出現 episode 與 reflection。

`check2_reflection.py` 用 `namespacePath` 掃整個 strategy，以 `common.MARKERS` 的特徵詞（中英文都有，reflection 是英文、會抽象化）交叉比對：

| strategy | A 的 record | B 的 record | 混到對方特徵詞 |
|---|---|---|---|
| semantic | 17 | 24 | 0 |
| user preference | 9 | 10 | 0 |
| episodic episode | 3 | 2 | 0 |
| episodic reflection（actor 層級） | 2 | 3 | 0 |

沒有任何 record 落在無法歸屬到使用者的 namespace。原文見 `results/check2-records.json`。B 的 reflection 範例：

> "Pre-Authorization Confirmation Before Executing Bookings with Identifiers"… "Applies when users provide booking codes, reference numbers, or identifiers (e.g., **BRAVO-4402**)"…
> "Logical Itinerary Sequencing for Multi-Day Travel"… "(e.g., 14-day **Iceland** campervan trip)"

**reflection 不是匿名的**：會保留使用者給的識別碼與具體行程。設在 strategy 層級（`/strategy/{memoryStrategyId}/`）的話，這些內容會被所有使用者的檢索讀到。

### #7 刪除一位使用者的全部資料

`check7_delete.py` 用 `guard.forget_actor()`（已改用 `namespacePath` 與分頁）刪 A：

```
刪除前：sessions 8、records {episodic 5, pref 9, semantic 17}
forget_actor：events 64、records 31，耗時 11.2 秒
API 順序：ListSessions → (ListEvents → DeleteEvent×N) ×8 session → (ListMemoryRecords → BatchDeleteMemoryRecords) ×3 strategy
呼叫次數：ListSessions 1、ListEvents 8、DeleteEvent 64、ListMemoryRecords 3、BatchDeleteMemoryRecords 3
刪除後立即：records {episodic 0, pref 0, semantic 5}   ← 列表有延遲
5 分鐘後：records 全部 0
```

- **record 刪除有延遲**：剛刪完立刻列，semantic 還列出 5 筆；5 分鐘後歸零。刪除作業要「刪完等幾分鐘再掃一次」。
- **actorId、sessionId 刪不掉**：event 全刪後，`ListSessions` 仍列出 A 的 8 個 session（每個 0 個 event），`ListActors` 仍列出 `wp5-user-a`。沒有刪除 actor 或 session 的 API。**actorId 不能用 email 這類個資**，要用不透明的 ID。
- 64 個 event 刪除耗時約 11 秒（單執行緒、未碰到 `DeleteEvent` 每 actor + session 5 TPS 的限制）。

### #5、#8 每位使用者的成本

情境：一位使用者一天 100 個 event、20 次檢索、Runtime 在線 2 小時、Browser 10 分鐘（Browser 未實跑，用單價估算）。費用算法、單價與逐項表格見 [WP5 回填的「實際費用」](../../../../91-work-packages/WP5-user-state-isolation.md#實際費用)。

| 版本 | 怎麼跑 | Memory | Runtime | Browser | 合計（USD / 月） |
|---|---|---|---|---|---|
| 3 天版（2026-10-02 – 10-04） | EC2 `t4g.nano` 上 `cost_day.py 3` | 1.1587 | 0.7352 | 0.6365 | **2.5304** |
| 1 天版（2026-10-02） | 本機 `cost_day.py` | 1.4775 | 0.7237 | 0.6365 | **2.8377** |

- 兩版只差在 Memory 長期儲存：3 天版每天寫同樣 5 句話，後兩天被合併進既有 record（每天 9.7 筆 vs 38 筆）。
- `USAGE_LOGS` 依 session 加總與 metric 差 0%（#5）。
- **VM 開機的用量記在第一次呼叫之前**：每個 session 都有約 7 秒、約 1 vCPU 的紀錄，時間戳在第一次呼叫前 6–43 分鐘，之後空白。VM 從預先開好的池子分配，開機用量算在後來拿到它的 session 頭上。算費用的時間窗要往前多抓（`cost_report.py` 抓開始前 60 分鐘）。
- event 每筆間隔 1 秒寫入，3 天 0 個萃取失敗；連續寫入（1 天版）有 8 個 `LTM_RATE_EXCEEDED`。

### 原始資料（`results/`）

| 檔案 | 內容 |
|---|---|
| `usage-logs-wp5.jsonl.gz` | `USAGE_LOGS` 裡所有 `wp5-` 開頭 session 的原始紀錄（30,536 筆），含 #3、#4、#10、#11 與兩版成本的 session |
| `metrics-wp0_min.csv` | `wp0_min` 的 `CPUUsed-vCPUHours`、`MemoryUsed-GBHours`，5 分鐘一點 |
| `cost-days.json` | 兩版每天的 session ID、時間、3 天版的 record 數 |
| `cost-3day.txt`、`cost-day.txt` | `cost_report.py` 的輸出 |
| `check1-*.json`、`check2-records.json`、`check7-delete.txt` | #1、#2、#7 的原始輸出 |

沒有留下的：EC2 上的執行 log（S3 清理時一起刪了），以及成本用 Memory 的 record 內容（只留數量）。

用原始資料重算（在 `91-work-packages/scripts/` 下）：

```bash
python3 -c "import gzip, sys; from usage_cost import aggregate, write_csv; write_csv(aggregate(gzip.open('../../02-memory/experiments/tenant-guard/aws/results/usage-logs-wp5.jsonl.gz', 'rt').read().splitlines()), sys.stdout)"
```
