#!/usr/bin/env python3
"""v2.4.1 数据库拆分迁移脚本（v241-container-split Task 6.1）

将 monolith 的 data/dev.db 拆分为 3 个独立 SQLite 文件：
- data/ctrl.db  : devices + logs + alembic_version  (ctrl 容器)
- data/config.db: alembic_version                   (config 容器，无业务表)
- data/data.db  : assets + backups + tasks + alembic_version (data 容器)

策略：拷贝 dev.db → 3 份 → 各自 DROP 不属于该容器的表（保留索引/触发器）
- 原 dev.db 不删，自动备份为 dev.db.bak
- SQLite 默认 PRAGMA foreign_keys=OFF，DROP devices 表后 backups.device_id 仍可查询

用法：
    python scripts/migrate-v241-split-db.py            # 默认 ./data/dev.db
    python scripts/migrate-v241-split-db.py --src /path/to/dev.db
    python scripts/migrate-v241-split-db.py --dry-run  # 只打印计划不执行
"""
import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

# 库表归属（按 v241-container-split/design.md D5 决策）
CTRL_TABLES = {"devices", "logs"}
DATA_TABLES = {"assets", "backups", "tasks"}
SHARED_TABLES = {"alembic_version"}  # 每个容器都保留迁移版本表


def get_all_tables(conn) -> list:
    """获取所有业务表名（排除 sqlite_* 内部表）"""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row[0] for row in cur.fetchall()]


def count_rows(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def backup_src(src: Path) -> Path:
    """备份原 dev.db → dev.db.bak（不覆盖已存在的备份）"""
    bak = src.with_suffix(src.suffix + ".bak")
    if bak.exists():
        print(f"[跳过备份] 已存在 {bak}（不覆盖）")
        return bak
    shutil.copy2(src, bak)
    print(f"[备份] {src} → {bak}")
    return bak


def copy_to_target(src: Path, target: Path, force: bool = False):
    """复制 src → target（target 存在时按 --force 决定）"""
    if target.exists():
        if not force:
            print(f"[跳过] {target} 已存在（用 --force 覆盖）")
            return False
        target.unlink()
    shutil.copy2(src, target)
    print(f"[复制] {src} → {target}")
    return True


def drop_tables_not_in(db_path: Path, keep: set):
    """在 db_path 中 DROP 所有不在 keep 集合里的表"""
    conn = sqlite3.connect(db_path)
    try:
        # SQLite 默认 foreign_keys=OFF，DROP 顺序无关
        all_tables = get_all_tables(conn)
        dropped = []
        for t in all_tables:
            if t not in keep:
                conn.execute(f"DROP TABLE IF EXISTS {t}")
                dropped.append(t)
        conn.commit()
        print(f"[DROP] {db_path.name}: 删除 {len(dropped)} 张表 → {dropped}")
    finally:
        conn.close()


def vacuum(db_path: Path):
    """VACUUM 回收空间"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()
    print(f"[VACUUM] {db_path.name}")


def verify_counts(src: Path, ctrl: Path, data: Path):
    """验证迁移后数据量与原 dev.db 一致"""
    print("\n[验证] 数据量对比")
    print(f"{'表':<20} {'dev.db':<10} {'ctrl.db':<10} {'data.db':<10} {'结果':<10}")
    print("-" * 60)

    src_conn = sqlite3.connect(src)
    ctrl_conn = sqlite3.connect(ctrl)
    data_conn = sqlite3.connect(data)

    all_ok = True
    for table in sorted(CTRL_TABLES | DATA_TABLES):
        src_cnt = count_rows(src_conn, table) if table in get_all_tables(src_conn) else 0
        ctrl_cnt = count_rows(ctrl_conn, table) if table in get_all_tables(ctrl_conn) else 0
        data_cnt = count_rows(data_conn, table) if table in get_all_tables(data_conn) else 0

        if table in CTRL_TABLES:
            ok = src_cnt == ctrl_cnt
            target_cnt = ctrl_cnt
        else:
            ok = src_cnt == data_cnt
            target_cnt = data_cnt

        mark = "✓" if ok else "✗ MISMATCH"
        all_ok = all_ok and ok
        print(f"{table:<20} {src_cnt:<10} {ctrl_cnt:<10} {data_cnt:<10} {mark}({target_cnt})")

    src_conn.close()
    ctrl_conn.close()
    data_conn.close()

    if not all_ok:
        print("\n[失败] 数据量不一致，请检查 dev.db.bak 并回滚")
        sys.exit(1)
    print("\n[成功] 数据量一致")


def main():
    parser = argparse.ArgumentParser(description="v2.4.1 monolith → 3 容器 SQLite 拆分")
    parser.add_argument("--src", default="./data/dev.db", help="源 dev.db 路径")
    parser.add_argument("--out-dir", default="./data", help="输出目录（ctrl.db/config.db/data.db）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的目标文件")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划不执行")
    args = parser.parse_args()

    src = Path(args.src).resolve()
    out_dir = Path(args.out_dir).resolve()
    ctrl_db = out_dir / "ctrl.db"
    config_db = out_dir / "config.db"
    data_db = out_dir / "data.db"

    print(f"=== v2.4.1 数据库拆分迁移 ===")
    print(f"源: {src}")
    print(f"输出: {out_dir}")
    print(f"  ctrl.db  → devices + logs + alembic_version")
    print(f"  config.db → alembic_version（无业务表）")
    print(f"  data.db  → assets + backups + tasks + alembic_version")
    print()

    if not src.exists():
        print(f"[错误] 源文件不存在: {src}")
        sys.exit(1)

    if args.dry_run:
        # 只打印现状
        conn = sqlite3.connect(src)
        print("[dry-run] 当前 dev.db 表数据量:")
        for t in get_all_tables(conn):
            print(f"  {t}: {count_rows(conn, t)} rows")
        conn.close()
        return

    # 1. 备份 dev.db
    backup_src(src)

    # 2. 拷贝到 3 份
    for target, label in [(ctrl_db, "ctrl"), (config_db, "config"), (data_db, "data")]:
        ok = copy_to_target(src, target, force=args.force)
        if not ok:
            print(f"[中止] {target} 已存在，迁移未完成")
            sys.exit(1)

    # 3. 各自 DROP 不属于该容器的表
    drop_tables_not_in(ctrl_db, keep=CTRL_TABLES | SHARED_TABLES)
    drop_tables_not_in(config_db, keep=SHARED_TABLES)
    drop_tables_not_in(data_db, keep=DATA_TABLES | SHARED_TABLES)

    # 4. VACUUM 回收空间
    vacuum(ctrl_db)
    vacuum(config_db)
    vacuum(data_db)

    # 5. 验证
    verify_counts(src, ctrl_db, data_db)

    print("\n=== 迁移完成 ===")
    print(f"原 dev.db 保留在: {src}")
    print(f"备份: {src.with_suffix(src.suffix + '.bak')}")
    print(f"\n下一步:")
    print(f"  1. 启动 3 容器模式: docker compose --profile split up")
    print(f"  2. 验证业务正常后可删除 dev.db（保留 dev.db.bak）")
    print(f"  3. 回滚: python scripts/rollback-v241-split-db.py")


if __name__ == "__main__":
    main()
