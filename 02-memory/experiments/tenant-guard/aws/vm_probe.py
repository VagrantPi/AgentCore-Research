"""在 Runtime 的 VM 裡執行（由 check34_scoped_creds.py 透過 InvokeAgentRuntimeCommand 送進去）。

argv[1]：
  scoped  用環境變數 WP5_AK/WP5_SK/WP5_ST（後端發的範圍縮小憑證）讀 users/A、users/B
  self    用 VM 自己的憑證（execution role）AssumeRole ROLE_ARN（不帶 session policy），再讀 users/A、users/B
"""
import os
import sys

import boto3

REGION, BUCKET, ROLE = "ap-northeast-1", os.environ["WP5_BUCKET"], os.environ.get("WP5_ROLE")


def read_both(s3):
    for user in "AB":
        try:
            body = s3.get_object(Bucket=BUCKET, Key=f"users/{user}/note.txt")["Body"].read().decode()
            print(f"read users/{user}: OK {body!r}")
        except Exception as e:
            print(f"read users/{user}: DENIED {type(e).__name__}: {str(e)[:160]}")


if sys.argv[1] == "scoped":
    s3 = boto3.client("s3", region_name=REGION, aws_access_key_id=os.environ["WP5_AK"],
                      aws_secret_access_key=os.environ["WP5_SK"], aws_session_token=os.environ["WP5_ST"])
    read_both(s3)
else:
    me = boto3.client("sts", region_name=REGION).get_caller_identity()["Arn"]
    print("VM identity:", me)
    try:
        c = boto3.client("sts", region_name=REGION).assume_role(RoleArn=ROLE, RoleSessionName="wp5-vm-self")["Credentials"]
        print("AssumeRole: OK")
    except Exception as e:
        print(f"AssumeRole: DENIED {type(e).__name__}: {str(e)[:200]}")
        sys.exit(0)
    read_both(boto3.client("s3", region_name=REGION, aws_access_key_id=c["AccessKeyId"],
                           aws_secret_access_key=c["SecretAccessKey"], aws_session_token=c["SessionToken"]))
