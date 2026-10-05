# WP6 不用 AgentCore 的開源方案

> 回答：如果不用 AgentCore，自架要用哪些元件拼出同樣的東西？每一層缺什麼？真實價格是多少？要多養幾個元件？
>
> 估點：A 半 5、B 半 5。優先序：6（風險低、價值中）。前置：無（可以和其他 WP 平行）。分群：A 負責第 1、5、6 層，B 負責第 2、3、4 層。

## 目標

給「自架」一個和方案 B 同尺度的對照。**不是做完整 PoC**，而是每一層選 2 個以上候選，填完「有 / 沒有 / 要自己做」，每層至少實測一個真實數字，價格一律用官網價或報價單。

## 前提

| 前提 | 來源等級 | 出處 |
|---|---|---|
| 自建每個元件的難度評估（低 / 中 / 高）是研究庫的工程判斷，沒有實際數據 | `[推測]` | [00 自建 vs 採用](../00-overview/build-vs-buy.md) |
| 自建比較便宜的情境是判斷，沒有數據 | `[推測]` | 同上 |
| OpenClaw 自架的建議規格是 2 vCPU / 4 GB / 40 GB；一個主程序服務一個人 | 外部資料 | 討論中引用的 OpenClaw 文件 |
| Harness 匯出的 Strands 程式碼可以部署到任何能跑 Python 3.12+ 的地方 | `[官方已寫]` | [00 Harness vs Runtime](../00-overview/harness-vs-runtime.md) |

## 要比較的層與候選

每層至少 2 個候選；同事可以增補，但增補的也要填滿同一張表。

| 層 | 對應的 AgentCore 元件 | 候選（起點） | 要回答的問題 |
|---|---|---|---|
| 1. 隔離執行環境（每人一台） | Runtime microVM | Firecracker 直接用（含 firecracker-containerd）、E2B（可自架）、Daytona、Kata Containers on EKS | 冷啟動秒數（實測一次）；每人每小時成本，**閒置時另列**；VM 回收與記憶體清除由誰負責；8 小時以上的長任務怎麼辦 |
| 2. Agent 框架與技能 | Harness / Strands、Skills | OpenClaw 自架（Lightsail 或 EC2 一人一台）、Strands、LangGraph、Claude Agent SDK | 技能格式（是否相容 SKILL.md）；工具白名單能否在框架**外**強制；一個程序能否同時服務一位使用者的多個聊天室 |
| 3. 工具閘道與授權 | Gateway + Policy（設計變更後改由自家 MCP server 負責，見 [WP2](WP2-capability-boundary.md#設計變更背景)） | 自家 MCP server 內嵌授權函式庫：OPA、Cedar（開源）、Casbin；或自架 MCP gateway 類專案 | 在自家 server 裡依使用者過濾 `tools/list`、檢查 `tools/call`、限流與計量，用哪個函式庫最省事；規則能不能做形式驗證 |
| 4. 雲端瀏覽器與接手 | Browser + Live View | Browserbase、Steel、自架 Chromium 加 noVNC 或 DCV（本機瀏覽器 ego (lite) 已評估、不採用，見 [README](README.md#評估過不採用)） | Live View 與接手是否內建；profile 保存；每小時價格（官網價）；手機瀏覽是否支援 |
| 5. 記憶 | Memory | 自管 Postgres + pgvector、Mem0、Zep | 跨使用者隔離靠什麼（schema、row-level security、各自的 collection）；萃取策略要不要自己寫 |
| 6. 可觀測與成本分攤 | Observability + USAGE_LOGS | OpenTelemetry + 任一後端、Langfuse | 每位使用者的成本能不能算出來 |

## 步驟

1. 每層先做 1 小時的文件調研，填「有 / 沒有 / 要自己做」。
2. 每層挑一個候選實測一個數字：第 1 層的冷啟動、第 2 層的「一個程序兩個聊天室同時發訊」、第 3 層的「依使用者過濾工具」要寫幾行、第 4 層的 Live View 開啟時間、第 5 層的一次寫入加檢索延遲。
3. 價格：到各候選的官網 Pricing 頁截圖，標日期；沒有公開價格的寫信要報價，沒拿到就填「無公開價格」。自架的用 AWS Pricing Calculator 算 EC2 加 EBS，**閒置時段另列**。
4. 列出自架相比 AgentCore **要自己維運的元件清單**（VM 排程、映像更新、瀏覽器更新、授權引擎、記憶萃取、監控），每項估點（費氏數列，定義見 [README](README.md#估點與排序原則)）。這一項允許標「估算」。
5. 把 [`00-overview/build-vs-buy.md`](../00-overview/build-vs-buy.md) 的「元件對照」表更正成實測後的版本。

## 檢核點

| # | 檢核點 | 來源等級 | 判定 |
|---|---|---|---|
| 1 | 六層都填完「有 / 沒有 / 要自己做」 | — | 表格完整 |
| 2 | 每層至少一個候選有實測數字 | — | 六個數字 |
| 3 | 每人每月成本有官網價或報價單，標日期；閒置時段另列 | 成本 | USD |
| 4 | 自架要自己維運的元件清單與估點 | `[推測]`（允許） | 清單 |
| 5 | 第 1 層：每人一台常駐 VM 時，100 位使用者的月費（含閒置） | 成本 | USD |
| 6 | 第 2 層：OpenClaw 自架時，能否在框架外強制工具白名單（不是靠 prompt） | `[推測]` | 是 / 否 |
| 7 | 第 4 層：有沒有候選能做到「使用者接手登入、交還後 agent 繼續」 | `[推測]` | 候選名稱 |
| 8 | 和 WP1、WP5 的數字並列後，方案 C 比方案 B 便宜的使用者規模門檻（如果有） | 成本 | 人數，或「無」 |

## 判定對選型的影響

- 檢核點 6、7 任一否定 → 方案 C 在能力邊界或接手登入有缺口，要加進決策矩陣的阻斷項。
- 檢核點 8 的門檻和產品預估的使用者數比較，決定方案 C 是否值得再投入。

## 交付

- 本檔案下方的回填區，包含六層的比較表、價格截圖路徑。
- 更正後的 [`00-overview/build-vs-buy.md`](../00-overview/build-vs-buy.md)。

## 關聯

- 研究庫：[00 自建 vs 採用](../00-overview/build-vs-buy.md)、[00 Harness vs Runtime](../00-overview/harness-vs-runtime.md)、[90 框架整合](../90-integrations/README.md)、[Nova Act 00 總覽](../nova-act/00-overview/README.md)（有和其他瀏覽器自動化方案的比較）

## 回填

### 執行資訊

| | A 半：第 1、5、6 層 | B 半：第 2、3、4 層 |
|---|---|---|
| 負責人 | Kais | Kais（2026-10-04 從 RomanChen 接手） |
| 執行日期 | 2026-10-02（文件與價格調研；實測未做） | 2026-10-04 |
| 區域 | ap-northeast-1（東京） | 本機實測；模型呼叫東京 Bedrock（`jp.anthropic.claude-haiku-4-5-20251001-v1:0`） |
| 資源 tag | `wp=WP6`、`owner=kais`、`project=hyfai`（本階段沒有建立 AWS 資源） | 本階段沒有建立 AWS 資源 |
| 使用的 AWS 帳號 | 無（沒有碰 AWS） | 050571774557（只呼叫 Bedrock） |
| 價格截圖 | [`evidence/WP6/`](evidence/WP6/)，檔名 `L{層}-<候選>-pricing-2026-10-02.png` | [`evidence/WP6/`](evidence/WP6/)，檔名 `L4-<候選>-pricing-2026-10-04.png` |
| 實測腳本 | 見第 5 層實測 | 第 2 層 [`90-integrations/experiments/chatroom-concurrency/`](../90-integrations/experiments/chatroom-concurrency/README.md)、第 3 層 [`08-policy/experiments/cedar-skill-gating/`](../08-policy/experiments/cedar-skill-gating/README.md) |

- AWS 價格出處：EC2、EBS、RDS、ElastiCache、S3 的價格頁是動態載入，截圖看不到東京價。東京單價取自 AWS 官方 Price List 公開檔 `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<服務>/current/ap-northeast-1/index.json`（EC2 版本 20260925174521）。截圖只當頁面證據，不是價格出處。
- 月時數用 730 h；「每天活躍 8 h」= 243.3 h/月，其餘 486.7 h 停機。
- A 半的費用（第 1、5、6 層）全部是官網單價加假設用量的估算，本階段沒有花費。
- B 半本階段花費：只有 Bedrock Haiku 4.5 呼叫，token 數沒量到（OpenClaw 的 log 不記用量，同時段 WP7 也在呼叫同一個模型）。本機 docker／程序不計費。

### 結論

1. 整體：方案 C 沒有比方案 B 便宜的人數門檻，見 [#8 門檻](#8-門檻方案-c-比方案-b-便宜的使用者規模)。
2. 第 1 層「每人一台強隔離 VM」不一定要自己寫排程器：可以買 E2B 託管，或用 Kata on EKS（中）。純 Firecracker 自寫才是高難度。100 人 24h 常駐時，託管約 $12.2k/月，自架約 $9.0k/月。
3. 第 2 層：OpenClaw 可以只靠設定檔在框架外鎖掉 exec、上網（實測），但預設全開、經 HTTP 進來的請求等同 owner、官方明說一個租戶一個 gateway；自架就是每人一台機器，100 人 24h 約 $3.5k／月，跟 AgentCore 保守估算（$3.4k）差不多、是實測值（$832）的 4 倍。Strands 本身不帶多餘工具，但每個聊天室要一個 Agent 實例。
4. 第 3 層：授權函式庫（Cedar、OPA、Casbin）省不了程式碼，手寫 70 行換成 Cedar 還有約 60 行（查 DB、403／429、限流、計量都還在）；多得到的是型別檢查與日後的形式驗證。MCP gateway 類專案要多養一個服務、購買資料要多一份，不值得。**維持 WP2 的手寫做法。**
5. 第 4 層：託管瀏覽器沒有一家在官方文件寫明支援「手機上操作 Live View」；反而 AgentCore 用的 DCV Web Client SDK 從 1.10.1（2025-10-22）起支援 iOS Safari／Chrome、Android Chrome 與觸控 `[官方已寫]`。Steel、Cloudflare Browser Run 有正式的接手、交還機制。價格上只有 Cloudflare 比 AgentCore Browser 便宜一點（每小時 $0.09 vs $0.101，100 人每月只差 $1.4），不實測；改在 iOS 模擬器 Safari 實測 AgentCore 的接手（[mobile-takeover](../05-built-in-tools/experiments/mobile-takeover/README.md)）：點擊、英數、中文都能送進遠端，交還後自動化接得上，但 viewer 要自己加輸入框轉送按鍵。
6. 第 5 層：Mem0、Zep 有現成的萃取與檢索，但跨使用者隔離大多靠應用程式帶 `user_id`。只有自管 pgvector 加 RLS 能在資料層強制。100 人規模的 AgentCore Memory 約 $45/月，比 Mem0（$249）、Zep（$150–300）便宜。
7. 第 6 層：LLM 成本可以算到每位使用者（Langfuse、Phoenix 有內建價格表）。VM、瀏覽器、記憶這些非 LLM 成本沒有任何候選現成提供，要自己維護 session→user 對照再合併。

### 檢核表

| # | 檢核點 | 來源等級 | 結果 | 證據 | 對選型的影響 |
|---|---|---|---|---|---|
| 1 | 六層都填完「有 / 沒有 / 要自己做」 | `[官方已寫]` / `[推測]` 逐格標 | 通過（A 半第 1、5、6 層；B 半第 2、3、4 層） | 各層的能力表 | — |
| 2 | 每層至少一個候選有實測數字 | — | 第 5 層完成：寫入到搜得到 pgvector 365 ms、Mem0 1.85 s（AgentCore 對照 65.9 s）；第 1、6 層依「範圍調整」跳過（託管比 AgentCore 貴）；第 2 層：兩個聊天室並行 Strands 468–592 ms、OpenClaw 793–1,048 ms，10／10 沒串；第 3 層：Cedar 25 行、83 µs；第 4 層：候選以價格判定不實測；改測方案 B 的 AgentCore Live View，開頁到第一個畫面 1.7–1.9 秒（第一次 5.6 秒） | 下方「實測：第 5 層」、「範圍調整」；[chatroom-concurrency](../90-integrations/experiments/chatroom-concurrency/README.md)、[cedar-skill-gating](../08-policy/experiments/cedar-skill-gating/README.md)、[mobile-takeover](../05-built-in-tools/experiments/mobile-takeover/README.md) | 第 5 層自架在即時性上勝出，但要自己寫萃取或接 Mem0；第 4 層方案 C 候選沒有實測數字，但價差小（每月 $1.4），不影響選型 |
| 3 | 每人每月成本有官網價，標日期；閒置另列 | 成本 | 通過（A、B 兩半皆為估算） | 各層的費用段、`evidence/WP6/`（含 `L4-*`） | — |
| 4 | 自架要自己維運的元件與估點 | `[推測]` | 通過 | 下方「維運元件與估點」 | — |
| 5 | 第 1 層：100 人每人一台常駐 VM 的月費 | 成本 | 24h：自架約 $9.0k、託管約 $12.2k；8h：自架約 $3.3k、託管約 $4.2k | 第 1 層的費用段 | 自架 8h 情境的前提是全體同時段使用、host 能整台停機 |
| 6 | OpenClaw 自架時，能否在框架外強制工具白名單 | `[推測]` | **可以，但不是預設**：`tools.deny` 關掉 exec、上網後，以使用者身分要求執行指令、讀網頁都被拒（實測）；預設設定兩者都會照做（實測） | [探測結果](../90-integrations/experiments/chatroom-concurrency/README.md#結果2026-10-04) | 不是阻斷項，但要另外補三件事，見第 2 層 |
| 7 | 有沒有候選能做到「使用者接手登入、交還後 agent 繼續」 | `[推測]` | Steel（steel-mcp-server handoff）、Cloudflare Browser Run（`Cloudflare.handoff`）有正式機制；**手機上能否操作，託管的沒有一家官方寫支援**（noVNC 支援手機，但交還要自己做） | 第 4 層表 | 方案 B 反而比較有把握，見第 4 層「#7：方案 B 的手機接手」 |
| 8 | 方案 C 比方案 B 便宜的使用者規模門檻 | 成本 | **無**（第 1 層：隨需價下，自架每 GB-h 的價格是 AgentCore 的 3.1 倍，跟人數無關） | 第 1 層判定、下方「#8 門檻」 | 方案 C 不用為了省錢再投入 |

### 第 1 層：隔離執行環境

| 能力 | Firecracker 直接用 | E2B 託管 | E2B 自架 | Daytona | Kata on EKS |
|---|---|---|---|---|---|
| 每人一台隔離 VM | 有，排程、網路、映像要自己做 | 有（每 sandbox 一台 Firecracker microVM） | 有，要自己部署 | **預設是 container，不是 VM**；VM sandbox 現行文件已不標 beta，但只能從既有 VM snapshot 建立 `[矛盾]` | 有，要 nested virtualization 或 bare metal |
| VM 回收與記憶體清除 | 要自己做；官方警告同一 snapshot 不能重複還原 | 官方沒寫；暫停時記憶體整份保存 | 要自己做 | 官方沒寫 | 隨 pod 刪除，細節官方沒寫 `[推測]` |
| 縮到 0 | 要自己做 | 有（按秒計費） | 要自己做 | 有：container 用 auto stop、archive；VM 用 stop／pause（預設 60 分鐘 auto-pause），VM 沒有 archive | 要自己設 autoscaler `[推測]` |
| 8 小時以上長任務 | 有，沒有上限 | Pro 單次 24h，可 pause/resume 接續 | 沒有平台上限 | 文件沒寫 | 有 `[推測]` |
| pause/resume | snapshot 有，管理層要自己做 | 有（暫停約 4 秒/GiB、還原約 1 秒） | 有（內建） | 只有 VM sandbox | 沒有，只能保存 PVC `[推測]` |
| 官方宣稱冷啟動 | ≤125 ms（只算 VMM 到 init、1 vCPU/128 MiB） | resume 約 1 秒；create 沒寫 | 同左 | 「sub 90ms」（行銷頁，應指 container） | 沒寫 |

- 來源：[Firecracker SPECIFICATION](https://github.com/firecracker-microvm/firecracker/blob/main/SPECIFICATION.md)、[E2B persistence](https://docs.e2b.dev/sandbox/persistence)、[e2b-dev/infra](https://github.com/e2b-dev/infra)、[Daytona VM sandboxes](https://www.daytona.io/docs/en/sandboxes/#vm-sandboxes)、[Daytona billing](https://www.daytona.io/docs/en/billing/)、[E2B 價格 FAQ](https://docs.e2b.dev/faq/calculate-sandbox-price)、[Kata install](https://github.com/kata-containers/kata-containers/blob/main/docs/install/README.md)、[EC2 nested virtualization](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/amazon-ec2-nested-virtualization.html) `[官方已寫]`
- AWS 上跑 Firecracker 或 Kata 要 nested virtualization：只支援 C7i/C8i、M7i/M8i、R7i/R8i 等 Intel 家族，**不支援 Graviton**，不另收費，AWS 建議延遲敏感的負載用 bare metal `[官方已寫]`。
- `[矛盾]` Daytona：VM sandbox 在 2026-10-02 的文件已不標 beta，列為正式 sandbox class（`daytona-vm-small/medium/large`），但官方也沒寫 GA。VM 啟動秒數官方沒寫。
- `[矛盾]` E2B infra README 有一段提到「AWS and GCP」，同頁又說 Terraform 只有 GCP，並寫「evaluation package, not a production deployment pattern」。以 Terraform 只有 GCP 為準：E2B 自架在 AWS 要自己移植。

**每人每小時成本**（基準 2 vCPU / 4 GB / 40 GB）

| 候選 | 運行中 | 閒置 |
|---|---|---|
| E2B 託管 | $0.1656/h（vCPU $0.1008 + RAM $0.0648），另加 Pro $150/月 | 暫停不收 vCPU／RAM 費 `[官方已寫]`（「Paused and killed sandboxes are not billed」）；暫停的 sandbox 無限期保留。儲存費官方沒寫（`[推測]` 不收，磁碟含在費率內）。Pro 寫「20+ GiB」，但沒有加購價、沒寫能否設 40 GB |
| Daytona | $0.16938/h（含 35 GiB 磁碟 $0.00378/h） | stopped／paused 只收磁碟 `[官方已寫]`；archived（只有 container）全部不收。**單一 sandbox 磁碟上限 10 GiB `[官方已寫]`**，40 GB 要寫信給 support（官方沒寫流程）；10 GiB 時閒置約 $0.00054/h |
| Firecracker 自架（nested `c8i.large`） | $0.11797/h + EBS $0.00526/h | host 停機只剩 EBS；host 常開時閒置仍全額 |
| Kata on EKS | 同上，再加 EKS 控制平面 $73/月 | 同上 |
| AgentCore Runtime（對照） | 上限 $0.2168/h（2 vCPU × $0.0895 + 4 GB × $0.00945，CPU 吃滿時）；只收實際用掉的 CPU | CPU 幾乎不收、記憶體照收（4 GB 時 $0.0378/h）；WP0 實測閒置成本約占 session 費用九成 |

- AgentCore 單價與閒置行為取自 [WP0 回填](WP0-cost-baseline.md#回填)（實測）。
- Code Interpreter 對照（[WP3 回填](WP3-sandbox-egress.md#回填)）：約 1 vCPU / 1 GB 吃滿時每小時約 $0.10；E2B 同規格約 $0.067/h（$0.0504 + $0.0162）。
- 冷啟動基準：WP0 從台灣呼叫，新 session 第一次約 0.85–0.95 秒，但 VM 在呼叫前已開好約 32 秒，不是真正的冷啟動；是否為預先開好的 VM 池由 WP1 確認。

**檢核點 5：第 1 層 100 人月費**

| 候選 | 情境 A：24h 常駐 | 情境 B：每天活躍 8h |
|---|---|---|
| E2B 託管 | 0.1656 × 730 × 100 + 150 = **$12,239**（不含磁碟超額） | 0.1656 × 243.3 × 100 + 150 = **$4,179**（暫停不收運算費，`[官方已寫]`） |
| Daytona | 0.16938 × 730 × 100 = **$12,365**（前提是 40 GB 獲准，預設上限 10 GiB） | 4,121 + 0.00378 × 486.7 × 100 = **$4,305**（停機只收磁碟，`[官方已寫]`） |
| Firecracker 自架 | 0.11797 × 730 × 100 + 3.84 × 100 = **$8,996** | 0.11797 × 243.3 × 100 + 384 = **$3,255** |
| Kata on EKS | 8,996 + 73 = **$9,069** | 3,255 + 73 = **$3,327** |
| AgentCore Runtime（對照，上限） | 0.2168 × 730 × 100 = **$15,826**（CPU 全時吃滿） | 0.2168 × 243.3 × 100 = **$5,275**（只算活躍時段且 CPU 吃滿；未計閒置記憶體） |

不含維運人力、host 行程開銷（約 10–15% `[推測]`）。AgentCore 那列是上限：它只收實際用掉的 CPU，真實月費要用 WP1、WP5 的實際用量重算，不能直接拿來判定檢核點 8。

#### 第 1 層判定（2026-10-02，用 [WP1 #10](WP1-runtime-session.md#10-成本情境) 的實測）

- **AgentCore 每個在線 session 每小時約 $0.0114**：WP1 讓 20 位使用者各在線約 2.42 小時（8,710 秒，含 30 分鐘閒置），總費用 $0.551548。算式 0.551548 ÷ 20 ÷ 2.42 h。這是最小 agent（不呼叫模型，約 1.1 GB、0.011 vCPU），金額 92% 是記憶體。
- 真的 agent 記憶體會更大，所以另外算一個保守值：4 GB 加平均 0.1 vCPU，4 × 0.00945 + 0.1 × 0.0895 = **$0.0467／h**。
- E2B 依實際配置收費，不管有沒有用到。就算縮到 1 vCPU／1 GB，也要 0.0504 + 0.0162 = **$0.0666／h**，另加 Pro $150／月。

| 100 人月費 | 24h 在線 | 每天 8h |
|---|---|---|
| AgentCore 實測（$0.0114／h） | **$832** | **$277** |
| AgentCore 保守（$0.0467／h） | $3,413 | $1,137 |
| E2B（2 vCPU／4 GB，原估算） | $12,239 | $4,179 |
| E2B（縮到 1 vCPU／1 GB） | $5,012 | $1,770 |
| Firecracker 自架（每人一台 `c8i.large`） | $8,996 | $3,255 |

- 判定：E2B、Daytona 在任何一種算法下都比 AgentCore 貴，第 1 層不實測。
- 自架也沒有比較便宜的人數門檻：nested virtualization 要用 Intel 機型，`c8i.large` 每 GB-h 是 0.11797 ÷ 4 = $0.0295，AgentCore 是 $0.00945，貴 3.1 倍；多人共用一台 host 也只是把每人的 GB 攤平，不會改變這個比例。Savings Plans、Spot 沒算：要折到原價的 32% 以下（0.00945 ÷ 0.0295）才會比 AgentCore 便宜。3 年期 Savings Plans 或 Spot 有可能做到，但那時還要再加 host 開銷與維運人力 `[推測]`。
- 但書：WP1 的情境是每 5 分鐘 ping 一次、不呼叫模型。真實 agent 的記憶體與 CPU 用量要等正式 agent 上 Runtime 後，再用 `USAGE_LOGS` 重算。

### 第 2 層：Agent 框架與技能

| 能力 | OpenClaw 自架 | Strands | LangGraph | Claude Agent SDK |
|---|---|---|---|---|
| SKILL.md | 有，遵循 AgentSkills 規格；每個 agent 可設 skills 白名單 `[官方已寫]` | 有，`AgentSkills` plugin `[官方已寫]` | 核心沒有；建在其上的 Deep Agents 有 `[官方已寫]` | 有，只能從檔案系統載入 `[官方已寫]` |
| 框架外強制工具白名單 | **可以，但要自己鎖**：`tools.deny` 整組關掉後，exec、上網被擋（實測）；預設全開（實測）。細節見下方 #6 | 有：只有程式碼傳進去的工具 `[官方已寫]` | 有：工具在程式碼裡綁定 `[推測]` | 要自己做：Bash、WebFetch 等預設就在，要用 `disallowed_tools` 或 PreToolUse hook 擋 `[官方已寫]` |
| 一個程序服務同一人的多個聊天室 | 有：每個 session 一條 lane，不同 session 並行，同一 session 排隊（實測） | 要每個聊天室一個 `Agent`；同一個實例並行會丟 `ConcurrencyException`（實測） | 有：每個聊天室一個 thread_id ＋ checkpointer `[推測]` | 有：一個 session 一個子程序 `[官方已寫]` |
| 一個程序服務多位使用者 | **沒有**，官方要求一個租戶一個 gateway `[官方已寫]` | 要自己做 `[官方已寫]` | 有：custom auth ＋ owner filter（LangSmith 部署）`[官方已寫]` | 有條件可以：每個租戶獨立 cwd 與設定目錄 `[官方已寫]` |
| 每個請求帶不同使用者 token 給 MCP server | 沒有：`mcp.servers` 的 headers 是靜態的 `[官方已寫]` | 要每個請求重建 MCP client `[推測]`；WP2 的 Runtime agent 就是這樣做 | 有：graph factory 裡依使用者建 client `[官方已寫]` | 有：每次 `query()` 可給 headers `[官方已寫]` |
| 授權／最近 release | MIT；2026.9.8（2026-10-03），一天出好幾版 | Apache-2.0；1.57.2（2026-10-01） | MIT；1.2.12（2026-09-21） | repo 標 MIT，README 寫受 Anthropic 商業條款規範 `[矛盾]`；0.2.163（2026-09-30） |

- 來源：[OpenClaw tool policy](https://docs.openclaw.ai/gateway/config-tools/tool-policy)、[OpenClaw queue](https://docs.openclaw.ai/concepts/queue)、[OpenClaw multi-tenant](https://docs.openclaw.ai/gateway/multi-tenant-hosting)、[OpenClaw MCP](https://docs.openclaw.ai/tools/mcp)、[OpenClaw OpenAI HTTP API](https://docs.openclaw.ai/gateway/openai-http-api)、[Strands skills](https://strandsagents.com/docs/user-guide/harness/configure/skills/)、[Strands exceptions](https://strandsagents.com/docs/api/python/strands.types.exceptions/)、[LangChain MCP auth](https://docs.langchain.com/oss/python/langchain/mcp/auth)、[LangSmith resource auth](https://docs.langchain.com/langsmith/resource-auth)、[Claude Agent SDK permissions](https://code.claude.com/docs/en/agent-sdk/permissions)、[Claude Agent SDK hosting](https://code.claude.com/docs/en/agent-sdk/hosting) `[官方已寫]`
- OpenClaw 的 Bedrock provider 不是內建的，要另外裝 `@openclaw/amazon-bedrock-provider`；沒裝時回 500：`No API provider registered for api: bedrock-converse-stream`。
- `[矛盾]` OpenClaw main lane 的預設並行上限：官方 queue 頁寫 `max(8, CPU×4)`，舊版第三方鏡像寫 4。

**實測：一個程序兩個聊天室同時發訊**（[腳本與原始數據](../90-integrations/experiments/chatroom-concurrency/README.md)）

| 框架 | 次數 | 重疊執行 | 答對、沒串到另一個聊天室 | 單次延遲 |
|---|---|---|---|---|
| Strands 1.57.2（每聊天室一個 Agent） | 5 | 5／5 | 10／10 | 468–592 ms |
| OpenClaw 2026.9.8（每聊天室一個 session key） | 5 | 5／5 | 10／10 | 793–1,048 ms |

- 同一個 Strands `Agent` 實例同時收兩個請求：第二個直接丟 `ConcurrencyException`。
- 同一個 OpenClaw session 同時兩個請求：session 已存在時排隊（約 0.9 秒、1.6–1.8 秒完成）；新 session 的第一則訊息就並行時，一個回 500 `SessionWorkStartChangedError ... Retry.`，呼叫端要重試。

**#6 鎖緊後還要補的三件事**

1. **經 HTTP 進來的請求等同 owner**（[官方已寫]）：後端轉送使用者原文時，`/` 指令會以 owner 身分處理。`commands.config`、`commands.bash`、`commands.mcp`、`commands.debug` 預設就關；`/elevated` 要用 `tools.elevated.enabled: false` 關，最好再加 `commands.text: false`。
2. **內建 plugin 的工具不在 deny 的群組裡**：鎖緊後模型還看得到 `file_fetch`、`file_write`、`dir_list` 等（`group:plugins`），這次因為沒有配對節點用不了。嚴格白名單要連 `group:plugins` 一起 deny 再只放行 MCP，寫法官方沒寫、未測。OpenClaw 一天出好幾版、工具群組一直加，deny 清單要隨版本重審。
3. **網路要另外擋**：OpenClaw 本身不限制對外連線 `[官方已寫]`，要靠 Security Group 或 egress proxy 只放行 Bedrock 與自家 MCP server（跟方案 B 的 [WP3](WP3-sandbox-egress.md) 同一套做法）。授權判定仍然在自家 MCP server。

- 探測的教訓：第一版用 `echo WP6_EXEC_$((6*7))` 當標記，鎖緊後模型沒有呼叫 exec 卻回出 `WP6_EXEC_42`（自己算的），從 session 資料庫確認後改用隨機 nonce 重跑。拿模型回覆判定「有沒有執行」時，標記一定要是模型猜不到的值。

**第 2 層：OpenClaw 自架，每人一台**（官方建議 2 vCPU／4 GB／40 GB；東京 `t4g.medium` $0.0432／h、gp3 $0.096／GB-月，與 [WP2](WP2-capability-boundary.md#實際費用-1) 同一組單價）

| | 24h 常駐 | 每天 8h（其餘停機） |
|---|---|---|
| 每人 | 0.0432 × 730 + 40 × 0.096 = **$35.38** | 0.0432 × 243.3 + 3.84 = **$14.35** |
| 100 人 | **$3,538** | **$1,435** |
| AgentCore Runtime 對照（100 人，A 半「第 1 層判定」） | 實測 $832、保守 $3,409 | 實測 $277、保守 $1,136 |

- 不含公網 IPv4（每台 $3.65／月）、模型 token、維運人力。每人一台 EC2 本身就是 VM 隔離，所以這個數字同時涵蓋第 1、2 層。
- 停機再開機要等 EC2 開機加 OpenClaw 啟動，首句延遲會遠大於 AgentCore 的預喚醒（WP1 實測 p50 170–196 ms），沒實測。
- Strands、LangGraph、Claude Agent SDK 是函式庫，費用落在第 1 層的執行環境上，不另計。

### 第 3 層：工具閘道與授權

| 能力 | OPA（opa-wasm） | Cedar（cedar-wasm） | Casbin（node-casbin） | agentgateway | IBM ContextForge |
|---|---|---|---|---|---|
| 依使用者過濾工具清單 | 要自己做：逐工具判斷；wasm 版沒寫支援 partial eval `[推測]` | 逐工具 `isAuthorized`（實測）；`isAuthorizedPartial` 有匯出但上游標為實驗功能 `[推測]` | 有：`batchEnforce` 一次判多筆 `[官方已寫]` | 有：CEL 規則自動濾掉 `tools/list`，但只看得到 JWT claims，已購買清單要塞進 JWT `[官方已寫]` | 有：RBAC、team、virtual server；購買紀錄要同步進它的 DB `[官方已寫]` |
| 限流與計量 | 要自己做 | 要自己做 | 要自己做 | 限流有（依 JWT claim、可依工具分）；計量要自己做 `[官方已寫]` | 有 RateLimiter 外掛，多實例要 Redis `[官方已寫]` |
| 形式驗證 | 沒有 SMT；有 `opa test`、`opa check --strict` `[官方已寫]` | 型別檢查有（實測）；SMT 用 Rust 的 `cedar-policy-symcc`（要 cvc5），npm 沒有 `[官方已寫]` | 沒有 | 沒有 | 沒有 |
| Node 整合 | 1.10.0，最後 release 2024-11，README 自稱 Work in Progress `[官方已寫]` | 4.13.0（2026-09-15），有 TS 型別 `[官方已寫]` | 5.51.1（2026-06）`[官方已寫]` | 獨立的 Rust 執行檔 | Python 服務 |
| 每次判斷延遲 | Go 版 RBAC 範例約 45 µs `[官方已寫]` | 本機 wasm：preparse 後約 83 µs、不 preparse 約 300 µs（實測）；論文 4–5 µs 是原生 Rust | Go 版約 0.16 ms；Node 版官方沒寫 | 官方沒寫 | 官方沒寫 |
| 要多養的元件 | 無 | 無 | 無 | gateway 本身 `[推測]` | gateway ＋ SQLite／Postgres，Redis 選配 `[官方已寫]` |
| 授權條款 | Apache-2.0 | Apache-2.0 | Apache-2.0 | Apache-2.0 | Apache-2.0 |

- 來源：[cedar-wasm](https://github.com/cedar-policy/cedar/tree/main/cedar-wasm)、[Cedar analysis](https://aws.amazon.com/blogs/opensource/introducing-cedar-analysis-open-source-tools-for-verifying-authorization-policies)、[Cedar 論文](https://arxiv.org/abs/2403.04651)、[npm-opa-wasm](https://github.com/open-policy-agent/npm-opa-wasm)、[OPA policy performance](https://www.openpolicyagent.org/docs/policy-performance)、[Casbin benchmark](https://casbin.apache.org/docs/benchmark/)、[agentgateway tool access](https://agentgateway.dev/docs/kubernetes/latest/mcp/tool-access/)、[ContextForge](https://ibm.github.io/mcp-context-forge/latest/) `[官方已寫]`。版本與 release 日期是 2026-10-04 查 npm registry、GitHub API。
- Docker MCP Gateway、MCPJungle 沒查到依 JWT 使用者過濾工具的功能，不列。

**實測：「買了才能用」用 Cedar 寫要幾行**（[腳本](../08-policy/experiments/cedar-skill-gating/README.md)）：授權本體 25 行（schema、policy、DB 資料轉 entities、判斷、`tools/list` 過濾），A 的清單沒有 flight、B 有、A 呼叫 flight 被拒。查 DB、403／429、限流、帳本這些手寫版大部分的行數都省不掉。

- 跟函式庫無關、但該修的：WP2 的限流是「先數再放行」，不是原子操作。改成 `UPDATE … WHERE count < limit RETURNING`，或用 Redis `INCR`。
- 什麼時候改用 Cedar：規則超過「買了沒」一種（方案分級、組織共享、試用期），或要對外證明權限邊界時。

**第 3 層**：函式庫都是開源、內嵌在自家 server，不另收費；gateway 類要多一台主機（agentgateway 約 `t4g.small` $15.8／月起；ContextForge 再加 Postgres）`[推測]`。方案 B 的授權也是在自家 server 手寫，這一層兩案成本相同。

### 第 4 層：雲端瀏覽器與接手

| 能力 | Browserbase | Steel 託管 | Steel 自架（steel-browser） | 自架 Chromium＋noVNC | Cloudflare Browser Run |
|---|---|---|---|---|---|
| Live View 可互動 | 有，可唯讀或可讀寫 `[官方已寫]` | 有，預設可互動 `[官方已寫]` | 有內建除錯頁 `[官方已寫]` | 要自己做；noVNC 本身可互動 | 有 `[官方已寫]` |
| 接手、交還後 agent 繼續 | 原始 session 沒有正式機制，只能靠「可互動＋agent 自己等」；pause／resume 只限它自家的 Agents API `[官方已寫]` | 有：`steel-mcp-server`（MIT）的 `steel_session_handoff`，Take control／Hand back `[官方已寫]` | 要自己做，可接 steel-mcp-server `[推測]` | 要自己做 | 有：CDP 指令 `Cloudflare.handoff`，等 `handoffComplete`，最長 30 分 `[官方已寫]` |
| 手機上操作 | **沒有正式支援**：「Mobile keyboards aren't officially supported」`[官方已寫]` | 官方沒寫 | 官方沒寫 | noVNC 寫支援 iOS、Android `[官方已寫]`；KasmVNC 直連不支援 Safari `[官方已寫]` | 官方沒寫 |
| profile 保存 | 有，Context 設 `persist: true` 無限期保存；一人一個 Context 要自己管 `[官方已寫]` | 有，30 天沒用自動刪除、單一 300 MB `[官方已寫]` | 第三方說沒有 `[推測]` | 要自己做 | 官方沒寫跨 session profile |
| 網域白名單 | 有 `allowedDomains`，只擋主框架跳轉 `[官方已寫]` | 官方沒寫 | 要自己做 | 要自己做（Chromium 政策或代理） | 官方沒寫 |
| Live View 開啟時間 | 官方沒寫 | 官方沒寫 | 官方沒寫 | 要自己量 | 官方沒寫；未實測（價格判定） |
| 授權 | 商用 | 商用 | Apache-2.0，仍標 beta | noVNC MPL-2.0 | 商用 |

- 來源：[Browserbase live view](https://docs.browserbase.com/features/session-live-view)、[Browserbase contexts](https://docs.browserbase.com/features/contexts)、[Browserbase pause/resume](https://www.browserbase.com/changelog/pause-and-resume-for-agents)、[Steel human-in-the-loop](https://docs.steel.dev/overview/sessions-api/human-in-the-loop)、[steel-mcp-server](https://github.com/steel-dev/steel-mcp-server)、[Steel profiles](https://docs.steel.dev/overview/profiles-api/overview)、[noVNC](https://github.com/novnc/noVNC)、[Cloudflare live view](https://developers.cloudflare.com/browser-run/features/live-view/)、[Cloudflare human-in-the-loop](https://developers.cloudflare.com/browser-run/features/human-in-the-loop/) `[官方已寫]`
- browserless 是 SSPL-1.0，閉源商用要買商業授權，不採用。
- 風險：Cloudflare 官方寫 Browser Run 一律被標成 bot 流量，有些網站即使是人在登入也可能被擋；Cloudflare Live View 連結預設 5 分鐘內要開始連線（最長可設 1 小時），推播後使用者晚開就會失效。Browserbase 每個 session 最少算 1 分鐘，頻繁開短 session 比 AgentCore（實測每次約 5–6 秒計費）貴。
- `[矛盾]` AgentCore Live View 能不能在手機上用：[DCV Web Client SDK release notes](https://docs.aws.amazon.com/dcv/latest/websdkguide/doc-history-release-notes.html) 1.10.1（2025-10-22）寫「Added mobile browser support (Chrome on Android, Chrome and Safari on iOS)」並加了 `setTrackpadMode`；較舊的支援瀏覽器表沒有手機。以 release notes 為準。WP2 #8 回填寫的「DCV 網頁客戶端官方不支援 iOS／Android」要更正。
- `[矛盾]` Browserbase API 文件寫 `keepAlive` 是「Hobby Plan and above」，定價頁沒有 Hobby 方案；Steel 2025-10 部落格的方案名稱與現行文件對不上。

**價格**（定價頁讀取日 2026-10-04）

| 方案 | 月費 | 含時數 | 超量單價 | 計費單位 | 並發 |
|---|---|---|---|---|---|
| AgentCore Browser（對照） | — | — | 約 $0.101／browser-hour | 秒 | — |
| Browserbase Developer | $20 | 100 h | $0.10／h | 分鐘，每 session 最少 1 分 | 25 |
| Browserbase Startup | $99 | 500 h | $0.10／h | 同上 | 100 |
| Steel Launch | $0 ＋ 用量 | 一次性 $30 額度 | $0.10／h | 分鐘，無條件進位 | 10；單 session 最長 15 分 |
| Steel Scale | $250 ＋ 用量 | 每月 $100 額度 | $0.08／h | 同上 | 100；單 session 最長 1 小時 |
| Cloudflare Workers Paid | $5 | 10 h | $0.09／h | 每天以秒累計，月底四捨五入 | 含 10 個（每日峰值取月平均），超過每個 $2 |
| Cloudflare Workers Free | $0 | 每天 10 分鐘 | 不能超量 | — | 3 |

- AgentCore 對照值的算法：WP2 實測 5 個 session 共 28 秒、0.005707 vCPU-h、0.029116 GB-h（[WP2 #11](WP2-capability-boundary.md#實際費用-1)），回推平均 0.73 vCPU、3.74 GB，0.734 × $0.0895 + 3.743 × $0.00945 = $0.101／h。

| 100 人月費 | 每人 1 h（共 100 h） | 每人 5 h（共 500 h） |
|---|---|---|
| AgentCore Browser | $10.1 | $50.5 |
| Browserbase | $20（Developer） | $60（Developer：20 + 400 × 0.10） |
| Steel | $10（Launch，但單 session 15 分、並發 10） | $250（Scale：250 + max(0, 40 − 100)） |
| Cloudflare | $13.1（5 + 90 × 0.09） | $49.1（5 + 490 × 0.09） |

依 A 半的範圍規則，只有 Cloudflare 比 AgentCore 便宜，但 100 人、每人 5 h 每月只省 $1.4，不值得另外實測，以價格判定。第 4 層的實測改做方案 B 自己的 AgentCore Browser（決策真正卡的是手機接手），見下方「實測：手機上接手 AgentCore Browser」。

**實測：手機上接手 AgentCore Browser**（[mobile-takeover](../05-built-in-tools/experiments/mobile-takeover/README.md)，iOS 模擬器 Mobile Safari，2026-10-04）

| 項目 | 結果 |
|---|---|
| Live View 開頁到第一個畫面 | 第一次 5.6 秒（含下載 2 MB 的 dcv.js）；之後 1.7–1.9 秒（3 次） |
| 點擊傳到遠端 | 成功 |
| 直接對 DCV 畫面打字 | **失敗**：Safari 點 canvas 不會取得焦點，按鍵沒地方接、也不叫出螢幕鍵盤 |
| viewer 加 HTML 輸入框、按鍵轉給 `connection.sendKeyboardEvent` | 成功：叫出 iOS 螢幕鍵盤，「Taipei 101」＋Enter 送進遠端並完成搜尋 |
| 中文（輸入法選完字的字串逐字送） | 成功，但連續送第一個字會掉；每個事件間隔 30 ms 後完整 |
| 交還後自動化接著做 | 成功；但接手會切斷原本的 CDP 連線，交還後要重新連 |
| 手機尺寸視窗（390×844） | 網站改成手機版排版，字看得清楚 |
| 同一 session 兩個 Live View | 第二個 `Connection limit reached` |
| 視窗尺寸對費用（`USAGE_LOGS`，每條件 3 筆、各 300 秒） | 不開 Live View：1280×720 $0.0870／h、390×844 $0.0857／h，範圍重疊、**沒有可分辨的差異**；開 Live View：$0.0906 vs $0.0876，手機尺寸便宜約 3.3%；開 Live View 本身多 2–4%；記憶體固定約 4 GB。100 人、每人 5 h 全程開 Live View 每月只差 $1.5 |
| 自動化偶爾卡死 | `evaluate`／`mouse.wheel` 偶爾永遠不返回（約 7%）。卡住後遠端 Chrome 閒置、WebSocket 沒斷 → 是 AgentCore automation stream 吞掉指令，**與 Live View、視窗尺寸、Browser 類型無關**；44 次重現沒觸發。對策：每個 CDP 指令設逾時、逾時重連重試 |

- 實作上要注意：每個瀏覽器操作都要設逾時，卡住就重連 CDP 或重開 session；改手機尺寸是為了看得清楚，不是省錢。這組工作負載的實測單價（$0.086–0.092／h）比上方用 WP2 回推的 $0.101 低，費用隨網頁與操作而變。
- 限制：模擬器的 HID 事件不等於實體手機的觸控與螢幕鍵盤；真正的注音輸入（`compositionend`）沒測，中文那一項用按鈕模擬選完字的字串。費用：接手測試約 $0.013（479 秒 × $0.101／h，系統 browser 沒有投遞）；尺寸費用實驗 19 個 session `USAGE_LOGS` 實測 $0.136。

**#7：方案 B 的手機接手**

- 方案 B 反而比較有把握：DCV Web Client SDK 1.10.1 起官方支援手機瀏覽器 `[官方已寫]`；hephclaw 的 iOS App 已在 Simulator 的真 WKWebView 收到 AgentCore Live View 串流（1280×720，`canvasHasContent: true`），實體 iPhone 的觸控與鍵盤未驗證（hephclaw `docs/agent-workspace/mobile-browser-research-20260930.md`）。方案 C 選託管瀏覽器時要自己實機驗證。AgentCore 已在 iOS 模擬器 Safari 實測接手、英數與中文輸入、交還後繼續都可行（[mobile-takeover](../05-built-in-tools/experiments/mobile-takeover/README.md)），條件是 viewer 自己加輸入框轉送按鍵；實體手機的螢幕鍵盤與注音輸入仍未驗證

### 第 5 層：記憶

| 能力 | 自管 Postgres + pgvector | Mem0 雲端／自架 | Zep 雲端／Graphiti 自架 |
|---|---|---|---|
| 短期對話歷史 | 要自己做 | 沒有獨立功能，用 user_id／agent_id／run_id 分範圍 | Zep 有（thread）；Graphiti 要自己做 `[推測]` |
| 長期記憶與語意檢索 | 要自己做（HNSW／IVFFlat） | 有 | 有（graph 檢索） |
| LLM 萃取 | 要自己寫整條 pipeline | 內建，新版單次 LLM 呼叫、**只新增** | 內建；自訂萃取指令要 Flex Plus；Graphiti 每個 episode 觸發多次 LLM 呼叫 |
| 合併去重與衝突 | 要自己做 | 不去重、不覆寫，衝突靠檢索排序 `[推測]` | 有：舊事實標記失效、不刪除 |
| 跨使用者隔離 | `user_id` WHERE（應用層），或 **RLS（資料層強制）**；RLS 要加 `FORCE ROW LEVEL SECURITY`，否則表擁有者會繞過 | 應用層帶 `filters={"user_id": ...}`；Platform 的 API key 綁 project，角色只有 READER／OWNER，沒有 per-user key（官方文件沒寫此功能）。OSS 的 per-user key 綁 dashboard 使用者，不是記憶的 `user_id` | Zep：每位使用者獨立 user graph（服務內結構隔離）；Graphiti：`group_id`，靠應用層 `[推測]` |
| 官方宣稱延遲 | 沒有 | p50 0.88–1.09 秒、每次約 7K token（README，沒說是寫入還是寫入加檢索）；雲端 add 是非同步 | Graphiti「通常次秒級」；Zep 託管「sub-200ms」 |

- 來源：[PostgreSQL RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)、[pgvector](https://github.com/pgvector/pgvector)、[mem0ai/mem0](https://github.com/mem0ai/mem0)、[Mem0 add](https://docs.mem0.ai/core-concepts/memory-operations/add)、[Zep concepts](https://help.getzep.com/concepts)、[getzep/graphiti](https://github.com/getzep/graphiti) `[官方已寫]`
- pgvector 的近似索引是先掃索引再套 WHERE，依使用者過濾後結果可能變少。建議 partition、獨立表，或開 iterative scan `[官方已寫]`。
- `[矛盾]` Mem0 舊論文（arXiv 2504.19413）描述萃取與整併，新版 README 寫只做 ADD。以新版 README 為準。

#### 實測：第 5 層寫入加檢索延遲（2026-10-02）

- 腳本與原始數據：[`02-memory/experiments/latency-compare/`](../02-memory/experiments/latency-compare/README.md)。資源 tag：`wp=WP6`、`owner=kais`、`project=hyfai`。
- 從台灣筆電呼叫東京（STS RTT 中位數 43–68 ms）。pgvector 和 Mem0 的 DB 是本機 docker，embedding 用 Titan V2、Mem0 萃取用 Haiku 4.5（`jp.`），都在東京 Bedrock。
- 每次試驗用新的使用者、同一則訊息。`visible_ms` 是從開始寫入到搜尋第一次找回這筆資料。

| 候選 | 次數 | 寫入 p50 | 搜尋 p50 | 寫入到搜得到 p50／p90 |
|---|---|---|---|---|
| pgvector（存原句，不萃取） | 10 | 192 ms | 170 ms | **365／463 ms** |
| Mem0 OSS 2.2.1（同步萃取） | 10 | 1,683 ms | 170 ms | **1.85／2.07 s** |
| AgentCore Memory（對照組，非同步萃取） | 5 | 243 ms | 337 ms | **65.9／68.1 s**（4 次命中；第一次 5 分鐘內沒萃取出來，原因沒查） |

- **自架比 AgentCore 快很多的是「剛寫入就要搜得到」：** AgentCore 的長期記憶要等約 66 秒的背景萃取，Mem0 同步萃取約 1.9 秒。搜尋本身三者都在 0.2–0.35 秒。
- 同一個 session 內的前文本來就靠短期記憶，66 秒只影響「剛說完的事實，下一個 session 馬上要用」的情境，對選型影響小。
- 費用約 $0.36（Haiku $0.22、`RetrieveMemoryRecords` 輪詢 270 次 $0.135），算式見腳本 README。
- 清理：docker 容器已移除；兩個 `wp6_latency_*` memory 都已刪除（見腳本 README 的清理確認）。

**第 5 層：100 人月費**（假設 `[推測]`：每人每月 30 session × 10 輪 = 共 3 萬輪，每輪 1 次寫入加 1 次檢索，共 2 萬筆長期記憶、20 GB）

| 候選 | 月費 | 算式 |
|---|---|---|
| AgentCore Memory（對照） | 約 $45 | 6 萬 event × $0.25/千 + 2 萬筆 × $0.75/千 + 3 萬次檢索 × $0.50/千（單價見 [`read-write-cost.md`](../02-memory/read-write-cost.md)） |
| Mem0 雲端 | $249 | 3 萬次檢索超過 Starter 的 5 千次，要 Pro |
| Zep 雲端 | $150–300 | 每則訊息 1–2 credit，6–12 萬 credits，Flex $125 加超量 |
| 自管 pgvector（RDS 東京） | 單 AZ 約 $76.5；Multi-AZ 約 $153 | `db.t4g.medium` $0.101/h × 730 + 20 GB × $0.138；不含萃取 LLM 費。運行中閒置照收；停止時不收實例時數，仍收儲存、備份、public IPv4，連續停滿 7 天自動啟動 `[官方已寫]`（[RDS 停止實例](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html)） |
| Mem0 自架 | 約 $110（單 AZ）；Multi-AZ 約 $186；compose 內建 Postgres 單機約 $33.5 | server 主機 `t4g.medium` $0.0432/h × 730 + 20 GB gp3 = $33.46（官方沒寫建議規格，`[推測]`）+ RDS 單 AZ $76.49；單機版無 HA、無備份。不含萃取 LLM 費 |
| Graphiti 自架（Neo4j） | 約 $16.7–33.5 | Neo4j 5.26 官方最低 2 vCPU／2 GB／10 GB → `t4g.small` $0.0216/h × 730 + 10 GB gp3 = $16.73；實務 `t4g.medium` $33.46 `[推測]`。Graphiti 是函式庫，跑在應用程式裡；不含 LLM 費 |

**萃取用 LLM 月費**（自建三個候選都要加；AgentCore 內建策略已含在上表）

假設 `[推測]`：每月 3 萬次寫入，每次 6.5K 輸入 + 0.5K 輸出 token；embedding 寫入與檢索各 1 次、每次 200 token（共 12M token）。7K token 取自 Mem0 README 的基準表，那是 managed 平台、top_200 檢索預算下的數字，不是單次寫入 `[矛盾]`，所以下表可能高估，要實測。

| 模型（東京） | 每百萬 token 輸入／輸出 | 月費 |
|---|---|---|
| Claude Haiku 4.5（`jp.` Geo profile） | $1.10／$5.50 | 214.5 + 82.5 + Titan V2 0.35 ≈ **$297**（Global profile 約 $270） |
| Amazon Nova Lite | $0.072／$0.288 | 14.04 + 4.32 + 0.35 ≈ **$18.7** |
| Amazon Nova Micro | $0.042／$0.168 | 8.19 + 2.52 + 0.35 ≈ **$11.1** |
| gpt-5-mini（Mem0 自架預設） | $0.25／$2.00 | 48.75 + 30 + text-embedding-3-small 0.24 ≈ **$79**（推理 token 算進輸出，可能偏低） |

- 東京單價取自 Bedrock Price List 東京檔（2026-09-30）`[官方已寫]`；OpenAI 取自[各模型頁](https://developers.openai.com/api/docs/models/gpt-5-mini) `[官方已寫]`。Titan Text Embeddings V2 東京 $0.029、Cohere Embed 4 $0.12 每百萬 token。
- 東京沒有 In-Region 的 Haiku 4.5、Nova Micro，只能走 cross-region profile；Haiku 4.5 的 Geo 價比 Global 貴 10%。Nova Lite、Titan V2、Cohere Embed 4 東京可直接 on-demand `[官方已寫]`（各模型的 [model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html)）。
- `[矛盾]` Nova Micro 的 Price List 有東京 SKU，文件卻寫東京沒有 In-Region。單價以 Price List 為準。
- 汰換風險：Haiku 4.5 的 model card 寫「EOL no sooner than Oct 16, 2026」；gpt-5-mini 在 OpenAI 已標 Deprecated。
- 實測更正（2026-10-02，[`latency-compare`](../02-memory/experiments/latency-compare/README.md)）：Mem0 2.2.1 每次 `add` 呼叫 LLM 1 次，平均 8.6K 輸入、80 輸出 token（使用者還沒有既有記憶時）。照這個數字重算，Haiku 4.5 是 283.8 + 13.2 + 0.35 ≈ **$297**：輸入多估少了、輸出多估了，合計剛好跟原估算相同。另外 mem0ai 2.2.1 搭 Nova 會在 Converse 參數驗證失敗，要用 Nova 就得修 mem0 或自己包 LLM client。

### 第 6 層：可觀測與成本分攤

| 能力 | OTel + Tempo 自架／Grafana Cloud | Langfuse 雲端／自架 | Phoenix 自架／Arize AX |
|---|---|---|---|
| trace / span | 有 | 有，OTLP 只收 HTTP，**不收 gRPC** | 有（OpenInference） |
| token 計量與成本換算 | 沒有原生；Tempo 不能單獨當分攤方案 `[推測]` | 有，內建價格表，可自訂 model definition | 有，內建價格表，可自訂 |
| 依 user／session 彙總 | 要自己寫查詢 | UI 有；**Metrics API v2 不能用 userId／sessionId 當 group-by**，要自己 loop 或拉 Observations 彙總 | session 有；per user 沒查到 |
| 非 LLM 成本掛到使用者 | 要自己做 | 要自己做（只有 generation／embedding 計成本） | 要自己做 |
| 資料可查詢延遲 | 未查 | 官方寫 15–30 秒（Langfuse v4 宣稱 real-time，此數字可能過時） | 未查 |

- 來源：[Langfuse token & cost](https://langfuse.com/docs/observability/features/token-and-cost-tracking)、[Langfuse Metrics API](https://langfuse.com/docs/metrics/features/metrics-api)、[Langfuse OTel](https://langfuse.com/integrations/native/opentelemetry)、[Langfuse scaling](https://langfuse.com/self-hosting/configuration/scaling)、[Phoenix cost tracking](https://arize.com/docs/phoenix/tracing/how-to-tracing/cost-tracking) `[官方已寫]`
- Langfuse Cloud 的 JP 區在 AWS ap-northeast-1（東京），Hobby、Core 都能選，定價頁沒有區域加價 `[官方已寫]`。JP 區 Postgres 備份複製到大阪，ClickHouse（trace）與 S3 不跨區複製。來源：[Langfuse data regions](https://langfuse.com/security/data-regions)
- Langfuse 舊版 metrics 端點（可依 user 彙總）在 Cloud 只服務到 2026-11-16 `[官方已寫]`。
- AgentCore 的 `USAGE_LOGS` 只有 `session.id`，沒有使用者 ID（[WP0 回填](WP0-cost-baseline.md#回填)），所以 session→user 對照不論自架或 AgentCore 都要自己維護。
- 自架相對 AgentCore 要自己補的維度：`user.id`（AgentCore 也沒有自動帶，待實測）、`session.id`（用 baggage 帶）、Runtime 資源用量（自架時沒有 `USAGE_LOGS`，要改看 CloudWatch Agent 或 cAdvisor）。
- Langfuse 自架必須有 ClickHouse（沒有替代），共六個元件：Web、Worker、Postgres、Redis、ClickHouse、S3。Docker Compose 版官方定位是「單一 VM，無 HA、無擴展、無備份」`[官方已寫]`。

**第 6 層：100 人月費**（假設 `[推測]`：每人每天 10 則對話，每則 35 units、135 KB）

| 候選 | 月費 | 算式 |
|---|---|---|
| AgentCore 內建觀測（對照） | 約 $1.55 | span 攝入 4.05 GB × $0.35 + 儲存 4.05 × $0.033（東京 CloudWatch Price List，2026-09-22）；只算 span，不含 `APPLICATION_LOGS`（vended logs 東京 $0.76/GB 起，量要實測） |
| Langfuse Cloud Core | 約 $105 | 105 萬 units：$29 + 90 萬 × $8/10 萬 + 5 萬 × $7/10 萬 |
| Grafana Cloud Traces | $19 | 4.05 GB 低於含的 50 GB；沒有成本換算 |
| Langfuse 自架（拆開部署） | 約 $340 | `t4g.xlarge` + RDS + Valkey + ClickHouse（`r7g.large`）+ EBS + S3；不含 ALB、備份、Multi-AZ |
| Langfuse 自架（單 VM Compose） | 約 $137 | 只適合實驗；撐不撐得住待實測 |
| Phoenix 自架（Postgres） | 約 $113 | `t4g.medium` + RDS `db.t4g.medium` |

觀測後端要 24h 收資料，沒有閒置折扣。

### #8 門檻：方案 C 比方案 B 便宜的使用者規模

合併 A、B 兩半，逐層看「自架或託管」相對 AgentCore 的成本結構：

| 層 | 方案 C 最便宜的路線 | 跟 AgentCore 比 | 門檻 |
|---|---|---|---|
| 1＋2 執行環境＋框架 | OpenClaw 或自寫 agent，每人一台 EC2 | 24h：$35.4 vs 實測 $8.3、保守 $34.1／人；8h：$14.4 vs $2.8、$11.4／人。都隨人數線性，每人都比較貴 | **無** |
| 3 授權 | 手寫（兩案相同） | 相同 | — |
| 4 瀏覽器 | Cloudflare Browser Run | 每小時便宜 11%，但有 $5 月費：(5 − 0.9) ÷ (0.101 − 0.09) ≈ 每月 373 browser-hours 以上才便宜，約 75 人（每人 5 h）；100 人、500 h 時也只省 $1.4 | 約 75 人，金額可忽略 |
| 5 記憶 | 自管 pgvector（RDS 單 AZ $76.5 固定）＋ Nova Micro 萃取（每人 $0.111） | AgentCore 每人約 $0.45：76.5 ÷ (0.45 − 0.111) ≈ 226 人以上才便宜；萃取用 Haiku 4.5（每人 $2.97）時永遠不會便宜 | 約 226 人（Nova Micro）／無（Haiku） |
| 6 觀測 | — | A 半已判定 AgentCore 便宜 | 無 |

- **結論：無門檻。** 金額最大的是第 1、2 層的執行環境，自架每人每月都比較貴，而且隨人數線性增加，沒有規模效益。第 4、5 層雖然在 75、226 人以上有門檻，每月省下的是幾十美元等級，抵不過第 1、2 層每人多出的 $3–27，也抵不過維運估點（上表加 A 半，挑最省的路線也有約 60 點：OpenClaw 每人一台 19、授權 1、託管瀏覽器 6、Mem0 自架 19、Langfuse Cloud 約 13）。
- 但書：AgentCore 的實測值來自不呼叫模型的最小 agent（WP1 #10）。真實 agent 的記憶體若接近保守估算（4 GB），第 1、2 層的差距會縮到每人 $1–3，那時要用正式 agent 的 `USAGE_LOGS` 重算。

### 自架要自己維運的元件與估點（`[推測]`，費氏數列）

| 層 | 路線 | 主要元件 | 估點合計 |
|---|---|---|---|
| 1 | 純 Firecracker | VM 排程與生命週期 API（21）、host fleet、映像、網路、記憶體清除、pause/resume、計量 | 約 68 |
| 1 | Kata on EKS | 節點群組與 Karpenter、映像、狀態保存（只有 PVC） | 約 36 |
| 1 | E2B 自架 | 移植到 AWS（13）、host fleet、映像 | 約 50 |
| 2 | OpenClaw 每人一台 | 每人一台機器的開通、啟停與回收（8）、版本升級與 deny 清單隨版重審（5）、對外網路控管（3）、使用者 token 輪換（MCP headers 是靜態的，要改 ENV 加重啟，3） | 約 19 |
| 2 | Strands／LangGraph 自寫 | 框架本身不用維運；聊天室對應實例、session 路由（3），執行環境算在第 1 層 | 約 3 |
| 3 | 手寫（同方案 B） | 無額外；限流改原子操作（1） | 約 1 |
| 3 | 改用 Cedar | 規則與 schema、DB → entities 轉換（2） | 約 2 |
| 3 | agentgateway／ContextForge | 部署與升級（3）、購買資料同步進 JWT 或它的 DB（5）、限流計量接回自家帳本（3） | 約 11 |
| 4 | 託管（Cloudflare、Steel） | 接手交還接進 App（3）、手機實機驗證與鍵盤補強（3） | 約 6 |
| 4 | 自架 Chromium＋noVNC | 一人一容器的隔離與擴展（8）、瀏覽器更新（3）、接手交還狀態機與逾時（5）、手機觸控與鍵盤（5）、profile 加密保存（3）、網域白名單代理（3） | 約 27 |
| 5 | 自管 pgvector | 萃取 pipeline（8）、去重與衝突（8）、索引、RLS、對話表 | 約 28 |
| 5 | Mem0 自架 | 去重策略、server 部署、RLS | 約 19 |
| 5 | Graphiti 自架 | 圖資料庫維運（5）、限流 | 約 23 |
| 6 | Langfuse 自架 | 六元件部署（8）、升級、擴展、session→user 合併報表（5）、隱私 | 約 34；改用 Cloud 省約 18–21 |

### 範圍調整（2026-10-02）

接下來 WP6 只實測**估算月費比 AgentCore 便宜的託管方案**。託管方案的估算月費如果已經比 AgentCore 高，就不實測，直接以價格判定。自架方案也不再追加實測，已經做完的 pgvector、Mem0 OSS 保留。

| 層 | 託管候選 | 100 人估算月費 | AgentCore 對照 | 判定 |
|---|---|---|---|---|
| 1 | E2B、Daytona | 24h $12.2k–12.4k；8h $4.2k–4.3k。E2B 縮到 1 vCPU／1 GB 也要 $5.0k／$1.8k | 實測 $832／$277；保守估 $3.4k／$1.1k（見下方「第 1 層判定」） | **跳過**：任何一種算法都比 AgentCore 貴 |
| 5 | Mem0 Platform、Zep Cloud | $249；$150–300 | 約 $45 | **跳過**：比 AgentCore 貴 3–7 倍 |
| 6 | Langfuse Cloud Core | 約 $105 | 約 $1.55（只算 span） | **跳過**：比 AgentCore 貴約 68 倍 |

原列的「待實測」項目都已完成或依上表跳過：第 1 層冷啟動（Firecracker、Kata 自架不測）；第 5 層一次寫入加檢索延遲（pgvector、Mem0 OSS 已完成；Mem0 Platform、Zep Cloud 跳過）；第 6 層 Langfuse 實測；寫信問 E2B、Daytona（暫停期間的儲存費、40 GB 磁碟、VM sandbox 啟動秒數），第 1 層跳過，不用問。

### 清理確認

- [x] 沒有建立 AWS 資源
- [x] OpenClaw gateway 已停止；裝在暫存目錄，`~/.openclaw` 不存在、沒有裝 launchd 服務；`/tmp/openclaw/` log 已刪除
- [x] 子 agent 的暫存測試檔在 session scratchpad，不在 repo
- [x] 第 4 層實測的兩個 AgentCore Browser session 已關閉，`list-browser-sessions --status READY` 為空；沒有註冊 Cloudflare
- [x] 尺寸費用實驗的自訂 Browser `wp6_viewport`、USAGE_LOGS delivery source／delivery 已刪
- [x] 第 5 層實測的 docker 容器與 `wp6_latency_*` memory 已刪除（見第 5 層實測）

### 要更正研究庫的段落

前五列是 A 半，2026-10-02 已套用；後五列是 B 半。

| 檔案:行號 | 原本寫的 | 調研結果 |
|---|---|---|
| `00-overview/build-vs-buy.md:21` | session 強隔離要自己寫一整套排程器，難度高 | 拆三級：買 E2B 託管＝低；Kata on EKS＝中；純 Firecracker＝高。AWS 上要 Intel nested virtualization。Daytona 預設是 container；VM sandbox 雖已不標 beta，但磁碟上限 10 GiB、只能從 VM snapshot 建立 |
| `00-overview/build-vs-buy.md:22` | 短期記憶用 Redis／Postgres，低 | 自建低成立；Mem0 沒有獨立對話歷史，Zep thread 才是對應物 |
| `00-overview/build-vs-buy.md:23` | 合併、去重、衝突、隔離全部要自己設計 | Mem0 只新增不去重；Zep／Graphiti 有失效機制；只有 pgvector 加 RLS 能在資料層強制隔離 |
| `06-observability/README.md:104` | log 大約每 GB $0.50 | $0.50 是美東價；東京標準 Logs 攝入 $0.76/GB。span 的 $0.35/GB 東京相同 |
| `00-overview/build-vs-buy.md:30` | 觀測低–中，標準成熟 | 改成中：trace 與 LLM 成本換算成熟，每位使用者全成本分攤不成熟；Langfuse 自架六元件；只收 HTTP OTLP |
| `00-overview/build-vs-buy.md:19` | Harness：框架都已經處理好了，低 | 框架本身低；但 OpenClaw 預設全開、一個租戶一個 gateway，每人一台機器；Strands 每個聊天室要一個 Agent 實例 |
| `00-overview/build-vs-buy.md:24` | Gateway：自己架 MCP server，中 | 技能授權放自家 MCP server 手寫即可（WP2 實證），MCP gateway 類專案要多養服務、購買資料多一份，不值得 |
| `00-overview/build-vs-buy.md:27` | Policy：在工具 proxy 前面放 OPA 或 Cedar，中 | 「買了才能用」這種規則，函式庫省不了程式碼（70 行→約 60 行），多得到的是型別檢查與形式驗證；規則變複雜再用 Cedar |
| `91-work-packages/WP2-capability-boundary.md:205` | #8：要另測手機能否開 Live View（DCV 網頁客戶端官方不支援 iOS／Android） | DCV Web Client SDK 1.10.1 起官方支援 iOS Safari／Chrome、Android Chrome `[官方已寫]`；hephclaw 已在 Simulator 真 WKWebView 收到串流，實機未驗證 |
| `00-overview/build-vs-buy.md:29` | Browser：自己維運一組 headless Chrome，中–高 | 託管（Cloudflare、Steel）有接手交還機制、價格與 AgentCore 相近；手機上操作 Live View 託管的沒有一家官方支援（AgentCore 的 DCV 1.10.1 起支援）；自架要做接手狀態機與手機觸控，約 27 點 |
