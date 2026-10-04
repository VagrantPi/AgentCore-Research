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

## 實作時要做的事

1. **viewer 上要有自己的輸入框**，把 `keydown`／`keyup` 轉給 `connection.sendKeyboardEvent`；輸入法選字中（`isComposing`）的按鍵不轉，`compositionend` 拿到的字串逐字送，事件之間留間隔。
2. **agent 端在交還後重新連 CDP**，不能沿用接手前的連線。
3. **Browser 視窗設成手機尺寸**（`viewPort`），不然 1280 寬縮到手機上字太小。
4. 一個 session 同時只能有有限個 Live View 連線：換裝置或重開頁面前要先斷開舊的。

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
