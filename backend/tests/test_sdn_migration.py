"""S1 迁移 012 隔离测试。

说明：本项目 alembic 为「棕地」迁移链（002/003/004 对 create_all 预建的
devices/logs 等基表做 ALTER），无法从空库一路 upgrade 到 head。因此这里只
隔离验证 S1 迁移 012 自身：在 stamp 到 011 的旧库（仅含旧 SDN 表骨架）上
upgrade/downgrade 012，验证建表/加列/部分唯一索引。
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
