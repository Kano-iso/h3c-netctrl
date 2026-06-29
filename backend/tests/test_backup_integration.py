"""配置备份集成测试（v2.3 真实设备）

测试设备：192.168.100.4 (Leaf-03)，SSH 端口 22。
所有测试带 @pytest.mark.integration，默认 skip，需 --integration 显式开启。

覆盖：
- 创建 startup 配置备份
- 验证备份文件存在且有内容
- 列表备份，验证新备份出现在列表中
- 锁定备份，验证锁定后无法删除
- 解锁并删除备份
- 轮转：创建 6 份备份，验证最旧的非锁定备份被移除
"""
import os
import time

import paramiko
import pytest


# ==================== 设备凭据 ====================

BACKUP_HOST = os.getenv("INTEGRATION_BACKUP_HOST", "192.168.100.4")
BACKUP_PORT = int(os.getenv("INTEGRATION_BACKUP_PORT", "22"))
BACKUP_USERNAME = os.getenv("INTEGRATION_BACKUP_USERNAME", "admin")
BACKUP_PASSWORD = os.getenv("INTEGRATION_BACKUP_PASSWORD", "Admin@123")


# ==================== 辅助函数 ====================


def _check_ssh_reachable(host: str, port: int, username: str, password: str, timeout: int = 5) -> bool:
    """快速检测 SSH 是否可达（单次尝试）"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=host, port=port,
            username=username, password=password,
            timeout=timeout, look_for_keys=False, allow_agent=False,
        )
        client.close()
        return True
    except Exception:
        return False


def wait_for_ssh(host: str, port: int, username: str, password: str,
                 timeout: int = 120, interval: int = 5) -> bool:
    """等待 SSH 可达，每 interval 秒重试，最多 timeout 秒

    用于设备重启后等待 SSH 就绪。
    """
    start = time.time()
    while time.time() - start < timeout:
        if _check_ssh_reachable(host, port, username, password, timeout=5):
            return True
        time.sleep(interval)
    return False


def _create_device(client, name: str, host: str, port: int, username: str, password: str) -> dict:
    """通过 API 创建设备，返回 device dict"""
    resp = client.post("/api/devices", json={
        "name": name,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
    })
    assert resp.status_code == 200, f"创建设备失败: {resp.text}"
    data = resp.json()
    assert data["success"] is True, f"创建设备返回失败: {data}"
    return data["data"]


# ==================== 测试用例 ====================


@pytest.mark.integration
def test_create_backup_startup(client):
    """创建 startup 配置备份，验证 API 返回 success=True 且备份有内容"""
    if not _check_ssh_reachable(BACKUP_HOST, BACKUP_PORT, BACKUP_USERNAME, BACKUP_PASSWORD):
        pytest.skip(f"设备 {BACKUP_HOST}:{BACKUP_PORT} SSH 不可达")

    device = _create_device(client, "Leaf-03-Backup", BACKUP_HOST, BACKUP_PORT,
                            BACKUP_USERNAME, BACKUP_PASSWORD)

    try:
        resp = client.post(
            f"/api/devices/{device['id']}/backup",
            json={"types": ["startup"]},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True, f"备份创建失败: {data}"
        assert "backups" in data["data"], f"响应缺少 backups 字段: {data}"
        backups = data["data"]["backups"]
        assert len(backups) >= 1, f"期望至少1份备份，实际 {len(backups)} 份"
        backup = backups[0]
        assert backup["type"] == "startup", f"备份类型应为 startup，实际 {backup['type']}"
        assert backup["size"] > 0, f"备份文件应大于0字节，实际 {backup['size']} 字节"
        assert backup["content_hash"], "备份应包含 content_hash"
        assert backup["filename"], "备份应包含 filename"
    except Exception:
        # 清理设备（setup_db 也会自动清理，但主动清理更安全）
        client.delete(f"/api/devices/{device['id']}")
        raise


@pytest.mark.integration
def test_list_backups_contains_new(client):
    """列表备份，验证新创建的备份出现在列表中"""
    if not _check_ssh_reachable(BACKUP_HOST, BACKUP_PORT, BACKUP_USERNAME, BACKUP_PASSWORD):
        pytest.skip(f"设备 {BACKUP_HOST}:{BACKUP_PORT} SSH 不可达")

    device = _create_device(client, "Leaf-03-List", BACKUP_HOST, BACKUP_PORT,
                            BACKUP_USERNAME, BACKUP_PASSWORD)

    try:
        # 先创建一份备份
        create_resp = client.post(
            f"/api/devices/{device['id']}/backup",
            json={"types": ["startup"]},
        )
        assert create_resp.status_code == 200
        create_data = create_resp.json()
        assert create_data["success"] is True
        new_backup_id = create_data["data"]["backups"][0]["id"]

        # 列表备份
        list_resp = client.get(f"/api/devices/{device['id']}/backup")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data["success"] is True
        assert list_data["data"]["device_id"] == device["id"]
        backups = list_data["data"]["backups"]
        assert len(backups) >= 1, "列表应至少包含1份备份"

        # 验证新备份在列表中
        backup_ids = [b["id"] for b in backups]
        assert new_backup_id in backup_ids, f"新备份 id={new_backup_id} 不在列表中: {backup_ids}"
    except Exception:
        client.delete(f"/api/devices/{device['id']}")
        raise


@pytest.mark.integration
def test_lock_backup_prevents_delete(client):
    """锁定备份后删除应失败，解锁后可删除"""
    if not _check_ssh_reachable(BACKUP_HOST, BACKUP_PORT, BACKUP_USERNAME, BACKUP_PASSWORD):
        pytest.skip(f"设备 {BACKUP_HOST}:{BACKUP_PORT} SSH 不可达")

    device = _create_device(client, "Leaf-03-Lock", BACKUP_HOST, BACKUP_PORT,
                            BACKUP_USERNAME, BACKUP_PASSWORD)

    try:
        # 创建备份
        create_resp = client.post(
            f"/api/devices/{device['id']}/backup",
            json={"types": ["startup"]},
        )
        assert create_resp.status_code == 200
        create_data = create_resp.json()
        assert create_data["success"] is True
        backup_id = create_data["data"]["backups"][0]["id"]

        # 锁定
        lock_resp = client.post(
            f"/api/devices/{device['id']}/backup/{backup_id}/lock",
            json={"locked": True},
        )
        assert lock_resp.status_code == 200
        lock_data = lock_resp.json()
        assert lock_data["success"] is True, f"锁定失败: {lock_data}"
        assert lock_data["data"]["locked"] is True

        # 尝试删除锁定备份 → 应失败
        del_resp = client.delete(
            f"/api/devices/{device['id']}/backup/{backup_id}",
        )
        assert del_resp.status_code == 200
        del_data = del_resp.json()
        assert del_data["success"] is False, f"锁定备份不应被删除: {del_data}"
        assert "锁定" in del_data.get("error", ""), f"错误信息应包含'锁定': {del_data}"

        # 解锁
        unlock_resp = client.post(
            f"/api/devices/{device['id']}/backup/{backup_id}/lock",
            json={"locked": False},
        )
        assert unlock_resp.status_code == 200
        unlock_data = unlock_resp.json()
        assert unlock_data["success"] is True, f"解锁失败: {unlock_data}"

        # 删除
        del2_resp = client.delete(
            f"/api/devices/{device['id']}/backup/{backup_id}",
        )
        assert del2_resp.status_code == 200
        del2_data = del2_resp.json()
        assert del2_data["success"] is True, f"解锁后删除失败: {del2_data}"
    except Exception:
        client.delete(f"/api/devices/{device['id']}")
        raise


# ======================== 单元测试（不需设备） ========================

def test_rotate_respects_locked_backups():
    """v2.3 修复：locked 备份永远不被轮转

    场景：device 有 5 份非锁定 + 2 份锁定备份（共 7 份），keep=5
    期望：2 份锁定保留 + 5 份非锁定保留 = 7 份总数（无删除）
    """
    from app.database import Base, engine, SessionLocal
    from app.utils.backup_manager import BackupManager
    from app.models import Backup, Device
    from datetime import datetime, timedelta

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.query(Backup).delete()
        db.query(Device).delete()
        db.commit()

        device = Device(
            name="rotate_test",
            host="192.168.100.4",
            port=22,
            username="x",
            password_encrypted="x",
        )
        db.add(device)
        db.commit()
        device_id = device.id

        now = datetime.utcnow()
        # 5 份非锁定
        for i in range(5):
            db.add(Backup(
                device_id=device_id,
                filename=f"nonlocked_{i}.cfg",
                file_path=f"/tmp/test_{i}.cfg",
                backup_type="startup",
                size=100,
                content_hash=f"nl{i}",
                locked=False,
                created_at=now + timedelta(seconds=i),
            ))
        # 2 份锁定
        for i in range(2):
            db.add(Backup(
                device_id=device_id,
                filename=f"locked_{i}.cfg",
                file_path=f"/tmp/locked_{i}.cfg",
                backup_type="startup",
                size=100,
                content_hash=f"lk{i}",
                locked=True,
                created_at=now + timedelta(seconds=10 + i),
            ))
        db.commit()

        mgr = BackupManager(device_id, "192.168.100.4", 22, "x", "x")
        deleted = mgr.rotate(device_id, keep=5, db=db)

        all_backups = db.query(Backup).filter(Backup.device_id == device_id).all()
        locked = [b for b in all_backups if b.locked]
        unlocked = [b for b in all_backups if not b.locked]

        # 锁定全保留
        assert len(locked) == 2, f"锁定应保留 2，实际 {len(locked)}"
        # 非锁定保留 5
        assert len(unlocked) == 5, f"非锁定应保留 5，实际 {len(unlocked)}"
        # 删除数 = 0（5 非锁定 - keep 5 = 0）
        assert deleted == 0, f"期望删除 0，实际 {deleted}"
        # 总数 7
        assert len(all_backups) == 7
    finally:
        db.query(Backup).delete()
        db.query(Device).delete()
        db.commit()
        db.close()


def test_rotate_deletes_oldest_unlocked_only():
    """v2.3 修复：锁定备份不被轮转删除

    场景：device 有 7 份非锁定 + 1 份锁定（共 8 份），keep=5
    期望：删除 2 份最旧的非锁定，保留 5 份非锁定 + 1 份锁定 = 6 份
    """
    from app.database import Base, engine, SessionLocal
    from app.utils.backup_manager import BackupManager
    from app.models import Backup, Device
    from datetime import datetime, timedelta

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.query(Backup).delete()
        db.query(Device).delete()
        db.commit()

        device = Device(
            name="rotate_test2",
            host="192.168.100.4",
            port=22,
            username="x",
            password_encrypted="x",
        )
        db.add(device)
        db.commit()
        device_id = device.id

        now = datetime.utcnow()
        # 7 份非锁定
        for i in range(7):
            db.add(Backup(
                device_id=device_id,
                filename=f"nl_{i}.cfg",
                file_path=f"/tmp/nl_{i}.cfg",
                backup_type="startup",
                size=100,
                content_hash=f"nl{i}",
                locked=False,
                created_at=now + timedelta(seconds=i),
            ))
        # 1 份锁定
        db.add(Backup(
            device_id=device_id,
            filename="locked.cfg",
            file_path="/tmp/locked.cfg",
            backup_type="startup",
            size=100,
            content_hash="locked",
            locked=True,
            created_at=now + timedelta(seconds=10),
        ))
        db.commit()

        mgr = BackupManager(device_id, "192.168.100.4", 22, "x", "x")
        deleted = mgr.rotate(device_id, keep=5, db=db)

        all_backups = db.query(Backup).filter(Backup.device_id == device_id).all()
        locked = [b for b in all_backups if b.locked]
        unlocked = [b for b in all_backups if not b.locked]

        # 锁定 1 保留
        assert len(locked) == 1
        # 非锁定 5 保留（最新 nl2-nl6）
        assert len(unlocked) == 5
        hashes = {b.content_hash for b in unlocked}
        assert hashes == {"nl2", "nl3", "nl4", "nl5", "nl6"}, f"期望 nl2-nl6，实际 {hashes}"
        # 删除 2
        assert deleted == 2, f"期望删除 2，实际 {deleted}"
        # 总数 6
        assert len(all_backups) == 6
    finally:
        db.query(Backup).delete()
        db.query(Device).delete()
        db.commit()
        db.close()


def test_rotate_protects_locked_from_deletion():
    """v2.3 修复：锁定备份按时间也参与排序，但不被删除

    场景：1 份旧锁定 + 5 份新非锁定，keep=5
    期望：保留旧锁定 + 5 份新非锁定 = 6 份总数（无删除）
    旧 bug：旧锁定被轮转删除（应该被保护）
    """
    from app.database import Base, engine, SessionLocal
    from app.utils.backup_manager import BackupManager
    from app.models import Backup, Device
    from datetime import datetime, timedelta

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        db.query(Backup).delete()
        db.query(Device).delete()
        db.commit()

        device = Device(
            name="rotate_test3",
            host="192.168.100.4",
            port=22,
            username="x",
            password_encrypted="x",
        )
        db.add(device)
        db.commit()
        device_id = device.id

        now = datetime.utcnow()
        # 1 份旧的锁定备份（最早创建）
        db.add(Backup(
            device_id=device_id,
            filename="old_locked.cfg",
            file_path="/tmp/old_locked.cfg",
            backup_type="startup",
            size=100,
            content_hash="old_locked",
            locked=True,
            created_at=now,  # 最早
        ))
        # 5 份新的非锁定
        for i in range(5):
            db.add(Backup(
                device_id=device_id,
                filename=f"new_{i}.cfg",
                file_path=f"/tmp/new_{i}.cfg",
                backup_type="startup",
                size=100,
                content_hash=f"new{i}",
                locked=False,
                created_at=now + timedelta(seconds=10 + i),
            ))
        db.commit()

        mgr = BackupManager(device_id, "192.168.100.4", 22, "x", "x")
        deleted = mgr.rotate(device_id, keep=5, db=db)

        all_backups = db.query(Backup).filter(Backup.device_id == device_id).all()
        locked = [b for b in all_backups if b.locked]

        # 旧锁定必须保留
        assert len(locked) == 1, f"旧锁定应保留，实际删除"
        assert locked[0].content_hash == "old_locked"
        # 删除 0
        assert deleted == 0
    finally:
        db.query(Backup).delete()
        db.query(Device).delete()
        db.commit()
        db.close()


@pytest.mark.integration
def test_backup_rotation_keeps_limit(client):
    """创建 6 份备份，验证轮转后只保留 BACKUP_KEEP=5 份，最旧的非锁定备份被移除"""
    if not _check_ssh_reachable(BACKUP_HOST, BACKUP_PORT, BACKUP_USERNAME, BACKUP_PASSWORD):
        pytest.skip(f"设备 {BACKUP_HOST}:{BACKUP_PORT} SSH 不可达")

    device = _create_device(client, "Leaf-03-Rotate", BACKUP_HOST, BACKUP_PORT,
                            BACKUP_USERNAME, BACKUP_PASSWORD)

    try:
        # 创建 6 份 startup 备份（BACKUP_KEEP=5，第6份触发轮转移除最旧）
        for i in range(6):
            resp = client.post(
                f"/api/devices/{device['id']}/backup",
                json={"types": ["startup"]},
            )
            assert resp.status_code == 200, f"第 {i+1} 次备份请求失败: {resp.text}"
            data = resp.json()
            assert data["success"] is True, f"第 {i+1} 次备份失败: {data}"

        # 列表备份，验证总数 ≤ 5
        list_resp = client.get(f"/api/devices/{device['id']}/backup")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data["success"] is True
        backups = list_data["data"]["backups"]
        total = list_data["data"]["total"]
        assert total <= 5, f"轮转后应保留 ≤5 份备份，实际 {total} 份"
        assert len(backups) == total, f"备份列表长度与 total 不一致: {len(backups)} vs {total}"
    except Exception:
        client.delete(f"/api/devices/{device['id']}")
        raise