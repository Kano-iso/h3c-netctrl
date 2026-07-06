#!/usr/bin/env python3
"""SQLite 数据库 dump 工具（v2.6.1 fix-backup-data-integrity Task 4）

用途：把一个 SQLite 数据库的所有表 dump 成 JSON 文件，保留全表数据
场景：清理 monolith 模式历史残留（如 data/dev.db）前先备份内容

用法：
    python3 tools/dump_db.py <db_path> [--output <output_path>]

示例：
    python3 tools/dump_db.py data/dev.db
    # 默认输出：data/dev_db_dump_<时间戳>.json

    python3 tools/dump_db.py data/dev.db --output /tmp/dev_dump.json

输出格式：
    {
        "db_path": "data/dev.db",
        "dumped_at": "2026-07-06T10:00:00",
        "tables": {
            "devices": [{"id": 1, "name": "...", ...}, ...],
            "logs": [...],
            ...
        }
    }
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def dump_db(db_path: str) -> dict:
    """dump SQLite 数据库所有表为 dict"""
    if not Path(db_path).exists():
        raise FileNotFoundError(f"DB 文件不存在: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        table_names = [r[0] for r in cur.fetchall()]

        tables = {}
        for tname in table_names:
            cur.execute(f"SELECT * FROM {tname}")
            rows = cur.fetchall()
            # Row -> dict，BLOB 保持 bytes
            tables[tname] = [dict(r) for r in rows]
    finally:
        conn.close()

    return {
        "db_path": db_path,
        "dumped_at": datetime.utcnow().isoformat() + "Z",
        "tables": tables,
    }


def main():
    parser = argparse.ArgumentParser(
        description="SQLite 数据库 dump 工具（v2.6.1 T4）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("db_path", help="要 dump 的 SQLite db 文件路径")
    parser.add_argument(
        "--output", "-o",
        help="输出 JSON 文件路径（默认：<db_path>_dump_<时间戳>.json）",
    )
    args = parser.parse_args()

    try:
        result = dump_db(args.db_path)
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    if args.output:
        out_path = Path(args.output)
    else:
        # 默认：./data/dev_db_dump_20260706T100000.json
        src = Path(args.db_path)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        out_path = src.parent / f"{src.stem}_dump_{ts}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    table_summary = ", ".join(
        f"{t}={len(rows)}" for t, rows in result["tables"].items()
    )
    print(f"已 dump: {args.db_path} -> {out_path}")
    print(f"  表统计: {table_summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
