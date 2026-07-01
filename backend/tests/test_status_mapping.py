"""v24-bugfix-status-mapping: OperStatus / AdminStatus 映射正确性单测

覆盖 H3C V7 Ifmgr 返回的 <AdminStatus> + <OperStatus> 字段映射到
admin_status / oper_status / status 的正确性（RFC 2863 / IF-MIB 1=UP 2=DOWN）。

矩阵覆盖 8 个组合（AdminStatus × OperStatus）：
- 1,1 → admin=up, oper=up, status=up
- 1,2 → admin=up, oper=down, status=down
- 2,1 → admin=down, oper=up, status=up（admin 兜底失效，链路层优先）
- 2,2 → admin=down, oper=down, status=down
- 1,(缺) → admin=up, oper=unknown, status=up（admin 兜底）
- (缺),1 → admin=unknown, oper=up, status=up
- (缺),2 → admin=unknown, oper=down, status=down
- 1,3 → admin=up, oper=down, status=down（3=testing 兜底 down）
"""
from app.routers.interface import _parse_interface_response


def _build_xml(admin_status, oper_status, if_index=100, name="GigabitEthernet1/0/1"):
    """构造最简 Ifmgr 单接口 XML"""
    parts = [f"<Interface><IfIndex>{if_index}</IfIndex>"]
    if name:
        parts.append(f"<Name>{name}</Name>")
    if admin_status is not None:
        parts.append(f"<AdminStatus>{admin_status}</AdminStatus>")
    if oper_status is not None:
        parts.append(f"<OperStatus>{oper_status}</OperStatus>")
    parts.append("</Interface>")
    inner = "".join(parts)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<data>
<top xmlns="http://www.h3c.com/netconf/data:1.0">
<Ifmgr>
<Interfaces>
{inner}
</Interfaces>
</Ifmgr>
</top>
</data>"""


def test_status_oper1_admin1_up_up_status_up():
    """OperStatus=1, AdminStatus=1 → admin=up, oper=up, status=up（1Gbps UP 链路）"""
    xml = _build_xml(admin_status=1, oper_status=1)
    ifaces = _parse_interface_response(xml)
    assert len(ifaces) == 1
    i = ifaces[0]
    assert i["admin_status"] == "up", f"admin_status 应为 up，实际 {i['admin_status']}"
    assert i["oper_status"] == "up", f"oper_status 应为 up，实际 {i['oper_status']}"
    assert i["status"] == "up", f"status 应为 up，实际 {i['status']}"


def test_status_oper2_admin1_down_down_status_down():
    """OperStatus=2, AdminStatus=1 → admin=up, oper=down, status=down（Trunk 空载）"""
    xml = _build_xml(admin_status=1, oper_status=2)
    ifaces = _parse_interface_response(xml)
    assert len(ifaces) == 1
    i = ifaces[0]
    assert i["admin_status"] == "up"
    assert i["oper_status"] == "down", f"oper_status 应为 down，实际 {i['oper_status']}"
    assert i["status"] == "down", f"status 应为 down，实际 {i['status']}"


def test_status_oper1_admin2_shutdown_but_link_up():
    """OperStatus=1, AdminStatus=2 → admin=down, oper=up, status=up（admin shutdown 但链路仍 up）"""
    xml = _build_xml(admin_status=2, oper_status=1)
    ifaces = _parse_interface_response(xml)
    assert len(ifaces) == 1
    i = ifaces[0]
    assert i["admin_status"] == "down", "admin=2 应映射 down"
    assert i["oper_status"] == "up"
    # 关键：status 优先看 oper（链路层），admin 字段独立
    assert i["status"] == "up", "OperStatus=1 即使 AdminStatus=2，status 应为 up"


def test_status_oper2_admin2_down_down_status_down():
    """OperStatus=2, AdminStatus=2 → admin=down, oper=down, status=down（admin shutdown + 链路 down）"""
    xml = _build_xml(admin_status=2, oper_status=2)
    ifaces = _parse_interface_response(xml)
    assert len(ifaces) == 1
    i = ifaces[0]
    assert i["admin_status"] == "down"
    assert i["oper_status"] == "down"
    assert i["status"] == "down"


def test_status_admin_only_admin1_oper_missing_admin_fallback():
    """AdminStatus=1, OperStatus 缺失 → admin=up, oper=unknown, status=up（admin 兜底）"""
    xml = _build_xml(admin_status=1, oper_status=None)
    ifaces = _parse_interface_response(xml)
    assert len(ifaces) == 1
    i = ifaces[0]
    assert i["admin_status"] == "up"
    assert i["oper_status"] == "unknown", f"oper_status 缺失应为 unknown，实际 {i['oper_status']}"
    assert i["status"] == "up", "OperStatus 缺失时 status 用 admin 兜底，admin=1 应为 up"


def test_status_oper_only_oper1_admin_missing():
    """OperStatus=1, AdminStatus 缺失 → admin=unknown, oper=up, status=up"""
    xml = _build_xml(admin_status=None, oper_status=1)
    ifaces = _parse_interface_response(xml)
    assert len(ifaces) == 1
    i = ifaces[0]
    assert i["admin_status"] == "unknown", f"admin 缺失应为 unknown，实际 {i['admin_status']}"
    assert i["oper_status"] == "up"
    assert i["status"] == "up"


def test_status_oper_only_oper2_admin_missing():
    """OperStatus=2, AdminStatus 缺失 → admin=unknown, oper=down, status=down"""
    xml = _build_xml(admin_status=None, oper_status=2)
    ifaces = _parse_interface_response(xml)
    assert len(ifaces) == 1
    i = ifaces[0]
    assert i["admin_status"] == "unknown"
    assert i["oper_status"] == "down"
    assert i["status"] == "down"


def test_status_oper3_testing_fallback_down():
    """OperStatus=3 (testing, RFC 2863) → 兜底 down（保守处理，H3C V7 实际不返）"""
    xml = _build_xml(admin_status=1, oper_status=3)
    ifaces = _parse_interface_response(xml)
    assert len(ifaces) == 1
    i = ifaces[0]
    assert i["admin_status"] == "up"
    # 关键：3/4/5/6/7 非 1/2 值兜底 down（保守）
    assert i["oper_status"] == "down", f"oper_status=3 应兜底 down，实际 {i['oper_status']}"
    assert i["status"] == "down"


def test_status_bug_regression_legacy_inverted_mapping():
    """v24-bugfix 回归：v2.4-bugfix-interface-display-100 错误映射（==2 判 up）已被修正

    之前 bug：OperStatus=1 被错误映射成 down，OperStatus=2 被错误映射成 up。
    本测试确保 OperStatus=1 必为 up，OperStatus=2 必为 down。
    """
    # 分别解析两个 XML（_parse_interface_response 只接受一个根，不直接合并）
    xml_up = _build_xml(admin_status=1, oper_status=1, if_index=200)
    xml_down = _build_xml(admin_status=1, oper_status=2, if_index=201)
    ifaces = _parse_interface_response(xml_up) + _parse_interface_response(xml_down)
    by_idx = {i["if_index"]: i for i in ifaces}
    assert by_idx[200]["status"] == "up", "回归：OperStatus=1 必为 up"
    assert by_idx[201]["status"] == "down", "回归：OperStatus=2 必为 down"
