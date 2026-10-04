"""WP7 / WP1 #11 共用的 VPC：先照 OpenClaw 範例帶 NAT，之後拔掉 NAT 變成 WP3 B 半的「無 NAT、無 IGW」。

子命令：
  up          建 VPC、2 個 private subnet（apne1-az4、az1）、public subnet＋IGW＋NAT、S3 gateway 與 interface endpoint
  drop-nat    刪 NAT、EIP、預設路由、IGW、public subnet
  drop-ep     刪全部 endpoint 與 endpoint 安全群組（停止計費）
  down        刪 private subnet、Runtime 安全群組、路由表、VPC（網卡清掉後才刪得掉）
  archive     把第 1 輪已刪除的資源紀錄移到 round1（補測前用）
  up-tight    補測：在無 NAT 的 VPC 建 #6 收緊版的 endpoint（bedrock-runtime 開 private DNS、加 STS）
  show        印出 infra.json

每個資源的 ID 與建立／刪除時間（UTC）記在 infra.json，計費用「小時數 × 官網價」。
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

REGION = "ap-northeast-1"
HERE = Path(__file__).parent
STATE = HERE / "infra.json"
TAGS = [{"Key": "wp", "Value": "WP7"}, {"Key": "owner", "Value": "kais"}, {"Key": "project", "Value": "hyfai"}]
CIDR = "10.70.0.0/16"
PRIVATE = [("apne1-az4", "10.70.1.0/24"), ("apne1-az1", "10.70.2.0/24")]
PUBLIC = ("apne1-az4", "10.70.0.0/24")
# 範例 vpc_stack.py 的 interface endpoint，加上 WP3 B 半用的 bedrock-agentcore
INTERFACE = ["bedrock-runtime", "ssm", "ecr.api", "ecr.dkr", "secretsmanager", "logs", "monitoring", "bedrock-agentcore"]
# 範例把 bedrock-runtime 的 private DNS 關掉，讓 global.* inference profile 走 NAT
NO_PRIVATE_DNS = {"bedrock-runtime"}
# WP3 B 半：只放行 ECR 層 bucket 會拉不到映像，改用全允許＋拒絕匿名請求
S3_POLICY = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Principal": "*", "Action": "*", "Resource": "*"},
    {"Effect": "Deny", "Principal": "*", "Action": "*", "Resource": "*",
     "Condition": {"Null": {"aws:PrincipalArn": "true"}}},
]}

ec2 = boto3.client("ec2", region_name=REGION)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(s):
    STATE.write_text(json.dumps(s, indent=2))


def spec(kind, name):
    return [{"ResourceType": kind, "Tags": TAGS + [{"Key": "Name", "Value": name}]}]


def rec(s, key, rid, **extra):
    s[key] = {"id": rid, "created": now(), **extra}
    save(s)
    print(f"{key}: {rid}")


def up():
    s = load()
    zones = {z["ZoneId"]: z["ZoneName"] for z in ec2.describe_availability_zones()["AvailabilityZones"]}
    if "vpc" not in s:
        v = ec2.create_vpc(CidrBlock=CIDR, TagSpecifications=spec("vpc", "wp7-vpc"))["Vpc"]["VpcId"]
        ec2.get_waiter("vpc_available").wait(VpcIds=[v])
        ec2.modify_vpc_attribute(VpcId=v, EnableDnsHostnames={"Value": True})
        ec2.modify_vpc_attribute(VpcId=v, EnableDnsSupport={"Value": True})
        rec(s, "vpc", v)
    vpc = s["vpc"]["id"]

    for i, (az, cidr) in enumerate(PRIVATE):
        key = f"private_subnet_{i}"
        if key not in s:
            sid = ec2.create_subnet(VpcId=vpc, CidrBlock=cidr, AvailabilityZone=zones[az],
                                    TagSpecifications=spec("subnet", f"wp7-private-{az}"))["Subnet"]["SubnetId"]
            rec(s, key, sid, az=az)
    if "private_rt" not in s:
        rt = ec2.create_route_table(VpcId=vpc, TagSpecifications=spec("route-table", "wp7-private-rt"))["RouteTable"]["RouteTableId"]
        for i in range(len(PRIVATE)):
            ec2.associate_route_table(RouteTableId=rt, SubnetId=s[f"private_subnet_{i}"]["id"])
        rec(s, "private_rt", rt)

    if "public_subnet" not in s:
        sid = ec2.create_subnet(VpcId=vpc, CidrBlock=PUBLIC[1], AvailabilityZone=zones[PUBLIC[0]],
                                TagSpecifications=spec("subnet", "wp7-public"))["Subnet"]["SubnetId"]
        rec(s, "public_subnet", sid)
    if "igw" not in s:
        igw = ec2.create_internet_gateway(TagSpecifications=spec("internet-gateway", "wp7-igw"))["InternetGateway"]["InternetGatewayId"]
        ec2.attach_internet_gateway(InternetGatewayId=igw, VpcId=vpc)
        rec(s, "igw", igw)
    if "public_rt" not in s:
        rt = ec2.create_route_table(VpcId=vpc, TagSpecifications=spec("route-table", "wp7-public-rt"))["RouteTable"]["RouteTableId"]
        ec2.create_route(RouteTableId=rt, DestinationCidrBlock="0.0.0.0/0", GatewayId=s["igw"]["id"])
        assoc = ec2.associate_route_table(RouteTableId=rt, SubnetId=s["public_subnet"]["id"])["AssociationId"]
        rec(s, "public_rt", rt, assoc=assoc)
    if "eip" not in s:
        e = ec2.allocate_address(Domain="vpc", TagSpecifications=spec("elastic-ip", "wp7-nat-eip"))["AllocationId"]
        rec(s, "eip", e)
    if "nat" not in s:
        n = ec2.create_nat_gateway(SubnetId=s["public_subnet"]["id"], AllocationId=s["eip"]["id"],
                                   TagSpecifications=spec("natgateway", "wp7-nat"))["NatGateway"]["NatGatewayId"]
        rec(s, "nat", n)
        ec2.get_waiter("nat_gateway_available").wait(NatGatewayIds=[n])
        ec2.create_route(RouteTableId=s["private_rt"]["id"], DestinationCidrBlock="0.0.0.0/0", NatGatewayId=n)
        print("nat available, default route added")

    if "endpoint_sg" not in s:
        g = ec2.create_security_group(GroupName="wp7-endpoint-sg", Description="WP7 VPC endpoints: 443 from VPC",
                                      VpcId=vpc, TagSpecifications=spec("security-group", "wp7-endpoint-sg"))["GroupId"]
        ec2.authorize_security_group_ingress(GroupId=g, IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": CIDR}]}])
        rec(s, "endpoint_sg", g)
    if "runtime_sg" not in s:
        # 範例：容器的安全群組只允許對外 443
        g = ec2.create_security_group(GroupName="wp7-runtime-sg", Description="WP7 AgentCore runtime: egress 443 only",
                                      VpcId=vpc, TagSpecifications=spec("security-group", "wp7-runtime-sg"))["GroupId"]
        ec2.revoke_security_group_egress(GroupId=g, IpPermissions=[
            {"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}])
        ec2.authorize_security_group_egress(GroupId=g, IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}])
        rec(s, "runtime_sg", g)

    endpoints(s, INTERFACE, NO_PRIVATE_DNS)


def endpoints(s, services, no_private_dns):
    vpc = s["vpc"]["id"]
    subnets = [s[f"private_subnet_{i}"]["id"] for i in range(len(PRIVATE))]
    if "ep_s3" not in s:
        e = ec2.create_vpc_endpoint(VpcId=vpc, ServiceName=f"com.amazonaws.{REGION}.s3", VpcEndpointType="Gateway",
                                    RouteTableIds=[s["private_rt"]["id"]], PolicyDocument=json.dumps(S3_POLICY),
                                    TagSpecifications=spec("vpc-endpoint", "wp7-s3"))["VpcEndpoint"]["VpcEndpointId"]
        rec(s, "ep_s3", e)
    for svc in services:
        key = f"ep_{svc}"
        if key not in s:
            e = ec2.create_vpc_endpoint(VpcId=vpc, ServiceName=f"com.amazonaws.{REGION}.{svc}", VpcEndpointType="Interface",
                                        SubnetIds=subnets, SecurityGroupIds=[s["endpoint_sg"]["id"]],
                                        PrivateDnsEnabled=svc not in no_private_dns,
                                        TagSpecifications=spec("vpc-endpoint", f"wp7-{svc}"))["VpcEndpoint"]["VpcEndpointId"]
            rec(s, key, e, azs=len(subnets))
    print("subnets:", ",".join(subnets), "runtime_sg:", s["runtime_sg"]["id"])


# #6 收緊後的最小組合：無 NAT，bedrock-runtime 開 private DNS，加 STS（容器建 scoped 憑證要用）
TIGHT = ["bedrock-runtime", "sts", "secretsmanager", "ecr.api", "ecr.dkr", "logs"]


def up_tight():
    """補測（第 2 輪）：在已拔掉 NAT 的 VPC 重建收緊版 endpoint。第 1 輪的紀錄先用 archive 移到 round1。"""
    s = load()
    if "endpoint_sg" not in s:
        g = ec2.create_security_group(GroupName="wp7-endpoint-sg", Description="WP7 VPC endpoints: 443 from VPC",
                                      VpcId=s["vpc"]["id"], TagSpecifications=spec("security-group", "wp7-endpoint-sg"))["GroupId"]
        ec2.authorize_security_group_ingress(GroupId=g, IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": CIDR}]}])
        rec(s, "endpoint_sg", g)
    endpoints(s, TIGHT, set())
    ids = [s[k]["id"] for k in s if k.startswith("ep_") and k != "ep_s3"]
    while any(e["State"] != "available" for e in ec2.describe_vpc_endpoints(VpcEndpointIds=ids)["VpcEndpoints"]):
        time.sleep(10)
    print("all interface endpoints available")


def archive():
    """把已刪除、第 2 輪要重建的資源紀錄移到 round1，保留第 1 輪的時間供計費。"""
    s = load()
    r1 = s.setdefault("round1", {})
    for k in [k for k, v in s.items() if k != "round1" and isinstance(v, dict) and "deleted" in v
              and (k.startswith("ep_") or k in ("endpoint_sg", "bucket", "secret", "guardrail", "role", "ecr", "runtime", "usage_delivery"))]:
        r1[k] = s.pop(k)
    save(s)
    print("archived:", sorted(r1))


def mark_deleted(s, key):
    s[key]["deleted"] = now()
    save(s)
    print(f"deleted {key}: {s[key]['id']}")


def drop_nat():
    s = load()
    if "deleted" not in s["nat"]:
        ec2.delete_route(RouteTableId=s["private_rt"]["id"], DestinationCidrBlock="0.0.0.0/0")
        ec2.delete_nat_gateway(NatGatewayId=s["nat"]["id"])
        ec2.get_waiter("nat_gateway_deleted").wait(NatGatewayIds=[s["nat"]["id"]])
        mark_deleted(s, "nat")
    if "deleted" not in s["eip"]:
        ec2.release_address(AllocationId=s["eip"]["id"])
        mark_deleted(s, "eip")
    if "deleted" not in s["public_rt"]:
        ec2.disassociate_route_table(AssociationId=s["public_rt"]["assoc"])
        ec2.delete_route_table(RouteTableId=s["public_rt"]["id"])
        mark_deleted(s, "public_rt")
    if "deleted" not in s["igw"]:
        ec2.detach_internet_gateway(InternetGatewayId=s["igw"]["id"], VpcId=s["vpc"]["id"])
        ec2.delete_internet_gateway(InternetGatewayId=s["igw"]["id"])
        mark_deleted(s, "igw")
    if "deleted" not in s["public_subnet"]:
        ec2.delete_subnet(SubnetId=s["public_subnet"]["id"])
        mark_deleted(s, "public_subnet")


def drop_ep():
    s = load()
    keys = [k for k in s if k.startswith("ep_") and "deleted" not in s[k]]
    if keys:
        ec2.delete_vpc_endpoints(VpcEndpointIds=[s[k]["id"] for k in keys])
        for k in keys:
            mark_deleted(s, k)
    while ec2.describe_vpc_endpoints(Filters=[{"Name": "vpc-id", "Values": [s["vpc"]["id"]]},
                                              {"Name": "vpc-endpoint-state", "Values": ["deleting", "available"]}])["VpcEndpoints"]:
        time.sleep(10)
    if "deleted" not in s["endpoint_sg"]:
        ec2.delete_security_group(GroupId=s["endpoint_sg"]["id"])
        mark_deleted(s, "endpoint_sg")


def down():
    s = load()
    for key in ["private_subnet_0", "private_subnet_1", "runtime_sg", "private_rt", "vpc"]:
        if "deleted" in s[key]:
            continue
        rid = s[key]["id"]
        if key.startswith("private_subnet"):
            ec2.delete_subnet(SubnetId=rid)
        elif key == "runtime_sg":
            ec2.delete_security_group(GroupId=rid)
        elif key == "private_rt":
            ec2.delete_route_table(RouteTableId=rid)
        else:
            ec2.delete_vpc(VpcId=rid)
        mark_deleted(s, key)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    {"up": up, "drop-nat": drop_nat, "drop-ep": drop_ep, "down": down, "archive": archive, "up-tight": up_tight,
     "show": lambda: print(json.dumps(load(), indent=2))}[cmd]()
