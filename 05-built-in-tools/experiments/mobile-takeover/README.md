# 手機上接手 AgentCore Browser：Live View、輸入、交還

WP6 第 4 層與 #7 的實測（[WP6 回填](../../../91-work-packages/WP6-oss-alternatives.md#第-4-層雲端瀏覽器與接手)），也回答 WP2 #8 的前半：AgentCore Browser 的 Live View 能不能在手機瀏覽器上看、點、打字，交還後自動化能不能接著做。

不經 hephclaw 後端（正式後端 `BROWSER_ENABLED` 沒開）：本機腳本直接開 AgentCore Browser，在 `http://localhost` 起一頁 DCV viewer，用 iOS 模擬器的 Safari 打開，idb 送點擊與按鍵。

| 元件 | 用什麼 |
|---|---|
| Browser | 系統 browser `aws.browser.v1`，東京（不建資源；系統 browser 的 session 不能加 tag） |
| 自動化端 | `bedrock-agentcore` 1.24.0 的 `BrowserClient` ＋ Playwright `connect_over_cdp` |
| Live View | DCV Web Client SDK（hephclaw 內嵌的 `backend/browser-assets/dcvjs-esm`，執行時直接讀，不放進本 repo）；連線流程照抄 hephclaw `web/browser-view/dcv-session.mjs` |
| 手機 | Xcode 27 的 iPhone 17 Pro 模擬器，iOS 26.5，Mobile Safari |
| 操作 | idb（`idb ui tap`、`idb ui text`、`idb ui key`） |

## 怎麼跑

```bash
brew install facebook/fb/idb-companion && pipx install fb-idb
uv run takeover.py --viewport 1280x720          # 開 session、導到維基首頁、起 http://localhost:8765/
xcrun simctl openurl <udid> http://localhost:8765/
curl -X POST localhost:8765/take                 # take_control：automation stream → DISABLED
idb ui tap --udid <udid> <x> <y>                 # 點遠端的搜尋框，再點 viewer 上方的輸入框
idb ui text --udid <udid> "Taipei 101"; idb ui key --udid <udid> 40
curl -X POST localhost:8765/release              # release_control：automation stream → ENABLED
curl localhost:8765/check                        # Playwright 讀目前頁面
curl -X POST localhost:8765/stop
```

每一步記在 [`results.csv`](results.csv)。

## 結果（2026-10-04）

| 項目 | 結果 | 證據 |
|---|---|---|
| Live View 在 iOS Safari 顯示 | **成功**，`secureContext: true`（localhost） | [`takeover-ascii.png`](takeover-ascii.png) |
| Safari 開頁到第一個畫面（`firstFrame`） | 第一次 **5.6 秒**（含下載 2 MB 的 dcv.js）；之後重開 **1.7–1.9 秒**（3 次） | `results.csv` 的 `viewer_first_frame` |
| 點擊（觸控）傳到遠端 | **成功**，接手前、接手後都傳得到（遠端搜尋框取得焦點） | — |
| 直接對 DCV 畫面打字 | **失敗**：Safari 點 canvas 不會讓任何元素取得焦點，按鍵沒地方接，也不會叫出螢幕鍵盤 | — |
| 加一個 HTML 輸入框，把按鍵轉給 DCV（`connection.sendKeyboardEvent`） | **成功**：點輸入框叫出 iOS 螢幕鍵盤；「Taipei 101」＋Enter 共 24 個事件轉過去，遠端搜尋到「台北101」條目 | [`takeover-ascii.png`](takeover-ascii.png) |
| 中文（模擬輸入法選完字後的字串） | 逐字包成 `KeyboardEvent({key})` 轉送。**連續送時第一個字會掉**（「台北101」→「北101」）；每個事件間隔 30 ms 後完整出現 | [`takeover-cjk.png`](takeover-cjk.png) |
| take_control／release_control | 各約 0.3 秒；`take` 後 automation stream 為 `DISABLED` | `results.csv` |
| 交還後自動化接著做 | **成功**，Playwright 讀到使用者搜尋出來的「台北101 - 维基百科」頁。但**接手會切斷原本的 CDP 連線**（`TargetClosedError`），交還後要重新連 | `results.csv` 的 `check` |
| 手機尺寸視窗（390×844） | 網站改成手機版排版，字在手機上看得清楚 | [`viewport-390x844.png`](viewport-390x844.png) |
| 同一個 session 同時兩個 Live View | 第二個連線回 `Connection limit reached` | `results.csv` 的 `viewer_connect_error` |

## 視窗尺寸與 Live View 對費用的影響（`viewport_cost.py`，2026-10-04）

自訂 Browser `wp6_viewport`（tag `wp=WP6`），`USAGE_LOGS` 投遞到 `wp0-usage-dst`。每個 session 跑同一段工作負載 300 秒（依序開維基首頁、維基「台北101」、GitHub Explore、BBC News，每頁捲 20 次），時間到立刻 `stop()`。4 個條件同一輪並行，「開 Live View」用兩台模擬器的 Safari 各連一個。每個條件 3 筆有效，原始數據 [`viewport_report.csv`](viewport_report.csv)、[`viewport_runs.csv`](viewport_runs.csv)。

| 視窗 | Live View | 每 browser-hour（平均，範圍） | 平均 vCPU | 平均記憶體 |
|---|---|---|---|---|
| 1280×720 | 不開 | **$0.0870**（0.0864–0.0876） | 0.550 | 3.99 GB |
| 390×844 | 不開 | **$0.0857**（0.0832–0.0905） | 0.536 | 3.99 GB |
| 1280×720 | 開 | **$0.0906**（0.0895–0.0919） | 0.591 | 3.99 GB |
| 390×844 | 開 | **$0.0876**（0.0862–0.0884） | 0.563 | 3.94 GB |

- **不開 Live View 時，尺寸對費用沒有可分辨的差異**：兩者範圍重疊，平均只差 1.5%。
- **開 Live View 時，手機尺寸便宜約 3.3%**（範圍不重疊），因為串流的像素少。
- **開 Live View 多花 2–4%**（1280×720 +4.1%、390×844 +2.2%），只在使用者看的時候發生。
- 記憶體固定約 4 GB、不隨尺寸變，佔每小時費用約 43%（3.99 × $0.00945 = $0.0377）。
- 換算 100 人、每人每月 5 小時都開著 Live View：1280×720 $45.3 vs 390×844 $43.8，**每月差 $1.5**。改手機尺寸是為了看得清楚，不是為了省錢。
- 這組工作負載的單價（$0.086–0.092／h）比 WP2 估的 $0.101 低，費用會隨網頁與操作而變。

**自動化偶爾卡死（AgentCore 自動化通道的問題，不是 Live View）**：尺寸費用實驗中有 3 個 session 在載完第一頁後的捲動階段卡住，`page.evaluate`／`mouse.wheel` 永遠不返回，直到 session 逾時。追查結果（重現腳本 `lv_hang.py`、`hang_batch.sh`，時間線 `hang_timeline.py`）：

| 證據 | 說明 |
|---|---|
| 卡住後遠端 Chrome 的 vCPU 立刻掉到閒置（每 10 秒平均 0.05–0.10），一直到 session 被關；正常的 session 在 0.17–1.00 之間起伏 | 瀏覽器沒當掉也沒在忙，是**指令沒送到瀏覽器** |
| Playwright 沒收到斷線事件，直到 session 逾時才 `TargetClosedError` | WebSocket 沒斷，指令或回應在 AgentCore 的 automation stream 中間不見了 |
| 只卡在沒有逾時的指令（`evaluate`、`mouse.wheel`）；`goto` 有 30 秒逾時從沒卡死 | 有逾時就會報錯而不是卡死 |
| 同一時間開的 4 個 session（2 個開 Live View、2 個沒開）CDP 連線都慢到 21 秒；平常中位數 1.4 秒（34 次） | AgentCore 自動化端點會整體性地短暫變慢（[`hang_batch_full-1.md`](hang_batch_full-1.md)） |
| 重現：簡化版系統 browser 8 次、自訂 Browser 12 次、完整工作負載 24 次（各一半開 Live View），**都沒重現出無限卡死** | 偶發，原因在服務端，本機無法穩定觸發 |

- **跟 Live View 的關聯不成立**：開 Live View 43 次卡 3 次（約 7%），沒開 20 次卡 0 次，樣本太少分不出差別。先前寫的「開著 Live View 會卡死」是錯的。
- 也排除：自訂 vs 系統 browser、視窗尺寸（兩種都卡過）。
- 能做的是在我們這端防護：**每個 CDP 指令都設逾時（`evaluate` 也要，例如包一層 `asyncio.wait_for`），逾時就重連 CDP 並重試一次**；正式環境監控卡死率。卡住的 session 不算進上表（秒數 602、361，標為 INVALID）。
- 除錯花費：自訂 Browser 36 個 session，至 14:39 UTC 已到的 27 個 `USAGE_LOGS` 實測 $0.072，全部估約 $0.16；系統 browser 8 個（沒有投遞）以秒數估約 $0.01。臨時建的 `wp6_viewport-M5wOn5rphr` 與投遞已刪。

- 費用：19 個 session（含第 1 輪、除錯與卡住的）共 6,403 秒，`USAGE_LOGS` 實測 **$0.136**。
- 清理：Browser `wp6_viewport`、delivery source／delivery 已刪。

## 接手時才切手機版（`mobile_handoff.py`，2026-11-05）

hephagent 的 Nova Act 要 1600×1000，整個 session 改手機尺寸會影響自動化。改成：session 維持 1600×1000，接手前用 CDP 模擬 Pixel 7（412×915、Android UA、touch），viewer 加 `?crop=412x1003` 只放大左上角那一塊。本機 Chromium（Pixel 7 尺寸）開 viewer 代替手機，系統 browser，東京。

| 項目 | 結果 | 證據 |
|---|---|---|
| 模擬後頁面 | `innerWidth` 412、Android UA、`maxTouchPoints` 5，網站排成手機版 | `results.csv` 的 `emulated` |
| 裁切放大後的 Live View | 手機版、字看得清楚。**串流含 Chrome 分頁列＋網址列 88 px**，裁切高度要 915＋88 | [`handoff-A-keep-automation.png`](handoff-A-keep-automation.png) |
| 點擊座標（不 take_control） | 目標 (300, 600) → 頁面收到 (300, 601)，`pointerType: touch` | `A_tap` |
| 點擊座標（take_control 後） | 同上，(300, 601) | `B_tap` |
| 交還後清模擬（同一條 CDP 連線） | `clearDeviceMetricsOverride` 後回到 1599 寬、桌面 UA | `A_cleared` |
| 交還後清模擬（take_control 切斷舊連線後重連） | **UA／touch 自動消失，但 412 寬殘留**；新連線直接 `clear` 清不掉，要先 `setDeviceMetricsOverride` 再 `clear` 才回到 1599 | `B_clear_only`、`B_override_then_clear` |

| take_control 期間網站收到的 UA | **桌面版**：接手中在 viewer 點進 `httpbin.org/headers`，伺服器收到 `X11; Linux x86_64`、`Sec-CH-UA-Mobile: ?0`。UA／touch 在 CDP 斷線那一刻就掉了，只剩 412 寬 | `C_server_saw_during_takeover`、[`handoff-C-during.png`](handoff-C-during.png) |

結論：方案可行，但兩條路效果不同。
- **take_control（現行流程）**：接手期間只剩 412 寬，看 CSS 寬度的 RWD 網站是手機版；看 UA／client hints 的網站給桌面版。交還後要「先 `setDeviceMetricsOverride` 再 `clear`」清殘留寬度。
- **不切 automation stream**（hephagent `BROWSER_HANDOFF_KEEP_AUTOMATION`）：UA、touch、寬度整段都在，交還時同一條連線 `clear` 就乾淨。

費用：3 個 session 各約 1 分鐘，系統 browser 以秒數估 < $0.01。

## 改成縮 Chrome 視窗（`window_bounds.py`，2026-11-05）

裁網頁區域的做法，新分頁的分頁列、彈出視窗、Chrome 右上角的提示都會落在裁切範圍外。改用 CDP `Browser.setWindowBounds` 把 Chrome 視窗本身縮到左上角，viewer 裁同一塊。

| 項目 | 結果 | 證據 |
|---|---|---|
| AgentCore 允許改視窗大小 | 可以，`windowState` 本來就是 `normal`，設完 `innerWidth` 跟著變 | `results.csv` 的 `window_resized` |
| 最小寬度 | **Chrome 視窗最小 500**：要 412 會被拉到 500，所以裁 500×1003 | 同上 |
| 新分頁（`target=_blank`） | 開在同一個視窗、本來就 500 寬；4 個分頁都看得到、都有 ×；網址列、⋮ 選單完整 | [`window-2-tabs-crop.png`](window-2-tabs-crop.png) |
| 彈出視窗（`window.open` 帶尺寸） | 另開一個 1456×853 的視窗蓋住整個桌面；對它的 window 一樣 `setWindowBounds` 縮到 500×1003 後完整看得到 | [`window-3-popup-crop.png`](window-3-popup-crop.png) |
| 彈出視窗關掉 | 回到主視窗，4 個分頁都在 | [`window-4-popup-closed-crop.png`](window-4-popup-closed-crop.png) |
| 交還 | `setWindowBounds` 回 1600×1000，`innerWidth` 回 1599 | `window_restored` |

注意：
- 只縮視窗不改 UA：網站拿到桌面 UA，看寬度的 RWD 會排窄版（維基仍是桌面版的窄排、底部有橫向捲軸）。要手機版還是得對每個分頁加 `setUserAgentOverride`／touch（新分頁在 `context.on("page")` 補）——本輪沒測。
- 彈出視窗沒有分頁列，**使用者無法自己關掉**；通常由網站（OAuth、3DS）自己關。
- 縮視窗與縮彈出視窗都要 CDP 連線還在，只適用不切 automation stream 的接手。

## 縮視窗＋UA／touch（`window_ua.py`，2026-11-05）

縮視窗 500×1003 之外，每個分頁 `Emulation.setUserAgentOverride`（含 `userAgentMetadata` mobile）＋`setTouchEmulationEnabled`；新分頁、彈出視窗在 `context.on("page")` 補。新頁開 `httpbin.org/headers` 看伺服器**第一個請求**收到什麼。

| 項目 | 結果 | 證據 |
|---|---|---|
| 主分頁 | Android UA、`maxTouchPoints` 5、`pointer: coarse`、`userAgentData.mobile`，維基變手機版、沒有橫向捲軸、Chrome 工具列完整 | [`window-ua-1-main.png`](window-ua-1-main.png) |
| 新分頁／彈出視窗第一個請求（只靠 `on("page")`） | **桌面 UA**（`X11`、`?0`、`"Linux"`）：`on("page")` 觸發時第一個請求已送出；重新整理後才是手機 | `results.csv` 的 `tab_first_load`、`pop_first_load` |
| 加 `context.route` 改寫 `user-agent` header | 第一個請求就是 Android UA；但 **`Sec-CH-UA-Mobile`／`-Platform` 改不掉**（仍 `?0`／`"Linux"`，Chrome 在攔截之後才加），要到第二個請求才一致 | 同上（第二輪） |
| 交還 | 清模擬、關新頁、視窗回 1600×1000：1599 寬、桌面 UA、touch 0 | `restored` |

注意：
- 第一個請求 UA 說 Android、client hints 說 Linux，指紋不一致；看 UA 排版的網站沒影響，嚴格的反機器人可能起疑。登入／3DS 彈窗不能靠重新整理補（一次性網址、POST）。
- hephagent 接手期間的 passthrough（`workspace-browser-agent-network.js:163`）原則是「不讀 header」；改寫 UA 要讀 `request.headers()` 再整包送回，跟 PCI 那條原則衝突，要先講好。

## 縮視窗撐不撐得過 take_control（`window_takecontrol.py`，2026-11-05）

| 項目 | 結果 | 證據 |
|---|---|---|
| 縮到 500×1003 後 take_control（stream `DISABLED`、CDP 斷） | 接手期間視窗維持 500 寬，Live View 是窄版排版 | [`window-tc-during.png`](window-tc-during.png) |
| release_control 後重連 | bounds 仍 500×1003、`innerWidth` 500：視窗大小是瀏覽器狀態，不綁 CDP 連線 | `results.csv` 的 `after_release` |
| 從新連線縮回 | 1599×999、`innerWidth` 1599 | `restored` |

結論：兩條接手路（take_control、keepAutomation）都能用「接手前縮視窗、交還後縮回」；不碰任何請求。take_control 那條只是沒有手機 UA／touch。

## 實作時要做的事

1. **viewer 上要有自己的輸入框**，把 `keydown`／`keyup` 轉給 `connection.sendKeyboardEvent`；輸入法選字中（`isComposing`）的按鍵不轉，`compositionend` 拿到的字串逐字送，事件之間留間隔。
2. **agent 端在交還後重新連 CDP**，不能沿用接手前的連線。
3. **Browser 視窗設成手機尺寸**（`viewPort`），不然 1280 寬縮到手機上字太小。
4. 一個 session 同時只能有有限個 Live View 連線：換裝置或重開頁面前要先斷開舊的。
5. **每個 CDP 指令都要有逾時，逾時就重連重試**：AgentCore 的 automation stream 偶爾會吞掉指令（約 7%，與 Live View 無關，見上一節）。

## 限制

- **不是實體手機。** idb 送的是模擬器的 HID 事件：點擊和打字能證明 DCV 在 iOS WebKit 收得到輸入，但實體手機的觸控手感、螢幕鍵盤上的注音輸入（真正的 `compositionend`）都沒測。中文那一項用的是按鈕模擬「輸入法選完字」的字串。
- 只測公開網站（維基百科），沒有真的登入；登入表單的密碼欄、OTP 欄行為應相同，未測。
- 只測 Mobile Safari；hephclaw 先前測過 WKWebView 的串流（hephclaw repo 的 `docs/agent-workspace/mobile-browser-research-20260930.md`），Android Chrome 沒測。

## 費用

兩個 session 共 479 秒（394 秒＋85 秒），以 WP2 實測的每 browser-hour $0.101 估約 **$0.013**。系統 browser 沒有開 `USAGE_LOGS` 投遞，所以是 session 秒數 × 單價的估算。

## 清理

- [x] 兩個 session 都已 `stop()`；`list-browser-sessions --status READY` 為空
- [x] 本機 server 已停
- [ ] idb（`idb-companion`、`fb-idb`）保留在開發機，之後實機測試沿用
