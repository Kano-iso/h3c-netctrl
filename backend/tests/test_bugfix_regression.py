"""关键 bug 回归测试 — 防止之前踩过的坑再次出现。

每个测试对应一个具体 bug 场景，必须有清晰说明。
"""
import json


# === Bug #1: H3C Ifmgr 解析器过滤了所有接口 ===
#
# 真实场景：H3C 设备返回的 Ifmgr XML 中，很多接口只有 IfIndex 和 PVID，
# 没有 Name 和 LinkType 字段。早期解析器要求 name 和 mode 都存在，
# 导致 23 个接口被过滤成 0 个。

def test_bug1_h3c_ifmgr_keeps_minimal_interfaces(client, created_device, real_device_netconf):
    """回归：H3C 真实响应（只有 IfIndex/PVID）必须被正确解析

    Bug 历史：v20-netconf-refactor 变更中，解析器要求每个接口必须有
    Name 和 LinkType，导致 H3C 真实响应（23 个接口）被过滤为 0 个。
    修复：只检查 IfIndex，其他字段缺失时用默认值。
    """
    device_id = created_device["id"]
    resp = client.get(f"/api/devices/{device_id}/interfaces")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True, f"接口列表获取失败: {data.get('error')}"

    interfaces = data["data"]
    # 关键断言：必须有 23 个接口（不是 0 个）
    assert len(interfaces) == 23, f"应保留 23 个接口，实际 {len(interfaces)}"

    # 每个接口必须有 if_index 字段
    for iface in interfaces:
        assert "if_index" in iface, f"接口缺少 if_index: {iface}"
        assert isinstance(iface["if_index"], int)


# === Bug #2: DeviceResponse Pydantic v2 model_validate 错误 ===
#
# 真实场景：上次给 DeviceResponse 加 protected_interfaces 字段时，
# 错误地重写了 model_validate，导致 GET /api/devices 一直 500。

def test_bug2_device_response_pydantic_v2_compatibility(client, created_device):
    """回归：GET /api/devices 必须返回成功，protected_interfaces 是 list

    Bug 历史：DeviceResponse.model_validate 错误实现，Pydantic v2
    类型校验失败，整个设备管理界面 500。
    修复：改用 field_validator(mode="before")。
    """
    # 关键测试：直接 GET /api/devices（不是单设备）
    resp = client.get("/api/devices")
    assert resp.status_code == 200, f"GET /api/devices 失败: {resp.text}"
    data = resp.json()
    assert data["success"] is True, f"响应失败: {data}"

    devices = data["data"]
    assert len(devices) >= 1

    # 关键断言：protected_interfaces 必须是 list[int]，不是 str
    for device in devices:
        assert isinstance(device["protected_interfaces"], list), \
            f"device {device['id']}: protected_interfaces 应为 list, 实际 {type(device['protected_interfaces'])}"


def test_bug2b_pydantic_handles_invalid_json(client, db):
    """回归：数据库里 JSON 解析失败时，不能 500

    边界场景：万一数据库里 protected_interfaces 字段被破坏（非法 JSON），
    Pydantic 校验失败 → 500。修复后必须返回空 list。
    """
    from app.models import Device, Asset
    from app.utils.crypto import encrypt_password

    # 手动插入一条 protected_interfaces 是非法 JSON 的设备
    device = Device(
        name="Bad-JSON",
        host="192.168.1.99",
        port=830,
        username="admin",
        password_encrypted=encrypt_password("test"),
        protected_interfaces="not-a-valid-json",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    # GET 必须不报 500
    resp = client.get("/api/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # 找到这条设备
    bad = next((d for d in data["data"] if d["id"] == device.id), None)
    assert bad is not None
    # 解析失败时应该是空 list
    assert bad["protected_interfaces"] == []


# === Bug #3: DeviceDetail.vue 漏 import computed，设备详情白屏 ===
#
# 真实场景：加 isIfaceProtected = computed(...) 时，漏了 import，
# Vue setup 阶段 ReferenceError，设备详情页白屏。
# 注：前端 bug 暂不在 pytest 覆盖范围，由 `npm run build` 兜底。
# 此测试只保证后端字段返回正确，前端 import 错由 build 抓。

def test_bug3_device_api_returns_protected_interfaces_for_frontend(client, created_device):
    """回归：前端需要 protected_interfaces 字段，必须在 API 响应中"""
    resp = client.get(f"/api/devices/{created_device['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert "protected_interfaces" in data["data"]
    assert data["data"]["protected_interfaces"] == [2]
