# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""清掉 WP5 建的資源。用法：uv run cleanup.py iam-s3 | memory

只刪 state.json 記錄的、名稱以 wp5 開頭的資源。
"""
import sys

from common import client, load_state

st = load_state()
if sys.argv[1] == "iam-s3":
    iam = client("iam")
    for role in ["wp5-mem-user-a", "wp5-mem-user-b", "wp5-user-data"]:
        for p in iam.list_role_policies(RoleName=role)["PolicyNames"]:
            iam.delete_role_policy(RoleName=role, PolicyName=p)
        iam.delete_role(RoleName=role)
        print("刪除 role", role)
    bucket = st["bucket"]
    assert bucket.startswith("wp5-")
    s3 = client("s3")
    for o in s3.list_objects_v2(Bucket=bucket).get("Contents", []):
        s3.delete_object(Bucket=bucket, Key=o["Key"])
    s3.delete_bucket(Bucket=bucket)
    print("刪除 bucket", bucket)
elif sys.argv[1] == "memory":
    assert st["memoryId"].startswith("wp5_")
    client("bedrock-agentcore-control").delete_memory(memoryId=st["memoryId"])
    print("刪除 memory", st["memoryId"])
