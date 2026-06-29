"""备份 API 测试（v2.3 add-v22-qa-repair 1.1.2）

覆盖 backup 7 个 API：smoke + 错误码 + 中文错误信息。
"""
from unittest.mock import MagicMock, patch

from app.models import Backup


# ======================== POST /api/devices/{id}/backup ========================

def test_create_backup_success(client, created_device):
    """POST /api/devices/{id}/backup 成功（mock BackupManager）"""
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
        assert len(data["data"]["backups"]) == 1
        assert data["data"]["backups"][0]["type"] == "startup"


def test_create_backup_device_not_found(client):
    """POST /api/devices/{id}/backup 设备不存在"""
    resp = client.post("/api/devices/99999/backup", json={"types": ["startup"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]


def test_create_backup_invalid_type(client, created_device):
    """POST /api/devices/{id}/backup types 非法 422"""
    resp = client.post(
        f"/api/devices/{created_device['id']}/backup",
        json={"types": ["invalid"]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不支持" in data["error"]


def test_create_backup_all_failed(client, created_device):
    """POST /api/devices/{id}/backup 所有类型均失败"""
    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.create_backup.return_value = []  # 空列表 = 全部失败
        MockBM.return_value = mock_mgr
        resp = client.post(
            f"/api/devices/{created_device['id']}/backup",
            json={"types": ["startup"]}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "失败" in data["error"]


# ======================== GET /api/devices/{id}/backup ========================

def test_list_backups_success(client, created_device):
    """GET /api/devices/{id}/backup 成功"""
    resp = client.get(f"/api/devices/{created_device['id']}/backup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["device_id"] == created_device["id"]
    assert isinstance(data["data"]["backups"], list)


def test_list_backups_device_not_found(client):
    """GET /api/devices/{id}/backup 设备不存在"""
    resp = client.get("/api/devices/99999/backup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]


# ======================== GET /api/devices/{id}/backup/{bid} ========================

def test_download_backup_not_found(client, created_device):
    """GET /api/devices/{id}/backup/{bid} 备份不存在 404"""
    resp = client.get(f"/api/devices/{created_device['id']}/backup/99999")
    assert resp.status_code == 404


def test_download_backup_file_missing(client, created_device, db):
    """GET /api/devices/{id}/backup/{bid} 文件丢失 410"""
    backup = Backup(
        device_id=created_device["id"],
        filename="missing.cfg",
        file_path="/nonexistent/missing.cfg",
        backup_type="startup",
        size=100,
        content_hash="abc",
        locked=False,
    )
    db.add(backup)
    db.commit()

    resp = client.get(f"/api/devices/{created_device['id']}/backup/{backup.id}")
    assert resp.status_code == 410


# ======================== DELETE /api/devices/{id}/backup/{bid} ========================

def test_delete_backup_success(client, created_device, db):
    """DELETE /api/devices/{id}/backup/{bid} 成功（mock BackupManager）"""
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
        resp = client.delete(
            f"/api/devices/{created_device['id']}/backup/{backup.id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


def test_delete_backup_locked(client, created_device, db):
    """DELETE /api/devices/{id}/backup/{bid} 锁定备份 403"""
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
        mock_mgr.delete_backup.return_value = False  # locked=True
        MockBM.return_value = mock_mgr
        resp = client.delete(
            f"/api/devices/{created_device['id']}/backup/{backup.id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "锁定" in data["error"]


def test_delete_backup_not_found(client, created_device):
    """DELETE /api/devices/{id}/backup/{bid} 备份不存在"""
    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.delete_backup.side_effect = Exception("备份不存在")
        MockBM.return_value = mock_mgr
        resp = client.delete(
            f"/api/devices/{created_device['id']}/backup/99999"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


# ======================== POST /api/devices/{id}/backup/{bid}/lock ========================

def test_lock_backup_success(client, created_device, db):
    """POST /api/devices/{id}/backup/{bid}/lock 成功"""
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
        assert data["data"]["locked"] is True


def test_lock_backup_unlock(client, created_device, db):
    """POST /api/devices/{id}/backup/{bid}/lock 解锁"""
    backup = Backup(
        device_id=created_device["id"],
        filename="test.cfg",
        file_path="/tmp/test.cfg",
        backup_type="startup",
        size=100,
        content_hash="abc",
        locked=True,
    )
    db.add(backup)
    db.commit()

    with patch("app.routers.backup.BackupManager") as MockBM:
        MockBM.return_value = MagicMock()
        resp = client.post(
            f"/api/devices/{created_device['id']}/backup/{backup.id}/lock",
            json={"locked": False}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["locked"] is False


# ======================== POST /api/devices/{id}/backup/{bid}/restore ========================

def test_restore_backup_success(client, created_device, db):
    """POST /api/devices/{id}/backup/{bid}/restore 成功"""
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


def test_restore_backup_not_found(client, created_device):
    """POST /api/devices/{id}/backup/{bid}/restore 备份不存在"""
    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.restore.side_effect = Exception("备份不存在")
        MockBM.return_value = mock_mgr
        resp = client.post(
            f"/api/devices/{created_device['id']}/backup/99999/restore",
            json={"with_reboot": False}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


# ======================== POST /api/backups ========================

def test_create_all_backups_success(client, created_device):
    """POST /api/backups 全量备份成功"""
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
        assert data["data"]["total"] >= 1


def test_create_all_backups_no_devices(client):
    """POST /api/backups 无设备"""
    # 不创建任何设备 → 应返回 error
    resp = client.post("/api/backups")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "无设备" in data["error"]


def test_create_all_with_types_filter(client, created_device):
    """v2.3 新增：全量备份 body 传 types 过滤"""
    # 每次新 mock，避免前次测试残留
    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.create_backup.return_value = [
            {"id": 1, "type": "startup", "size": 100, "content_hash": "abc",
             "filename": "x.cfg", "created_at": "2026-06-29T10:00:00"}
        ]
        MockBM.return_value = mock_mgr

        # 每次 patch 进入都清空 mock.call_args
        mock_mgr.reset_mock()

        # body={types:["startup"]} → 只备 startup
        r1 = client.post("/api/backups", json={"types": ["startup"]})
        assert r1.status_code == 200
        assert r1.json()["success"] is True
        # 验证传给 BackupManager 的 types（第一次调用 = 第一次 client.post）
        first_call = mock_mgr.create_backup.call_args_list[0]
        passed_types = first_call.kwargs.get("types") or first_call[1].get("types")
        assert passed_types == ["startup"], f"期望 ['startup']，实际 {passed_types}"

        # body={types:["running"]} → 只备 running
        r2 = client.post("/api/backups", json={"types": ["running"]})
        assert r2.status_code == 200
        assert r2.json()["success"] is True

        # body={} → 默认全备（向后兼容）
        r3 = client.post("/api/backups", json={})
        assert r3.status_code == 200
        assert r3.json()["success"] is True


def test_create_all_invalid_type(client, created_device):
    """v2.3 新增：全量备份不支持的类型 → 200 + 错误"""
    r = client.post("/api/backups", json={"types": ["xxx"]})
    assert r.status_code == 200
    assert r.json()["success"] is False
    assert "不支持的备份类型" in r.json()["error"]