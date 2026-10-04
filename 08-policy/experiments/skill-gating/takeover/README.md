# WP2 #8：接手登入由 server 主導

[WP2 #8](../../../../91-work-packages/WP2-capability-boundary.md#回填) 的實測。需要登入時，自家 MCP server 停下自動操作、把 Live View 連結**直接推給 App**，使用者在手機上登入、交還後 server 接著做；agent 從頭到尾拿不到 Live View URL。

接手的做法沿用 WP6 的 [`mobile-takeover`](../../../../05-built-in-tools/experiments/mobile-takeover/README.md)（DCV viewer、輸入框轉送按鍵、交還後重連 CDP、每個 CDP 指令設逾時），WP4 的程式不存在。

## 架構

```
agent.py（本機 Strands＋Haiku 4.5，MCP client，帶 userB 的 60 秒 actor JWT）
   │ MCP tools/call  com_wp2_login-web__login_and_check
   ▼
本機 HephAgora（wp2/skill-gating 分支，docker compose -p hephagora-wp2，port 13000）
   │ 驗 JWT、檢查購買、寫調用帳本
   │ binding：mcp_server type=http → http://host.docker.internal:13200/mcp，timeout_ms 300000
   ▼
browser_skill.py（Python MCP server＋viewer＋模擬 App 推播端點，port 13200，用 server 自己的 AWS 憑證）
   ├─ StartBrowserSession（系統 browser、390×844）→ 開 https://the-internet.herokuapp.com/login
   ├─ 偵測到密碼欄位 → take_control → 一次性 viewer ticket
   ├─ POST /push {user, title, url} → pushes.jsonl（模擬推播服務；URL 只走這條路）
   ├─ 等使用者在 viewer 按「交還」（工具總預算 270 秒，比 binding 的 300 秒早結束）→ release_control → 重連 CDP
   └─ 讀登入結果 → 只回 {"status", "message"} 給 HephAgora／agent
iOS 模擬器 Safari＋idb（扮演 App 與使用者）：讀 pushes.jsonl → 開 viewer → 輸入帳密 → 登入 → 交還
```

測試站是公開的自動化練習站，帳密寫在頁面上（tomsmith／SuperSecretPassword!）。

## 怎麼跑

```bash
# 1. 本機 HephAgora（在 HephAgora repo，wp2/skill-gating 分支）
docker compose -p hephagora-wp2 --profile localdb -f docker-compose.yml -f docker-compose.wp2-local.yml up -d --build db app
PSQL="docker compose -p hephagora-wp2 --profile localdb -f docker-compose.yml -f docker-compose.wp2-local.yml exec -T db psql -U hephagora -d hephagora"
PSQL="$PSQL" bash scripts/wp2/setup-consumer.sh
$PSQL -v ON_ERROR_STOP=1 < scripts/wp2/seed.sql
$PSQL -v ON_ERROR_STOP=1 < <本目錄>/seed-takeover.sql
HA=http://localhost:13000 bash scripts/wp2/check.sh          # 15 項全過

# 2. 本目錄
uv run browser_skill.py &                                     # MCP 在 :13200/mcp
bash authz_check.sh                                           # 新 service 也受授權管
uv run agent.py --user userB                                  # 呼叫工具後會等使用者
cat pushes.jsonl                                              # 推播來的 viewer 連結
xcrun simctl openurl <udid> <viewer 連結>
# 模擬器上：點遠端欄位 → 點上方輸入框 → 打字（idb ui tap／text／key）→ 登入 → 按「完成，交還給 agent」
```

## 結果（2026-10-05 台灣時間，iOS 模擬器 iPhone 17 Pro）

| 情境 | 結果 | 證據 |
|---|---|---|
| 授權：B 看得到工具、A 看不到、A 直接呼叫 | 通過：A 呼叫回 `Unknown tool` | `authz_check.sh` |
| 主流程：偵測登入頁 → take → 推播 | 5.7 秒推出（有 CDP 逾時重連時 34–62 秒） | `events.csv` |
| 手機開推播連結 → Live View 第一個畫面 | 2.4 秒 | `events.csv` 的 `viewer_first_frame`、[`1-login-page.png`](1-login-page.png) |
| 使用者在手機上輸入帳密、登入 | 成功（帳號、密碼經上方輸入框轉送，Enter 送出） | [`3-logged-in.png`](3-logged-in.png) |
| 交還 → release → 重連 CDP → 讀結果 | release 0.2 秒、重連加讀取 3.6 秒；讀到「You logged into a secure area!」 | `events.csv` |
| agent 收到的結果 | `{"status": "logged_in", "message": "You logged into a secure area!"}`，回覆「登入成功！」（從 agent 開始呼叫算 135 秒，大部分是使用者在登入） | [`transcript.json`](transcript.json) |
| **Live View URL 不經 agent** | **通過**：agent 對話紀錄、agent 輸出、HephAgora log、調用帳本，搜尋 `browser-streams`／`live-view`／`/viewer/`／`X-Amz-Signature`／ticket／`localhost:13200` 都是 0 筆；帳本只記 userB、ok、132.7 秒 | 上述檔案 |
| 使用者沒交還 | 通過：工具開始後 270 秒 release、停 session，回 `{"status": "user_did_not_complete_login", "waited_seconds": 270}`，agent 正常轉告使用者 | [`transcript_timeout.json`](transcript_timeout.json) |
| 最終版（加了重試與總預算）再跑一次主流程 | 通過：這次沒有發生 CDP 逾時（重連重試在兩次逾時情境的 `goto` 都有救回，見 `login-856A41`、`login-HWS09D`）；交還後 1.5 秒拿到結果，agent 回「登入成功！✅」；URL 搜尋同樣 0 筆 | `events.csv` 的 `login-GK1XN7` |

### 發現

1. **雲端瀏覽器會跳「要儲存密碼嗎？」**（[`2-save-password-prompt.png`](2-save-password-prompt.png)）：使用者接手時輸入的帳密，Chrome 的密碼管理員會想存下來。如果 Browser 用了會保存的 profile，下一個操作這個 profile 的人或 agent 就可能拿到。正式版要用企業政策關掉（`PasswordManagerEnabled: false`），並把「接手時輸入的帳密不會被保存」列入驗收。
2. **HephAgora 呼叫外部 MCP server 時不帶 actor**（只帶 OAuth bearer）。browser_skill.py 不知道該推給哪個使用者，這次用固定的 userB。正式版要讓 HephAgora 把 actor 傳給 binding（例如加一個 header），約 5 行，或把推播交回 HephAgora 自己做。
3. **錯誤時 HephAgora 把內部 server 位址回給 agent**：工具丟例外時，agent 收到的錯誤含 `_meta.server: http://host.docker.internal:13200/mcp`（成功時沒有這個欄位）。不是 Live View URL，但內部位址也不該讓 agent 看到，正式版要在 HephAgora 拿掉。
4. **等待時間要用總預算算**：第一版固定等 240 秒，結果開頁就花了 62 秒（測試站架在 Heroku，閒置後第一次開很慢，加上一次 CDP 逾時重連），總共 302 秒，被 HephAgora 的 300 秒先判逾時，agent 只收到 `Request timed out`。改成「工具從開始算最多 270 秒」。HephAgora 放棄後 server 端仍有照常 release、停 session。
5. **iOS 鍵盤開著時，點擊偶爾會落在錯的位置**：第二次主流程，鍵盤開著時點密碼欄兩次都沒點到（遠端游標落在約 200 px 下方），收起鍵盤後同一個座標就點準了；第一次主流程鍵盤開著卻點得準，所以是偶發的，推測跟 Safari 在鍵盤彈出時捲動可視範圍有關。正式 viewer 要處理（例如輸入框放在不會觸發捲動的位置、或依 `visualViewport` 修正座標），並在真機上驗。
6. agent 呼叫工具期間要一直等使用者登入（這次 2 分多鐘），所以 binding 的 `timeout_ms` 和 agent 端 MCP 的 HTTP 逾時都要拉長。正式版較好的做法是工具先回「已請使用者登入」，登入完成再用新的一輪通知 agent，不讓一次工具呼叫掛好幾分鐘。

## 限制

- **模擬器不是真手機**；WP2 原本要求一支 iOS、一支 Android 真機，沒做。
- agent 跑在本機，不是 Runtime。「URL 不經 agent」由 server 的設計決定，跟 agent 跑哪裡無關；但 Runtime 的 trace 沒有驗。
- 用系統 browser，沒有加 URL 白名單（WP2 #7 已驗過 MANAGED 白名單）。
- 只有一個測試站、一種登入表單；有 CAPTCHA、OTP、跨站 SSO 的網站沒測。

## 費用與清理

- AgentCore Browser：系統 browser 5 個 session（主流程 130、179 秒；逾時 302、270 秒；一次 `goto` 逾時就失敗的 31 秒），共約 912 秒，以 WP6 實測的每 browser-hour 約 $0.09 估約 **$0.02**（系統 browser 沒有 `USAGE_LOGS` 投遞）。
- Haiku 4.5：5 次對話，各 2 輪，量很小（未量 token）。
- `transcript_timeout.json` 是最後一次逾時情境；中間那次被 HephAgora 先判逾時、以及帶出 `_meta.server` 的那次，紀錄被後來的執行覆蓋，內容記在上方「發現」。
- 清理：見 WP2 回填。
