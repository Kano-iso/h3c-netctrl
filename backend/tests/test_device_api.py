"""设备管理 API 测试"""

from unittest.mock import patch


def test_create_device(client):
    """测试创建设备"""
    resp = client.post("/api/devices", json={
        "name": "SW-Test",
        "host": "192.168.1.1",
        "port": 830,
        "username": "admin",
        "password": "SyntheticTestPass!1"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["name"] == "SW-Test"
    assert data["data"]["host"] == "192.168.1.1"
    assert data["data"]["sdn_role"] is None


def test_update_device_sdn_role(client):
    """设备可显式标记 SDN 业务角色；默认纳管不自动加入 EVPN Fabric。"""
    create_resp = client.post("/api/devices", json={
        "name": "SW-SDN",
        "host": "192.168.1.10",
        "port": 830,
        "username": "admin",
        "password": "SyntheticTestPass!1"
    })
    device_id = create_resp.json()["data"]["id"]

    resp = client.put(f"/api/devices/{device_id}", json={"sdn_role": "evpn_leaf"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["sdn_role"] == "evpn_leaf"


def test_list_devices(client):
    """测试获取设备列表"""
    # 先创建一个设备
    client.post("/api/devices", json={
        "name": "SW-1",
        "host": "192.168.1.1",
        "port": 830,
        "username": "admin",
        "password": "SyntheticTestPass!1"
    })
    resp = client.get("/api/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["data"]) >= 1


def test_list_devices_does_not_probe_restore_support(client):
    """设备列表不能同步探测真实设备，否则前端首屏会被阻塞。"""
    client.post("/api/devices", json={
        "name": "SW-No-Probe",
        "host": "192.0.2.10",
        "port": 830,
        "username": "admin",
        "password": "SyntheticTestPass!1"
    })
    with patch("app.utils.backup_manager.BackupManager.check_restore_support") as probe:
        resp = client.get("/api/devices")

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    probe.assert_not_called()


def test_get_device(client):
    """测试获取单个设备"""
    create_resp = client.post("/api/devices", json={
        "name": "SW-1",
        "host": "192.168.1.1",
        "port": 830,
        "username": "admin",
        "password": "SyntheticTestPass!1"
    })
    device_id = create_resp.json()["data"]["id"]
    resp = client.get(f"/api/devices/{device_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "SW-1"


def test_update_device(client):
    """测试更新设备"""
    create_resp = client.post("/api/devices", json={
        "name": "SW-1",
        "host": "192.168.1.1",
        "port": 830,
        "username": "admin",
        "password": "SyntheticTestPass!1"
    })
    device_id = create_resp.json()["data"]["id"]
    resp = client.put(f"/api/devices/{device_id}", json={"name": "SW-Updated"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "SW-Updated"


def test_delete_device(client):
    """测试删除设备"""
    create_resp = client.post("/api/devices", json={
        "name": "SW-1",
        "host": "192.168.1.1",
        "port": 830,
        "username": "admin",
        "password": "SyntheticTestPass!1"
    })
    device_id = create_resp.json()["data"]["id"]
    resp = client.delete(f"/api/devices/{device_id}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ============ v241-supplement Task 4.2: split 模式 cleanup 集成 ============

def test_delete_device_monolith_no_cleanup_call(client, monkeypatch):
    """monolith 模式删设备不调内部 API（SERVICE_NAME != 'ctrl'）"""
    # 创建设备
    create_resp = client.post("/api/devices", json={
        "name": "SW-Monolith",
        "host": "192.168.1.100",
        "port": 830,
        "username": "admin",
        "password": "SyntheticTestPass!1",
    })
    device_id = create_resp.json()["data"]["id"]

    # 监控 internal_api.cleanup_device 是否被调
    from app.routers import device as device_router
    cleanup_called = {"count": 0}
    import app.internal_api as internal_api_mod

    original = internal_api_mod.cleanup_device

    def spy(device_id):
        cleanup_called["count"] += 1
        return {"success": True, "data": {"deleted_assets": 0, "deleted_backups": 0}}

    monkeypatch.setattr(internal_api_mod, "cleanup_device", spy)

    # 删设备
    resp = client.delete(f"/api/devices/{device_id}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    # 关键断言：monolith 模式不调 cleanup
    assert cleanup_called["count"] == 0, "monolith 模式不应调 internal_api.cleanup_device"


def test_delete_device_split_calls_cleanup(client, monkeypatch):
    """split 模式（SERVICE_NAME='ctrl'）删设备 → 调内部 API cleanup_device"""
    import os
    monkeypatch.setenv("SERVICE_NAME", "ctrl")

    # 创建设备
    create_resp = client.post("/api/devices", json={
        "name": "SW-Split",
        "host": "192.168.1.200",
        "port": 830,
        "username": "admin",
        "password": "SyntheticTestPass!1",
    })
    device_id = create_resp.json()["data"]["id"]

    # 监控 cleanup 调用
    cleanup_called = {"count": 0, "args": None}
    import app.internal_api as internal_api_mod

    def spy(did):
        cleanup_called["count"] += 1
        cleanup_called["args"] = did
        return {"success": True, "data": {"deleted_assets": 2, "deleted_backups": 3}}

    monkeypatch.setattr(internal_api_mod, "cleanup_device", spy)

    # 删设备
    resp = client.delete(f"/api/devices/{device_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # 关键断言：split 模式调 cleanup，返回 data 带 cleanup 信息
    assert cleanup_called["count"] == 1
    assert cleanup_called["args"] == device_id
    assert data["data"]["cleanup"]["deleted_assets"] == 2
    assert data["data"]["cleanup"]["deleted_backups"] == 3

    # 清理 SERVICE_NAME
    monkeypatch.delenv("SERVICE_NAME")


def test_delete_device_split_cleanup_failure_tolerated(client, monkeypatch):
    """split 模式 cleanup 失败不阻塞主流程：返回 success:true + warning"""
    import os
    monkeypatch.setenv("SERVICE_NAME", "ctrl")

    # 创建设备
    create_resp = client.post("/api/devices", json={
        "name": "SW-Split-Fail",
        "host": "192.168.1.201",
        "port": 830,
        "username": "admin",
        "password": "SyntheticTestPass!1",
    })
    device_id = create_resp.json()["data"]["id"]

    # mock cleanup 抛异常
    import app.internal_api as internal_api_mod
    def boom(did):
        raise RuntimeError("data 容器不可达")
    monkeypatch.setattr(internal_api_mod, "cleanup_device", boom)

    # 删设备
    resp = client.delete(f"/api/devices/{device_id}")
    assert resp.status_code == 200
    data = resp.json()
    # 关键断言：设备已删事实优先
    assert data["success"] is True
    assert "已删除" in data["data"]["message"]
    # warning 字段携带 cleanup 错误
    assert "warning" in data["data"]
    assert "data 容器不可达" in data["data"]["warning"]

    monkeypatch.delenv("SERVICE_NAME")
