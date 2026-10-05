# 技能授權用 Cedar 寫：和手寫版比較

WP6 第 3 層的實測（[WP6 回填](../../../91-work-packages/WP6-oss-alternatives.md#第-3-層工具閘道與授權)）。WP2 在自家 MCP server（HephAgora）手寫的「買了才能用」約 70 行（[`skill-gating`](../skill-gating/README.md)）。這裡用開源 Cedar（`@cedar-policy/cedar-wasm` 4.13.0）寫同一條規則，看能省多少、多了什麼。

## 怎麼跑

```bash
npm i
node check.cjs
```

## 結果（2026-10-04，本機 Node 24）

```
cedar 4.13.0
validate success []
tools/list A [ 'todo_add', 'todo_list' ]
tools/list B [ 'todo_add', 'todo_list', 'flight_search' ]
A tools/call flight_search deny
statefulIsAuthorized µs/次 83.4
OK
```

- **授權本體 25 行**（不含註解與空行）：schema 4 行、policy 2 行、DB 資料轉成 Cedar entities、判斷函式、`tools/list` 過濾。
- **省不掉的部分**：查購買紀錄與技能表、回 403／429、每小時限流、寫調用帳本。手寫版的 70 行大部分是這些，換成 Cedar 只少掉「判斷買了沒」那幾行，還多一層「DB → entities」的轉換和一個 WASM 相依套件。
- **多得到的**：`validate()` 依 schema 做型別檢查；規則和程式碼分開。要證明「新規則沒有放寬權限」得用 Rust 的 `cedar-policy-symcc`（要裝 cvc5），npm 版沒有這個介面。
- **延遲**：`statefulIsAuthorized`（policy、schema 先 preparse）每次約 83 µs；每次都重新解析的 `isAuthorized` 約 300 µs（第 3 層調研時另測）。論文的 4–5 µs 是原生 Rust，不能直接引用。對一次 MCP 呼叫（WP2 實測 p50 21 ms）都可以忽略。
- 列表過濾用逐工具判斷。`isAuthorizedPartial` 也有匯出，但上游把 partial evaluation 標為實驗功能，沒用。
