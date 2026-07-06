"""backup_integrity 自检 + 清理模块测试（v2.6.1 fix-backup-data-integrity Task 2a/2b）

覆盖场景：
- check_backup_files() 只读检查：全存在 / 部分缺失 / file_path 为空
- cleanup_missing_backups() 删除：删文件不存在的行 / 保留存在的行
- run_startup_check() 集成入口：返回 summary dict
"""
import os

from app.models import Backup
from app.utils.backup_integrity import (
    check_backup_files,
    cleanup_missing_backups,
    run_startup_check,
)


def _make_backup(db, device_id, file_path, filename="x.cfg", btype="startup"):
    """辅助：插入一条 backup 记录（绕过加密/复杂字段）"""
    bk = Backup(
        device_id=device_id,
        filename=filename,
        file_path=file_path,
        backup_type=btype,
        size=100,
        content_hash="abc",
        locked=False,
    )
    db.add(bk)
    db.commit()
    db.refresh(bk)
    return bk


# ======================== check_backup_files ========================

def test_check_backup_files_empty(db):
    """DB 无 backup 记录 → total=0, missing=0"""
    result = check_backup_files(db)
    assert result == {"total": 0, "missing": 0, "missing_files": []}


def test_check_backup_files_all_exist(db, created_device):
    """文件物理存在 → 全部 OK"""
    real_path = "/tmp/test_backup_integrity_existing.cfg"
    with open(real_path, "w") as f:
        f.write("config content")
    try:
        _make_backup(db, created_device["id"], real_path)
        result = check_backup_files(db)
        assert result["total"] == 1
        assert result["missing"] == 0
        assert result["missing_files"] == []
    finally:
        if os.path.exists(real_path):
            os.remove(real_path)


def test_check_backup_files_some_missing(db, created_device):
    """部分文件物理丢失 → 正确报告 missing 列表"""
    real_path = "/tmp/test_backup_integrity_real.cfg"
    with open(real_path, "w") as f:
        f.write("content")
    try:
        bk_real = _make_backup(db, created_device["id"], real_path)
        bk_ghost1 = _make_backup(
            db, created_device["id"], "/nonexistent/ghost1.cfg", filename="g1.cfg"
        )
        bk_ghost2 = _make_backup(
            db, created_device["id"], "/nonexistent/ghost2.cfg", filename="g2.cfg"
        )

        result = check_backup_files(db)
        assert result["total"] == 3
        assert result["missing"] == 2
        missing_ids = {m["id"] for m in result["missing_files"]}
        assert missing_ids == {bk_ghost1.id, bk_ghost2.id}
        assert bk_real.id not in missing_ids
    finally:
        if os.path.exists(real_path):
            os.remove(real_path)


def test_check_backup_files_file_path_empty(db, created_device):
    """file_path 为空（异常数据）也视为 missing"""
    bk = _make_backup(db, created_device["id"], "", filename="empty.cfg")
    result = check_backup_files(db)
    assert result["total"] == 1
    assert result["missing"] == 1
    assert result["missing_files"][0]["id"] == bk.id
    assert result["missing_files"][0]["file_path"] == ""


# ======================== cleanup_missing_backups ========================

def test_cleanup_missing_backups_deletes_ghost_rows(db, created_device):
    """删除文件不存在的行"""
    real_path = "/tmp/test_cleanup_real.cfg"
    with open(real_path, "w") as f:
        f.write("content")
    try:
        bk_real = _make_backup(db, created_device["id"], real_path)
        bk_ghost1 = _make_backup(
            db, created_device["id"], "/nonexistent/ghost_a.cfg", filename="ga.cfg"
        )
        bk_ghost2 = _make_backup(
            db, created_device["id"], "/nonexistent/ghost_b.cfg", filename="gb.cfg"
        )
        # 提前取 id 到本地变量（避免 cleanup 删行后访问 .id 触发 SQLAlchemy reload → ObjectDeletedError）
        real_id, ghost1_id, ghost2_id = bk_real.id, bk_ghost1.id, bk_ghost2.id

        result = cleanup_missing_backups()
        assert result["scanned"] == 3
        assert result["deleted"] == 2
        assert set(result["deleted_ids"]) == {ghost1_id, ghost2_id}

        # 验证 DB 实际状态（用新 query 避免触碰已删实例）
        remaining_ids = {b.id for b in db.query(Backup).all()}
        assert remaining_ids == {real_id}
    finally:
        if os.path.exists(real_path):
            os.remove(real_path)


def test_cleanup_missing_backups_keeps_when_no_missing(db, created_device):
    """无缺失 → 不删任何行"""
    real_path = "/tmp/test_cleanup_keepall.cfg"
    with open(real_path, "w") as f:
        f.write("content")
    try:
        bk1 = _make_backup(db, created_device["id"], real_path, filename="k1.cfg")
        bk2 = _make_backup(
            db, created_device["id"], real_path, filename="k2.cfg"
        )

        result = cleanup_missing_backups()
        assert result["scanned"] == 2
        assert result["deleted"] == 0
        assert result["deleted_ids"] == []

        remaining = db.query(Backup).count()
        assert remaining == 2
    finally:
        if os.path.exists(real_path):
            os.remove(real_path)


# ======================== run_startup_check ========================

def test_run_startup_check_uses_independent_session(db, created_device, caplog):
    """集成入口：自动建/关 session，返回 summary"""
    import logging
    bk_ghost = _make_backup(
        db, created_device["id"], "/nonexistent/ghost_runstartup.cfg",
        filename="grun.cfg"
    )
    ghost_id = bk_ghost.id  # 提前取 id
    real_path = "/tmp/test_runstartup_real.cfg"
    with open(real_path, "w") as f:
        f.write("content")
    try:
        _make_backup(db, created_device["id"], real_path, filename="rreal.cfg")

        with caplog.at_level(logging.INFO, logger="app"):
            result = run_startup_check()

        assert result["scanned"] == 2
        assert result["deleted"] == 1
        assert ghost_id in result["deleted_ids"]

        # 启动日志：WARN 已记录被删 ids
        warn_msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any(str(ghost_id) in m for m in warn_msgs)
    finally:
        if os.path.exists(real_path):
            os.remove(real_path)
