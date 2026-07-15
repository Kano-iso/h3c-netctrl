"""VPCConfigPlanner 单元测试（v3.0 sdn-vpc-netconf-schema-xml T3 双套 payload 适配版）

## 覆盖

### plan_vpc_create (5 unit × 4 字段)
- 返回 List[TemplateUnit] 长度 = 5
- unit name 顺序 = vsi-l2 / evpn / l3vpn / vsi-l3 / global
- cli_commands 含 vsi / vxlan / evpn / vpn-instance / vsi-interface 关键字
- dry_run=True/False 等价

### plan_vpc_delete (3 unit)
- 长度 = 3
- 不含 l3vpn（共享保留）
- 含 undo vsi + undo interface

### plan_port_bind
- service_instance 非空 → 1 unit (port-bind, Mode 1)
- service_instance 空 → 1 unit (port-bind, Mode 2 fallback)

### plan_port_unbind
- 同时 undo 2 种模式

### serialize/deserialize
- serialize_template_units 返 JSON 字符串
- deserialize_template_units 还原 List[TemplateUnit]
- 往返一致

### .2/.3 现状回推
- VNI=10 → RD=1:1
"""

import json
from types import SimpleNamespace

import pytest

from app.services.sdn_device_adapter import (
    H3cV7Adapter,
    TemplateUnit,
    UNIT_EVPN,
    UNIT_GLOBAL,
    UNIT_L3VPN,
    UNIT_VSI_L2,
    UNIT_VSI_L3,
    deserialize_template_units,
    serialize_template_units,
)
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


# ─────────── 工具：把所有 unit 的 cli 拼成 text ───────────

def _cli_text(units):
    """把 List[TemplateUnit] 所有 unit 的 cli_commands 拼成单字符串"""
    lines = []
    for u in units:
        lines.extend(u.cli_commands)
    return "\n".join(lines)


# ======================== plan_vpc_create ========================

def test_plan_vpc_create_returns_5_units(planner, vpc, tenant):
    """plan_vpc_create 返 5 个 TemplateUnit（v3.0 T3 5 unit 拆分）"""
    units = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    assert isinstance(units, list)
    assert len(units) == 5
    assert all(isinstance(u, TemplateUnit) for u in units)


def test_plan_vpc_create_unit_names(planner, vpc, tenant):
    """plan_vpc_create 5 unit name 顺序正确"""
    units = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    names = [u.name for u in units]
    assert names == [UNIT_VSI_L2, UNIT_EVPN, UNIT_L3VPN, UNIT_VSI_L3, UNIT_GLOBAL]


def test_plan_vpc_create_contains_keywords(planner, vpc, tenant):
    """plan_vpc_create 各 unit cli_commands 含 vsi/vxlan/evpn/vpn-instance/vsi-interface 关键字"""
    units = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    text = _cli_text(units)
    assert "vsi vpc0001" in text
    assert "vxlan 20000" in text
    assert "evpn encapsulation vxlan" in text
    assert "ip vpn-instance l3vpn" in text
    assert "interface Vsi-interface1" in text
    assert "vxlan tunnel mac-learning disable" in text


def test_plan_vpc_create_dry_run_equivalent(planner, vpc, tenant):
    """dry_run=True/False 当前实现完全等价（planner 纯计算）"""
    units1 = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    units2 = planner.plan_vpc_create(vpc, tenant, dry_run=False)
    assert len(units1) == len(units2)
    for u1, u2 in zip(units1, units2):
        assert u1.name == u2.name
        assert u1.cli_commands == u2.cli_commands


# ======================== plan_vpc_delete ========================

def test_plan_vpc_delete_returns_3_units(planner, vpc):
    """plan_vpc_delete 返 3 个 TemplateUnit（vsi-l2/evpn/vsi-l3，保留 l3vpn/global）"""
    units = planner.plan_vpc_delete(vpc, dry_run=True)
    assert len(units) == 3
    text = _cli_text(units)
    assert "undo vsi vpc0001" in text
    assert "undo interface Vsi-interface1" in text
    # 关键: 不应包含 l3vpn 删除
    assert "undo ip vpn-instance" not in text


def test_plan_vpc_delete_no_l3vpn_no_global(planner, vpc):
    """plan_vpc_delete 不输出 l3vpn / global（共享保留）"""
    units = planner.plan_vpc_delete(vpc, dry_run=True)
    names = [u.name for u in units]
    assert UNIT_L3VPN not in names
    assert UNIT_GLOBAL not in names


# ======================== plan_port_bind ========================

def test_plan_port_bind_with_service_instance(planner, vpc):
    """service_instance 非空 → Mode 1（1 unit, 含 xconnect vsi access）"""
    binding = SimpleNamespace(
        interface_name="GigabitEthernet1/0/14",
        service_instance=1001,
        access_vlan=2,
    )
    units = planner.plan_port_bind(binding, vpc, mode="auto", dry_run=True)
    assert len(units) == 1
    text = _cli_text(units)
    assert "service-instance 1001" in text
    assert "xconnect vsi vpc0001 access" in text
    assert "port access vlan" not in text  # 不走 fallback


def test_plan_port_bind_fallback_to_access_vlan(planner, vpc):
    """service_instance 空 → Mode 2 fallback（1 unit, port access vlan）"""
    binding = SimpleNamespace(
        interface_name="GigabitEthernet1/0/14",
        service_instance=None,
        access_vlan=2,
    )
    units = planner.plan_port_bind(binding, vpc, mode="auto", dry_run=True)
    assert len(units) == 1
    text = _cli_text(units)
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
    units = planner.plan_port_unbind(binding, vpc, dry_run=True)
    assert len(units) == 1
    text = _cli_text(units)
    assert "undo service-instance 1001" in text
    assert "undo port access vlan 2" in text


def test_plan_port_unbind_handles_only_service_instance(planner, vpc):
    """plan_port_unbind 只配 service_instance 时, 不输出 undo access vlan"""
    binding = SimpleNamespace(
        interface_name="GigabitEthernet1/0/14",
        service_instance=1001,
        access_vlan=None,
    )
    units = planner.plan_port_unbind(binding, vpc, dry_run=True)
    text = _cli_text(units)
    assert "undo service-instance 1001" in text
    assert "undo port access vlan" not in text


# ======================== serialize/deserialize ========================

def test_serialize_deserialize_roundtrip(planner, vpc, tenant):
    """List[TemplateUnit] ↔ JSON roundtrip 保持一致（v3.0 T3 双套 payload）"""
    units = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    json_str = VPCConfigPlanner.serialize(units)
    assert isinstance(json_str, str)
    # 内部委托给 serialize_template_units
    units2 = VPCConfigPlanner.deserialize(json_str)
    assert len(units) == len(units2)
    for u1, u2 in zip(units, units2):
        assert u1.name == u2.name
        assert u1.cli_commands == u2.cli_commands
        assert u1.xml_payloads == u2.xml_payloads
        assert u1.undo_cli == u2.undo_cli
        assert u1.undo_xml == u2.undo_xml


def test_serialize_uses_adapter_helper(planner, vpc, tenant):
    """VPCConfigPlanner.serialize 实际调 serialize_template_units（adapter 层 helper）"""
    units = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    json1 = VPCConfigPlanner.serialize(units)
    json2 = serialize_template_units(units)
    # 同一输入应产生同一 JSON
    data1 = json.loads(json1)
    data2 = json.loads(json2)
    assert data1 == data2


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

    units = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    text = _cli_text(units)
    # vsi_name 是 vpc{999:04d} = vpc0999
    assert "vsi vpc0999" in text
    assert "vxlan 10" in text
    # RD = 1:{10 // 10} = 1:1
    assert "route-distinguisher 1:1" in text
    # l3vpn RD = 1:{l3_vni} = 1:10000
    assert "route-distinguisher 1:10000" in text
