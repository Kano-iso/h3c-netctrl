"""VPCConfigPlanner 单元测试（v3.0 sdn-vpc-device-templates Task 7）

10 用例覆盖:
- plan_vpc_create 14 条命令 + dry_run
- plan_vpc_delete 2 条
- plan_port_bind 2 模式 (service_instance / access_vlan)
- plan_port_bind mode=auto 决策
- plan_port_unbind 兼容 2 种模式
- serialize/deserialize roundtrip
- .2/.3 现状回推 (VNI=10, RD=1:1)
"""

from types import SimpleNamespace

import pytest

from app.services.sdn_device_adapter import H3cV7Adapter
from app.services.vpc_config_planner import VPCConfigPlanner


@pytest.fixture
def adapter():
    return H3cV7Adapter()


@pytest.fixture
def planner(adapter):
    return VPCConfigPlanner(adapter)


@pytest.fixture
def vpc():
    """标准测试 VPC"""
    return SimpleNamespace(
        id=1,
        vni=20000,
        cidr="10.0.1.0/24",
        gateway_ip="10.0.1.1",
        gateway_mac="00-00-00-00-4e20-01",
        vsi_interface=1,
    )


@pytest.fixture
def tenant():
    return SimpleNamespace(rd="1:1", l3_vni=10000)


# ======================== plan_vpc_create ========================

def test_plan_vpc_create_returns_14_commands(planner, vpc, tenant):
    """plan_vpc_create 返 14 条命令 (与 design.md 一致)"""
    cmds = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    assert len(cmds) == 14
    assert all(c["mode"] == "configure" for c in cmds)


def test_plan_vpc_create_contains_vsi_and_vxlan(planner, vpc, tenant):
    """plan_vpc_create 含 vsi/vxlan/evpn/vpn-instance/vsi-interface 关键字"""
    cmds = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    text = "\n".join(c["command"] for c in cmds)
    assert "vsi vpc0001" in text
    assert "vxlan 20000" in text
    assert "evpn encapsulation vxlan" in text
    assert "ip vpn-instance l3vpn" in text
    assert "interface Vsi-interface1" in text
    assert "vxlan tunnel mac-learning disable" in text


def test_plan_vpc_create_dry_run_does_not_persist(planner, vpc, tenant):
    """dry_run=True 时不写 SdnDeployment (planner 本身不写 DB, 由调用方决定)"""
    cmds = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    assert len(cmds) == 14
    # dry_run=True/False 当前实现完全等价 (planner 纯计算)
    cmds2 = planner.plan_vpc_create(vpc, tenant, dry_run=False)
    assert cmds == cmds2


# ======================== plan_vpc_delete ========================

def test_plan_vpc_delete_returns_2_commands(planner, vpc):
    """plan_vpc_delete 返 2 条命令 (vsi + vsi-interface, 保留 l3vpn)"""
    cmds = planner.plan_vpc_delete(vpc, dry_run=True)
    assert len(cmds) == 2
    text = "\n".join(c["command"] for c in cmds)
    assert "undo vsi vpc0001" in text
    assert "undo interface Vsi-interface1" in text
    # 关键: 不应包含 l3vpn 删除
    assert "undo ip vpn-instance" not in text


# ======================== plan_port_bind ========================

def test_plan_port_bind_with_service_instance(planner, vpc):
    """service_instance 非空 → Mode 1 (4 条命令, 含 xconnect)"""
    binding = SimpleNamespace(
        interface_name="GigabitEthernet1/0/14",
        service_instance=1001,
        access_vlan=2,
    )
    cmds = planner.plan_port_bind(binding, vpc, mode="auto", dry_run=True)
    assert len(cmds) == 4
    text = "\n".join(c["command"] for c in cmds)
    assert "service-instance 1001" in text
    assert "xconnect vsi vpc0001 access" in text
    assert "port access vlan" not in text  # 不走 fallback


def test_plan_port_bind_fallback_to_access_vlan(planner, vpc):
    """service_instance 空 → Mode 2 fallback (3 条, port access vlan)"""
    binding = SimpleNamespace(
        interface_name="GigabitEthernet1/0/14",
        service_instance=None,
        access_vlan=2,
    )
    cmds = planner.plan_port_bind(binding, vpc, mode="auto", dry_run=True)
    assert len(cmds) == 3
    text = "\n".join(c["command"] for c in cmds)
    assert "port access vlan 2" in text
    assert "service-instance" not in text  # 不走 Mode 1


# ======================== plan_port_unbind ========================

def test_plan_port_unbind_handles_both_modes(planner, vpc):
    """plan_port_unbind 同时 undo service_instance + access vlan"""
    binding = SimpleNamespace(
        interface_name="GigabitEthernet1/0/14",
        service_instance=1001,
        access_vlan=2,
    )
    cmds = planner.plan_port_unbind(binding, vpc, dry_run=True)
    text = "\n".join(c["command"] for c in cmds)
    assert "undo service-instance 1001" in text
    assert "undo port access vlan 2" in text


def test_plan_port_unbind_handles_only_service_instance(planner, vpc):
    """plan_port_unbind 只配 service_instance 时, 不输出 undo access vlan"""
    binding = SimpleNamespace(
        interface_name="GigabitEthernet1/0/14",
        service_instance=1001,
        access_vlan=None,
    )
    cmds = planner.plan_port_unbind(binding, vpc, dry_run=True)
    text = "\n".join(c["command"] for c in cmds)
    assert "undo service-instance 1001" in text
    assert "undo port access vlan" not in text


# ======================== serialize/deserialize ========================

def test_serialize_deserialize_roundtrip(planner, vpc, tenant):
    """List[ConfigCommand] ↔ JSON roundtrip 保持一致"""
    cmds = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    json_str = VPCConfigPlanner.serialize(cmds)
    assert isinstance(json_str, str)
    cmds2 = VPCConfigPlanner.deserialize(json_str)
    assert cmds == cmds2


# ======================== .2/.3 现状回推 ========================

def test_plan_vpc_create_matches_leaf02_vpna():
    """.2 (Leaf-01) vpna 现状回推: VNI=10 → RD=1:1 (spec.md Scenario)

    spec.md 注释: "route-distinguisher 1:1 (与 1:10 一致 — .2 用 VNI/10 = 1)"
    即: VNI=10 → 10 // 10 = 1 → RD=1:1
    """
    adapter = H3cV7Adapter()
    planner = VPCConfigPlanner(adapter)

    vpc = SimpleNamespace(
        id=999,
        vni=10,  # .2 vpna 实际 VNI=10
        cidr="10.0.1.0/24",
        gateway_ip="10.0.1.1",
        gateway_mac="00-00-00-00-4e20-01",
        vsi_interface=1,
    )
    tenant = SimpleNamespace(rd="1:10", l3_vni=10000)

    cmds = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    text = "\n".join(c["command"] for c in cmds)
    # vsi_name 是 vpc{999:04d} = vpc0999 (vpca 是 .2 的命名习惯, 我们用 vpcXXXX 格式)
    assert "vsi vpc0999" in text
    assert "vxlan 10" in text
    # RD = 1:{10 // 10} = 1:1
    assert "route-distinguisher 1:1" in text
    # l3vpn RD = 1:{l3_vni} = 1:10000
    assert "route-distinguisher 1:10000" in text
