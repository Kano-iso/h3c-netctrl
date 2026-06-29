"""测试 backup rotation: 锁定备份不被轮转删除

v2.3 用户提问：锁定备份能否被轮转掉？答：不能。
v2.2.0 老代码已按"非锁定 keep N"轮转，本测试用例保护此逻辑。
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


def test_rotation_5_unlocked_2_locked_keeps_all(db_session, make_device):
    """5 非锁定 + 2 锁定 = 7 份，keep=5，期望：rotate(0)"""
    from app.utils.backup_manager import BackupManager
    dev_id = make_device()

    # 创建 7 份（5 非锁定 + 2 锁定）
    for i in range(5):
        _make_backup(db_session, dev_id, "running", False, f"f{i}.cfg", i)
    for i in range(2):
        _make_backup(db_session, dev_id, "running", True, f"locked{i}.cfg", 5 + i)

    mgr = BackupManager(device_id=dev_id, host="192.0.2.1", port=22,
                        username="test", password="test", db=db_session)
    deleted = mgr.rotate(device_id=dev_id, keep=5, db=db_session)
    assert deleted == 0, f"7 份 ≤ keep=5 + 2 锁定，不应删，实际删 {deleted}"

    remaining = db_session.query(__import__('app.models', fromlist=['Backup']).Backup).filter(
        __import__('app.models', fromlist=['Backup']).Backup.device_id == dev_id
    ).count()
    assert remaining == 7, f"应保留 7 份，实际 {remaining}"


def test_rotation_7_unlocked_1_locked_keeps_5_plus_locked(db_session, make_device):
    """7 非锁定 + 1 锁定 = 8 份，keep=5，期望：删 2 个最旧非锁定，剩 5+1"""
    from app.utils.backup_manager import BackupManager
    from app.models import Backup
    dev_id = make_device()

    # 7 个非锁定（按 created_at 升序：f0 最早，f6 最新）
    for i in range(7):
        _make_backup(db_session, dev_id, "running", False, f"u{i}.cfg", i)
    # 1 个锁定（中间时间）
    locked_id = _make_backup(db_session, dev_id, "running", True, "locked_mid.cfg", 3)

    mgr = BackupManager(device_id=dev_id, host="192.0.2.1", port=22,
                        username="test", password="test", db=db_session)
    deleted = mgr.rotate(device_id=dev_id, keep=5, db=db_session)
    assert deleted == 2, f"应删 2 个最旧非锁定，实际删 {deleted}"

    # 验证锁定还在
    locked = db_session.query(Backup).filter(Backup.id == locked_id).first()
    assert locked is not None, "锁定备份不应被删"
    assert locked.locked is True

    # 验证剩 6 份（5 非锁定 + 1 锁定）
    remaining = db_session.query(Backup).filter(Backup.device_id == dev_id).count()
    assert remaining == 6, f"应剩 6 份，实际 {remaining}"


def test_rotation_old_locked_protected(db_session, make_device):
    """1 旧锁定 + 5 新非锁定 = 6 份，keep=5，期望：rotate(0)（保护旧锁定）"""
    from app.utils.backup_manager import BackupManager
    from app.models import Backup
    dev_id = make_device()

    # 1 旧锁定（最早时间 -10 分钟）
    old_locked_id = _make_backup(db_session, dev_id, "startup", True, "old_locked.cfg", -10)
    # 5 个非锁定（最新）
    for i in range(5):
        _make_backup(db_session, dev_id, "running", False, f"u{i}.cfg", i)

    mgr = BackupManager(device_id=dev_id, host="192.0.2.1", port=22,
                        username="test", password="test", db=db_session)
    deleted = mgr.rotate(device_id=dev_id, keep=5, db=db_session)
    assert deleted == 0, f"旧锁定在最前，不应被删，实际删 {deleted}"

    # 验证旧锁定还在
    old_locked = db_session.query(Backup).filter(Backup.id == old_locked_id).first()
    assert old_locked is not None, "旧锁定不应被删"
    assert old_locked.locked is True
