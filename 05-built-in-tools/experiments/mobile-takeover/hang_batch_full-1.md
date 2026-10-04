# 完整工作負載第 1 批（2026-10-04 約 22:04–22:25 台灣時間）

原始 `hang_batch.log` 被第 2 批開跑時覆蓋（批次腳本開頭會清空 log，我沒先另存）。以下是當時在終端機讀到並記下的結果。

條件：`lv_hang.py --full --browser-id wp6_viewport-M5wOn5rphr`，4 條並行（8771、8772 開 Live View；8773、8774 不開），各 3 次。看門狗門檻當時是 20 秒、觸發後主程式就提前結束（之後改成 45 秒、等證據寫完）。

| 次 | 8771（Live View） | 8772（Live View） | 8773（不開） | 8774（不開） |
|---|---|---|---|---|
| #1 | OK | OK | OK | OK |
| #2 | 「HANG」 | 「HANG」 | 「HANG」 | 「HANG」 |
| #3 | OK | OK | OK | OK |

- #2 的四個「HANG」都**不是無限卡死**：都停在 CDP 連線前，`cdp connected` 分別在 21.4、21.5、21.2、21.0 秒才出現，看門狗在 20 秒就觸發。session：`01M43KXVQ38BF6GCQ468423XAW`、`01M43KXVNZP2QK8YGEJYG2227V`、`01M43KXVPV9499AR81W3A740FR`、`01M43KXVNJY1E1JV5CGBFP1MJH`。
- 因為主程式提前結束，看門狗的證據沒寫出來，`hang/` 下這 4 個資料夾是空的。
- 同一時間開的 4 個 session（含 2 個沒開 Live View）**一起**慢到 21 秒；三批合計 34 次的 CDP 連線時間中位數 1.4 秒、#3 四條都是 2.9 秒。→ 慢的是 AgentCore 自動化端點在那個時間點，與 Live View 無關。
