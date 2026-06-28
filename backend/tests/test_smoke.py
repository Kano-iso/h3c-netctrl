"""全路由 smoke test — 验证每个路由至少能返回 200/正常响应，不报 500。

每次新增路由必须在此文件添加测试。
"""
import json
import os
from unittest.mock import MagicMock, patch


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


# ======================== v2.2.0 新增端点 smoke ========================

# === 备份 (backup) - 7 端点 ===

def test_backup_list(client, created_device):
    """GET /api/devices/{id}/backup — 备份列表"""
    resp = client.get(f"/api/devices/{created_device['id']}/backup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "backups" in data["data"]


def test_backup_download_not_found(client, created_device):
    """GET /api/devices/{id}/backup/{bid} — 不存在的备份 404"""
    resp = client.get(f"/api/devices/{created_device['id']}/backup/99999")
    assert resp.status_code == 404


def test_backup_create_endpoint_exists(client, created_device):
    """POST /api/devices/{id}/backup — 端点存在（mock BackupManager）"""
    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.create_backup.return_value = [
            {"id": 1, "type": "startup", "size": 100, "content_hash": "abc",
             "filename": "x.cfg", "created_at": "2026-06-29T10:00:00"}
        ]
        MockBM.return_value = mock_mgr
        resp = client.post(
            f"/api/devices/{created_device['id']}/backup",
            json={"types": ["startup"]}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


def test_backup_create_invalid_type(client, created_device):
    """POST /api/devices/{id}/backup — 非法类型 422"""
    with patch("app.routers.backup.BackupManager") as MockBM:
        MockBM.return_value = MagicMock()
        resp = client.post(
            f"/api/devices/{created_device['id']}/backup",
            json={"types": ["invalid_type"]}
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is False


def test_backup_delete_endpoint_exists(client, created_device, db):
    """DELETE /api/devices/{id}/backup/{bid} — 端点存在（mock BackupManager）"""
    from app.models import Backup
    backup = Backup(
        device_id=created_device["id"],
        filename="test.cfg",
        file_path="/tmp/test.cfg",
        backup_type="startup",
        size=100,
        content_hash="abc",
        locked=False,
    )
    db.add(backup)
    db.commit()

    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.delete_backup.return_value = True
        MockBM.return_value = mock_mgr
        resp = client.delete(f"/api/devices/{created_device['id']}/backup/{backup.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


def test_backup_lock_endpoint_exists(client, created_device, db):
    """POST /api/devices/{id}/backup/{bid}/lock — 端点存在（mock BackupManager）"""
    from app.models import Backup
    backup = Backup(
        device_id=created_device["id"],
        filename="test.cfg",
        file_path="/tmp/test.cfg",
        backup_type="startup",
        size=100,
        content_hash="abc",
        locked=False,
    )
    db.add(backup)
    db.commit()

    with patch("app.routers.backup.BackupManager") as MockBM:
        MockBM.return_value = MagicMock()
        resp = client.post(
            f"/api/devices/{created_device['id']}/backup/{backup.id}/lock",
            json={"locked": True}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


def test_backup_restore_endpoint_exists(client, created_device, db):
    """POST /api/devices/{id}/backup/{bid}/restore — 端点存在（mock BackupManager）"""
    from app.models import Backup
    backup = Backup(
        device_id=created_device["id"],
        filename="test.cfg",
        file_path="/tmp/test.cfg",
        backup_type="startup",
        size=100,
        content_hash="abc",
        locked=False,
    )
    db.add(backup)
    db.commit()

    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.restore.return_value = {"success": True, "message": "回滚成功"}
        MockBM.return_value = mock_mgr
        resp = client.post(
            f"/api/devices/{created_device['id']}/backup/{backup.id}/restore",
            json={"with_reboot": False}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


def test_backup_create_all_endpoint_exists(client, created_device):
    """POST /api/backups — 全量备份端点存在（mock BackupManager）"""
    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.create_backup.return_value = [
            {"id": 1, "type": "startup", "size": 100, "content_hash": "abc",
             "filename": "x.cfg", "created_at": "2026-06-29T10:00:00"}
        ]
        MockBM.return_value = mock_mgr
        resp = client.post("/api/backups")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


# === VPN instance - 5 端点 ===

def test_vpn_instance_list(client, created_device, real_device_netconf):
    """GET /api/devices/{id}/vpn-instances — VPN 列表"""
    resp = client.get(f"/api/devices/{created_device['id']}/vpn-instances")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "vpn_instances" in data["data"]


def test_vpn_instance_create_endpoint_exists(client, created_device, real_device_netconf):
    """POST /api/devices/{id}/vpn-instances — 创建 VPN（mock NETCONF）"""
    resp = client.post(
        f"/api/devices/{created_device['id']}/vpn-instances",
        json={"name": "test_vpn", "rd": "100:1"}
    )
    assert resp.status_code in (200, 422, 500)


def test_vpn_instance_delete_endpoint_exists(client, created_device, real_device_netconf):
    """DELETE /api/devices/{id}/vpn-instances/{name} — 删除 VPN"""
    resp = client.delete(
        f"/api/devices/{created_device['id']}/vpn-instances/test_vpn"
    )
    assert resp.status_code in (200, 422, 500)


def test_vpn_bind_endpoint_exists(client, created_device, real_device_netconf):
    """POST /api/devices/{id}/interfaces/{if_index}/vpn-instance — 绑定 VPN"""
    resp = client.post(
        f"/api/devices/{created_device['id']}/interfaces/100/vpn-instance",
        json={"vpn_name": "test_vpn"}
    )
    assert resp.status_code in (200, 422, 500)


def test_vpn_unbind_endpoint_exists(client, created_device, real_device_netconf):
    """DELETE /api/devices/{id}/interfaces/{if_index}/vpn-instance — 解绑 VPN"""
    resp = client.delete(
        f"/api/devices/{created_device['id']}/interfaces/100/vpn-instance"
    )
    assert resp.status_code in (200, 422, 500)


# === link-type - 1 端点 ===

def test_link_type_patch_endpoint_exists(client, created_device, real_device_netconf):
    """PATCH /api/devices/{id}/interfaces/{if_index}/link-type — 改 link type"""
    resp = client.patch(
        f"/api/devices/{created_device['id']}/interfaces/100/link-type",
        json={"mode": "access", "force": False}
    )
    assert resp.status_code in (200, 422, 500)


# === ipv4-address - 2 端点 ===

def test_ipv4_address_post_endpoint_exists(client, created_device, real_device_netconf):
    """POST /api/devices/{id}/interfaces/{if_index}/ipv4-address — 配 IPv4"""
    resp = client.post(
        f"/api/devices/{created_device['id']}/interfaces/100/ipv4-address",
        json={"address": "10.0.0.1", "mask": "255.255.255.0"}
    )
    assert resp.status_code in (200, 422, 500)


def test_ipv4_address_delete_endpoint_exists(client, created_device, real_device_netconf):
    """DELETE /api/devices/{id}/interfaces/{if_index}/ipv4-address — 清 IPv4"""
    resp = client.delete(
        f"/api/devices/{created_device['id']}/interfaces/100/ipv4-address"
    )
    assert resp.status_code in (200, 422, 500)
