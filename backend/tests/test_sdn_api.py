"""SDN/VPC API 测试（v3.0 sdn-vpc-model-and-foundation）

覆盖：租户 CRUD（5 端点） + VPC CRUD（3 端点） + 编号分配器。
"""
import pytest

from app.utils.sdn_allocator import SdnAllocator, validate_cidr


# ======================== 租户 CRUD ========================

def test_create_tenant_success(client, db):
    """POST /api/sdn/tenants 创建成功，自动分配 RD/RT/L3VNI。"""
    resp = client.post("/api/sdn/tenants", json={"name": "t1", "description": "first tenant"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    t = data["data"]
    assert t["name"] == "t1"
    assert t["rd"] == "100:1"
    assert t["import_rt"] == "100:1"
    assert t["export_rt"] == "100:1"
    assert t["l3_vni"] >= 10000  # 避开前 1000
    assert t["auto_assigned"] is True
    assert t["vpc_count"] == 0


def test_create_tenant_duplicate_name(client, db):
    """POST /api/sdn/tenants 同名创建返回 409 + sdn.tenant_name_exists。"""
    client.post("/api/sdn/tenants", json={"name": "dup"})
    resp = client.post("/api/sdn/tenants", json={"name": "dup"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.tenant_name_exists"
    assert "dup" in data["error"]


def test_get_tenants_empty(client, db):
    """GET /api/sdn/tenants 空列表。"""
    resp = client.get("/api/sdn/tenants")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 0
    assert data["data"]["tenants"] == []


def test_get_tenants_with_data(client, db):
    """GET /api/sdn/tenants 含 2 个租户。"""
    client.post("/api/sdn/tenants", json={"name": "t1"})
    client.post("/api/sdn/tenants", json={"name": "t2"})
    resp = client.get("/api/sdn/tenants")
    data = resp.json()
    assert data["data"]["total"] == 2
    assert len(data["data"]["tenants"]) == 2


def test_get_tenant_by_id(client, db):
    """GET /api/sdn/tenants/{id} 存在。"""
    create = client.post("/api/sdn/tenants", json={"name": "t1"}).json()["data"]
    resp = client.get(f"/api/sdn/tenants/{create['id']}")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["name"] == "t1"


def test_get_tenant_not_found(client, db):
    """GET /api/sdn/tenants/999 不存在 → sdn.tenant_not_found。"""
    resp = client.get("/api/sdn/tenants/999")
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.tenant_not_found"


# ======================== VPC CRUD ========================

def test_create_vpc_success(client, db):
    """POST /api/sdn/vpcs 创建成功，自动分配 VNI/Vsi-interface/VLAN。"""
    tenant = client.post("/api/sdn/tenants", json={"name": "t1"}).json()["data"]
    resp = client.post(
        "/api/sdn/vpcs",
        json={"name": "vpc-1", "tenant_id": tenant["id"], "cidr": "192.168.10.0/24"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    v = data["data"]
    assert v["name"] == "vpc-1"
    assert v["tenant_id"] == tenant["id"]
    assert v["tenant_name"] == "t1"
    assert v["cidr"] == "192.168.10.0/24"
    assert v["vni"] >= 20000  # L2VNI_START
    assert v["vsi_interface"] >= 1000  # VSI_IF_START
    assert v["vlan_id"] >= 2000  # VLAN_START
    # v3.0 ADR-103: vsi_name 改为 vpc{id:04d}，第一个 vpc id=1 → vpc0001
    assert v["vsi_name"] == "vpc0001"
    assert v["status"] == "pending"


def test_create_vpc_default_gateway_ip(client, db):
    """创建 VPC 不传 gateway_ip，验证自动取 CIDR 最后一个可用地址。"""
    tenant = client.post("/api/sdn/tenants", json={"name": "t1"}).json()["data"]
    resp = client.post(
        "/api/sdn/vpcs",
        json={"name": "vpc-1", "tenant_id": tenant["id"], "cidr": "192.168.10.0/24"},
    )
    data = resp.json()
    assert data["data"]["gateway_ip"] == "192.168.10.254"


def test_create_vpc_tenant_not_found(client, db):
    """创建 VPC 时 tenant_id 不存在 → sdn.vpc_tenant_not_found。"""
    resp = client.post(
        "/api/sdn/vpcs",
        json={"name": "vpc-1", "tenant_id": 999, "cidr": "192.168.10.0/24"},
    )
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.vpc_tenant_not_found"


def test_create_vpc_invalid_cidr_format(client, db):
    """CIDR 格式非法 → 422。"""
    tenant = client.post("/api/sdn/tenants", json={"name": "t1"}).json()["data"]
    resp = client.post(
        "/api/sdn/vpcs",
        json={"name": "vpc-1", "tenant_id": tenant["id"], "cidr": "bad"},
    )
    assert resp.status_code == 422  # pydantic validation


def test_create_vpc_invalid_cidr_range(client, db):
    """CIDR 前缀越界（/7）→ 422。"""
    tenant = client.post("/api/sdn/tenants", json={"name": "t1"}).json()["data"]
    resp = client.post(
        "/api/sdn/vpcs",
        json={"name": "vpc-1", "tenant_id": tenant["id"], "cidr": "10.0.0.0/7"},
    )
    assert resp.status_code == 422


def test_get_vpcs_empty(client, db):
    """GET /api/sdn/vpcs 空列表。"""
    resp = client.get("/api/sdn/vpcs")
    data = resp.json()
    assert data["data"]["total"] == 0


def test_get_vpcs_by_tenant(client, db):
    """GET /api/sdn/vpcs?tenant_id=1 按租户过滤。"""
    t1 = client.post("/api/sdn/tenants", json={"name": "t1"}).json()["data"]
    t2 = client.post("/api/sdn/tenants", json={"name": "t2"}).json()["data"]
    client.post("/api/sdn/vpcs", json={"name": "vpc-1", "tenant_id": t1["id"], "cidr": "192.168.10.0/24"})
    client.post("/api/sdn/vpcs", json={"name": "vpc-2", "tenant_id": t2["id"], "cidr": "192.168.20.0/24"})

    resp = client.get(f"/api/sdn/vpcs?tenant_id={t1['id']}")
    data = resp.json()
    assert data["data"]["total"] == 1
    assert data["data"]["vpcs"][0]["name"] == "vpc-1"


def test_get_vpc_by_id(client, db):
    """GET /api/sdn/vpcs/{id} 存在。"""
    tenant = client.post("/api/sdn/tenants", json={"name": "t1"}).json()["data"]
    vpc = client.post(
        "/api/sdn/vpcs",
        json={"name": "vpc-1", "tenant_id": tenant["id"], "cidr": "192.168.10.0/24"},
    ).json()["data"]
    resp = client.get(f"/api/sdn/vpcs/{vpc['id']}")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["name"] == "vpc-1"
    assert data["data"]["tenant_name"] == "t1"


def test_get_vpc_not_found(client, db):
    """GET /api/sdn/vpcs/999 → sdn.vpc_not_found。"""
    resp = client.get("/api/sdn/vpcs/999")
    data = resp.json()
    assert data["error_key"] == "sdn.vpc_not_found"


# ======================== 编号分配器 ========================

def test_allocator_reserved_range(client, db):
    """编号避开前 1000 号段。"""
    tenant = client.post("/api/sdn/tenants", json={"name": "t1"}).json()["data"]
    assert tenant["l3_vni"] >= 10000

    vpc = client.post(
        "/api/sdn/vpcs",
        json={"name": "vpc-1", "tenant_id": tenant["id"], "cidr": "192.168.10.0/24"},
    ).json()["data"]
    assert vpc["vni"] >= 20000
    assert vpc["vsi_interface"] >= 1000
    assert vpc["vlan_id"] >= 2000


def test_allocator_increment(client, db):
    """连续创建 3 个租户，RD 递增。"""
    t1 = client.post("/api/sdn/tenants", json={"name": "t1"}).json()["data"]
    t2 = client.post("/api/sdn/tenants", json={"name": "t2"}).json()["data"]
    t3 = client.post("/api/sdn/tenants", json={"name": "t3"}).json()["data"]
    assert t1["rd"] == "100:1"
    assert t2["rd"] == "100:2"
    assert t3["rd"] == "100:3"
    assert t1["l3_vni"] < t2["l3_vni"] < t3["l3_vni"]


def test_allocator_static_methods():
    """SdnAllocator 静态方法直接验证。"""
    # RD 派生
    assert SdnAllocator.allocate_rd(1) == "100:1"
    assert SdnAllocator.allocate_rd(42) == "100:42"
    # RT 派生
    assert SdnAllocator.allocate_rt(1) == ("100:1", "100:1")
    # gateway_ip 推导
    assert SdnAllocator.derive_gateway_ip("192.168.10.0/24") == "192.168.10.254"
    assert SdnAllocator.derive_gateway_ip("10.0.0.0/8") == "10.255.255.254"
    # gateway_mac 推导 (v3.0 T6: H3C V7 mac-address H-H-H 格式 = 3 组 4 hex)
    # vni=20000 → 0x4E20 → 001a-2b00-4e20
    assert SdnAllocator.derive_gateway_mac(20000) == "001a-2b00-4e20"
    # vni=20001 → 001a-2b00-4e21
    assert SdnAllocator.derive_gateway_mac(20001) == "001a-2b00-4e21"
    # VSI 名称 (ADR-103 vpc{id:04d})
    assert SdnAllocator.build_vsi_name(1) == "vpc0001"
    assert SdnAllocator.build_vsi_name(123) == "vpc0123"
    # CIDR 校验
    assert validate_cidr("192.168.10.0/24") is None
    assert validate_cidr("192.168.10.0/7") is not None
    assert validate_cidr("192.168.10.0/31") is not None
    assert validate_cidr("not-a-cidr") is not None


def test_delete_tenant_cascades_vpcs(client, db):
    """DELETE 租户级联清理其下 VPC。"""
    tenant = client.post("/api/sdn/tenants", json={"name": "t1"}).json()["data"]
    client.post(
        "/api/sdn/vpcs",
        json={"name": "vpc-1", "tenant_id": tenant["id"], "cidr": "192.168.10.0/24"},
    )
    assert client.get(f"/api/sdn/vpcs?tenant_id={tenant['id']}").json()["data"]["total"] == 1

    # 删除租户
    del_resp = client.delete(f"/api/sdn/tenants/{tenant['id']}")
    assert del_resp.json()["success"] is True

    # VPC 也被清理
    assert client.get(f"/api/sdn/vpcs?tenant_id={tenant['id']}").json()["data"]["total"] == 0