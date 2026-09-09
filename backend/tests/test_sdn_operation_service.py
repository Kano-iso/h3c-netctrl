"""S1 共享变更安全服务单元测试（资源声明/幂等/指纹/计划/CAS）。"""
import threading
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    SdnDeployment,
    SdnOperation,
    SdnPlan,
    SdnPortBinding,
    SdnResourceClaim,
    SdnTenant,
    SdnVpc,
    Device,
)
from app.services.sdn_operation_service import (
    SdnOperationError,
    acquire_claims,
    claim_deployment,
    compute_access_fingerprint,
    compute_semantic_hash,
    consume_plan,
    create_plan,
    device_port_key,
    ordered_claim_keys,
    release_claims,
    resolve_operation,
    snapshot_identity,
    tenant_key,
    vpc_device_key,
    vpc_key,
)


def _seed(db: Session):
    device = Device(name="Leaf-04", host="192.168.100.5", username="admin",
                    password_encrypted="x", protected_interfaces="[]",
                    platform="LSTN", sdn_role="evpn_leaf")
    db.add(device)
    db.flush()
    tenant = SdnTenant(name="研发", rd="1:1", import_rt="1:1", export_rt="1:1", l3_vni=10001)
    db.add(tenant)
    db.flush()
    vpc = SdnVpc(tenant_id=tenant.id, name="vpc-a", cidr="10.1.0.0/24", gateway_ip="10.1.0.1",
                 gateway_mac="00:00:5e:00:01:01", vni=10001, vsi_name="vsi-a", vsi_interface=1,
                 vlan_id=100, status="deployed", version=0)
    db.add(vpc)
    db.commit()
    return device, tenant, vpc


# ── 锁序 ──

def test_ordered_claim_keys_uses_rank_not_lexicographic(db):
    keys = [device_port_key(5, 2), vpc_key(1), vpc_device_key(1, 5), tenant_key(1)]
    assert ordered_claim_keys(keys) == ["tenant:1", "vpc:1", "vpc-device:1:5", "device-port:5:2"]


# ── 资源声明互斥（held + ambiguous）──

def test_acquire_same_key_conflicts(db):
    acquire_claims(db, ["vpc:1"])
    db.commit()
    with pytest.raises(SdnOperationError) as ei:
        acquire_claims(db, ["vpc:1"])
    assert ei.value.error_key == "sdn.resource_busy"


def test_ambiguous_claim_blocks_new_owner(db):
    acquire_claims(db, ["vpc:1"], operation_id=1, attempt_id=1)
    db.commit()
    # 把 claim 标 ambiguous：released_at 仍 NULL，仍独占
    claim = db.query(SdnResourceClaim).filter(SdnResourceClaim.resource_key == "vpc:1").first()
    claim.status = "ambiguous"
    db.commit()
    with pytest.raises(SdnOperationError) as ei:
        acquire_claims(db, ["vpc:1"], operation_id=2, attempt_id=2)
    assert ei.value.error_key == "sdn.resource_busy"


def test_release_allows_reacquire(db):
    acquire_claims(db, ["vpc:1"], attempt_id=1)
    db.commit()
    release_claims(db, ["vpc:1"], owner_attempt_id=1)
    db.commit()
    # released_at 置非空后唯一索引解除 → 可重新获取
    acquire_claims(db, ["vpc:1"], attempt_id=2)
    db.commit()


# ── deployment CAS ──

def test_claim_deployment_cas(db):
    _, _, vpc = _seed(db)
    dep = SdnDeployment(vpc_id=vpc.id, device_id=1, action="create", unit="vpc-create-all",
                        planned_config="[]", status="pending")
    db.add(dep)
    db.commit()
    claimed = claim_deployment(db, dep.id, attempt_id=9)
    assert claimed.status == "running"
    with pytest.raises(SdnOperationError) as ei:
        claim_deployment(db, dep.id, attempt_id=10)
    assert ei.value.error_key == "sdn.deployment_not_pending"


# ── 幂等 / 指纹 ──

def test_fingerprint_deterministic_and_field_sensitive():
    base = dict(tenant_id=1, vpc_id=1, device_id=5, if_index=2, interface_name="GigabitEthernet1/0/2",
                access_vlan=None, service_instance=3200, expected_host_ip="10.1.1.2", auto_apply=True, mode="auto")
    a = compute_access_fingerprint(**base)
    b = compute_access_fingerprint(**base)
    assert a == b
    c = compute_access_fingerprint(**{**base, "device_id": 6})
    assert a != c


def test_resolve_operation_duplicate_conflict_and_scope(db):
    _seed(db)
    fp = "f" * 64
    op, created = resolve_operation(
        db, idempotency_key="k1", fingerprint=fp, operation_type="terminal_access",
        tenant_id=1, vpc_id=1, device_id=5, plan_id=None, expected_host_ip=None,
        request_payload_json=None, scope_json="{}",
    )
    db.commit()
    assert created is True

    # 同 key 同 fingerprint → duplicate
    op2, created2 = resolve_operation(
        db, idempotency_key="k1", fingerprint=fp, operation_type="terminal_access",
        tenant_id=1, vpc_id=1, device_id=5, plan_id=None, expected_host_ip=None,
        request_payload_json=None, scope_json="{}",
    )
    assert created2 is False and op2.id == op.id

    # 同 key 异 fingerprint → conflict
    with pytest.raises(SdnOperationError) as ei:
        resolve_operation(
            db, idempotency_key="k1", fingerprint="e" * 64, operation_type="terminal_access",
            tenant_id=1, vpc_id=1, device_id=5, plan_id=None, expected_host_ip=None,
            request_payload_json=None, scope_json="{}",
        )
    assert ei.value.error_key == "sdn.idempotency_conflict"

    # 同 key 跨 scope（不同 device）→ 404 不泄漏
    with pytest.raises(SdnOperationError) as ei:
        resolve_operation(
            db, idempotency_key="k1", fingerprint=fp, operation_type="terminal_access",
            tenant_id=1, vpc_id=1, device_id=6, plan_id=None, expected_host_ip=None,
            request_payload_json=None, scope_json="{}",
        )
    assert ei.value.error_key == "sdn.idempotency_not_found"


# ── 计划 ──

def test_plan_expire_and_consume(db):
    plan = create_plan(db, plan_id="p1", semantic_hash="h", version_snapshot_json="{}", scope_json="{}", ttl_seconds=-1)
    db.commit()
    with pytest.raises(SdnOperationError) as ei:
        consume_plan(db, "p1")
    assert ei.value.error_key == "sdn.plan_expired"

    plan2 = create_plan(db, plan_id="p2", semantic_hash="h", version_snapshot_json="{}", scope_json="{}")
    db.commit()
    consumed = consume_plan(db, "p2")
    assert consumed.status == "consumed"
    with pytest.raises(SdnOperationError) as ei2:
        consume_plan(db, "p2")
    assert ei2.value.error_key == "sdn.plan_consumed"


# ── 身份快照 ──

def test_snapshot_identity(db):
    snapshot_identity(db, entity_kind="vpc", entity_id=7, identity={"name": "x"}, deleted=True)
    db.commit()
    from app.models import SdnIdentitySnapshot
    snap = db.query(SdnIdentitySnapshot).filter(SdnIdentitySnapshot.entity_kind == "vpc", SdnIdentitySnapshot.entity_id == 7).first()
    assert snap is not None and snap.deleted_at is not None


# ── 崩溃窗口：started 后无终态 → 阻塞重放（unknown），不盲目重放 ──

def test_started_unit_without_completion_blocks_replay(db):
    from app.models import SdnAttemptUnit
    from app.services.sdn_operation_service import create_attempt, create_attempt_units, mark_unit_started
    a = create_attempt(db, operation_id=1, kind="execute", owner="1")
    create_attempt_units(db, a.id, ["port-bind"])
    db.commit()
    assert mark_unit_started(db, a.id, 0) is True
    db.commit()
    # 已 started（I/O 前崩溃，无终态）：再次 start 被拒 → 不会盲目重放
    assert mark_unit_started(db, a.id, 0) is False
    unit = db.query(SdnAttemptUnit).filter(SdnAttemptUnit.attempt_id == a.id, SdnAttemptUnit.unit_index == 0).first()
    assert unit.state == "started"


# ── 并发（同 deployment 认领）──

def test_concurrent_deployment_claim_single_winner(db):
    _, _, vpc = _seed(db)
    dep = SdnDeployment(vpc_id=vpc.id, device_id=1, action="create", unit="vpc-create-all",
                        planned_config="[]", status="pending")
    db.add(dep)
    db.commit()

    results = []

    def worker(attempt_id):
        s = SessionLocal()
        try:
            try:
                claim_deployment(s, dep.id, attempt_id=attempt_id)
                s.commit()
                results.append("ok")
            except SdnOperationError:
                s.rollback()
                results.append("conflict")
        finally:
            s.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("ok") == 1
    assert results.count("conflict") == 4
