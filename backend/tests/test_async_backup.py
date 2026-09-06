"""异步备份/回滚 API 端点测试（v24-feat-async-backup-status）

覆盖 4 个异步端点：
- POST /api/devices/{id}/backup-async
- POST /api/devices/{id}/backup/{bid}/restore-async
- GET  /api/tasks/{task_id}
- POST /api/tasks/{task_id}/cancel

注意：task_manager 是全局单例，max_workers=1 串行执行。
每个测试必须等待任务到达终态，避免跨测试污染。
"""
import time
from unittest.mock import MagicMock, patch

from app.models import Backup


def _wait_task_terminal(client, task_id: int, timeout: float = 5.0) -> dict:
    """轮询任务状态直到终态（success/failed/cancelled），超时抛错"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        if not data["success"]:
            return data
        status = data["data"]["status"]
        if status in ("success", "failed", "cancelled"):
            return data["data"]
        time.sleep(0.05)
    raise TimeoutError(f"任务 {task_id} 在 {timeout}s 内未到达终态")


# ======================== POST /api/devices/{id}/backup-async ========================

def test_backup_async_submit_success(client, created_device):
    """POST /api/devices/{id}/backup-async 成功提交，返回 task_id + 轮询到 success"""
    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.create_backup.return_value = [
            {"id": 1, "type": "startup", "size": 100, "content_hash": "abc",
             "filename": "x.cfg", "created_at": "2026-06-29T10:00:00"}
        ]
        MockBM.return_value = mock_mgr
        resp = client.post(
            f"/api/devices/{created_device['id']}/backup-async",
            json={"types": ["startup"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "task_id" in data["data"]
        assert data["data"]["status"] == "pending"
        assert data["data"]["status_url"] == f"/api/tasks/{data['data']['task_id']}"

        task_data = _wait_task_terminal(client, data["data"]["task_id"])
        assert task_data["status"] == "success"
        assert task_data["progress"] == 100
        assert task_data["task_type"] == "backup"
        assert task_data["device_id"] == created_device["id"]
        assert task_data["result"] is not None


def test_backup_async_device_not_found(client):
    """POST /api/devices/{id}/backup-async 设备不存在"""
    resp = client.post("/api/devices/99999/backup-async", json={"types": ["startup"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]


def test_backup_async_invalid_type(client, created_device):
    """POST /api/devices/{id}/backup-async 类型非法"""
    resp = client.post(
        f"/api/devices/{created_device['id']}/backup-async",
        json={"types": ["invalid"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不支持" in data["error"]


def test_backup_async_failed(client, created_device):
    """POST /api/devices/{id}/backup-async 备份全失败 → 任务 status=failed"""
    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.create_backup.return_value = []  # 空列表 = 全失败
        MockBM.return_value = mock_mgr
        resp = client.post(
            f"/api/devices/{created_device['id']}/backup-async",
            json={"types": ["startup"]},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        task_id = resp.json()["data"]["task_id"]

        task_data = _wait_task_terminal(client, task_id)
        assert task_data["status"] == "failed"
        assert "失败" in task_data["error"]


# ======================== POST /api/devices/{id}/backup/{bid}/restore-async ========================

def test_restore_async_submit_success(client, created_device, db):
    """POST /api/devices/{id}/backup/{bid}/restore-async 成功提交 + 轮询到 success"""
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
            f"/api/devices/{created_device['id']}/backup/{backup.id}/restore-async",
            json={"with_reboot": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        task_id = data["data"]["task_id"]

        task_data = _wait_task_terminal(client, task_id)
        assert task_data["status"] == "success"
        assert task_data["task_type"] == "restore"


def test_restore_async_device_not_found(client):
    """POST /api/devices/{id}/backup/{bid}/restore-async 设备不存在"""
    resp = client.post(
        f"/api/devices/99999/backup/1/restore-async",
        json={"with_reboot": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]


def test_restore_async_backup_not_found(client, created_device):
    """POST /api/devices/{id}/backup/{bid}/restore-async 备份不存在"""
    resp = client.post(
        f"/api/devices/{created_device['id']}/backup/99999/restore-async",
        json={"with_reboot": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]


# ======================== GET /api/tasks/{task_id} ========================

def test_get_task_status_not_found(client):
    """GET /api/tasks/{task_id} 任务不存在"""
    resp = client.get("/api/tasks/99999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]


def test_get_task_status_running_then_success(client, created_device):
    """GET /api/tasks/{task_id} 轮询路径：能捕获中间态并最终 success"""
    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()

        def slow_create(*args, **kwargs):
            time.sleep(0.3)
            return [{"id": 1, "type": "startup", "size": 100, "content_hash": "abc",
                     "filename": "x.cfg", "created_at": "2026-06-29T10:00:00"}]
        mock_mgr.create_backup.side_effect = slow_create
        MockBM.return_value = mock_mgr

        resp = client.post(
            f"/api/devices/{created_device['id']}/backup-async",
            json={"types": ["startup"]},
        )
        task_id = resp.json()["data"]["task_id"]

        # 捕获中间态
        time.sleep(0.1)
        mid_resp = client.get(f"/api/tasks/{task_id}")
        assert mid_resp.status_code == 200
        mid_data = mid_resp.json()["data"]
        assert mid_data["status"] in ("pending", "running", "success")

        # 等待终态
        task_data = _wait_task_terminal(client, task_id)
        assert task_data["status"] == "success"
        assert task_data["progress"] == 100


# ======================== POST /api/tasks/{task_id}/cancel ========================

def test_cancel_task_success(client, created_device):
    """POST /api/tasks/{task_id}/cancel 取消正在运行的任务

    _async_backup_fn 流程：progress_cb(10) → 检查 cancel → create_backup → progress_cb(90) → return
    _run 在 fn 返回后再检查 cancel_event，若已 set 则标记 cancelled。
    """
    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()

        def slow_create(*args, **kwargs):
            time.sleep(1.0)  # 阻塞 1s，期间从外部触发 cancel
            return [{"id": 1, "type": "startup", "size": 100, "content_hash": "abc",
                     "filename": "x.cfg", "created_at": "2026-06-29T10:00:00"}]
        mock_mgr.create_backup.side_effect = slow_create
        MockBM.return_value = mock_mgr

        resp = client.post(
            f"/api/devices/{created_device['id']}/backup-async",
            json={"types": ["startup"]},
        )
        task_id = resp.json()["data"]["task_id"]

        # 等任务进入 running（create_backup 已开始执行）
        time.sleep(0.3)

        cancel_resp = client.post(f"/api/tasks/{task_id}/cancel")
        assert cancel_resp.status_code == 200
        cancel_data = cancel_resp.json()
        assert cancel_data["success"] is True
        assert cancel_data["data"]["cancelled"] is True

        # 等待终态（create_backup 1s 后返回，_run 检查 cancel_event → cancelled）
        task_data = _wait_task_terminal(client, task_id, timeout=5)
        assert task_data["status"] == "cancelled"


def test_cancel_task_not_found(client):
    """POST /api/tasks/{task_id}/cancel 任务不存在"""
    resp = client.post("/api/tasks/99999/cancel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["data"]["cancelled"] is False


def test_cancel_task_already_terminal(client, created_device):
    """POST /api/tasks/{task_id}/cancel 任务已完成，无法取消"""
    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()
        mock_mgr.create_backup.return_value = [
            {"id": 1, "type": "startup", "size": 100, "content_hash": "abc",
             "filename": "x.cfg", "created_at": "2026-06-29T10:00:00"}
        ]
        MockBM.return_value = mock_mgr

        resp = client.post(
            f"/api/devices/{created_device['id']}/backup-async",
            json={"types": ["startup"]},
        )
        task_id = resp.json()["data"]["task_id"]

        # 等待任务完成
        _wait_task_terminal(client, task_id)

        # 已 success，无法取消
        cancel_resp = client.post(f"/api/tasks/{task_id}/cancel")
        assert cancel_resp.status_code == 200
        cancel_data = cancel_resp.json()
        assert cancel_data["success"] is False
        assert cancel_data["data"]["cancelled"] is False


# ======================== POST /api/backups-async（v241-supplement Task 8.4）========================


def test_backups_async_submit_immediate_return(client, created_device):
    """POST /api/backups-async 立即返回 task_id（不阻塞 7 设备串行）"""
    with patch("app.routers.backup.BackupManager") as MockBM:
        mock_mgr = MagicMock()

        def slow_create(*args, **kwargs):
            time.sleep(0.5)  # 模拟备份耗时
            return [{"id": 1, "type": "startup", "size": 100, "content_hash": "abc",
                     "filename": "x.cfg", "created_at": "2026-06-29T10:00:00"}]
        mock_mgr.create_backup.side_effect = slow_create
        MockBM.return_value = mock_mgr

        start = time.time()
        resp = client.post("/api/backups-async", json={"types": ["startup"]})
        elapsed = time.time() - start
        # 关键断言：< 200ms 返回（不阻塞等待所有设备）
        assert elapsed < 0.2, f"异步端点阻塞 {elapsed}s，未立即返回"

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "task_id" in data["data"]
        assert data["data"]["status"] == "pending"
        assert data["data"]["status_url"] == f"/api/tasks/{data['data']['task_id']}"


def test_backups_async_invalid_type(client):
    """POST /api/backups-async 类型非法"""
    resp = client.post("/api/backups-async", json={"types": ["invalid"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不支持" in data["error"]


def test_backups_async_success_with_2_devices(client, db):
    """POST /api/backups-async 2 设备都成功 → task success + result 含 success_count=2"""
    from app.models import Device
    from app.utils.crypto import encrypt_password
    enc1 = encrypt_password("Pass123!")
    enc2 = encrypt_password("Pass456!")

    d1 = Device(name="D1", host="1.1.1.1", port=830, username="u", password_encrypted=enc1)
    d2 = Device(name="D2", host="1.1.1.2", port=830, username="u", password_encrypted=enc2)
    db.add_all([d1, d2])
    db.commit()

    with patch("app.routers.backup.check_asset_online"), \
         patch("app.routers.backup._make_manager") as MockMakeManager:
        mock_mgr = MagicMock()
        mock_mgr.create_backup.return_value = [
            {"id": 1, "type": "startup", "size": 100, "content_hash": "abc",
             "filename": "x.cfg", "created_at": "2026-06-29T10:00:00"}
        ]
        MockMakeManager.return_value = mock_mgr

        resp = client.post("/api/backups-async", json={"types": ["startup"]})
        task_id = resp.json()["data"]["task_id"]

        task_data = _wait_task_terminal(client, task_id, timeout=10)
        assert task_data["status"] == "success"
        assert task_data["progress"] == 100
        assert task_data["task_type"] == "backup_all"
        assert task_data["result"]["total"] == 2
        assert task_data["result"]["success_count"] == 2
        assert task_data["result"]["failed_count"] == 0


def test_backups_async_empty_devices(client):
    """POST /api/backups-async 无设备时任务直接 failed（拉不到 device）"""
    with patch("app.routers.backup._async_backup_all_fn") as MockFn:
        # 模拟 _async_backup_all_fn 直接抛"无设备"
        def boom(*args, **kwargs):
            raise Exception("无设备可备份")
        MockFn.side_effect = boom

        resp = client.post("/api/backups-async", json={"types": ["startup"]})
        task_id = resp.json()["data"]["task_id"]

        task_data = _wait_task_terminal(client, task_id, timeout=5)
        assert task_data["status"] == "failed"
        assert "无设备" in task_data["error"]
