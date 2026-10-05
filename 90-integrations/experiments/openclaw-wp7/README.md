# 實驗：OpenClaw on AgentCore 官方範例實跑（WP7）

> 2026-10-04，東京，帳號 050571774557。結果與判讀見 [WP7 回填](../../../91-work-packages/WP7-openclaw-on-agentcore.md#回填)。

## 部署了什麼

範例：[aws-samples/sample-host-openclaw-on-amazon-bedrock-agentcore](https://github.com/aws-samples/sample-host-openclaw-on-amazon-bedrock-agentcore) @ `b0c427f`（2026-09-28，OpenClaw 2026.9.5）。

本帳號的 IAM 使用者沒有 CloudFormation、DynamoDB、Cognito 權限，範例的 CDK 部署不了，所以**只部署 Runtime 容器**，並用 boto3 直接呼叫 `InvokeAgentRuntime` 取代範例的 Router Lambda。

| 範例的元件 | 這次 |
|---|---|
| VPC：private subnet＋1 個 NAT＋7 個 interface endpoint＋S3 gateway | 照做（`vpc.py`），另加 `bedrock-agentcore` endpoint（WP3 B 半的架構） |
| Runtime（`bridge/` 映像、session storage `/mnt/workspace`、idle 1800 s、最長 8 h） | 照做（`deploy.py`），本機 arm64 build，映像 1.45 GB |
| Bedrock Guardrail | 照 `guardrails_stack.py` 用 boto3 建（不含 KMS） |
| execution role | 照 `agentcore_stack.py`，拿掉 Cognito、KMS、DynamoDB、scheduler |
| Router Lambda、API Gateway、Telegram webhook、DynamoDB、Cognito、Cron、Browser、KMS CMK | **沒有** |

呼叫 payload 照 Router：`{"action":"chat","userId","actorId","channel":"test","message"}`。`channel` 用 `test`，容器就不會自己去打 Telegram。

## 檔案

| 檔案 | 用途 |
|---|---|
| `vpc.py` | 建／拆 VPC：`up`（帶 NAT）→ `drop-nat`（變成無 NAT、無 IGW）→ `drop-ep` → `down` |
| `deploy.py` | 支援資源、push 映像、建 Runtime 與 `USAGE_LOGS` 投遞、切換 bedrock-runtime endpoint 的 private DNS、清理 |
| `wp7.py` | 量測：`first`、`burst`、`restore`、`idle`、`load`、`boundary`，加上 `logs`、`tokens` |
| `metrics.py` | 用 CloudWatch metric 對帳 token 與 guardrail text unit |
| `first.csv`、`burst.csv`、`restore.csv`、`load.csv`、`boundary.jsonl` | 原始結果 |
| `logs_excerpt.txt`、`logs_excerpt_round2.txt` | Runtime log 的關鍵行（log group 已隨清理刪除） |
| `wp7-cost.csv` | 每個 session 的 vCPU-h、GB-h、金額（`usage_cost.py` 於 2026-10-04 算出）；原始 `USAGE_LOGS` 在 [`91-work-packages/evidence/usage-logs/wp0-usage.jsonl.gz`](../../../91-work-packages/evidence/usage-logs/wp0-usage.jsonl.gz) |
| `bedrock_metrics.json`、`export.py` | Sonnet 4.6 token 與 guardrail text unit 的每分鐘指標，以及匯出它的腳本 |
| `infra.json` | 每個資源的 ID 與建立／刪除時間（UTC），endpoint、NAT 的費用就是用它算的；第 1 輪的紀錄在 `round1` 底下 |

## 執行順序

```bash
uv run --with boto3 python vpc.py up
uv run --with boto3 python deploy.py support
docker build --platform linux/arm64 -t wp7-openclaw:local <範例>/bridge
uv run --with boto3 python deploy.py push
uv run --with boto3 python deploy.py runtime          # 先建 USAGE_LOGS 投遞，再開 session
uv run --with boto3 python wp7.py first --users f01,f02,...
uv run --with boto3 python wp7.py burst --n 20
uv run --with boto3 python wp7.py restore --users r01,r02,r03
uv run --with boto3 python wp7.py idle --user i01 --wait 1900
uv run --with boto3 python wp7.py load --users 10 --rounds 10
uv run --with boto3 python wp7.py boundary --user x01 --tag nat --wait-full
uv run --with boto3 python vpc.py drop-nat            # WP7 #6、WP1 #11
uv run --with boto3 python wp7.py first --users n01
uv run --with boto3 python deploy.py bedrock-dns on   # #6b
uv run --with boto3 python vpc.py drop-ep
uv run --with boto3 python deploy.py cleanup
# 補測（第 2 輪，09:19–09:27 UTC）：#6 收緊版設定下驗 exec 連外、S3 匿名外送、#3 檔案可見
uv run --with boto3 python vpc.py archive
uv run --with boto3 python vpc.py up-tight            # 不要和 deploy.py 同時跑，兩者都會寫 infra.json
uv run --with boto3 python deploy.py support && uv run --with boto3 python deploy.py push && uv run --with boto3 python deploy.py runtime
uv run --with boto3 python wp7.py boundary --user x11 --tag r2-exec-nonat --wait-full --prompt "..."
uv run --with boto3 python vpc.py drop-ep
uv run --with boto3 python deploy.py cleanup
uv run --with boto3 python vpc.py down                # 隔天，網卡清掉後
```

## 量測方法的限制

- 呼叫端是台灣的筆電，延遲包含台灣到東京的網路來回。沒有 Telegram → API Gateway → Lambda 那一段，範例 README 的 23 秒、70 秒是從 webhook 算起。
- 「首則回覆」是 `InvokeAgentRuntime` 從送出到拿到回應的時間；「完整 OpenClaw 回覆」是 `status` 回報 `openclawReady` 之後再送一句的時間。
- 回應本身不標示是輕量 agent 還是完整 OpenClaw 回的，要看 log 的 `Routing via lightweight agent` 和 `OpenClaw ready — switching`。
