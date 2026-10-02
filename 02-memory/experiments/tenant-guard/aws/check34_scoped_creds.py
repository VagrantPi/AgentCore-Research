# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""#3、#4：範圍縮小的臨時憑證、VM 自己 AssumeRole。

用法：
  uv run check34_scoped_creds.py setup            建 bucket、users/A|B/note.txt、role /wp/wp5-user-data
  uv run check34_scoped_creds.py scoped           #3：後端發「只限 users/A/*」的憑證，帶進 VM 讀 A、B
  uv run check34_scoped_creds.py self unsafe      #4：trust 信任 execution role，VM 自己 AssumeRole 讀 B
  uv run check34_scoped_creds.py self safe        #4：trust 只信任後端，VM 自己 AssumeRole 應被拒

VM 內執行程式用 InvokeAgentRuntimeCommand，沿用 WP0 的 wp0_min（PUBLIC），在 VM 裡 pip install boto3。
"""
import base64
import pathlib
import secrets
import shlex
import sys
import time
import uuid

from common import ACCOUNT, REGION, TAGS, client, load_state, save_state

HERE = pathlib.Path(__file__).parent
RUNTIME = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:runtime/wp0_min-HsBwOc6VWU"
ROLE_NAME = "wp5-user-data"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/wp/{ROLE_NAME}"
iam, s3 = client("iam"), client("s3")


def setup():
    bucket = load_state().get("bucket") or f"wp5-isolation-{secrets.token_hex(4)}"
    s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in TAGS.items()]})
    for u in "AB":
        s3.put_object(Bucket=bucket, Key=f"users/{u}/note.txt", Body=f"user {u} 的私人資料".encode())
    iam.create_role(RoleName=ROLE_NAME, Path="/wp/", AssumeRolePolicyDocument=(HERE / "iam/trust-backend.json").read_text(),
                    Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()])
    iam.put_role_policy(RoleName=ROLE_NAME, PolicyName="wp5-user-data",
                        PolicyDocument=(HERE / "iam/user-data.json").read_text().replace("BUCKET", bucket))
    save_state(bucket=bucket)
    print("bucket", bucket, "role", ROLE_ARN)


def run_in_vm(mode, env):
    """把 vm_probe.py 送進新的 runtime session 執行，回傳 stdout。"""
    code = base64.b64encode((HERE / "vm_probe.py").read_bytes()).decode()
    exports = " ".join(f"{k}='{v}'" for k, v in env.items())
    cmd = (f"pip install -q --target /tmp/py boto3 >/dev/null 2>&1; echo {code} | base64 -d > /tmp/vm_probe.py && "
           f"{exports} PYTHONPATH=/tmp/py python /tmp/vm_probe.py {mode}")
    sid = f"wp5-check34-{mode}-{uuid.uuid4().hex}"
    # command 不經過 shell（直接拆成 argv 執行），要自己包 sh -c
    resp = client("bedrock-agentcore").invoke_agent_runtime_command(
        agentRuntimeArn=RUNTIME, runtimeSessionId=sid, body={"command": f"sh -c {shlex.quote(cmd)}", "timeout": 300})
    out = []
    for ev in resp["stream"]:
        chunk = ev.get("chunk", {})
        if "contentDelta" in chunk:
            d = chunk["contentDelta"]
            out.append(d.get("stdout") or d.get("stderr") or "")
        elif "contentStop" in chunk:
            out.append(f"\n[exit {chunk['contentStop'].get('exitCode')}]")
        elif ev and "chunk" not in ev:
            out.append(f"\n[stream error] {ev}")
    # 用完立刻停掉，避免閒置 15 分鐘計費
    client("bedrock-agentcore").stop_runtime_session(agentRuntimeArn=RUNTIME, runtimeSessionId=sid)
    return sid, "".join(out)


def set_trust(name):
    iam.update_assume_role_policy(RoleName=ROLE_NAME, PolicyDocument=(HERE / f"iam/{name}").read_text())
    print("trust →", name, "；等 IAM 傳播 15 秒")
    time.sleep(15)


bucket = load_state().get("bucket")
mode = sys.argv[1]
if mode == "setup":
    setup()
elif mode == "scoped":
    policy = (HERE / "iam/session-policy-user.json").read_text().replace("BUCKET", bucket).replace("USER", "A")
    c = client("sts").assume_role(RoleArn=ROLE_ARN, RoleSessionName="wp5-user-a", Policy=policy,
                                  DurationSeconds=900)["Credentials"]
    sid, out = run_in_vm("scoped", {"WP5_BUCKET": bucket, "WP5_AK": c["AccessKeyId"],
                                    "WP5_SK": c["SecretAccessKey"], "WP5_ST": c["SessionToken"]})
    print(sid); print(out)
else:
    set_trust("trust-backend-and-exec-UNSAFE.json" if sys.argv[2] == "unsafe" else "trust-backend.json")
    sid, out = run_in_vm("self", {"WP5_BUCKET": bucket, "WP5_ROLE": ROLE_ARN})
    print(sid); print(out)
