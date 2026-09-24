"""S2-014 契约测试：VPC 范围例外管理后端纵向切片（业务上下文，零设备 I/O）。

覆盖：
- CRUD（PUT 新建/替换、GET 列表、DELETE 清除，清除=直接删除且不级联历史）；
- 唯一性（同一 VPC+device 至多一条当前记录；直插重复行被唯一约束拒绝）；
- 成员准入（VPC/设备不存在 → 既有 404 语义；非 EVPN Leaf → 422/409 语义，不按名称推断）；
- 过期/有效边界（过期时间必须晚于当前；过期在读取时 state=expired，不自动删除）；
- 必填 reason / 长度限制 / 类型白名单 / 时间格式；
- 脱敏（响应不含凭据/protected_interfaces/原始配置/快照）；
- 零设备 I/O、零隐式采集（写操作只改数据库）；
- scope 事实分类与 aggregate 不受例外影响（例外不把 not_targeted 改 targeted、
  不把 drifted 改 aligned、不从分母移除设备）；exception 白名单 additive（无例外 null）；
- 畸形历史稳定降级（state-projection 不 500）；
- 迁移 013：空库升级、幂等升级、唯一索引。
"""
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.models import Device, SdnDeployment, SdnScopeException, SdnValidationSnapshot, SdnVpc
from app.routers.sdn import _serialize_scope_exception
from app.services.sdn_state_projection import SCOPE_NOT_TARGETED, SCOPE_TARGETED

NOW = datetime.utcnow()


class _FakeRow:
    """畸形历史序列化纯函数测试用的假行。"""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _create_tenant_via_api(client, name="t1"):
    return client.post("/api/sdn/tenants", json={"name": name}).json()["data"]


def _create_vpc_via_api(client, tenant_id, name="vpc-1"):
    return client.post("/api/sdn/vpcs", json={"name": name, "tenant_id": tenant_id, "cidr": "192.168.2.0/24", "gateway_ip": "192.168.2.254"}).json()["data"]


def _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf"):
    dev = Device(name=name, host=ip, port=830, username="admin", password_encrypted="SECRET-ENC", protected_interfaces="[]", platform="LSTN", sdn_role=sdn_role)
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def _add_create_deployment(db, vpc, device):
    from app.models import SdnVpc as V

    version = db.query(V).filter(V.id == vpc["id"]).first().version
    db.add(SdnDeployment(vpc_id=vpc["id"], device_id=device.id, action="create", unit="vpc-create-all",
                         status="success", version=version, planned_config='[{"secret": "RAW-PLAN-1"}]',
                         config_completed_at=datetime.utcnow()))
    db.commit()


def _put_exception(client, vpc_id, device_id, body):
    return client.put(f"/api/sdn/vpcs/{vpc_id}/devices/{device_id}/scope-exception", json=body)


def _list_exceptions(client, vpc_id):
    resp = client.get(f"/api/sdn/vpcs/{vpc_id}/scope-exceptions")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _clear_exception(client, vpc_id, device_id):
    return client.delete(f"/api/sdn/vpcs/{vpc_id}/devices/{device_id}/scope-exception")


def _projection(client, vpc_id):
    resp = client.get(f"/api/sdn/vpcs/{vpc_id}/state-projection")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _member(data, device_id):
    return next(m for m in data["scope"]["members"] if m["device_id"] == device_id)


def _db_count(db, vpc_id, device_id):
    return db.query(SdnScopeException).filter(
        SdnScopeException.vpc_id == vpc_id, SdnScopeException.device_id == device_id).count()


# ── CRUD / 替换 / 唯一性 ──


def test_exception_crud_create_list_clear(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)

    resp = _put_exception(client, vpc["id"], leaf.id, {"exception_type": "intentional_exclusion", "reason": "业务有意排除"})
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["exception_type"] == "intentional_exclusion"
    assert body["reason"] == "业务有意排除"
    assert body["state"] == "active"
    assert body["version"] == 1
    assert body["expires_at"] is None

    listed = _list_exceptions(client, vpc["id"])["exceptions"]
    assert len(listed) == 1
    assert listed[0]["device_id"] == leaf.id
    assert listed[0]["state"] == "active"

    # 清除 = 直接删除该行（删除子行不向上级联父对象）
    clear = _clear_exception(client, vpc["id"], leaf.id).json()["data"]
    assert clear["deleted"] is True
    assert _list_exceptions(client, vpc["id"])["exceptions"] == []
    assert _db_count(db, vpc["id"], leaf.id) == 0
    assert db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).count() == 1  # 父 VPC 仍在
    assert db.query(Device).filter(Device.id == leaf.id).count() == 1  # 父设备仍在


def test_exception_delete_does_not_cascade_up_to_parents(client, db):
    """清除例外不删除 VPC/device/deployment/snapshot 历史。"""
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    db.add(SdnValidationSnapshot(
        vpc_id=vpc["id"], device_id=leaf.id, validation_result="active", validation_details="{}",
        snapshot_data="{}", collection_started_at=NOW - timedelta(minutes=1),
        collection_completed_at=NOW,
    ))
    db.commit()
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "m"})
    assert _clear_exception(client, vpc["id"], leaf.id).json()["data"]["deleted"] is True

    assert db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).count() == 1
    assert db.query(Device).filter(Device.id == leaf.id).count() == 1
    assert db.query(SdnDeployment).count() == 1
    assert db.query(SdnValidationSnapshot).count() == 1


def test_exception_replace_bumps_version_single_row(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "intentional_exclusion", "reason": "r1"})
    resp2 = _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "r2", "expires_at": (NOW + timedelta(days=1)).isoformat()})
    data2 = resp2.json()["data"]
    assert data2["exception_type"] == "maintenance_pause"
    assert data2["reason"] == "r2"
    assert data2["version"] == 2
    assert data2["state"] == "active"
    assert data2["expires_at"].startswith((NOW + timedelta(days=1)).isoformat()[:10])
    assert _db_count(db, vpc["id"], leaf.id) == 1  # 替换不产生第二条当前记录


def test_exception_uniqueness_constraint_blocks_second_current_row(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "intentional_exclusion", "reason": "r1"})
    db.add(SdnScopeException(vpc_id=vpc["id"], device_id=leaf.id, exception_type="maintenance_pause", reason="dup", version=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert _db_count(db, vpc["id"], leaf.id) == 1  # 唯一约束保证至多一条当前记录


def test_exception_repeat_put_stable_same_logical_state(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    body = {"exception_type": "maintenance_pause", "reason": "维护暂停", "expires_at": (NOW + timedelta(days=2)).isoformat()}
    first = _put_exception(client, vpc["id"], leaf.id, body).json()["data"]
    second = _put_exception(client, vpc["id"], leaf.id, body).json()["data"]
    assert first["exception_type"] == second["exception_type"] == "maintenance_pause"
    assert first["reason"] == second["reason"] == "维护暂停"
    assert second["version"] == first["version"] + 1  # 替换升级版本，逻辑状态稳定


# ── 成员准入 ──


def test_exception_member_admission_errors(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    access = _create_device(db, name="Access-01", ip="192.0.2.20", sdn_role="access")
    leaf = _create_device(db)

    r = _put_exception(client, vpc["id"], access.id, {"exception_type": "intentional_exclusion", "reason": "x"})
    assert r.json()["error_key"] == "sdn.device_not_fabric_member"  # 非成员明确拒绝，不按名称/platform 推断

    r = _put_exception(client, vpc["id"], 999999, {"exception_type": "intentional_exclusion", "reason": "x"})
    assert r.json()["error_key"] == "sdn.device_not_found"

    r = _put_exception(client, 999999, leaf.id, {"exception_type": "intentional_exclusion", "reason": "x"})
    assert r.json()["error_key"] == "sdn.vpc_not_found"


# ── 过期/有效边界 ──


def test_exception_expired_read_state_not_auto_deleted(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "m", "expires_at": (NOW + timedelta(days=1)).isoformat()})
    row = db.query(SdnScopeException).filter(SdnScopeException.vpc_id == vpc["id"], SdnScopeException.device_id == leaf.id).first()
    row.expires_at = NOW - timedelta(hours=1)  # 直接改历史时间模拟过期
    db.commit()

    listed = _list_exceptions(client, vpc["id"])["exceptions"]
    assert len(listed) == 1
    assert listed[0]["state"] == "expired"  # 读取时明确过期
    assert _db_count(db, vpc["id"], leaf.id) == 1  # 不自动删除
    # state-projection 同步返回 expired，不 500
    data = _projection(client, vpc["id"])
    assert _member(data, leaf.id)["exception"]["state"] == "expired"


def test_exception_expires_in_past_rejected(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    r = _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "m", "expires_at": (NOW - timedelta(minutes=1)).isoformat()})
    assert r.json()["error_key"] == "sdn.scope_exception_expires_in_past"
    assert _db_count(db, vpc["id"], leaf.id) == 0


def test_exception_expires_tz_z_and_offset(client, db):
    """Z 与带 offset ISO 均接受，统一换算为 UTC naive 存库且序列化稳定；过去时间仍拒绝。"""
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)

    future_z = (NOW + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "m", "expires_at": future_z})
    assert r.json()["data"]["state"] == "active"
    assert r.json()["data"]["expires_at"] == (NOW + timedelta(days=1)).replace(microsecond=0).isoformat()  # UTC naive 稳定序列化
    assert "+00:00" not in r.json()["data"]["expires_at"] and "Z" not in r.json()["data"]["expires_at"]

    # +08:00 → 换算为 UTC（10:00+08:00 == 02:00Z）
    r2 = _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "m", "expires_at": "2026-09-30T10:00:00+08:00"})
    assert r2.json()["data"]["state"] == "active"
    assert r2.json()["data"]["expires_at"] == "2026-09-30T02:00:00"

    past_z = (NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "m", "expires_at": past_z}).json()["error_key"] == "sdn.scope_exception_expires_in_past"
    assert _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "m", "expires_at": "2020-01-01T10:00:00+08:00"}).json()["error_key"] == "sdn.scope_exception_expires_in_past"


# ── 校验：必填 reason / 长度 / 类型 / 时间格式 ──


def test_exception_validation_errors(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)

    assert _put_exception(client, vpc["id"], leaf.id, {"exception_type": "intentional_exclusion"}).json()["error_key"] == "sdn.scope_exception_reason_required"
    assert _put_exception(client, vpc["id"], leaf.id, {"exception_type": "intentional_exclusion", "reason": "   "}).json()["error_key"] == "sdn.scope_exception_reason_required"
    assert _put_exception(client, vpc["id"], leaf.id, {"exception_type": "intentional_exclusion", "reason": "x" * 201}).json()["error_key"] == "sdn.scope_exception_reason_too_long"
    assert _put_exception(client, vpc["id"], leaf.id, {"exception_type": "ban", "reason": "x"}).json()["error_key"] == "sdn.scope_exception_invalid_type"
    assert _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "x", "expires_at": "not-a-date"}).json()["error_key"] == "sdn.scope_exception_expires_invalid"
    assert _db_count(db, vpc["id"], leaf.id) == 0


# ── 脱敏 ──


def test_exception_sanitized_no_secrets(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "intentional_exclusion", "reason": "业务排除"})

    raw = json.dumps({
        "list": _list_exceptions(client, vpc["id"]),
        "put": _put_exception(client, vpc["id"], leaf.id, {"exception_type": "intentional_exclusion", "reason": "业务排除"}).json(),
        "clear": _clear_exception(client, vpc["id"], leaf.id).json(),
        "projection": _projection(client, vpc["id"]),
    }, default=str)
    for forbidden in ("SECRET-ENC", "RAW-PLAN-1", "password_encrypted", "protected_interfaces", "planned_config", "snapshot_data"):
        assert forbidden not in raw, forbidden


# ── 零设备 I/O、零隐式采集 ──


def test_exception_zero_device_io_and_zero_implicit_collection(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    from app.services.sdn_validation_collector import SdnValidationCollector

    with patch.object(SdnValidationCollector, "sync", side_effect=AssertionError("must not trigger sync")):
        resp = _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "m"})
        assert resp.json()["data"]["state"] == "active"
        assert len(_list_exceptions(client, vpc["id"])["exceptions"]) == 1
        assert _clear_exception(client, vpc["id"], leaf.id).json()["data"]["deleted"] is True


# ── scope 事实分类与 aggregate 不受例外影响 ──


def test_exception_does_not_change_scope_facts_or_aggregate(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    unset_leaf = _create_device(db, name="Leaf-U", ip="192.0.2.3")
    target_leaf = _create_device(db, name="Leaf-T", ip="192.0.2.1")
    _add_create_deployment(db, vpc, target_leaf)
    # drifted 快照（vsi 缺失）→ leaves aggregate drifted
    vsi_cmd = f"display l2vpn vsi name {vpc['vsi_name']} verbose"
    db.add(SdnValidationSnapshot(
        vpc_id=vpc["id"], device_id=target_leaf.id, validation_result="active", validation_details="{}",
        snapshot_data=json.dumps({"commands": {vsi_cmd: {"success": True, "output": "The VSI does not exist.", "error": None}}}),
        collection_started_at=NOW - timedelta(minutes=2, seconds=30), collection_completed_at=NOW - timedelta(minutes=2),
    ))
    db.commit()

    before = _projection(client, vpc["id"])
    assert _member(before, unset_leaf.id)["classification"] == SCOPE_NOT_TARGETED
    assert before["scope"]["summary"]["eligible"] == 2
    assert before["leaves"][0]["aggregate"] == "drifted"
    assert _member(before, unset_leaf.id)["exception"] is None

    _put_exception(client, vpc["id"], unset_leaf.id, {"exception_type": "maintenance_pause", "reason": "维护中"})
    _put_exception(client, vpc["id"], target_leaf.id, {"exception_type": "intentional_exclusion", "reason": "有意排除"})

    after = _projection(client, vpc["id"])
    # 例外不改变事实分类：not_targeted 仍 not_targeted、targeted 仍 targeted
    assert _member(after, unset_leaf.id)["classification"] == SCOPE_NOT_TARGETED
    assert _member(after, target_leaf.id)["classification"] == SCOPE_TARGETED
    # 例外不改变 aggregate / leaves / 分母
    assert after["leaves"][0]["aggregate"] == "drifted"
    assert after["scope"]["summary"]["eligible"] == 2
    assert len(after["scope"]["members"]) == 2
    # 例外 additive 白名单
    assert _member(after, unset_leaf.id)["exception"]["exception_type"] == "maintenance_pause"
    assert _member(after, unset_leaf.id)["exception"]["state"] == "active"
    assert _member(after, target_leaf.id)["exception"]["exception_type"] == "intentional_exclusion"
    assert after["scope"]["summary"]["active_exception"] == 2
    assert after["scope"]["summary"][SCOPE_NOT_TARGETED] == 1
    assert after["scope"]["summary"][SCOPE_TARGETED] == 1


def test_exception_absent_member_null_and_idempotent_clear(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    data = _projection(client, vpc["id"])
    assert _member(data, leaf.id)["exception"] is None
    assert data["scope"]["summary"]["active_exception"] == 0
    r = _clear_exception(client, vpc["id"], leaf.id)
    assert r.status_code == 200
    assert r.json()["data"]["deleted"] is False  # 幂等清除，不 500


# ── 畸形历史稳定降级（state=invalid，绝不 active / 不计入 active_exception / 不 500）──


def _valid_row(**over):
    base = dict(vpc_id=1, device_id=2, exception_type="intentional_exclusion", reason="r",
                expires_at=None, version=1, created_at=NOW, updated_at=NOW)
    base.update(over)
    return _FakeRow(**base)


def test_exception_serializer_malformed_history_stable_invalid():
    """纯函数证明：任何畸形字段 → 脱敏白名单 + state=invalid。"""
    malformed = [
        {"exception_type": "legacy_garbage"},                                    # 非法 type
        {"exception_type": None},
        {"reason": ""},                                                          # 空 reason
        {"reason": "x" * 201},                                                   # 超长 reason
        {"reason": None},
        {"reason": 123},
        {"expires_at": "not-a-date"},                                            # 非 datetime expires_at（ORM 可能回传字符串）
        {"expires_at": 12345},
        {"version": None},                                                       # 缺失/非法 version
        {"version": 0},
        {"version": -3},
        {"version": True},                                                       # bool 不是合法 int
        {"version": "3"},
    ]
    for over in malformed:
        out = _serialize_scope_exception(_valid_row(**over))
        assert set(out.keys()) == {"vpc_id", "device_id", "exception_type", "reason",
                                   "expires_at", "state", "version", "created_at", "updated_at"}, over
        assert out["state"] == "invalid", over
        assert out["expires_at"] is None or isinstance(out["expires_at"], str), over

    # 合法语义不变：无过期 → active；过期 → expired；未来 → active
    assert _serialize_scope_exception(_valid_row())["state"] == "active"
    assert _serialize_scope_exception(_valid_row(expires_at=NOW - timedelta(hours=1)))["state"] == "expired"
    assert _serialize_scope_exception(_valid_row(expires_at=NOW + timedelta(hours=1)))["state"] == "active"


def test_exception_check_constraints_reject_new_dirty_data(client, db):
    """数据库 CHECK 阻止新脏数据（非法 type / 空 reason / version<1）。"""
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)

    def _try_insert(**kw):
        db.add(SdnScopeException(vpc_id=vpc["id"], device_id=leaf.id, **kw))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    _try_insert(exception_type="legacy_garbage", reason="x", version=1)
    _try_insert(exception_type="intentional_exclusion", reason="", version=1)
    _try_insert(exception_type="intentional_exclusion", reason="x", version=0)
    assert db.query(SdnScopeException).count() == 0  # 全部被拒，不留脏行


# ── 父对象删除不留下 orphan scope_exception（项目 ORM relationship cascade 方式）──


def test_parent_vpc_delete_cascades_exception(client, db):
    """删除父租户 → VPC 级联删除 → 例外子行一并清理，不留 orphan。"""
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "intentional_exclusion", "reason": "r"})
    assert _db_count(db, vpc["id"], leaf.id) == 1

    r = client.delete(f"/api/sdn/tenants/{tenant['id']}")
    assert r.json()["success"] is True
    assert db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).count() == 0
    assert _db_count(db, vpc["id"], leaf.id) == 0  # 无 orphan


def test_parent_device_delete_cascades_exception(client, db):
    """删除父设备 → 例外子行经 ORM cascade 清理，不留 orphan。"""
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "m"})
    assert _db_count(db, vpc["id"], leaf.id) == 1

    db.delete(leaf)
    db.commit()
    assert _db_count(db, vpc["id"], leaf.id) == 0
    assert db.query(Device).filter(Device.id == leaf.id).count() == 0


# ── 迁移 013 ──

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _alembic_config():
    from alembic.config import Config

    cfg = Config(os.path.join(_BACKEND_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND_ROOT, "migrations"))
    return cfg


def _index_exists(engine, table, name):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t AND name=:n"), {"t": table, "n": name}).fetchall()
    return len(rows) > 0


def _upgrade_013(cfg, db_file, monkeypatch):
    from alembic import command
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", str(db_file))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")
    command.stamp(cfg, "012")
    command.upgrade(cfg, "head")


def test_migration_013_upgrade_creates_table_and_indexes(monkeypatch, tmp_path):
    db_file = tmp_path / "up013.db"
    engine = create_engine(f"sqlite:///{db_file}")
    _upgrade_013(_alembic_config(), db_file, monkeypatch)
    with engine.connect() as conn:
        tables = [r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
    assert "sdn_scope_exceptions" in tables
    assert _index_exists(engine, "sdn_scope_exceptions", "uq_sdn_scope_exceptions_live")
    assert _index_exists(engine, "sdn_scope_exceptions", "ix_sdn_scope_exceptions_vpc")
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(sdn_scope_exceptions)")).fetchall()]
    for col in ("id", "vpc_id", "device_id", "exception_type", "reason", "expires_at", "version", "created_at", "updated_at"):
        assert col in cols, col
    # FK 指向 sdn_vpcs.id / devices.id（ondelete=CASCADE）
    with engine.connect() as conn:
        fks = conn.execute(text("PRAGMA foreign_key_list(sdn_scope_exceptions)")).fetchall()
    assert len(fks) == 2
    fk_map = {r[3]: r[2] for r in fks}  # col -> ref_table
    assert fk_map["vpc_id"] == "sdn_vpcs"
    assert fk_map["device_id"] == "devices"
    assert all(r[6] == "CASCADE" for r in fks)  # on_delete
    # CHECK 约束存在
    with engine.connect() as conn:
        sql = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='sdn_scope_exceptions'")).fetchone()[0]
    for ck in ("ck_sdn_scope_exceptions_type", "ck_sdn_scope_exceptions_reason_nonempty", "ck_sdn_scope_exceptions_version"):
        assert ck in sql, ck
    engine.dispose()


def test_migration_013_idempotent_upgrade(monkeypatch, tmp_path):
    db_file = tmp_path / "idem013.db"
    cfg = _alembic_config()
    _upgrade_013(cfg, db_file, monkeypatch)
    from alembic import command

    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")
    command.upgrade(cfg, "head")  # 再跑一次：幂等，不报错
    engine = create_engine(f"sqlite:///{db_file}")
    assert _index_exists(engine, "sdn_scope_exceptions", "uq_sdn_scope_exceptions_live")
    engine.dispose()
