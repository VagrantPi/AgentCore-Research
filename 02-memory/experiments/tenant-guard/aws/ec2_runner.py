# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""#8 成本 3 天版：在一台最小的 EC2（t4g.nano）上跑 `cost_day.py 3`，本機不必開著。

用法：
  uv run ec2_runner.py launch    建 bucket、role /wp/wp5-cost-runner、instance profile，開機器
  uv run ec2_runner.py status    機器狀態與 log 最後幾行（log 每 10 分鐘傳到 S3）
  uv run ec2_runner.py fetch     跑完後把機器上的 costDays 合併回本機 state.json，之後跑 cost_report.py
  uv run ec2_runner.py cleanup   刪機器（若還在）、bucket、instance profile、role

機器跑完會自己關機，關機即終止（InstanceInitiatedShutdownBehavior=terminate）。
不開 SSH、沒有 key pair、預設 security group（沒有對外開的 inbound）、強制 IMDSv2。
"""
import base64
import io
import json
import pathlib
import secrets
import sys
import tarfile
import time

from common import TAGS, client, load_state, save_state

HERE = pathlib.Path(__file__).parent
NAME = "wp5-cost-runner"
ACTOR = "wp5-user-cost3d"
TAG_LIST = [{"Key": k, "Value": v} for k, v in TAGS.items()]
st = load_state()
iam, s3, ec2 = client("iam"), client("s3"), client("ec2")


def user_data(bucket):
    """開機腳本：解開打包的程式、裝 uv、背景每 10 分鐘上傳 log、跑 3 天、上傳結果後關機。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in ["common.py", "cost_day.py"]:
            tar.add(HERE / f, arcname=f)
        data = json.dumps({"memoryId": st["memoryId"], "strategies": st["strategies"]}).encode()
        info = tarfile.TarInfo("state.json"); info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    payload = base64.b64encode(buf.getvalue()).decode()
    dest = f"s3://{bucket}/cost3d"
    return f"""#!/bin/bash
exec > /var/log/wp5-userdata.log 2>&1
set -x
export HOME=/root
mkdir -p /opt/wp5 && cd /opt/wp5
echo '{payload}' | base64 -d | tar xz
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
up() {{
  aws s3 cp cost3d.log {dest}/cost3d.log --region ap-northeast-1 --quiet
  aws s3 cp state.json {dest}/state.json --region ap-northeast-1 --quiet
  aws s3 cp /var/log/wp5-userdata.log {dest}/userdata.log --region ap-northeast-1 --quiet
}}
touch cost3d.log
( while true; do up; sleep 600; done ) &
WP5_COST_ACTOR={ACTOR} /usr/local/bin/uv run -q cost_day.py 3 > cost3d.log 2>&1
echo "exit $?" >> cost3d.log
up
shutdown -h now
"""


def launch():
    bucket = st.get("cost3dBucket") or f"wp5-cost3d-{secrets.token_hex(4)}"
    s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"})
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": TAG_LIST})
    iam.create_role(RoleName=NAME, Path="/wp/", Tags=TAG_LIST,
                    AssumeRolePolicyDocument=(HERE / "iam/cost-runner-trust.json").read_text())
    iam.put_role_policy(RoleName=NAME, PolicyName=NAME, PolicyDocument=(HERE / "iam/cost-runner.json").read_text()
                        .replace("MEMORY_ID", st["memoryId"]).replace("BUCKET", bucket))
    iam.create_instance_profile(InstanceProfileName=NAME, Path="/wp/", Tags=TAG_LIST)
    iam.add_role_to_instance_profile(InstanceProfileName=NAME, RoleName=NAME)
    save_state(cost3dBucket=bucket)
    print("bucket", bucket, "role / instance profile", NAME)

    ami = client("ssm").get_parameter(Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64")["Parameter"]["Value"]
    subnet = ec2.describe_subnets(Filters=[{"Name": "default-for-az", "Values": ["true"]}])["Subnets"][0]["SubnetId"]
    for attempt in range(10):   # 新建的 instance profile 要幾秒才能用
        try:
            inst = ec2.run_instances(
                ImageId=ami, InstanceType="t4g.nano", MinCount=1, MaxCount=1,
                IamInstanceProfile={"Name": NAME}, UserData=user_data(bucket),
                InstanceInitiatedShutdownBehavior="terminate",
                MetadataOptions={"HttpTokens": "required"},
                NetworkInterfaces=[{"DeviceIndex": 0, "SubnetId": subnet, "AssociatePublicIpAddress": True}],
                TagSpecifications=[{"ResourceType": t, "Tags": TAG_LIST + [{"Key": "Name", "Value": NAME}]}
                                   for t in ("instance", "volume", "network-interface")],
            )["Instances"][0]
            break
        except ec2.exceptions.ClientError as e:
            if "iamInstanceProfile" not in str(e) and "Invalid IAM Instance Profile" not in str(e):
                raise
            print("instance profile 還沒生效，10 秒後重試")
            time.sleep(10)
    save_state(cost3dInstance=inst["InstanceId"])
    print("instance", inst["InstanceId"], "AMI", ami, "subnet", subnet)


def status():
    if iid := st.get("cost3dInstance"):
        r = ec2.describe_instances(InstanceIds=[iid])["Reservations"]
        print("instance", iid, r[0]["Instances"][0]["State"]["Name"] if r else "已不存在")
    for key in ["cost3d.log", "userdata.log"]:
        try:
            body = s3.get_object(Bucket=st["cost3dBucket"], Key=f"cost3d/{key}")["Body"].read().decode()
            print(f"--- {key}（最後 8 行）\n" + "\n".join(body.splitlines()[-8:]))
        except s3.exceptions.NoSuchKey:
            print(f"--- {key}：還沒上傳")


def fetch():
    remote = json.loads(s3.get_object(Bucket=st["cost3dBucket"], Key="cost3d/state.json")["Body"].read())
    save_state(costDays=remote.get("costDays", []), costActor=remote.get("costActor", ACTOR))
    print("costDays", len(remote.get("costDays", [])), "天，actor", remote.get("costActor"))


def cleanup():
    if iid := st.get("cost3dInstance"):
        try:
            ec2.terminate_instances(InstanceIds=[iid])
            print("terminate", iid)
        except ec2.exceptions.ClientError as e:
            if "InvalidInstanceID.NotFound" not in str(e):
                raise
            print(iid, "已自行終止")   # 跑完自己關機即終止，正常情況
    if bucket := st.get("cost3dBucket"):
        assert bucket.startswith("wp5-")
        for o in s3.list_objects_v2(Bucket=bucket).get("Contents", []):
            s3.delete_object(Bucket=bucket, Key=o["Key"])
        s3.delete_bucket(Bucket=bucket)
        print("刪除 bucket", bucket)
    iam.remove_role_from_instance_profile(InstanceProfileName=NAME, RoleName=NAME)
    iam.delete_instance_profile(InstanceProfileName=NAME)
    iam.delete_role_policy(RoleName=NAME, PolicyName=NAME)
    iam.delete_role(RoleName=NAME)
    print("刪除 instance profile 與 role", NAME)


{"launch": launch, "status": status, "fetch": fetch, "cleanup": cleanup}[sys.argv[1]]()
