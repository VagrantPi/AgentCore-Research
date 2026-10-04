# Code Interpreter 網路模式實測腳本

說明見 [code-interpreter-data-agent.md](../../code-interpreter-data-agent.md#網路模式)。

在 Sandbox、Public、VPC 三種模式的 code interpreter 各執行一次（用 `executeCode` 送入整個檔案內容），比較輸出：

- DNS、HTTPS（PyPI、一般網站、同區域與其他區域的 S3、STS、別人的 bucket）
- 憑證來源（環境變數、MMDS 端點、MMDSv2 token、實際讀不讀得到憑證；只檢查存在與否，不印出內容）
- `aws sts get-caller-identity`、`pip download`、磁碟空間、CPU 數、matplotlib 存圖

只用 Python 標準函式庫。

## 執行

```bash
uv run run.py <codeInterpreterId>            # 開 session、送入 probe.py、印結果、關 session
```

## 結果（2026-10-02，東京，[WP3](../../../91-work-packages/WP3-sandbox-egress.md) A 半）

Sandbox、Public 由 A 實跑；VPC 模式由 WP3 B 半補上。兩個 code interpreter 都掛同一個**沒有任何權限**的 execution role（`/wp/wp3-ci-exec`）。

| 項目 | Sandbox | Public |
|---|---|---|
| DNS：pypi.org、example.com | ✗（解析失敗） | ✓ |
| DNS：`*.amazonaws.com`（S3、STS，含其他區域） | ✓ | ✓ |
| HTTPS：pypi.org、example.com | ✗ | ✓ |
| HTTPS：**同區域** S3（`s3.ap-northeast-1`） | **✓**（curl 307、AWS CLI 有回應） | ✓ |
| HTTPS：**其他區域** S3（`s3.us-east-1`、全域端點、us-east-1 的公開 bucket） | ✗（連線逾時） | ✓ |
| HTTPS：STS（區域端點與全域端點） | ✗ | ✓ |
| 同區域任意 bucket 名稱 | 有回應（不存在的 bucket 回 `NoSuchBucket`） | ✓ |
| 環境變數裡的憑證 | 無 | 無 |
| MMDS 不帶 token | 401 | 401 |
| MMDSv2 token | 拿得到 | 拿得到 |
| **用 token 讀 execution role 憑證** | **讀得到** | **讀得到** |
| `pip download` | ✗ | ✓ |
| 預先打包的 wheel：`pip install --no-index` | ✓ | — |
| 磁碟 / CPU | 9.1 GB 可用 / 2 | 9.1 GB 可用 / 2 |
| matplotlib 存圖 | ✓ | ✓ |
| 沙箱裡沒有 `AWS_REGION` | 是 | 是 |

**注意：**

- Sandbox 下 Python 的 DNS 偶爾解析 `s3.ap-northeast-1.amazonaws.com` 失敗（一次 `gaierror`，重測三次都成功）。要在 Sandbox 讀寫 S3 的程式要加重試。
- 沙箱裡沒有設 `AWS_REGION`，AWS CLI 預設打全域端點，在 Sandbox 會連不上；要明確帶 `--region`。
- Sandbox 下連不上的測試要等到逾時，整個 `executeCode` 會超過 boto3 預設的 60 秒讀取逾時，`run.py` 已把讀取逾時調成 600 秒。

## 結果：VPC 模式（2026-10-02，東京，[WP3](../../../91-work-packages/WP3-sandbox-egress.md) B 半）

code interpreter `wp3b_ci_vpc`：private subnet（`apne1-az4`），**不開 NAT、沒有 IGW**，只有 S3 gateway endpoint 和 `bedrock-agentcore` interface endpoint（私有 DNS）；另以 VPC peering 連到放 HephAgora 測試版的 VPC。execution role `/wp/wp3b-ci-exec` 同樣**沒有任何權限**。

| 項目 | VPC（無 NAT） | 對照 Sandbox |
|---|---|---|
| DNS：pypi.org、example.com | ✓（VPC Resolver 解析公網名稱） | ✗ |
| HTTPS：pypi.org、example.com | ✗（逾時） | ✗ |
| HTTPS：**同區域** S3 | ✓（經 gateway endpoint；根目錄 307、匿名讀私有 bucket 403、不存在的 bucket 404） | ✓ |
| HTTPS：其他區域 S3（`s3.us-east-1`、全域端點） | ✗ | ✗ |
| HTTPS：STS | ✗（沒有 STS endpoint） | ✗ |
| `bedrock-agentcore` 端點 | ✓（解析成 VPC 內私有 IP） | — |
| 經 peering 連 HephAgora 私有 IP | ✓（`/health` 200） | ✗（連不到 VPC 內資源） |
| MMDS／MMDSv2／用 token 讀 execution role 憑證 | 401／拿得到／**讀得到** | 同 |
| `aws sts get-caller-identity`、`pip download` | ✗（逾時） | ✗ |
| 磁碟 / CPU | 9.1 GB 可用 / 2 | 同 |

**S3 外送（A 半結論 2）在 VPC 模式擋得住：**

| S3 gateway endpoint 政策 | 沙箱匿名讀「白名單外 bucket 的公開物件」 | VPC 模式 Runtime 冷啟動（要從 ECR 拉映像） |
|---|---|---|
| 預設全開 | 200（讀得到） | 正常 |
| 只允許自家 bucket＋官方文件寫的 ECR 層 bucket `prod-ap-northeast-1-starport-layer-bucket` | **403** | **失敗（502）**：只放行文件寫的這個 bucket，映像拉不下來 |
| 全允許，但 `Deny` 匿名請求（`aws:PrincipalAccount` 為 Null） | **403** | **正常** |

- 外部對照 bucket 是臨時建的（只開放一個測試物件匿名讀取），測完即刪。
- 「拒絕匿名」擋的是 A 半點出的情境（沙箱用不簽章的請求寫入他人開放的 bucket）；用 execution role 簽章的跨帳號請求不在此列，但 role 本身沒有 S3 權限。

**注意：**

- **`probe.py` 在 VPC 模式會誤判同區域 S3 不通**：`try_https` 用 `urlopen`，會跟著 S3 根目錄的 307 轉址到 `aws.amazon.com`（外網）而逾時。實際上 TCP 5 ms、HTTP 307 都正常；判斷 S3 通不通要用不跟轉址的請求。
- VPC 模式的 code interpreter 建立約 5 分鐘（Sandbox／Public 幾乎立即）。第一次在帳號裡建 VPC 模式資源時，AWS 會自動建立服務連結角色 `AWSServiceRoleForBedrockAgentCoreNetwork`。
