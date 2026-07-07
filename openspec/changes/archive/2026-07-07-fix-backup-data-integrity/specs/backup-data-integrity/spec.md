# backup-data-integrity — Specification

## 范围

本 spec 描述 v2.6.1 修复备份数据在 split 模式下的 4 个独立问题：

1. **T1：vite proxy 下载路由** —— `GET /api/devices/{id}/backup/{id}` 走错容器
2. **T2：备份文件物理持久化** —— 35 条 backup 部分文件丢失
3. **T3：backup-async 数据一致性** —— task 报告假成功
4. **T4：环境清理** —— data 容器内 dev.db / ctrl.db 残留

不影响：v2.4.1 split 架构、BACKUP_KEEP=5 轮转逻辑、device CRUD / asset / 拓扑、v2.6.0 i18n。

---

## T1：vite proxy 下载路由

### 当前行为（v2.6.0）

`frontend/vite.config.js` 中 `DATA_PATTERN` 匹配：
```
/api/devices/{id}/backup-async           ✓
/api/devices/{id}/backup                 ✓
/api/devices/{id}/backup/{bid}/lock      ✓
/api/devices/{id}/backup/{bid}/restore   ✓
/api/devices/{id}/backup/{bid}/restore-async  ✓
/api/devices/{id}/backup/{bid}           ✗ (没匹配)
/api/devices/{id}/backup/{bid}/download  ✗ (前端没这个路径)
```

`/api/devices/{id}/backup/{bid}`（纯 GET 下载）落入兜底 → ctrl 容器 → 404（ctrl 没这个端点）。

### 期望行为（v2.6.1）

`/api/devices/{id}/backup/{bid}` 走 data 容器，返回备份文件（200）或 410（文件丢失）。

### 实现

加 `DOWNLOAD_PATTERN` 优先分支：
```js
const DOWNLOAD_PATTERN = /^\/api\/devices\/\d+\/backup\/\d+\/?$/

function pickTarget(url) {
  if (DOWNLOAD_PATTERN.test(url)) return isSplit ? DATA : BACKEND
  if (DATA_PATTERN.test(url)) return isSplit ? DATA : BACKEND
  if (CONFIG_PATTERN.test(url)) return isSplit ? CONFIG : BACKEND
  return isSplit ? CTRL : BACKEND
}
```

### 验收

- [ ] 浏览器 `fetch('/api/devices/1/backup/93')` 返回 200 (application/octet-stream) 或 410 (文件丢失)
- [ ] vite proxy 日志显示走 data 容器
- [ ] 现有路由不破：execute / interfaces / vlans / assets / tasks / backups-async
- [ ] qa-frontend lint + build 全过

---

## T2：备份文件物理持久化

### 当前行为（v2.6.0）

`backend/app/routers/backup.py:160 download_backup`：
```python
if not os.path.exists(backup.file_path):
    raise HTTPException(status_code=410, detail=f"备份文件已丢失: {backup.file_path}")
```

data 容器返回 410，但**没有启动时自检**，用户不知道哪些文件丢失。

### 期望行为（v2.6.1）

data 容器启动时跑 `check_backup_files()`，WARN 日志列出所有物理文件丢失的 backup 记录。

### 实现

`backend/app/utils/backup_integrity.py`（新）：
```python
def check_backup_files(db: Session) -> dict:
    """启动时自检：DB 里的 backup.file_path 是否物理存在"""
    bks = db.query(Backup).all()
    missing = []
    for b in bks:
        if not os.path.exists(b.file_path):
            missing.append({"id": b.id, "device_id": b.device_id, "file_path": b.file_path})
    return {"total": len(bks), "missing": len(missing), "missing_files": missing}
```

`backend/data_svc/main.py` 启动时调，**只 warn 不删不改**。

### 验收

- [ ] data 容器启动日志有 self-check 结果（total=35, missing=N）
- [ ] qa-backend pytest 新增 `test_check_backup_files` 单元测试（mock 几个 backup + 物理文件）
- [ ] 不破现有 download_backup 路由

---

## T3：backup-async 数据一致性

### 当前行为（v2.6.0）

`backend/app/utils/backup_manager.py:221 create_backup`：
```python
backup = Backup(...)
db.add(backup)
db.flush()  # flush 分配 autoincrement id
results.append({"id": backup.id, ...})  # 序列化临时 id
...
db.commit()  # 可能失败（SQLite BUSY / session 隔离 / dev.db 误连）
```

`_async_backup_fn` 把 results 传给 `task_manager._update_status`：
- 独立 session commit task 行（status=success, result_json）
- 即使 create_backup commit 失败，task 行也提交成功

→ **用户看到"假成功"**。

### 期望行为（v2.6.1）

create_backup commit 后**立即验证 backup 行真在 DB**：
- 验证失败 → 抛 BackupError
- BackupError 冒到 task_manager._run → task status=failed
- 前端看到真实失败

### 实现

#### T3a：DB_PATH 绝对路径

`backend/app/config.py`：
```python
class Settings(BaseSettings):
    # v2.6.1 fix-backup-data-integrity Task 3a
    # 绝对路径避免容器 cwd 变化误连 dev.db
    DB_PATH: str = "/app/data/data.db"
```

向后兼容：已有 `.env` 覆盖 `DB_PATH=./data/dev.db` 不受影响（core 模式）。

#### T3b：commit 后 refresh 验证

`backend/app/utils/backup_manager.py` create_backup line 305 之后：
```python
db.commit()
# v2.6.1 fix-backup-data-integrity Task 3b
# commit 后立即 refresh，验证行真在 DB（不依赖 session cache）
for r in results:
    db.expire(backup)  # 强制重新查询
    db.refresh(backup)
    b_row = db.query(Backup).filter(Backup.id == r["id"]).first()
    if not b_row:
        raise BackupError(
            f"commit 后 backup 行不存在: id={r['id']}, filename={r['filename']}"
        )
    r["id"] = b_row.id
    r["created_at"] = b_row.created_at.isoformat() if b_row.created_at else None
```

#### T3c：session expire_on_commit=False

`backend/app/routers/backup.py` `_async_backup_fn`：
```python
def _async_backup_fn(task_id, cancel_event, progress_cb, device_id, types):
    db = SessionLocal()
    db.expire_on_commit = False  # v2.6.1 fix-backup-data-integrity Task 3c
    try:
        ...
```

不动 SessionLocal 全局默认，只在长生命周期 session 显式设。

### 验收

- [ ] qa-backend pytest 新增 `test_create_backup_commit_verify` 测试
- [ ] 真机 .177 跑 backup-async → task 报告的 backup id 在 list 接口能立刻看到
- [ ] 不破现有 backup 流程（monolith + split 模式）

---

## T4：环境清理

### 当前行为（v2.6.0）

data 容器内 `/app/data/`（bind mount 主机 `./data/`）有 5 个 DB：
```
config.db       12 KB  7-03 04:13   (split 模式 config 容器)
ctrl.db        114 KB  7-06 15:16   (split 模式 ctrl 容器 DB，在 data 容器目录里！)
data.db         90 KB  7-06 15:16   (split 模式 data 容器)
dev.db         385 KB  7-05 02:52   (老 monolith 时代，35 backup, max id=1316)
dev.db.bak     159 KB  7-03 03:41   (老备份)
main.py       1.7 KB  7-03 03:59   (早期 main.py 副本)
```

`dev.db` 残留可能让 SQLAlchemy 看到混淆的 schema。

### 期望行为（v2.6.1）

data 容器内 `/app/data/` 只剩 `config.db` `data.db` 两个 DB。

### 实现

#### T4a：dump 工具

`tools/dump_db.py`（新）：
```python
TABLES = ['devices', 'backups', 'assets', 'tasks', 'logs', 'alembic_version']

def dump(db_path, output):
    """把 SQLite DB 关键表 dump 成 JSON"""
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
            result[t] = None
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
```

#### T4b/T4c：删除（决策点 + 实施）

**Apply 阶段决策**（用 AskUserQuestion 摆出选项）：
- A：dump 验证后直接删（dev.db 35 条 backup 都在 data.db）
- B：保留 dev.db（用户想保留历史快照）
- C：移走 dev.db 到 `./data/.archive/`（gitignored）

### 验收

- [ ] `python tools/dump_db.py --db ./data/dev.db --output /tmp/dev-snapshot.json` 成功
- [ ] `/tmp/dev-snapshot.json` 内容核对：35 backup 都在 data.db 存在
- [ ] data 容器内 `ls /app/data/` 只剩 config.db data.db
- [ ] 主机目录 `ls ./data/` 同步清理
- [ ] qa-backend pytest 全过（不破）

---

## 整体回归

### 不破坏

- v2.6.0 i18n 任何代码
- v2.6.1 fix-asset-stale-status（dashboard staleness 过滤）
- v2.6.1 fix-asset-collect-failure（asset 路由）
- v2.6.1 fix-vite-proxy-route（已有 prefix 路由）
- v2.6.1 fix-asset-split-password-decrypt（password 解密）
- v2.4.1 split 模式架构（ctrl / config / data 3 容器职责）
- BACKUP_KEEP=5 轮转逻辑

### 测试 baseline

- qa-backend 240+ → 245+ tests
- qa-frontend lint + build 维持
- 5 个新集成测试：
  - `test_vite_proxy_download_route`：T1 路由正确性
  - `test_check_backup_files`：T2 自检脚本
  - `test_create_backup_commit_verify`：T3b commit 验证
  - `test_db_path_absolute`：T3a 配置
  - `test_dump_db`：T4a dump 工具

### 性能

- T1 vite proxy 路由：增加一次 regex test，< 1ms 开销
- T2 启动自检：35 个 backup × os.path.exists()，< 100ms
- T3 commit refresh：每次 backup 多 1 次 SELECT，< 10ms 开销
- T4 删除：一次性操作，无性能影响
