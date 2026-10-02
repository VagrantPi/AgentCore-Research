# 記憶寫入加檢索延遲

WP6 第 5 層的實測（[WP6 回填](../../../91-work-packages/WP6-oss-alternatives.md#回填)）：同一則訊息寫進三種記憶後端，量三個數字。

- `write_ms`：寫入 API 從呼叫到回傳。
- `search_ms`：第一次搜尋從呼叫到回傳。
- `visible_ms`：從開始寫入，到搜尋第一次找回這筆資料。萃取是非同步的後端，只有這個數字能拿來比較。

每次試驗用新的 `user_id`。訊息是「我對花生過敏，平常住在台中。」加上助理回一句「好的，我記住了。」，查詢是「使用者有什麼食物過敏？」。

| 候選 | 寫入時做什麼 | 搜尋 |
|---|---|---|
| pgvector（本機 docker `pgvector/pgvector:pg17`） | Titan Text Embeddings V2（Bedrock 東京）算 embedding 後 INSERT，**不萃取** | 對查詢算 embedding，`WHERE user_id ORDER BY <=> LIMIT 5`，不建索引（全表掃描） |
| Mem0 OSS（mem0ai 2.2.1，vector store 用同一個 pgvector） | `add(infer=True)`：同步呼叫 LLM 萃取，再算 embedding 寫入 | `search(filters={"user_id": ...})` |
| AgentCore Memory（東京，built-in semantic strategy） | `CreateEvent`，萃取在背景非同步跑 | `RetrieveMemoryRecords`，每 2 秒輪詢一次 |

## 怎麼跑

```bash
docker run -d --name wp6-pgvector -e POSTGRES_PASSWORD=postgres -p 5433:5432 pgvector/pgvector:pg17
uv run bench.py pgvector --n 10
uv run bench.py mem0 --n 10
uv run bench.py agentcore --n 5     # 自己建暫時 memory，結束時刪掉
docker rm -f wp6-pgvector
```

`uv` 會依檔頭的 PEP 723 宣告裝相依套件。每次試驗會附加一列到 `results.csv`。

## 結果（2026-10-02，從台灣筆電呼叫東京）

| 候選 | 次數 | `write_ms` p50／p90 | `search_ms` p50／p90 | `visible_ms` p50／p90 | 存了什麼 |
|---|---|---|---|---|---|
| pgvector（不萃取） | 10 | 192／342 | 170／192 | **365／463** | 原句 |
| Mem0 OSS + Haiku 4.5 | 10 | 1,683／1,902 | 170／186 | **1,854／2,070** | `User has a peanut allergy` |
| AgentCore Memory | 5 | 243／1,934 | 337／442 | **65,922／68,051**（4 次命中，1 次 5 分鐘內沒萃取出來） | `用戶對花生過敏。` |

原始數據：[`results.csv`](results.csv)。

- **寫入到搜得到：pgvector 約 0.4 秒、Mem0 約 1.9 秒、AgentCore 約 66 秒。** AgentCore 的 `CreateEvent` 本身很快（p50 243 ms），但長期記憶要等背景萃取，4 次都在 64–68 秒之間，很穩定。smoke test 那次是 65 秒。
- AgentCore 第 0 次試驗（memory 剛變成 ACTIVE 後的第一個 event）輪詢 300 秒都沒有找到 record，後面 4 次都正常。原因沒有查；memory 已經刪掉，沒辦法確認之後有沒有萃取出來。第 0 次的 `write_ms` 1,934 ms 也是冷的第一次呼叫，所以 p90 偏高。
- 搜尋延遲三者差不多：pgvector、Mem0 約 170 ms（其中大部分是 Bedrock embedding 的往返），AgentCore 約 340 ms。
- 同一個 session 內的前文本來就靠短期記憶（AgentCore 是 `ListEvents`，自架是對話表），66 秒影響的是「剛說完的事實，下一個 session 馬上要用」的情境。

## 要注意的地方

- **網路位置：** 從台灣筆電呼叫，pgvector 的 DB 在本機（網路成本約 0），embedding 和 LLM 走到東京；AgentCore 整段都走到東京。所以這些是「台灣 → 東京」的數字，不是同一個 VPC 內的數字。每次執行都先量東京 STS 的往返時間（`rtt_ms` 欄，中位數 43–68 ms），部署到東京後大約可以每次 API 呼叫扣掉一個 RTT。
- **pgvector 不萃取，Mem0 和 AgentCore 有萃取，三者不是同一件事。** pgvector 存的是原句；Mem0 存的是 LLM 萃取出的事實（本次都是英文 `User has a peanut allergy`，「住在台中」沒有出現在第一筆結果）；AgentCore 存的是 `用戶對花生過敏。`。要用 pgvector 做長期記憶，萃取要自己寫，延遲會接近 Mem0。
- **Mem0 搭 Bedrock Nova 不能用：** mem0ai 2.2.1 的 Nova 路徑把 system prompt 當成一則 `role: system` 的 message 送進 Converse，`content` 又是字串，botocore 參數驗證直接失敗。改用 Claude Haiku 4.5（`jp.` Geo profile）才跑得動。
- **Mem0 的萃取 prompt 比預估大：** 腳本從 Converse 回應累計，10 次 `add` 共 10 次 LLM 呼叫、86,290 input token、800 output token，平均每次約 8.6K 輸入、80 輸出。這是使用者還沒有任何既有記憶的情況；既有記憶會放進 prompt，記憶越多越大。WP6 的萃取 LLM 月費假設每次 6.5K 輸入、0.5K 輸出：輸入要乘約 1.33 倍，輸出高估了約 6 倍。帳號層級的 CloudWatch 會混到同一帳號其他 session 的呼叫，所以不用它來算。
- Mem0 2.2.1 的 `search()` 不再接受 `user_id=`，要寫成 `filters={"user_id": ...}`。預設會送使用資料到 PostHog，腳本用 `MEM0_TELEMETRY=False` 關掉。
- 次數少（10、10、5 次），p90 只是參考。

## 費用

全部是用量 × 東京官網單價（包含 smoke test 與重跑）。

| 項目 | 用量 | 單價 | 費用 |
|---|---|---|---|
| Haiku 4.5（`jp.`），Mem0 萃取 | 22 次 `add` × 約 8.6K 輸入 ≈ 190K 輸入、約 1.8K 輸出 | $1.10／$5.50 每百萬 token | 0.209 + 0.010 ≈ **$0.22** |
| Titan Text Embeddings V2 | 約 3K token | $0.029 每百萬 token | 約 $0.0001 |
| AgentCore `RetrieveMemoryRecords` | 270 次（輪詢佔絕大部分） | $0.50 / 1,000 次 | **$0.135** |
| AgentCore `CreateEvent` | 6 次 | $0.25 / 1,000 | $0.0015 |
| AgentCore 長期儲存 | ≤ 6 筆，存在不到 15 分鐘 | $0.75 / 1,000 筆／月 | 約 $0 |
| **合計** | | | **約 $0.36** |

Haiku 的用量是用第二次重跑量到的「每次 `add` 8.6K」回推前 12 次。

## 清理確認（2026-10-02）

- `docker ps -a --filter name=wp6` 沒有輸出：容器已移除。
- `aws bedrock-agentcore-control list-memories --region ap-northeast-1`：兩個 `wp6_latency_*` memory 都已刪除（腳本在 `finally` 呼叫 `DeleteMemory`）。
