"""测试 backup rotation: v2.3.1 patch 改 BACKUP_KEEP 语义

v2.3.1 改：BACKUP_KEEP = "总份数"（含锁定），锁定优先保留不被删
v2.2.0 旧语义：BACKUP_KEEP = "非锁定份数"

锁定备份永远不被轮转删除（v2.2.0 承诺保留）。
锁定数 ≥ keep → 不删任何非锁定（用户锁太多属预期）。
锁定数 < keep → to_delete = 总份数 - keep，从最旧非锁定删。
"""
import os
import sys

import pytest

# 1) 添加 backend 目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def db_session():
    """内存 SQLite + create_all"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def make_device(db_session):
    """工厂函数：创建测试设备，返回 id"""
    from app.models import Device
    from app.utils.crypto import encrypt_password
    devices_created = []

    def _make(name="test_device"):
        dev = Device(
            name=name,
            host="192.0.2.1",  # RFC 5737 测试地址
            port=22,
            username="test",
            password_encrypted=encrypt_password("test"),
        )
        db_session.add(dev)
        db_session.commit()
        devices_created.append(dev.id)
        return dev.id

    return _make


def _make_backup(db_session, device_id, backup_type, locked, filename, created_offset_min=0):
    """工厂函数：创建备份记录"""
    from datetime import datetime, timedelta
    from app.models import Backup
    b = Backup(
        device_id=device_id,
        filename=filename,
        file_path=f"/tmp/{filename}",
        backup_type=backup_type,
        size=1000,
        content_hash="abc123",
        locked=locked,
    )
    # 手动设 created_at（默认是 now）
    b.created_at = datetime.utcnow() + timedelta(minutes=created_offset_min)
    db_session.add(b)
    db_session.commit()
    return b.id


# ============================================================
# v2.3.1 patch：BACKUP_KEEP 语义 = 总份数（含锁定）
# ============================================================


def test_rotation_5_unlocked_2_locked_keeps_5_total(db_session, make_device):
    """5 非锁定 + 2 锁定 = 7 份，keep=5，v2.3.1 期望：删 2 最旧非锁定，剩 5（3+2）

    v2.3.1 改：BACKUP_KEEP = 总份数。锁定数 2 < keep 5 → 删 2 份最旧非锁定。
    剩余：3 非锁定 + 2 锁定 = 5 份总数。
    """
    from app.utils.backup_manager import BackupManager
    from app.models import Backup
    dev_id = make_device()

    # 5 非锁定（按时间 0..4）
    unlocked_ids = []
    for i in range(5):
        unlocked_ids.append(_make_backup(db_session, dev_id, "running", False, f"u{i}.cfg", i))
    # 2 锁定（按时间 5,6）
    locked_ids = []
    for i in range(2):
        locked_ids.append(_make_backup(db_session, dev_id, "running", True, f"l{i}.cfg", 5 + i))

    mgr = BackupManager(device_id=dev_id, host="192.0.2.1", port=22,
                        username="test", password="test", db=db_session)
    deleted = mgr.rotate(device_id=dev_id, keep=5, db=db_session)
    assert deleted == 2, f"应删 2 个最旧非锁定（u0, u1），实际删 {deleted}"

    # 验证 u0, u1 已删，u2-u4 还在
    for i in range(2):
        b = db_session.query(Backup).filter(Backup.id == unlocked_ids[i]).first()
        assert b is None, f"u{i} 应被删"
    for i in range(2, 5):
        b = db_session.query(Backup).filter(Backup.id == unlocked_ids[i]).first()
        assert b is not None, f"u{i} 应保留"

    # 验证锁定全保留
    for i in range(2):
        b = db_session.query(Backup).filter(Backup.id == locked_ids[i]).first()
        assert b is not None, f"l{i} 不应被删"
        assert b.locked is True

    # 总数 = 5（3 非锁定 + 2 锁定）
    remaining = db_session.query(Backup).filter(Backup.device_id == dev_id).count()
    assert remaining == 5, f"应剩 5 份总数，实际 {remaining}"


def test_rotation_7_unlocked_1_locked_keeps_5_total(db_session, make_device):
    """7 非锁定 + 1 锁定 = 8 份，keep=5，v2.3.1 期望：删 3 最旧非锁定，剩 5（4+1）"""
    from app.utils.backup_manager import BackupManager
    from app.models import Backup
    dev_id = make_device()

    unlocked_ids = []
    for i in range(7):
        unlocked_ids.append(_make_backup(db_session, dev_id, "running", False, f"u{i}.cfg", i))
    locked_id = _make_backup(db_session, dev_id, "running", True, "locked_mid.cfg", 3)

    mgr = BackupManager(device_id=dev_id, host="192.0.2.1", port=22,
                        username="test", password="test", db=db_session)
    deleted = mgr.rotate(device_id=dev_id, keep=5, db=db_session)
    assert deleted == 3, f"应删 3 个最旧非锁定（u0,u1,u2），实际删 {deleted}"

    # 验证锁定还在
    locked = db_session.query(Backup).filter(Backup.id == locked_id).first()
    assert locked is not None, "锁定不应被删"
    assert locked.locked is True

    # 总数 = 5（4 非锁定 + 1 锁定）
    remaining = db_session.query(Backup).filter(Backup.device_id == dev_id).count()
    assert remaining == 5, f"应剩 5 份总数，实际 {remaining}"


def test_rotation_old_locked_protected_keeps_5_total(db_session, make_device):
    """1 旧锁定 + 5 新非锁定 = 6 份，keep=5，v2.3.1 期望：删 1 最旧非锁定，剩 5（4+1）"""
    from app.utils.backup_manager import BackupManager
    from app.models import Backup
    dev_id = make_device()

    # 1 旧锁定（最早 -10 分钟）
    old_locked_id = _make_backup(db_session, dev_id, "startup", True, "old_locked.cfg", -10)
    # 5 非锁定（0..4）
    unlocked_ids = []
    for i in range(5):
        unlocked_ids.append(_make_backup(db_session, dev_id, "running", False, f"u{i}.cfg", i))

    mgr = BackupManager(device_id=dev_id, host="192.0.2.1", port=22,
                        username="test", password="test", db=db_session)
    deleted = mgr.rotate(device_id=dev_id, keep=5, db=db_session)
    assert deleted == 1, f"应删 1 个最旧非锁定（u0），实际删 {deleted}"

    # 旧锁定还在
    old_locked = db_session.query(Backup).filter(Backup.id == old_locked_id).first()
    assert old_locked is not None, "旧锁定不应被删"
    assert old_locked.locked is True

    # u0 删，u1-u4 留
    b = db_session.query(Backup).filter(Backup.id == unlocked_ids[0]).first()
    assert b is None, "u0 应被删"
    for i in range(1, 5):
        b = db_session.query(Backup).filter(Backup.id == unlocked_ids[i]).first()
        assert b is not None, f"u{i} 应保留"

    # 总数 = 5
    remaining = db_session.query(Backup).filter(Backup.device_id == dev_id).count()
    assert remaining == 5, f"应剩 5 份总数，实际 {remaining}"


def test_rotation_5_locked_0_unlocked_keeps_all(db_session, make_device):
    """5 锁定 + 0 非锁定 = 5 份，keep=5，v2.3.1 期望：删 0（用户锁的，刚刚好 keep）"""
    from app.utils.backup_manager import BackupManager
    from app.models import Backup
    dev_id = make_device()

    for i in range(5):
        _make_backup(db_session, dev_id, "running", True, f"l{i}.cfg", i)

    mgr = BackupManager(device_id=dev_id, host="192.0.2.1", port=22,
                        username="test", password="test", db=db_session)
    deleted = mgr.rotate(device_id=dev_id, keep=5, db=db_session)
    assert deleted == 0, f"5 锁定 == keep=5，不应删，实际删 {deleted}"

    remaining = db_session.query(Backup).filter(Backup.device_id == dev_id).count()
    assert remaining == 5, f"应剩 5 份，实际 {remaining}"


def test_rotation_5_locked_2_unlocked_keeps_all_locked(db_session, make_device):
    """5 锁定 + 2 非锁定 = 7 份，keep=5，v2.3.1 期望：删 0（锁定数 ≥ keep，不删任何）

    用户锁太多属预期行为：保留 7 份（5 锁定 + 2 非锁定），不删任何。
    """
    from app.utils.backup_manager import BackupManager
    from app.models import Backup
    dev_id = make_device()

    for i in range(5):
        _make_backup(db_session, dev_id, "running", True, f"l{i}.cfg", i)
    for i in range(2):
        _make_backup(db_session, dev_id, "running", False, f"u{i}.cfg", 5 + i)

    mgr = BackupManager(device_id=dev_id, host="192.0.2.1", port=22,
                        username="test", password="test", db=db_session)
    deleted = mgr.rotate(device_id=dev_id, keep=5, db=db_session)
    assert deleted == 0, f"锁定 5 ≥ keep=5，不应删，实际删 {deleted}"

    remaining = db_session.query(Backup).filter(Backup.device_id == dev_id).count()
    assert remaining == 7, f"应保留 7 份（用户锁太多属预期），实际 {remaining}"


def test_rotation_0_locked_7_unlocked_keeps_5(db_session, make_device):
    """0 锁定 + 7 非锁定 = 7 份，keep=5，v2.3.1 期望：删 2 最旧，剩 5（行为不变）"""
    from app.utils.backup_manager import BackupManager
    from app.models import Backup
    dev_id = make_device()

    for i in range(7):
        _make_backup(db_session, dev_id, "running", False, f"u{i}.cfg", i)

    mgr = BackupManager(device_id=dev_id, host="192.0.2.1", port=22,
                        username="test", password="test", db=db_session)
    deleted = mgr.rotate(device_id=dev_id, keep=5, db=db_session)
    assert deleted == 2, f"应删 2 个最旧非锁定（u0,u1），实际删 {deleted}"

    remaining = db_session.query(Backup).filter(Backup.device_id == dev_id).count()
    assert remaining == 5, f"应剩 5 份，实际 {remaining}"


def test_rotation_empty(db_session, make_device):
    """0 份，keep=5，期望：删 0"""
    from app.utils.backup_manager import BackupManager
    dev_id = make_device()

    mgr = BackupManager(device_id=dev_id, host="192.0.2.1", port=22,
                        username="test", password="test", db=db_session)
    deleted = mgr.rotate(device_id=dev_id, keep=5, db=db_session)
    assert deleted == 0, f"空设备不应删，实际删 {deleted}"
