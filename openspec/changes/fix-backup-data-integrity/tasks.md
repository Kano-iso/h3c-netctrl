# fix-backup-data-integrity — Tasks

## 拆细原则（v2.6.1 复盘）

**v2.6.0 subagent 跑得太快（9 commit 一次过完）问题 → 本次拆 4 个独立 task，每步：**
- 1 commit（清晰的 type: 描述）
- 1 qa 验证（lint+build 或 pytest）
- 1 真机验证（如涉及容器）
- 1 报告数字给用户

**严格按顺序** —— T1 验证完才能开 T2，避免一次性改动大爆炸。

## Task 总览

| # | 任务 | 改的文件 | qa 验证 | 预计 commit |
|---|---|---|---|---|
| T1 | vite proxy 下载路由 | `frontend/vite.config.js` | qa-frontend lint+build | 1 |
| T2 | 备份文件持久化（自检+恢复） | `backend/app/utils/backup_integrity.py`(新) + `docker-compose.dev.yml` | qa-backend pytest + 容器内 `ls /data/backups/1/*.cfg` | 2 |
| T3 | backup-async 数据一致性 | `backend/app/utils/backup_manager.py` + `backend/app/config.py` + `backend/app/task_manager.py` | qa-backend pytest + 跑 backup-async 看 list 立刻看到 | 3 |
| T4 | 环境清理（dev.db 残留） | `tools/dump_db.py`(新) + `tools/cleanup_data_container.sh`(新) | qa-backend pytest + 容器内 `ls /app/data/` | 4 |

---

## Task 1：vite proxy 下载路由

**问题**：`GET /api/devices/{id}/backup/{id}` 无后缀，vite proxy DATA_PATTERN 没匹配，走 ctrl 容器 → 404

**文件**：
- `frontend/vite.config.js`（加 DOWNLOAD_PATTERN 分支）

**改动**：
```js
// 在 DATA_PATTERN / CONFIG_PATTERN 之后加：
const DOWNLOAD_PATTERN = /^\/api\/devices\/\d+\/backup\/\d+\/?$/

// pickTarget 函数加分支（优先级：DOWNLOAD → DATA → CONFIG → CTRL）：
function pickTarget(url) {
  if (DOWNLOAD_PATTERN.test(url)) return isSplit ? DATA : BACKEND
  if (DATA_PATTERN.test(url)) return isSplit ? DATA : BACKEND
  if (CONFIG_PATTERN.test(url)) return isSplit ? CONFIG : BACKEND
  return isSplit ? CTRL : BACKEND
}
```

**commit**：`fix(vite-proxy): 加下载 URL 路由分支，backup/{id} GET 走 data 容器 (v2.6.1 fix-backup-data-integrity Task 1)`

**qa 验证**：
- [ ] `docker compose -f docker-compose.dev.yml --profile qa run --rm qa-frontend` → `npm run lint && npm run build` 全过
- [ ] 浏览器 MCP 手动：`fetch('/api/devices/1/backup/93')` 走 data 容器（看 vite proxy 日志）
- [ ] 修复后：v2.6.0 已修的路由（execute/interfaces/vlans/assets）不破

**报告**：T1 完成，qa-frontend lint + build 通过，download 路由走对容器

---

## Task 2：备份文件持久化

**问题**：35 条 backup 中部分文件物理丢失（如 `/data/backups/1/20260702T194036__running.cfg`），data 容器返回 410

**子步骤**：
- T2a：加启动时自检脚本
- T2b：恢复或标注 410 原因

### T2a：自检脚本（不修改 data）

**文件**：
- `backend/app/utils/backup_integrity.py`（新）
- `backend/data_svc/main.py`（启动时调 self-check，只 warn 不删）

**改动**：
```python
# backend/app/utils/backup_integrity.py
def check_backup_files(db: Session) -> dict:
    """启动时自检：DB 里的 backup.file_path 是否物理存在
    Returns:
        {
            "total": int, "missing": int,
            "missing_files": [{"id": int, "device_id": int, "file_path": str}, ...]
        }
    """
    bks = db.query(Backup).all()
    missing = []
    for b in bks:
        if not os.path.exists(b.file_path):
            missing.append({"id": b.id, "device_id": b.device_id, "file_path": b.file_path})
    return {"total": len(bks), "missing": len(missing), "missing_files": missing}
```

`data_svc/main.py` 启动时：
```python
@app.on_event("startup")
async def startup_check():
    from app.database import SessionLocal
    from app.utils.backup_integrity import check_backup_files
    db = SessionLocal()
    try:
        result = check_backup_files(db)
        if result["missing"] > 0:
            logger.warning(
                f"启动自检: backup 物理文件缺失 {result['missing']}/{result['total']}，"
                f"详情: {result['missing_files'][:5]}"
            )
    finally:
        db.close()
```

**commit**：`feat(backup): 加启动时 backup 物理文件自检 (v2.6.1 fix-backup-data-integrity Task 2a)`

### T2b：恢复 / 标注 410 原因

**Apply 阶段决策**（用 AskUserQuestion 摆出选项）：
- A：删除 DB 行（同步 410 → 0，让 list 不再显示无法下载的备份）
- B：保留 DB 行 + 在 Backup schema 加 `file_missing: bool` 字段，前端 UI 显示"文件丢失"提示
- C：保留 DB 行 + 启动时自检 WARN（最低侵入，让用户手动决定）

**commit**：`fix(backup): 备份文件丢失处理策略 (v2.6.1 fix-backup-data-integrity Task 2b)`

**qa 验证**：
- [ ] qa-backend pytest 全过
- [ ] 启动 data 容器看日志有自检 warn
- [ ] 跑 `docker exec h3c-data python -c "from app.utils.backup_integrity import check_backup_files; from app.database import SessionLocal; print(check_backup_files(SessionLocal()))"` 看 missing 数

**报告**：T2 完成，自检脚本就位，X 个 backup 物理文件丢失（Apply 阶段报告具体数字）

---

## Task 3：backup-async 数据一致性

**问题**：task 报告 status=success + result.backups[0].id=102，但 DB 里 max id=101；8 个 task 全部 report id=102

**子步骤**：
- T3a：DB_PATH 改绝对路径（最小风险变更）
- T3b：BackupManager commit 后 refresh 验证
- T3c：session expire_on_commit=False

### T3a：DB_PATH 绝对路径

**文件**：
- `backend/app/config.py`

**改动**：
```python
class Settings(BaseSettings):
    # v2.6.1 fix-backup-data-integrity Task 3a
    # data 容器用绝对路径，避免 cwd 变化误连 dev.db
    # split 模式：data 容器在 /app 启动，DB_PATH 默认指向 /app/data/data.db
    # core 模式：backend 容器可保持 ./data/dev.db（向后兼容）
    DB_PATH: str = "/app/data/data.db"
```

**commit**：`fix(config): DB_PATH 默认绝对路径避免误连 dev.db (v2.6.1 fix-backup-data-integrity Task 3a)`

**qa 验证**：
- [ ] qa-backend pytest 全过（不破现有测试）
- [ ] 启动 data 容器，SQLAlchemy 能连 `/app/data/data.db`

### T3b：commit 后 refresh 验证

**文件**：
- `backend/app/utils/backup_manager.py`

**改动**：在 `create_backup` 内部 `db.commit()` 之后、`rotate()` 之前加：
```python
# v2.6.1 fix-backup-data-integrity Task 3b
# commit 后立即 refresh，验证行真在 DB（不依赖 session cache）
for r in results:
    db.refresh(backup)  # backup 对象可能已 expire
    b_row = db.query(Backup).filter(Backup.id == r["id"]).first()
    if not b_row:
        raise BackupError(
            f"commit 后 backup 行不存在: id={r['id']}, filename={r['filename']} "
            f"（疑似 session 隔离 / commit 失败）"
        )
    r["id"] = b_row.id  # 用真实 id 替换 flush 时分配的临时 id
    r["created_at"] = b_row.created_at.isoformat() if b_row.created_at else None
```

**commit**：`fix(backup-manager): commit 后 refresh 验证 backup 行真在 DB (v2.6.1 fix-backup-data-integrity Task 3b)`

**qa 验证**：
- [ ] qa-backend pytest 全过
- [ ] 手动跑 backup-async，验证 task 报告的 id 和 list 接口的 id 一致

### T3c：session expire_on_commit=False

**文件**：
- `backend/app/task_manager.py`
- `backend/app/routers/backup.py`（`_async_backup_fn`）

**改动**：
```python
# task_manager.py: SessionLocal() 默认 expire_on_commit=True
# v2.6.1 fix-backup-data-integrity Task 3c
# 长生命周期 session（task manager 跨函数）设 expire_on_commit=False
# 避免 session 关闭（finally 块）属性过期触发隐式 SQL
```

实际改：让 SessionLocal 默认 expire_on_commit=False（影响所有 session，但 SQLAlchemy 文档推荐默认 False 除非有特殊理由）

或者更稳妥：不动 SessionLocal，在 `_async_backup_fn` 内显式 `db.expire_on_commit = False`：
```python
def _async_backup_fn(task_id, cancel_event, progress_cb, device_id, types):
    db = SessionLocal()
    db.expire_on_commit = False  # v2.6.1 fix-backup-data-integrity Task 3c
    try:
        ...
```

**commit**：`fix(task-manager): session expire_on_commit=False 避免长生命周期 session 隐式 expire (v2.6.1 fix-backup-data-integrity Task 3c)`

**qa 验证**：
- [ ] qa-backend pytest 全过
- [ ] 跑 backup-async → task 报告的 backup id 在 list 接口能立刻看到

**报告**：T3 完成，3 个子步骤 commit 完成后，跑一次 backup-async 验证 task 报告与 list 一致

---

## Task 4：环境清理（dev.db 残留）

**问题**：data 容器 `/app/data/` 有 5 个 DB（`config.db` / `ctrl.db` / `data.db` / `dev.db` / `dev.db.bak`），dev.db 385KB 老 monolith 时代，ctrl.db 不应在 data 容器

**子步骤**：
- T4a：dump 工具（不删，先备份）
- T4b：合并或删 dev.db
- T4c：删 ctrl.db dev.db.bak main.py 残留

### T4a：dump 工具

**文件**：
- `tools/dump_db.py`（新）

**改动**：
```python
#!/usr/bin/env python3
"""DB dump 工具（v2.6.1 fix-backup-data-integrity Task 4a）

把 SQLite DB 里的关键表（devices / backups / assets / tasks / logs）dump 成 JSON，
用于 data 容器 /app/data 残留 DB 清理前的人肉验证。
"""
import sqlite3, json, sys
import argparse

TABLES = ['devices', 'backups', 'assets', 'tasks', 'logs', 'alembic_version']

def dump(db_path: str, output: str):
    conn = sqlite3.connect(db_path)
    result = {}
    for t in TABLES:
        try:
            c = conn.cursor()
            c.execute(f"SELECT * FROM {t}")
            cols = [d[0] for d in c.description]
            rows = c.fetchall()
            result[t] = {"columns": cols, "rows": [dict(zip(cols, r)) for r in rows]}
        except sqlite3.OperationalError:
            result[t] = None  # 表不存在
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"dumped {db_path} → {output}")
    for t, v in result.items():
        if v is None:
            print(f"  {t}: 表不存在")
        else:
            print(f"  {t}: {len(v['rows'])} rows")

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--db', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    dump(a.db, a.output)
```

**commit**：`feat(tools): dump_db.py 把 SQLite DB dump 成 JSON 供清理前验证 (v2.6.1 fix-backup-data-integrity Task 4a)`

**qa 验证**：
- [ ] `python tools/dump_db.py --db ./data/dev.db --output /tmp/dev-snapshot.json` 成功
- [ ] 检查 /tmp/dev-snapshot.json 内容，看 dev.db 是否真有历史价值

### T4b：删除 dev.db（决策点）

**Apply 阶段决策**（用 AskUserQuestion）：
- A：dump 后直接删（dev.db 是 7-05 老 monolith，35 条 backup 都在 data.db 里了）
- B：保留 dev.db 在主机目录（不动 data 容器内，bind mount 还会同步）
- C：移走 dev.db 到 `./data/.archive/dev-snapshot-2026-07-06.db`（gitignored 目录）

**commit**：`chore: 清理 data 容器 dev.db 残留 (v2.6.1 fix-backup-data-integrity Task 4b)`

### T4c：删 ctrl.db / dev.db.bak / main.py

**问题**：
- `ctrl.db` 114KB 在 data 容器内（不应该，ctrl 容器有自己的 volume 或路径）
- `dev.db.bak` 159KB 老备份
- `main.py` 1.7KB 早期 main.py 副本

**决策**：T4a dump 验证后，删这三个文件。**注意**：这是 bind mount 同步的，删了主机目录也消失。

**commit**：`chore: 清理 data 容器内 ctrl.db/dev.db.bak/main.py 残留 (v2.6.1 fix-backup-data-integrity Task 4c)`

**qa 验证**：
- [ ] qa-backend pytest 全过（不破）
- [ ] 容器内 `ls /app/data/` 只剩 config.db data.db
- [ ] 主机目录 `ls ./data/` 同步只剩 config.db data.db（如果 T4b 也删 dev.db）

**报告**：T4 完成，data 容器内环境干净（仅 2 个 DB）

---

## 完整验收清单（发版前）

- [ ] 4 个 task × 6 个 commit（T1 1 个 + T2 2 个 + T3 3 个 + T4 3 个 = 9 个 commit）
- [ ] qa-backend 245+ tests 全 PASS
- [ ] qa-frontend lint + build 全过
- [ ] playwright e2e 关键流程通过（Backup.vue 下载、立即全量备份）
- [ ] MCP 浏览器验证：split 模式点"下载"按钮真能下文件
- [ ] 真机 .177 跑 backup-async → list 立刻看到新备份
- [ ] 主目录 git status 干净
- [ ] RELEASE-NOTES-v2.6.1.md 写完
- [ ] VERSION-ROADMAP.md §v2.6.1 + §1 加 1 行
- [ ] README.md 顶部版本表同步
- [ ] change archive：`git mv openspec/changes/fix-backup-data-integrity/ archive/2026-07-06-fix-backup-data-integrity/`
- [ ] git tag v2.6.1 + push（**需用户确认**）
