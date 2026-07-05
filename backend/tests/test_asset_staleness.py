"""v2.6.1 fix-asset-stale-status — staleness 阈值 + 启动降级单测

覆盖：
- dashboard._get_asset_stats 按 staleness 阈值过滤（陈旧 online → stale）
- /internal/assets 返回 is_stale 字段（ASSET_STALE_ENABLED=True / False）
- app.main.degrade_stale_assets 启动时降级（幂等，ASSET_STALE_HOURS=0.01 边界）
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import Asset, Device


# ===== 工具 fixture =====

def _make_device(db, name="d1", host="1.1.1.1") -> Device:
    d = Device(name=name, host=host, port=830, username="u", password_encrypted="x")
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _make_asset(db, device_id, status="online", updated_at=None) -> Asset:
    a = Asset(device_id=device_id, status=status)
    if updated_at is not None:
        a.updated_at = updated_at
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ===== dashboard._get_asset_stats staleness 过滤 =====

def test_dashboard_stale_filter_old_updated_at_not_online(db):
    """staleness 过滤：asset.updated_at > 1h → 不算 online，单独计 stale"""
    from app.routers.dashboard import _get_asset_stats
    from app.config import settings

    d1 = _make_device(db, "d1", "1.1.1.1")
    d2 = _make_device(db, "d2", "1.1.1.2")
    now = datetime.utcnow()
    # online 但 5 小时前（> 1h 阈值）→ 应计 stale
    _make_asset(db, d1.id, "online", updated_at=now - timedelta(hours=5))
    # online 但 30 分钟前（< 1h 阈值）→ 应计 online
    _make_asset(db, d2.id, "online", updated_at=now - timedelta(minutes=30))

    online, offline, stale = _get_asset_stats(db)
    assert online == 1, f"30 分钟内的应计 online，实际 {online}"
    assert offline == 0
    assert stale == 1, f"5 小时前的应计 stale，实际 {stale}"


def test_dashboard_stale_filter_recent_updated_at_counted_online(db):
    """staleness 过滤：asset.updated_at <= 1h → 算 online"""
    from app.routers.dashboard import _get_asset_stats

    d1 = _make_device(db, "d1", "1.1.1.1")
    d2 = _make_device(db, "d2", "1.1.1.2")
    now = datetime.utcnow()
    _make_asset(db, d1.id, "online", updated_at=now - timedelta(minutes=10))
    _make_asset(db, d2.id, "online", updated_at=now - timedelta(minutes=59))

    online, offline, stale = _get_asset_stats(db)
    assert online == 2, f"2 条均在 1h 内，应计 online，实际 {online}"
    assert offline == 0
    assert stale == 0


# ===== app.main.degrade_stale_assets 启动降级 =====

def test_degrade_stale_assets_25h_old_online_becomes_offline(db):
    """启动时自动降级：mock 25h 前的 online asset，调用后变 offline"""
    from app.main import degrade_stale_assets

    d = _make_device(db, "d1", "1.1.1.1")
    now = datetime.utcnow()
    a = _make_asset(db, d.id, "online", updated_at=now - timedelta(hours=25))

    affected = degrade_stale_assets()
    assert affected == 1, f"应降级 1 行，实际 {affected}"

    db.refresh(a)
    assert a.status == "offline", f"25h 前的 online 应降级，实际 {a.status}"


def test_degrade_stale_assets_with_small_threshold_degrades(db, monkeypatch):
    """ASSET_STALE_HOURS=0.01（36s）边界：刚采集的设备 36s 后立即降级"""
    from app.config import settings
    from app.main import degrade_stale_assets

    # 模拟"30 秒前"采集的设备（> 0.01h = 36s 阈值后算陈旧）
    monkeypatch.setattr(settings, "ASSET_STALE_HOURS", 0.01)
    monkeypatch.setattr(settings, "ASSET_STALE_ENABLED", True)

    d = _make_device(db, "d1", "1.1.1.1")
    a = _make_asset(db, d.id, "online", updated_at=datetime.utcnow() - timedelta(seconds=60))

    affected = degrade_stale_assets()
    assert affected == 1, f"60s 前的应被 0.01h 阈值降级，实际 affected={affected}"
    db.refresh(a)
    assert a.status == "offline"


def test_degrade_stale_assets_disabled_no_degradation(db, monkeypatch):
    """ASSET_STALE_ENABLED=False：不降级（即使满足阈值）"""
    from app.config import settings
    from app.main import degrade_stale_assets

    monkeypatch.setattr(settings, "ASSET_STALE_HOURS", 1.0)
    monkeypatch.setattr(settings, "ASSET_STALE_ENABLED", False)

    d = _make_device(db, "d1", "1.1.1.1")
    a = _make_asset(db, d.id, "online", updated_at=datetime.utcnow() - timedelta(hours=100))

    affected = degrade_stale_assets()
    assert affected == 0, f"关闭时不应降级，实际 affected={affected}"
    db.refresh(a)
    assert a.status == "online", f"关闭时 100h 前的 online 应保持，实际 {a.status}"


# ===== /internal/assets is_stale 字段 =====

def test_internal_list_assets_includes_is_stale_field(client, db, monkeypatch):
    """/internal/assets 返回 is_stale: bool 字段（ASSET_STALE_ENABLED=True）"""
    from app.config import settings

    monkeypatch.setattr(settings, "ASSET_STALE_HOURS", 1.0)
    monkeypatch.setattr(settings, "ASSET_STALE_ENABLED", True)

    d_stale = _make_device(db, "d-stale", "1.1.1.1")
    d_fresh = _make_device(db, "d-fresh", "1.1.1.2")
    now = datetime.utcnow()
    _make_asset(db, d_stale.id, "online", updated_at=now - timedelta(hours=5))  # stale
    _make_asset(db, d_fresh.id, "online", updated_at=now - timedelta(minutes=10))  # fresh

    resp = client.get("/internal/assets")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    # 每条都应含 is_stale
    for a in data:
        assert "is_stale" in a, f"asset {a.get('id')} 缺 is_stale 字段"
    # 5h 前的应是 is_stale=True；10min 前的应是 is_stale=False
    by_dev = {a["device_id"]: a for a in data}
    assert by_dev[d_stale.id]["is_stale"] is True
    assert by_dev[d_fresh.id]["is_stale"] is False


def test_internal_list_assets_excludes_is_stale_when_disabled(client, db, monkeypatch):
    """/internal/assets ASSET_STALE_ENABLED=False 时不返 is_stale 字段"""
    from app.config import settings

    monkeypatch.setattr(settings, "ASSET_STALE_HOURS", 1.0)
    monkeypatch.setattr(settings, "ASSET_STALE_ENABLED", False)

    d = _make_device(db, "d1", "1.1.1.1")
    _make_asset(db, d.id, "online", updated_at=datetime.utcnow() - timedelta(hours=100))

    resp = client.get("/internal/assets")
    assert resp.status_code == 200
    data = resp.json()["data"]
    for a in data:
        assert "is_stale" not in a, "关闭时 MUST NOT 含 is_stale 字段"


# ===== dashboard split 模式 staleness 计数（回归：stale 只计 is_stale AND online）=====

def test_dashboard_stale_split_mode_only_counts_online_assets(db, monkeypatch):
    """回归：dashboard._get_asset_stats 在 split 模式下 stale 必须 status='online' AND is_stale

    背景：on_startup 降级后，stale 资产变 offline；dashboard 不应再计 stale（避免双计）
    模拟 split 模式：让 SQLAlchemy 抛 NoSuchTableError → 走 internal_api 路径
    """
    from app.config import settings
    from app.routers.dashboard import _get_asset_stats
    from sqlalchemy.exc import NoSuchTableError, OperationalError

    monkeypatch.setattr(settings, "ASSET_STALE_HOURS", 1.0)
    monkeypatch.setattr(settings, "ASSET_STALE_ENABLED", True)

    # mock internal_api.get_assets 返回 mixed 状态数据
    fake_assets = [
        {"id": 1, "device_id": 101, "status": "online", "is_stale": False},   # 新鲜 online
        {"id": 2, "device_id": 102, "status": "online", "is_stale": True},    # 过期 online → stale
        {"id": 3, "device_id": 103, "status": "offline", "is_stale": True},   # 已降级，不应计 stale
        {"id": 4, "device_id": 104, "status": "offline", "is_stale": False},  # 正常 offline
    ]
    from app import internal_api
    monkeypatch.setattr(internal_api, "get_assets", lambda: {"success": True, "data": fake_assets})

    # 模拟 split 模式：让所有 db.query 抛 NoSuchTableError
    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self
        def scalar(self):
            raise NoSuchTableError("simulated: ctrl has no assets table")
    db.query = lambda *a, **kw: FakeQuery()

    online, offline, stale = _get_asset_stats(db)
    assert online == 1, f"应只有 1 个新鲜 online，实际 {online}"
    assert offline == 2, f"应 2 个 offline（含已降级），实际 {offline}"
    assert stale == 1, f"应只 1 个 stale（online+is_stale），实际 {stale}"
