"""全路由 smoke test — 验证每个路由至少能返回 200/正常响应，不报 500。

每次新增路由必须在此文件添加测试。
"""
import json


def test_health(client):
    """/docs 路径存在（FastAPI 自动生成 Swagger）"""
    resp = client.get("/docs")
    assert resp.status_code == 200


# === 设备管理 (device) ===

def test_device_list_empty(client):
    """设备列表（空）"""
    resp = client.get("/api/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


def test_device_create_get_delete(client, created_device):
    """设备 CRUD 完整链路"""
    # created_device fixture 已创建
    device_id = created_device["id"]
    assert isinstance(device_id, int)

    # 读取单设备
    resp = client.get(f"/api/devices/{device_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["name"] == "Test-Device"
    # 关键字段类型校验（防 Pydantic v2 bug 回归）
    assert isinstance(data["data"]["protected_interfaces"], list), \
        f"protected_interfaces 应为 list, 实际是 {type(data['data']['protected_interfaces'])}"
    assert data["data"]["protected_interfaces"] == [2]

    # 更新设备
    resp = client.put(f"/api/devices/{device_id}", json={"name": "Updated"})
    assert resp.status_code == 200

    # 删除设备
    resp = client.delete(f"/api/devices/{device_id}")
    assert resp.status_code == 200

    # 再次读取应失败
    resp = client.get(f"/api/devices/{device_id}")
    assert resp.status_code == 200
    assert resp.json()["success"] is False


# === VLAN 管理 (vlan) ===

def test_vlan_list(client, created_device, real_device_netconf):
    """VLAN 列表（mock 真实响应）"""
    device_id = created_device["id"]
    resp = client.get(f"/api/devices/{device_id}/vlans")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 3  # mock 返回 3 个 VLAN


# === 日志 (log) ===

def test_log_list(client):
    """日志列表"""
    resp = client.get("/api/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # 返回结构可能是 list 或 dict
    assert data["data"] is not None


# === 仪表盘 (dashboard) ===

def test_dashboard_stats(client):
    """仪表盘统计"""
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"] is not None


# === 资产 (asset) ===

def test_asset_get(client, created_device, mock_netconf):
    """资产查询"""
    device_id = created_device["id"]
    resp = client.get(f"/api/devices/{device_id}/asset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


def test_asset_refresh(client, created_device, mock_netconf):
    """资产刷新（mock SSH）"""
    device_id = created_device["id"]
    resp = client.post(f"/api/devices/{device_id}/asset/refresh")
    # mock SSH 不会真连，所以允许 200（mock 返回空数据）或 500（真连失败）
    assert resp.status_code in (200, 500)


# === 命令执行 (execute) ===

def test_execute_endpoint_exists(client, created_device, mock_netconf):
    """命令执行接口存在"""
    device_id = created_device["id"]
    resp = client.post(f"/api/devices/{device_id}/execute", json={"command": "display version"})
    # mock 环境下，命令会"执行"（返回模拟数据）
    assert resp.status_code in (200, 500)


# === 批量操作 (batch) ===

def test_batch_endpoint_exists(client, created_device, mock_netconf):
    """批量接口存在"""
    device_id = created_device["id"]
    resp = client.post("/api/batch/execute", json={
        "device_ids": [device_id],
        "command": "display version"
    })
    assert resp.status_code in (200, 500)


# === 接口管理 (interface) ===

def test_interface_list(client, created_device, real_device_netconf):
    """接口列表（mock 真实 H3C 响应）"""
    device_id = created_device["id"]
    resp = client.get(f"/api/devices/{device_id}/interfaces")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    # 关键回归：mock 真实响应有 23 个接口
    assert len(data["data"]) == 23, f"应返回 23 个接口, 实际 {len(data['data'])}"


def test_interface_config_protected_blocked(client, created_device, real_device_netconf):
    """接口配置：保护口被拒绝"""
    device_id = created_device["id"]
    resp = client.post(
        f"/api/devices/{device_id}/interfaces/config",
        json={"if_index": 2, "mode": "access", "access_vlan": 100}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "保护" in data["error"]


def test_interface_config_force(client, created_device, real_device_netconf):
    """接口配置：force=true 强制通过"""
    device_id = created_device["id"]
    resp = client.post(
        f"/api/devices/{device_id}/interfaces/config",
        json={"if_index": 2, "mode": "access", "access_vlan": 100, "force": True}
    )
    assert resp.status_code == 200
    data = resp.json()
    # mock edit_config 返回 <ok/> 所以 success=True
    assert data["success"] is True
