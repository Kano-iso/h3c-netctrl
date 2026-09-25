"""S1 迁移 012 隔离测试（+ S1-027 空库 bootstrap 回归）。

本项目 alembic 为「棕地」迁移链：002/003/004 对 create_all 时代预建的
devices/logs 等基表做 ALTER。S1-027 修复后，001 作为链起点会幂等补建缺失基表
（devices/logs），因此**空库可以一路 upgrade 到 head**（见
test_fresh_empty_db_upgrade_head_bootstraps_base_tables）。以下仍隔离验证 S1
迁移 012 自身：在 stamp 到 011 的旧库（仅含旧 SDN 表骨架）上 upgrade/downgrade
012，验证建表/加列/部分唯一索引。
"""
import os

from sqlalchemy import create_engine, inspect, text


_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _alembic_config():
    from alembic.config import Config
    cfg = Config(os.path.join(_BACKEND_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND_ROOT, "migrations"))
    return cfg


def _make_legacy_schema(engine):
    """建一个「011 旧库」骨架：只含迁移 012 需要加列/建索引的那几张旧表（最小列）。"""
    with engine.begin() as conn:
        for t in ("sdn_vpcs", "sdn_port_bindings", "sdn_deployments", "sdn_validation_snapshots"):
            conn.execute(text(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY)"))
    return engine


def _stamp_011(cfg, db_file, monkeypatch):
    from alembic import command
    from app.config import settings
    monkeypatch.setattr(settings, "DB_PATH", str(db_file))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")
    command.stamp(cfg, "011")


def _column_type(engine, table, column):
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    for r in rows:
        if r[1] == column:
            return (r[2] or "").upper()
    return None


def _index_exists(engine, name):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND name=:n"), {"n": name}).fetchall()
    return len(rows) > 0


def test_upgrade_012_creates_tables_columns_index(monkeypatch, tmp_path):
    db_file = tmp_path / "up012.db"
    engine = create_engine(f"sqlite:///{db_file}")
    _make_legacy_schema(engine)
    engine.dispose()

    cfg = _alembic_config()
    _stamp_011(cfg, db_file, monkeypatch)

    from alembic import command
    command.upgrade(cfg, "012")

    engine = create_engine(f"sqlite:///{db_file}")
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    for t in ("sdn_plans", "sdn_operations", "sdn_attempts", "sdn_attempt_units",
              "sdn_resource_claims", "sdn_identity_snapshots"):
        assert t in tables, f"missing table {t}"

    # 部分唯一索引（held + ambiguous 都独占）；inspect.get_indexes 不报告部分索引，走 sqlite_master
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='sdn_resource_claims' "
            "AND name='uq_sdn_resource_claims_active'"
        )).fetchall()
    assert rows and "WHERE released_at IS NULL" in rows[0][0], "partial unique index missing"

    # 旧表加列
    assert "version" in {c["name"] for c in insp.get_columns("sdn_vpcs")}
    dep_cols = {c["name"] for c in insp.get_columns("sdn_deployments")}
    assert "operation_id" in dep_cols and "claimed_by_attempt_id" in dep_cols and "claimed_at" in dep_cols
    engine.dispose()


def test_upgrade_012_idempotent(monkeypatch, tmp_path):
    db_file = tmp_path / "up012b.db"
    engine = create_engine(f"sqlite:///{db_file}")
    _make_legacy_schema(engine)
    engine.dispose()

    cfg = _alembic_config()
    _stamp_011(cfg, db_file, monkeypatch)

    from alembic import command
    command.upgrade(cfg, "012")
    # 再 upgrade 一次应无副作用（_has_table/_has_column/_has_index 守卫）
    command.upgrade(cfg, "012")
    command.upgrade(cfg, "012")

    engine = create_engine(f"sqlite:///{db_file}")
    assert "sdn_operations" in set(inspect(engine).get_table_names())
    engine.dispose()


def test_downgrade_012_drops_s1_tables(monkeypatch, tmp_path):
    db_file = tmp_path / "down012.db"
    engine = create_engine(f"sqlite:///{db_file}")
    _make_legacy_schema(engine)
    engine.dispose()

    cfg = _alembic_config()
    _stamp_011(cfg, db_file, monkeypatch)

    from alembic import command
    command.upgrade(cfg, "012")
    command.downgrade(cfg, "011")

    engine = create_engine(f"sqlite:///{db_file}")
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert "sdn_operations" not in tables
    assert "sdn_resource_claims" not in tables
    assert "sdn_plans" not in tables
    # 旧表保留
    assert "sdn_vpcs" in tables
    engine.dispose()


def test_cr15_constraints_column_type_and_indexes(monkeypatch, tmp_path):
    """CR15: claimed_at 为 DateTime、attempt unit 唯一约束、identity 复合索引均实测。"""
    db_file = tmp_path / "cr15.db"
    engine = create_engine(f"sqlite:///{db_file}")
    _make_legacy_schema(engine)
    engine.dispose()

    cfg = _alembic_config()
    _stamp_011(cfg, db_file, monkeypatch)

    from alembic import command
    command.upgrade(cfg, "012")

    engine = create_engine(f"sqlite:///{db_file}")

    # claimed_at 为 DateTime（含 DATETIME 或 DATE）
    ctype = _column_type(engine, "sdn_deployments", "claimed_at")
    assert ctype and ("DATE" in ctype or "TIME" in ctype), f"claimed_at type={ctype!r}"

    # sdn_attempt_units (attempt_id, unit_index) 唯一约束存在
    assert _index_exists(engine, "uq_attempt_unit"), "uq_attempt_unit unique index missing"

    # sdn_identity_snapshots (entity_kind, entity_id, created_at) 复合索引存在
    assert _index_exists(engine, "ix_identity_kind_id_created"), "ix_identity_kind_id_created missing"

    # 唯一约束实际拒绝重复 (attempt_id, unit_index)
    from sqlalchemy import text as _t
    from sqlalchemy.exc import IntegrityError
    with engine.begin() as conn:
        conn.execute(_t("INSERT INTO sdn_operations (idempotency_key, fingerprint, operation_type, tenant_id, vpc_id, device_id) "
                        "VALUES ('k1','f','t',1,1,1)"))
        conn.execute(_t("INSERT INTO sdn_attempts (operation_id, kind, status) VALUES (1, 'execute', 'claimed')"))
        conn.execute(_t("INSERT INTO sdn_attempt_units (attempt_id, unit_index, unit_name, state) VALUES (1, 0, 'u', 'not_started')"))
        try:
            conn.execute(_t("INSERT INTO sdn_attempt_units (attempt_id, unit_index, unit_name, state) VALUES (1, 0, 'u2', 'not_started')"))
            raise AssertionError("duplicate (attempt_id, unit_index) should be rejected")
        except IntegrityError:
            pass
    engine.dispose()


def test_fresh_create_all_bootstrap_has_s1_schema(tmp_path):
    """CR10: 真实支持的新库引导路径——Base.metadata.create_all 生成完整 6 表 + 列 + 部分唯一索引。"""
    from sqlalchemy.orm import Session
    from app.database import Base

    db_file = tmp_path / "fresh.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    for t in ("sdn_plans", "sdn_operations", "sdn_attempts", "sdn_attempt_units",
              "sdn_resource_claims", "sdn_identity_snapshots", "sdn_deployments"):
        assert t in tables, f"missing table {t}"

    # 新列（config 完成时间）已在新库 bootstrap 中
    dep_cols = {c["name"] for c in insp.get_columns("sdn_deployments")}
    assert "config_started_at" in dep_cols and "config_completed_at" in dep_cols

    # 部分唯一索引（live 绑定唯一 + claim 独占）
    with engine.connect() as conn:
        idx = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='uq_sdn_port_bindings_live'"
        )).fetchall()
        claims = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='uq_sdn_resource_claims_active'"
        )).fetchall()
    assert idx and "WHERE status != 'unbound'" in idx[0][0]
    assert claims and "WHERE released_at IS NULL" in claims[0][0]
    engine.dispose()


def test_fresh_empty_db_upgrade_head_bootstraps_base_tables(monkeypatch, tmp_path):
    """S1-027 回归：空库一路 upgrade 到 head 必须成功。

    修复前 003 在空库上 `ALTER TABLE logs` 失败（logs 表只由 create_all 预建、
    迁移从未创建）；001 现在幂等补建 devices/logs 基表，全新库可完整升级。
    """
    from alembic import command
    from app.config import settings

    db_file = tmp_path / "fresh-upgrade.db"
    engine = create_engine(f"sqlite:///{db_file}")
    engine.dispose()

    cfg = _alembic_config()
    monkeypatch.setattr(settings, "DB_PATH", str(db_file))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")

    # 空库 → head（修复前在此抛 OperationalError: no such table: logs）
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_file}")
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    # 基表已引导 + 迁移链完整产物
    for t in ("devices", "logs", "assets", "backups", "tasks",
              "sdn_tenants", "sdn_vpcs", "sdn_operations", "sdn_attempts",
              "sdn_attempt_units", "sdn_validation_snapshots"):
        assert t in tables, f"missing table {t}"
    # 基表基础列 + 后续迁移加列
    dev_cols = {c["name"] for c in insp.get_columns("devices")}
    assert {"id", "name", "host", "username", "password_encrypted"} <= dev_cols
    assert {"protected_interfaces", "platform", "sdn_role"} <= dev_cols
    log_cols = {c["name"] for c in insp.get_columns("logs")}
    assert {"id", "device_id", "device_name", "action", "detail", "status"} <= log_cols
    assert "error_message" in log_cols

    # 幂等：重复 upgrade head 不报错、不重复建表
    command.upgrade(cfg, "head")
    insp2 = inspect(create_engine(f"sqlite:///{db_file}"))
    assert set(insp2.get_table_names()) == tables
    engine.dispose()


# ── S3-001 迁移 014：VPC 保障策略 + 只读评估运行 ──


def _stamp_013(cfg, db_file, monkeypatch):
    from alembic import command
    from app.config import settings
    monkeypatch.setattr(settings, "DB_PATH", str(db_file))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")
    command.stamp(cfg, "013")


def test_upgrade_014_creates_tables_columns_index(monkeypatch, tmp_path):
    """013 旧库（仅含旧 SDN 表骨架）→ upgrade 014 建两表 + 唯一约束 + 索引 + 约束列。"""
    db_file = tmp_path / "up014.db"
    engine = create_engine(f"sqlite:///{db_file}")
    _make_legacy_schema(engine)
    engine.dispose()

    cfg = _alembic_config()
    _stamp_013(cfg, db_file, monkeypatch)

    from alembic import command
    command.upgrade(cfg, "014")

    engine = create_engine(f"sqlite:///{db_file}")
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert "sdn_assurance_policies" in tables
    assert "sdn_assurance_runs" in tables

    pol_cols = {c["name"] for c in insp.get_columns("sdn_assurance_policies")}
    assert {"id", "vpc_id", "enabled", "cadence", "response_mode", "version",
            "created_at", "updated_at"} <= pol_cols
    run_cols = {c["name"] for c in insp.get_columns("sdn_assurance_runs")}
    assert {"id", "vpc_id", "trigger", "status", "started_at", "completed_at",
            "policy_version", "policy_enabled", "facts_json", "summary_json",
            "items_json", "created_at"} <= run_cols

    # 唯一约束（策略每 VPC 至多一条）+ run 列表索引
    assert _index_exists(engine, "uq_sdn_assurance_policies_vpc")
    assert _index_exists(engine, "ix_sdn_assurance_runs_vpc_id")

    # 约束列类型
    pol_vpc_type = _column_type(engine, "sdn_assurance_policies", "vpc_id")
    assert pol_vpc_type and "INT" in pol_vpc_type
    run_facts_type = _column_type(engine, "sdn_assurance_runs", "facts_json")
    assert run_facts_type and "TEXT" in run_facts_type

    # 唯一约束实际拒绝同一 VPC 两条策略（骨架旧表仅含 id 列）
    from sqlalchemy import text as _t
    from sqlalchemy.exc import IntegrityError
    with engine.begin() as conn:
        conn.execute(_t("INSERT INTO sdn_vpcs (id) VALUES (1)"))
        conn.execute(_t("INSERT INTO sdn_assurance_policies (vpc_id, enabled, cadence, response_mode, version) "
                        "VALUES (1, 1, 'manual', 'observe_only', 1)"))
        try:
            conn.execute(_t("INSERT INTO sdn_assurance_policies (vpc_id, enabled, cadence, response_mode, version) "
                            "VALUES (1, 0, '10m', 'observe_only', 1)"))
            raise AssertionError("duplicate vpc_id policy should be rejected")
        except IntegrityError:
            pass
    engine.dispose()


def test_upgrade_014_idempotent(monkeypatch, tmp_path):
    db_file = tmp_path / "up014b.db"
    engine = create_engine(f"sqlite:///{db_file}")
    _make_legacy_schema(engine)
    engine.dispose()

    cfg = _alembic_config()
    _stamp_013(cfg, db_file, monkeypatch)

    from alembic import command
    command.upgrade(cfg, "014")
    command.upgrade(cfg, "014")
    command.upgrade(cfg, "014")

    engine = create_engine(f"sqlite:///{db_file}")
    assert "sdn_assurance_policies" in set(inspect(engine).get_table_names())
    engine.dispose()


def test_downgrade_014_drops_tables(monkeypatch, tmp_path):
    db_file = tmp_path / "down014.db"
    engine = create_engine(f"sqlite:///{db_file}")
    _make_legacy_schema(engine)
    engine.dispose()

    cfg = _alembic_config()
    _stamp_013(cfg, db_file, monkeypatch)

    from alembic import command
    command.upgrade(cfg, "014")
    command.downgrade(cfg, "013")

    engine = create_engine(f"sqlite:///{db_file}")
    tables = set(inspect(engine).get_table_names())
    assert "sdn_assurance_policies" not in tables
    assert "sdn_assurance_runs" not in tables
    assert "sdn_vpcs" in tables  # 旧表保留
    engine.dispose()


# ============================ S3-002 迁移 015 ============================


def _upgrade_to_014(db_file, monkeypatch):
    """013 旧库骨架 → upgrade 014（S3-001 表）。"""
    engine = create_engine(f"sqlite:///{db_file}")
    _make_legacy_schema(engine)
    engine.dispose()
    cfg = _alembic_config()
    _stamp_013(cfg, db_file, monkeypatch)
    from alembic import command
    command.upgrade(cfg, "014")
    return cfg


def _insert_014_fixture(db_file):
    """014 库插一条 vpc + 策略 + 一条 completed manual run（供 015 数据保持验证）。"""
    from sqlalchemy import text as _t
    engine = create_engine(f"sqlite:///{db_file}")
    with engine.begin() as conn:
        conn.execute(_t("INSERT INTO sdn_vpcs (id) VALUES (1)"))
        conn.execute(_t(
            "INSERT INTO sdn_assurance_policies (vpc_id, enabled, cadence, response_mode, version) "
            "VALUES (1, 1, '10m', 'observe_only', 1)"
        ))
        conn.execute(_t(
            "INSERT INTO sdn_assurance_runs (vpc_id, trigger, status, started_at, completed_at, "
            "policy_version, policy_enabled, facts_json, summary_json, items_json) "
            "VALUES (1, 'manual', 'completed', '2026-09-25 00:00:00', '2026-09-25 00:00:01', "
            "1, 1, '{}', '{\"overall\": \"healthy\"}', '[]')"
        ))
    engine.dispose()


def test_upgrade_015_creates_slots_and_extends_runs(monkeypatch, tmp_path):
    """014 旧库（含数据）→ upgrade 015：slots 表 + 唯一索引 + runs 加 slot_key/error + CHECK 扩展。"""
    db_file = tmp_path / "up015.db"
    cfg = _upgrade_to_014(db_file, monkeypatch)
    _insert_014_fixture(db_file)

    from alembic import command
    command.upgrade(cfg, "015")

    engine = create_engine(f"sqlite:///{db_file}")
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert "sdn_assurance_slots" in tables
    assert "sdn_assurance_runs" in tables
    assert _index_exists(engine, "uq_sdn_assurance_slots_vpc")

    slot_cols = {c["name"] for c in insp.get_columns("sdn_assurance_slots")}
    assert {"id", "vpc_id", "slot_key", "cadence", "policy_version", "generation",
            "status", "due_at", "claimed_at", "claim_token", "lease_expires_at",
            "run_id", "error", "created_at", "updated_at"} <= slot_cols

    run_cols = {c["name"] for c in insp.get_columns("sdn_assurance_runs")}
    assert "slot_key" in run_cols and "error" in run_cols
    assert _index_exists(engine, "ix_sdn_assurance_runs_vpc_id")  # 重建后索引仍在
    # CR61：同窗口 (vpc_id, slot_key) 至多一条 run 的 DB 防御（与 ORM 命名一致）
    assert _index_exists(engine, "uq_sdn_assurance_runs_vpc_slot_key")

    # 014 旧数据保持（手动 run 的 slot_key 为 NULL）
    from sqlalchemy import text as _t
    with engine.connect() as conn:
        runs = conn.execute(_t(
            "SELECT trigger, status, slot_key, error FROM sdn_assurance_runs"
        )).fetchall()
        assert len(runs) == 1
        assert runs[0][0] == "manual" and runs[0][1] == "completed"
        assert runs[0][2] is None and runs[0][3] is None
        policies = conn.execute(_t(
            "SELECT enabled, cadence, version FROM sdn_assurance_policies"
        )).fetchall()
        assert len(policies) == 1 and policies[0][2] == 1

    # 新 CHECK 允许 status='failed'（014 旧 CHECK 会拒绝）
    with engine.begin() as conn:
        conn.execute(_t(
            "INSERT INTO sdn_assurance_runs (vpc_id, trigger, status, started_at, completed_at, "
            "policy_version, policy_enabled, slot_key, error, facts_json, summary_json, items_json) "
            "VALUES (1, 'scheduled', 'failed', '2026-09-25 01:00:00', '2026-09-25 01:00:01', "
            "1, 1, 'vpc:1:slot:gen:0', 'boom', '{}', '{\"overall\": null}', '[]')"
        ))
    # 唯一索引实际拒绝同一 VPC 两个窗口
    from sqlalchemy.exc import IntegrityError
    with engine.begin() as conn:
        conn.execute(_t(
            "INSERT INTO sdn_assurance_slots (vpc_id, slot_key, cadence, policy_version, generation, "
            "status, due_at) VALUES (1, 'vpc:1:slot:gen:0', '10m', 1, 0, 'pending', '2026-09-25 02:00:00')"
        ))
        try:
            conn.execute(_t(
                "INSERT INTO sdn_assurance_slots (vpc_id, slot_key, cadence, policy_version, generation, "
                "status, due_at) VALUES (1, 'vpc:1:slot:gen:1', '10m', 1, 1, 'pending', '2026-09-25 02:10:00')"
            ))
            raise AssertionError("duplicate vpc_id slot should be rejected")
        except IntegrityError:
            pass

    # CR61：同 (vpc_id, slot_key) 至多一条 run；slot_key NULL（manual）允许多行
    with engine.begin() as conn:
        conn.execute(_t(
            "INSERT INTO sdn_assurance_runs (vpc_id, trigger, status, started_at, completed_at, "
            "policy_version, policy_enabled, slot_key, facts_json, summary_json, items_json) "
            "VALUES (1, 'scheduled', 'completed', '2026-09-25 03:00:00', '2026-09-25 03:00:01', "
            "1, 1, 'vpc:1:slot:gen:5', '{}', '{}', '[]')"
        ))
        try:
            conn.execute(_t(
                "INSERT INTO sdn_assurance_runs (vpc_id, trigger, status, started_at, completed_at, "
                "policy_version, policy_enabled, slot_key, facts_json, summary_json, items_json) "
                "VALUES (1, 'scheduled', 'completed', '2026-09-25 03:01:00', '2026-09-25 03:01:01', "
                "1, 1, 'vpc:1:slot:gen:5', '{}', '{}', '[]')"
            ))
            raise AssertionError("duplicate (vpc_id, slot_key) run should be rejected")
        except IntegrityError:
            pass
        # 两条 manual（slot_key NULL）共存
        conn.execute(_t(
            "INSERT INTO sdn_assurance_runs (vpc_id, trigger, status, started_at, completed_at, "
            "policy_version, policy_enabled, facts_json, summary_json, items_json) "
            "VALUES (1, 'manual', 'completed', '2026-09-25 04:00:00', '2026-09-25 04:00:01', "
            "1, 1, '{}', '{}', '[]')"
        ))
        conn.execute(_t(
            "INSERT INTO sdn_assurance_runs (vpc_id, trigger, status, started_at, completed_at, "
            "policy_version, policy_enabled, facts_json, summary_json, items_json) "
            "VALUES (1, 'manual', 'completed', '2026-09-25 04:01:00', '2026-09-25 04:01:01', "
            "1, 1, '{}', '{}', '[]')"
        ))
    engine.dispose()


def test_upgrade_015_idempotent(monkeypatch, tmp_path):
    """015 重复升级 no-op（不重建、不丢数据）。"""
    db_file = tmp_path / "up015b.db"
    cfg = _upgrade_to_014(db_file, monkeypatch)
    _insert_014_fixture(db_file)

    from alembic import command
    command.upgrade(cfg, "015")
    command.upgrade(cfg, "015")

    from sqlalchemy import text as _t
    engine = create_engine(f"sqlite:///{db_file}")
    with engine.connect() as conn:
        runs = conn.execute(_t("SELECT count(*) FROM sdn_assurance_runs")).scalar()
        assert runs == 1  # 重复升级不重建、数据仍在
    assert _index_exists(engine, "uq_sdn_assurance_slots_vpc")
    assert _index_exists(engine, "uq_sdn_assurance_runs_vpc_slot_key")  # CR61 幂等
    engine.dispose()


def test_downgrade_015_drops_slots_restores_runs(monkeypatch, tmp_path):
    """降级 015→014：slots 表删除；runs 回到旧 schema（slot_key/error 去掉、CHECK 复原拒绝 failed）。"""
    db_file = tmp_path / "down015.db"
    cfg = _upgrade_to_014(db_file, monkeypatch)
    _insert_014_fixture(db_file)

    from alembic import command
    command.upgrade(cfg, "015")
    engine = create_engine(f"sqlite:///{db_file}")
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO sdn_assurance_slots (vpc_id, slot_key, cadence, policy_version, generation, "
            "status, due_at) VALUES (1, 'vpc:1:slot:gen:0', '10m', 1, 0, 'pending', '2026-09-25 03:00:00')"
        ))
        conn.execute(text(
            "INSERT INTO sdn_assurance_runs (vpc_id, trigger, status, started_at, completed_at, "
            "policy_version, policy_enabled, slot_key, error, facts_json, summary_json, items_json) "
            "VALUES (1, 'scheduled', 'failed', '2026-09-25 03:10:00', '2026-09-25 03:10:01', "
            "1, 1, 'vpc:1:slot:gen:0', 'boom', '{}', '{\"overall\": null}', '[]')"
        ))
    engine.dispose()

    command.downgrade(cfg, "014")

    engine = create_engine(f"sqlite:///{db_file}")
    tables = set(inspect(engine).get_table_names())
    assert "sdn_assurance_slots" not in tables
    run_cols = {c["name"] for c in inspect(engine).get_columns("sdn_assurance_runs")}
    assert "slot_key" not in run_cols and "error" not in run_cols
    assert _index_exists(engine, "ix_sdn_assurance_runs_vpc_id")
    assert not _index_exists(engine, "uq_sdn_assurance_runs_vpc_slot_key")  # CR61 索引随降级移除
    # 014 无 failed 语义；降级保留行并映射为 started，不冒充 completed。
    with engine.connect() as conn:
        statuses = [row[0] for row in conn.execute(text(
            "SELECT status FROM sdn_assurance_runs WHERE trigger='scheduled'"
        )).fetchall()]
    assert statuses == ["started"]
    # 旧 CHECK 复原：status='failed' 被拒绝
    from sqlalchemy.exc import IntegrityError
    with engine.begin() as conn:
        try:
            conn.execute(text(
                "INSERT INTO sdn_assurance_runs (vpc_id, trigger, status, started_at, completed_at, "
                "policy_version, policy_enabled, facts_json, summary_json, items_json) "
                "VALUES (1, 'scheduled', 'failed', '2026-09-25 04:00:00', '2026-09-25 04:00:01', "
                "1, 1, '{}', '{}', '[]')"
            ))
            raise AssertionError("status='failed' must be rejected at 014 schema")
        except IntegrityError:
            pass
    engine.dispose()


def test_orm_create_all_matches_015_unique_index(monkeypatch, tmp_path):
    """CR61：ORM create_all 生成的 run 表具名唯一索引与迁移 015 命名一致（幂等重复升级同）。"""
    from app.database import Base

    db_file = tmp_path / "orm015.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    assert _index_exists(engine, "uq_sdn_assurance_runs_vpc_slot_key")
    assert _index_exists(engine, "uq_sdn_assurance_slots_vpc")
    # ORM 表结构可再升级一次 015（幂等不炸）
    cfg = _alembic_config()
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")
    from alembic import command
    command.stamp(cfg, "014")
    command.upgrade(cfg, "015")
    assert _index_exists(engine, "uq_sdn_assurance_runs_vpc_slot_key")
    engine.dispose()
