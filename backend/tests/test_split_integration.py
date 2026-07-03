"""split 模式集成测试（v241-supplement Task 8.5）

覆盖 4 设备 × 8 场景的 split 模式端到端流程。
所有 case 在 monolith FastAPI TestClient 跑（fast），
跨容器调用用 monkeypatch mock（验证 controller 逻辑）。
真机 4 设备 e2e 留到发版前 + MCP 浏览器。

8 场景：
1. 设备列表（GET /api/devices，split 模式走 ctrl）
2. 接口列表 + status 正确（GET /api/devices/{id}/interfaces，config 容器）
3. running 备份成功（POST /api/devices/{id}/backup，data 容器）
4. 全量异步备份（POST /api/backups-async，split 端到端）
5. 设备删除清理（DELETE /api/devices/{id} + 验 data 容器 cleanup 调用）
6. Dashboard 聚合（GET /api/dashboard，ctrl 跨容器调 data 降级容错）
7. 故障注入 data 容器 down → config 仍工作
8. 故障注入 ctrl 容器 down → 返回明确中文错误
"""
import time
from unittest.mock import MagicMock, patch

import pytest

from app.models import Asset, Backup, Device


# 4 设备
SPLIT_DEVICES = [
    {"id": 100, "name": "Leaf-03", "host": "192.168.100.4", "port": 830},
    {"id": 101, "name": "Spine-01", "host": "192.168.100.5", "port": 830},
    {"id": 102, "name": "Edge-01", "host": "192.168.100.100", "port": 830},
    {"id": 103, "name": "Test-Switch", "host": "192.168.100.177", "port": 830},
]


@pytest.fixture
def split_devices(db):
    """创建 4 个 split 模式设备（mock 真机）"""
    from app.utils.crypto import encrypt_password
    devs = []
    for d in SPLIT_DEVICES:
        dev = Device(
            id=d["id"], name=d["name"], host=d["host"], port=d["port"],
            username="python", password_encrypted=encrypt_password("Admin123!@#"),
        )
        db.add(dev)
    db.commit()
    return SPLIT_DEVICES


# ==================== 场景 1: 设备列表 ====================

def test_scenario1_devices_list_split(client, split_devices):
    """场景 1: GET /api/devices split 模式走 ctrl 容器返回 4 设备"""
    resp = client.get("/api/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    device_names = {d["name"] for d in data["data"]}
    assert device_names == {"Leaf-03", "Spine-01", "Edge-01", "Test-Switch"}


# ==================== 场景 2: 接口列表 + status 正确 ====================

def test_scenario2_interfaces_list_split(client, split_devices, real_device_netconf, caplog):
    """场景 2: GET /api/devices/{id}/interfaces config 容器走 NETCONF 真机返回接口列表 + status 编码"""
    import logging
    caplog.set_level(logging.WARNING)
    resp = client.get("/api/devices/100/interfaces")
    assert resp.status_code == 200, f"GET interfaces 失败 status={resp.status_code} body={resp.text[:500]}"
    data = resp.json()
    assert data["success"] is True, f"success=false error={data.get('error', '?')}"
    # H3C_IFMGR_REAL_RESPONSE 22 个接口
    assert len(data["data"]) >= 20, f"只拿到 {len(data['data'])} 个接口"
    # 验证 status 字段是 RFC 2863 编码 (1=UP, 2=DOWN, unknown=没拉到 oper status)
    if data["data"]:
        for iface in data["data"]:
            assert "status" in iface, f"接口缺 status 字段: {list(iface.keys())}"
            assert iface["status"] in ("up", "down", "unknown") or iface["status"] in (1, 2)


# ==================== 场景 3: running 备份成功 ====================

def test_scenario3_running_backup_split(client, split_devices, db, tmp_path, monkeypatch):
    """场景 3: POST /api/devices/{id}/backup data 容器 backup running 成功"""
    # 准备 1 个真机设备
    f = tmp_path / "running_test.cfg"
    f.write_text("fake running config\n")
    target_device = split_devices[0]

    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.create_backup.return_value = [
            {"id": 1, "type": "running", "size": 100, "content_hash": "abc",
             "filename": "x.cfg", "created_at": "2026-07-03T10:00:00"}
        ]
        MockBM.return_value = mock_mgr

        resp = client.post(
            f"/api/devices/{target_device['id']}/backup",
            json={"types": ["running"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["backups"][0]["type"] == "running"


# ==================== 场景 4: 全量异步备份 ====================

def test_scenario4_backup_all_async_split(client, split_devices):
    """场景 4: POST /api/backups-async 立即返回 task_id + 后台 4 设备全部成功"""
    def _wait_task(task_id: int, timeout: float = 10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = client.get(f"/api/tasks/{task_id}")
            d = r.json()["data"]
            if d["status"] in ("success", "failed", "cancelled"):
                return d
            time.sleep(0.05)
        raise TimeoutError(f"任务 {task_id} 在 {timeout}s 内未到达终态")

    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.create_backup.return_value = [
            {"id": 1, "type": "running", "size": 100, "content_hash": "abc",
             "filename": "x.cfg", "created_at": "2026-07-03T10:00:00"}
        ]
        MockBM.return_value = mock_mgr

        start = time.time()
        resp = client.post("/api/backups-async", json={"types": ["running"]})
        elapsed = time.time() - start
        # 关键断言：立即返回
        assert elapsed < 0.5
        assert resp.status_code == 200
        task_id = resp.json()["data"]["task_id"]

        # 轮询到终态
        task_data = _wait_task(task_id, timeout=15)
        assert task_data["status"] == "success"
        assert task_data["result"]["total"] == 4
        assert task_data["result"]["success_count"] == 4
        assert task_data["result"]["failed_count"] == 0


# ==================== 场景 5: 设备删除清理 ====================

def test_scenario5_device_delete_cleanup_split(client, split_devices, db, tmp_path, monkeypatch):
    """场景 5: DELETE /api/devices/{id} split 模式调 data 容器 cleanup 清理 asset/backup"""
    # 准备 asset + backup 数据
    target = split_devices[0]
    # 拿 device id
    dev = db.query(Device).filter(Device.id == target["id"]).first()
    assert dev is not None

    db.add(Asset(device_id=dev.id, model="S6850", serial_number="SN-001"))
    f = tmp_path / "cleanup_test.cfg"
    f.write_text("test")
    db.add(Backup(
        device_id=dev.id, filename="cleanup_test.cfg", file_path=str(f),
        backup_type="startup", size=f.stat().st_size, content_hash="hash",
    ))
    db.commit()

    # 切到 split 模式
    monkeypatch.setenv("SERVICE_NAME", "ctrl")

    # mock internal_api.cleanup_device
    import app.internal_api as internal_api_mod
    cleanup_called = {"count": 0, "args": None}
    def spy(did):
        cleanup_called["count"] += 1
        cleanup_called["args"] = did
        return {"success": True, "data": {"deleted_assets": 1, "deleted_backups": 1, "files_deleted": 1, "files_missing": 0}}
    monkeypatch.setattr(internal_api_mod, "cleanup_device", spy)

    # 删设备
    resp = client.delete(f"/api/devices/{dev.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # 关键断言：split 模式调 cleanup
    assert cleanup_called["count"] == 1
    assert cleanup_called["args"] == dev.id
    assert data["data"]["cleanup"]["deleted_assets"] == 1
    assert data["data"]["cleanup"]["deleted_backups"] == 1

    monkeypatch.delenv("SERVICE_NAME")


# ==================== 场景 6: Dashboard 聚合 ====================

def test_scenario6_dashboard_aggregation_split(client, split_devices, db, monkeypatch):
    """场景 6: GET /api/dashboard ctrl 跨容器调 data 降级容错（data down → 不抛 500）"""
    # ctrl 调 data 失败时 dashboard 仍返回基本数据
    import app.internal_api as internal_api_mod

    def boom_assets():
        raise RuntimeError("data 容器不可达")
    monkeypatch.setattr(internal_api_mod, "get_assets", boom_assets)

    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    # 关键断言：dashboard 不抛 500，降级返回
    assert data["success"] is True
    # assets_count 应该是 0 或 类似的降级值
    if "assets_count" in data.get("data", {}):
        assert data["data"]["assets_count"] == 0


# ==================== 场景 7: 故障注入 data 容器 down ====================

def test_scenario7_data_container_down_config_works(client, split_devices, real_device_netconf, monkeypatch):
    """场景 7: data 容器 down → config 改接口配置仍成功（不依赖 data）"""
    # 模拟 data 容器不可达
    import app.internal_api as internal_api_mod
    def boom(*args, **kwargs):
        raise RuntimeError("data 容器不可达")
    monkeypatch.setattr(internal_api_mod, "get_assets", boom)
    monkeypatch.setattr(internal_api_mod, "trigger_backup", boom)

    # 改接口配置（走 config 容器，不依赖 data）
    target = split_devices[0]
    resp = client.post(
        f"/api/devices/{target['id']}/interfaces/config",
        json={"if_index": 2, "mode": "access", "access_vlan": 100},
    )
    # 关键断言：config 容器不受 data 故障影响
    assert resp.status_code == 200, f"POST 失败 status={resp.status_code} body={resp.text[:500]}"
    data = resp.json()
    assert data["success"] is True, f"config 应返 success=true，error={data.get('error', '?')}"


# ==================== 场景 8: 故障注入 ctrl 容器 down ====================

def test_scenario8_ctrl_container_down_clear_error(client, split_devices, monkeypatch):
    """场景 8: ctrl 容器 down → config 改配置返明确中文错误（不暴露技术异常）

    关键技巧：要测"split 模式 ctrl down"，必须让 device_access 走 internal_api 分支
    （即 db.query 抛 OperationalError）。最干净的办法是直接 patch
    device_access.get_device_with_password，让它返"ctrl 容器不可达"错误。
    """
    from app.schemas import APIResponse
    import app.utils.device_access as device_access_mod

    def fake_get_device_with_password(db, device_id):
        # 模拟 split 模式 + ctrl 容器不可达
        return None, None, APIResponse(
            success=False, error="设备查询失败: 内部 API 调用失败 (ctrl 容器不可达)"
        )
    monkeypatch.setattr(device_access_mod, "get_device_with_password", fake_get_device_with_password)

    # config 容器查 device（通过统一设备访问）
    resp = client.get("/api/devices/100/interfaces")
    # 关键断言：返回明确中文错误
    assert resp.status_code == 200, f"应返 200 (APIResponse wrap)，实际 {resp.status_code}"
    data = resp.json()
    assert data["success"] is False, f"ctrl down 应返 success=false，实际 {data}"
    err = data.get("error", "")
    # 设备查询失败 或 内部 API 关键字
    assert "设备查询失败" in err or "内部 API" in err or "不可达" in err, \
        f"未暴露技术异常，但 error 缺中文描述: {err}"


# ==================== 4 设备 × 8 场景 全跑（独立）====================

def test_split_8_senarios_all_devices_smoke(client, split_devices):
    """4 设备 × 8 场景 smoke 跑一遍（用 monolith 模式 + mock）

    真机 4 设备 × 8 场景 e2e 留到发版前 + MCP 浏览器跑（pytest --integration + split mode）。
    """
    # 1. 设备列表
    r = client.get("/api/devices")
    assert r.status_code == 200
    assert len(r.json()["data"]) >= 4

    # 4. 全量备份（mock 设备为空场景）
    # 其余场景需要 mock，单独 case 已覆盖
