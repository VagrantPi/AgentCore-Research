# 方案 B 的模型 token 費

決策矩陣裡方案 B 的每人月費（[WP5](../../../91-work-packages/WP5-user-state-isolation.md#實際費用)：約 $2.53–2.84）不含模型 token，而 WP7 實測方案 A 的模型費佔 94%。這裡用方案 B 的 agent 形狀實測每輪的 token 數，換算**每人每天 10 輪**的月費。

## 做法

- agent：Strands＋經 HephAgora `/mcp` 的工具（同 [WP2](../../../08-policy/experiments/skill-gating/takeover/README.md) 的 userB：`todo`、`flight`（stub）、`login-web`），system prompt 一句話
- 一天份 10 輪，同一個聊天室連續聊，歷史一路帶下去（`day.py` 的 `TURNS`）：查待辦 → 查東京機票 → 哪班最便宜 → 東京天氣 → 查大阪機票 → 比較 → 再查待辦 → 寫請假訊息 → 改正式 → 總結
- 每輪記 Bedrock 回傳的 `inputTokens`、`outputTokens`、`cacheReadInputTokens`、`cacheWriteInputTokens`、模型呼叫次數（`turns.csv`）
- 4 個組合：Haiku 4.5（`jp.`）／Sonnet 4.6（`global.`）× cache 關／開（Strands `CacheConfig(strategy="auto")`），每組跑 2–3 次
- 單價：AWS Price List 公開檔 `AmazonBedrockFoundationModels`／`ap-northeast-1`，publicationDate 2026-09-30（每百萬 token）

| 模型 | 輸入 | 輸出 | cache 讀 | cache 寫（5 分鐘） |
|---|---|---|---|---|
| Haiku 4.5 `jp.`（Regional） | $1.10 | $5.50 | $0.11 | $1.375 |
| Sonnet 4.6 `global.` | $3.00 | $15.00 | $0.30 | $3.75 |

## 怎麼跑

```bash
# 本機 HephAgora（見 08-policy/experiments/skill-gating/takeover/README.md 的步驟 1）
bash run_all.sh 2      # 4 組合各跑 2 次
python3 cost.py        # 換算
```

## 結果（2026-10-05）

原始數據：[`turns.csv`](turns.csv)（90 輪）。

| 組合 | 次數 | **每人每月**（10 輪／天 × 30 天） | 每輪輸入 | 每輪輸出 | 每輪 cache 讀 | 每輪模型呼叫 |
|---|---|---|---|---|---|---|
| Haiku 4.5，不開 cache | 3 | **$1.19**（0.93–1.36） | 2,592 | 200 | 0 | 1.27 |
| Haiku 4.5，開 cache | 2 | **$0.94**（0.90–0.98） | 2,026 | 165 | **0** | 1.10 |
| Sonnet 4.6，不開 cache | 2 | **$3.15**（2.86–3.43） | 2,546 | 190 | 0 | 1.35 |
| Sonnet 4.6，開 cache | 2 | **$2.23**（2.08–2.38） | 190 | 204 | 1,464 | 1.35 |

- **每輪輸入約 2,000–2,600 token、輸出約 200 token**；有呼叫工具的輪次會叫 2 次模型，平均每輪 1.1–1.4 次。比我先前粗估的每輪 9,000 token 少很多，也遠低於 OpenClaw 的 2.6 萬（WP7，帶 35 個工具定義）。
- **Haiku 開 cache 沒有作用**：cache 讀寫都是 0。官方文件寫 Haiku 4.5 每個 cache 點至少要 4,096 token（Sonnet 4.6 是 1,024），這組對話每次呼叫的上下文大多不到 4,096，所以沒被快取（[Bedrock prompt caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html#prompt-caching-models)）。Haiku 兩組的差距只是對話長短的自然變異。
- **Sonnet 開 cache 便宜約 29%，但這是樂觀值**：這次 10 輪是連續送的（間隔幾秒），cache 幾乎每次都命中。真實使用者的 10 輪分散在一天裡，輪與輪之間常超過 5 分鐘，cache 會過期，每輪第一次呼叫變成「寫入」（一般輸入的 1.25 倍）。用這次的數據估最壞情況（沒有任何命中）：**$3.43–4.06／月，比不開 cache 還貴**。實際會介於兩者之間：只有同一輪裡的第二次呼叫（工具呼叫後）一定會命中。1 小時 TTL 的寫入價是 2 倍，要看使用頻率才知道值不值得。

**合進每人月費**（基礎設施取 WP5 的 $2.53–2.84）：

| | 模型費 | 含模型的每人每月 |
|---|---|---|
| Haiku 4.5 | 約 $0.9–1.4 | **約 $3.4–4.2** |
| Sonnet 4.6（不開 cache） | 約 $2.9–3.4 | **約 $5.4–6.3** |
| 對照：方案 A（WP7，OpenClaw＋Sonnet 4.6） | — | 約 $20.7，另加網路固定費 |

## 敏感度（用這次的每輪 1.3 次模型呼叫換算）

正式 agent 的 system prompt、技能說明、工具結果都會比這次長。**每次呼叫多 1,000 個固定 token**，每人每月增加：

| | 不快取 | 快取命中（讀） |
|---|---|---|
| Haiku 4.5 | +$0.43 | +$0.04 |
| Sonnet 4.6 | +$1.17 | +$0.12 |

例如固定上下文多 5,000 token（長一點的 system prompt 加 10 個技能描述）：Haiku 不快取 +$2.2、Sonnet 不快取 +$5.9。Haiku 的上下文超過 4,096 後 cache 就會開始作用，但要輪與輪的間隔在 TTL 內才會命中。

## 限制

- 對話是固定腳本，不是真實使用者；一天只有一個聊天室、10 輪連續聊
- 工具是 stub 與待辦清單，回傳很短；真實技能（網頁瀏覽結果、搜尋結果）每次可能多幾千 token
- system prompt 只有一句話
- 不含 Memory 萃取等背景模型呼叫（WP5 的 Memory 費用已含）
- 輸出長度跟模型風格有關（Sonnet 的回覆格式較多），正式 prompt 可以控制

## 費用與清理

- 9 次一天份（90 輪）模型費合計約 **$0.54**（`cost.py` 的 `usd_day` 加總）
- 本機 HephAgora 已 down；沒有 AWS 資源要清（只呼叫 Bedrock）
