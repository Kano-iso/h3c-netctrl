"""asset_guard 校验函数测试（v2.6.1 fix-asset-backup-state-sync Task 1.6）

覆盖 4 象限：
- online + force=False → True（放行）
- offline + force=False → BackupError
- never_collected + force=False → BackupError
- offline + force=True → True（跳过 + WARNING 日志）
"""
import logging

import pytest

from app.models import Asset, Device
from app.utils.asset_guard import check_asset_online
from app.utils.backup_manager import BackupError


def _make_device(db, host="192.168.100.1"):
    """辅助：插一条 device 记录（绕过密码加密）"""
    d = Device(
        name=f"test-{host}",
        host=host,
        port=22,
        username="admin",
        password_encrypted="x",
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _make_asset(db, device_id, status):
    """辅助：插一条 asset 记录"""
    a = Asset(device_id=device_id, status=status)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ======================== online 场景 ========================

def test_check_asset_online_when_online_returns_true(db):
    """asset.status=online + force=False → 放行"""
    d = _make_device(db)
    _make_asset(db, d.id, "online")
    assert check_asset_online(d.id) is True


# ======================== offline 场景 ========================

def test_check_asset_online_when_offline_raises(db):
    """asset.status=offline + force=False → 抛 BackupError"""
    d = _make_device(db)
    _make_asset(db, d.id, "offline")
    with pytest.raises(BackupError, match="BACKUP_DEVICE_OFFLINE"):
        check_asset_online(d.id)


def test_check_asset_online_when_stale_raises(db):
    """asset.status=stale + force=False → 抛 BackupError"""
    d = _make_device(db)
    _make_asset(db, d.id, "stale")
    with pytest.raises(BackupError, match="BACKUP_DEVICE_OFFLINE"):
        check_asset_online(d.id)


# ======================== never_collected 场景 ========================

def test_check_asset_online_when_never_collected_raises(db):
    """设备无 asset 记录 + force=False → 抛 BackupError（never_collected）"""
    d = _make_device(db)
    # 不插 asset 记录
    with pytest.raises(BackupError, match="BACKUP_DEVICE_OFFLINE"):
        check_asset_online(d.id)


# ======================== force=True 场景 ========================

def test_check_asset_online_with_force_skips_check(db, caplog):
    """force=True → 跳过校验 + WARNING 日志（审计）"""
    d = _make_device(db)
    _make_asset(db, d.id, "offline")
    with caplog.at_level(logging.WARNING, logger="app"):
        assert check_asset_online(d.id, force=True) is True
    assert "force_backup" in caplog.text
    assert f"device_id={d.id}" in caplog.text


def test_check_asset_online_with_force_when_never_collected(db, caplog):
    """force=True + 设备无 asset 记录 → 仍放行（应急逃生通道）"""
    d = _make_device(db)
    with caplog.at_level(logging.WARNING, logger="app"):
        assert check_asset_online(d.id, force=True) is True
    assert "force_backup" in caplog.text
