#!/usr/bin/env python3
"""v2.4.1 数据库合并回退脚本（v241-container-split Task 6.2）

将 3 个独立 SQLite 文件合并回 monolith 的 data/dev.db：
- 从 ctrl.db 拷贝 devices + logs
- 从 data.db 拷贝 assets + backups + tasks
- config.db 无业务表，跳过
- alembic_version 从 ctrl.db 拷贝（保留主版本）

策略：
1. 从 dev.db.bak 恢复（如存在）→ 最可靠
2. 如无 .bak，则创建空 dev.db + 从 3 个分库拷贝所有表

用法：
    python scripts/rollback-v241-split-db.py            # 默认 ./data/
    python scripts/rollback-v241-split-db.py --data-dir /path/to/data
    python scripts/rollback-v241-split-db.py --dry-run  # 只打印计划
"""
import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

CTRL_TABLES = ["devices", "logs"]
DATA_TABLES = ["assets", "backups", "tasks"]
ALL_TABLES = CTRL_TABLES + DATA_TABLES  # 合并顺序：先 ctrl 后 data


def get_all_tables(conn) -> list:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row[0] for row in cur.fetchall()]


def count_rows(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def get_create_sql(conn, table: str) -> str:
    """获取表的 CREATE TABLE 语句"""
    cur = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    row = cur.fetchone()
    return row[0] if row else None


def copy_table_data(src_conn, dst_conn, table: str):
    """从 src 拷贝 table 的所有数据到 dst（dst 必须已建表）"""
    cols = [r[1] for r in src_conn.execute(f"PRAGMA table_info({table})").fetchall()]
    placeholders = ",".join(["?"] * len(cols))
    col_list = ",".join(cols)

    rows = src_conn.execute(f"SELECT {col_list} FROM {table}").fetchall()
    dst_conn.executemany(
        f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})",
        rows,
    )
    print(f"  [拷贝] {table}: {len(rows)} rows")


def restore_from_backup(bak: Path, target: Path):
    """从 dev.db.bak 恢复（最可靠方式）"""
    if target.exists():
        target.unlink()
    shutil.copy2(bak, target)
    print(f"[恢复] {bak} → {target}")


def merge_from_split(data_dir: Path, target: Path):
    """从 3 个分库合并创建新的 dev.db"""
    ctrl_db = data_dir / "ctrl.db"
    data_db = data_dir / "data.db"

    if not ctrl_db.exists() or not data_db.exists():
        print(f"[错误] 缺少 ctrl.db 或 data.db，无法合并")
        sys.exit(1)

    if target.exists():
        target.unlink()

    # 创建空 dev.db
    dst = sqlite3.connect(target)
    try:
        # 关闭外键约束（拷贝顺序无关）
        dst.execute("PRAGMA foreign_keys=OFF")

        # 从 ctrl.db 拷贝 devices + logs + alembic_version
        print("[合并] 从 ctrl.db 拷贝:")
        src_ctrl = sqlite3.connect(ctrl_db)
        try:
            for table in CTRL_TABLES + ["alembic_version"]:
                if table in get_all_tables(src_ctrl):
                    create_sql = get_create_sql(src_ctrl, table)
                    if create_sql:
                        dst.execute(create_sql)
                        copy_table_data(src_ctrl, dst, table)
        finally:
            src_ctrl.close()

        # 从 data.db 拷贝 assets + backups + tasks
        print("[合并] 从 data.db 拷贝:")
        src_data = sqlite3.connect(data_db)
        try:
            for table in DATA_TABLES:
                if table in get_all_tables(src_data):
                    create_sql = get_create_sql(src_data, table)
                    if create_sql:
                        dst.execute(create_sql)
                        copy_table_data(src_data, dst, table)
        finally:
            src_data.close()

        dst.commit()
    finally:
        dst.close()

    print(f"[合并完成] {target}")


def verify(target: Path):
    """验证合并后的 dev.db 表数据量"""
    print("\n[验证] 合并后 dev.db 表数据量:")
    conn = sqlite3.connect(target)
    try:
        for t in get_all_tables(conn):
            print(f"  {t}: {count_rows(conn, t)} rows")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="v2.4.1 3 容器 SQLite → monolith 合并回退")
    parser.add_argument("--data-dir", default="./data", help="含 ctrl.db/data.db 的目录")
    parser.add_argument("--target", default="./data/dev.db", help="合并后的 dev.db 路径")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 target")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划不执行")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    target = Path(args.target).resolve()
    bak = target.with_suffix(target.suffix + ".bak")

    print(f"=== v2.4.1 数据库合并回退 ===")
    print(f"数据目录: {data_dir}")
    print(f"目标: {target}")
    print(f"备份: {bak}")
    print()

    # 优先从 .bak 恢复
    if bak.exists():
        print(f"[策略] 检测到 {bak}，将优先从备份恢复（最可靠）")
        if args.dry_run:
            print("[dry-run] 将从备份恢复")
            return
        if target.exists() and not args.force:
            print(f"[跳过] {target} 已存在（用 --force 覆盖）")
            sys.exit(1)
        restore_from_backup(bak, target)
    else:
        print(f"[策略] 无 {bak}，从 3 个分库合并")
        if args.dry_run:
            print("[dry-run] 将合并 3 个分库")
            return
        if target.exists() and not args.force:
            print(f"[跳过] {target} 已存在（用 --force 覆盖）")
            sys.exit(1)
        merge_from_split(data_dir, target)

    verify(target)

    print("\n=== 回退完成 ===")
    print(f"dev.db 已恢复: {target}")
    print(f"可用 monolith 模式启动: docker compose up")


if __name__ == "__main__":
    main()
