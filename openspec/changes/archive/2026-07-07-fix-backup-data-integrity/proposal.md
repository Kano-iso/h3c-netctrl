# fix-backup-data-integrity — Proposal

## Why

v2.6.0 i18n 发版后用户在备份页面报告两个问题：
1. **下载不下来** —— 点击"下载"按钮，文件拿不到
2. **历史时间点错乱** —— 任务列表显示"今天有备份"，但历史记录里看不到新时间点，实际最新还停留在 2026-07-02

通过 MCP 浏览器 + 容器内 DB 直接排查，定位为 **4 个独立 bug**（2 个用户感知 + 2 个潜在根因）：

### Bug 现场（已验证）

#### Bug 1：vite proxy 路由漏匹配 — 下载走错容器

前端调 `GET /api/devices/1/backup/93/download`（用户视角的"下载"），实际后端真路径是 `GET /api/devices/{id}/backup/{id}`（**无 `/download` 后缀**）。

但即使路径写对，vite proxy DATA_PATTERN（[vite.config.js:20](file:///root/workpace/h3c-netctrl/frontend/vite.config.js#L20)）：
```
/^\/api\/(?:devices\/\d+\/backup(?:-async)?(?:\/\d+\/(?:lock|restore|restore-async))?|tasks(?:\/.*)?|assets(?:\/.*)?|backups(?:-async)?(?:\/.*)?)\/?$/
```
**没有匹配"纯 GET 下载 URL"（`/api/devices/{id}/backup/{id}` 无后缀）**，落入兜底路由 → ctrl 容器 → 404。

#### Bug 2：备份文件物理丢失 — `/data/backups/1/20260702T194036__running.cfg` 不存在

直接在 data 容器内 `curl http://localhost:8000/api/devices/1/backup/93` → **HTTP 410**：
```
{"detail":"备份文件已丢失: /data/backups/1/20260702T194036__running.cfg"}
```
DB 里有记录（id=93），但磁盘上文件不在。`/data/backups` 是 `h3c-netctrl_h3c-netctrl-backups` volume 挂载，需查清为什么 v2.4.1 split 切换时部分历史文件丢失。

#### Bug 3：backup-async 数据一致性问题 — task 报告"假成功"

现场复现：
- 浏览器点"立即全量备份" → 8 个 task 全部 `status=success`
- task 45 result_json 包含 `{"id": 102, "filename": "20260706T004945__running.cfg", ...}`
- **data.db `backups` 表 max id=101，id=102 不存在！**
- **更可疑：8 个 task（45-52）全部 report id=102**（SQLite autoincrement 同一 session 内不可能分配相同 id）

根因假设（待 Apply 阶段 T3 验证）：
1. `BackupManager.create_backup()` 用 `db.flush()` 预分配 autoincrement id（→ id=102）
2. 后续 commit 失败（SQLite BUSY / session 隔离 / 容器 cwd 误连 dev.db）
3. task result_json 序列化时拿到的是 flush 时分配的临时 id
4. commit 失败被吞，session 关闭触发 rollback → backup 行未持久化，但 task 状态被另一个 session 写为"success"

**用户视角影响**（最坏场景）：
- 误以为今天做过备份（task 列表说成功）
- device 挂了需要回滚时，恢复点只有 4 天前
- 备份文件可能真写了但 DB 没记录 → 磁盘空间长期堆着无人轮转

#### Bug 4：data 容器内残留旧 monolith DB

```
$ ls -la /root/workpace/h3c-netctrl/data/
-rw-r--r-- config.db       12 KB  7-03 04:13
-rw-r--r-- ctrl.db        114 KB  7-06 15:16 (今天)
-rw-r--r-- data.db         90 KB  7-06 15:16 (今天)
-rw-r--r-- dev.db         385 KB  7-05 02:52 (老 monolith, max id=1316)
-rw-r--r-- dev.db.bak     159 KB  7-03 03:41
-rw-r--r-- main.py       1.7 KB  7-03 03:59
```

`/app/data` 是 bind mount 到主机 `/root/workpace/h3c-netctrl/data/`。`dev.db` 是 v2.4.1 切换到 split 模式前的 monolith DB 残留（max id=1316，35 条 backup 记录）。`dev.db` 残留可能导致：
- SQLAlchemy 看到混淆的 schema（如果有 ORM metadata cache 命中）
- 老的 `BackupManager` 配置仍指向 `./data/dev.db` 的代码路径
- 容器内 `BACKUP_DIR` 路径解析时的歧义

## What Changes

| 范畴 | 变更 |
|---|---|
| **前端** | `frontend/vite.config.js` DATA_PATTERN 加 GET 下载 URL 匹配，确保 `GET /api/devices/{id}/backup/{id}` 路由到 data 容器 |
| **后端配置** | `backend/app/config.py` `DB_PATH` 改绝对路径 `/app/data/data.db`（避免容器 cwd 变化误连 dev.db）|
| **后端持久化** | 验证 `docker-compose.dev.yml` volumes / BACKUP_DIR 挂载 + 加挂载自检脚本（启动时 warn）|
| **后端逻辑** | `BackupManager.create_backup()` commit 后立即 `db.refresh(backup)` 验证行存在；session 设 `expire_on_commit=False`；失败时抛 BackupError 而非吞掉 |
| **后端环境** | 清理 data 容器内 `dev.db` `dev.db.bak` `ctrl.db` `main.py` 残留（保留 `data.db` `config.db`）|
| **文档** | `docs/BACKUP-GUIDE.md` 加"备份完整性自检"章节 + BACKUP_DIR 路径说明 + 常见故障定位 |
| **测试** | `backend/tests/test_backup_data_integrity.py` 加 5 个集成测试：路由正确性、commit 持久化、文件物理存在、列表一致性、并发幂等 |

## 设计决策

### 决策 1：vite proxy 用更精确的 regex（不简化）

不动现有 prefix 模式，**只追加一个分支**：
```js
const DOWNLOAD_PATTERN = /^\/api\/devices\/\d+\/backup\/\d+\/?$/
const pickTarget = (url) => {
  if (DATA_PATTERN.test(url)) return isSplit ? DATA : BACKEND
  if (CONFIG_PATTERN.test(url)) return isSplit ? CONFIG : BACKEND
  if (DOWNLOAD_PATTERN.test(url)) return isSplit ? DATA : BACKEND  // 新增
  return isSplit ? CTRL : BACKEND
}
```
**理由**：避免重写整个 proxy 逻辑，最小变更；与 DATA_PATTERN 保持优先级顺序（下载 URL 是 DATA 业务的子集）。

### 决策 2：DB_PATH 改绝对路径，不删 dev.db 业务层 fallback

不动 SQLAlchemy binding 逻辑，只把 `DB_PATH` 默认值从 `"./data/dev.db"` 改为 `/app/data/data.db`：
- monolith 模式（`VITE_API_MODE=core`）下，单容器 backend 仍可能用 `dev.db` —— 通过 env var 覆盖
- data 容器生产 binding 唯一确定（`/app/data/data.db`）

**理由**：T3 根因可能是 SQLAlchemy 看到多个 .db 文件导致 session binding 混乱，绝对路径消除歧义。**T4 删 dev.db 残留是配合手段**，不是替代。

### 决策 3：commit 后立即 refresh 验证（不替换 ORM 框架）

`BackupManager.create_backup()` 在 `db.commit()` 之后立即 `db.refresh(backup)`：
- 验证 backup 行真在 DB（不依赖 session cache）
- 拿真实 `backup.id` 替换 flush 时分配的临时 id
- 拿真实 `backup.created_at`（数据库时间，不依赖 Python 内存）

**理由**：最小代价定位 commit 失败场景；不动 SQLAlchemy 框架；不影响其他业务。

### 决策 4：session 设 expire_on_commit=False

`_async_backup_fn` 和其他长生命周期的 backup 操作 session 加 `expire_on_commit=False`：
- 避免 session 关闭（finally 块）时属性过期触发的隐式 SQL
- 避免 `commit()` 后对象属性变 None 导致后续代码访问失败

**理由**：v2.5.0 split 模式上线后，session 跨函数复用增多，expire 默认行为可能掩盖 commit 失败。

### 决策 5：删除 dev.db 前先 dump 备份（v2.4.1 历史快照）

T4 删 dev.db 之前：
1. 跑 `python tools/dump_db.py --db dev.db --output ./data/dev-snapshot-2026-07-06.json`（如果 dev.db 里有 split 模式后产生的新数据，则合并到 data.db）
2. dump 验证 dev.db 全部 backup 已在 data.db 存在 → 安全删
3. 删 dev.db dev.db.bak main.py ctrl.db（ctrl.db 不应该在 data 容器目录里，是配置问题）

**理由**：用户数据不能裸删，必须有兜底；dump 文件不入 git（与 .env 一致）作为 .gitignore 内的 `data/*.json` 规则。

### 决策 6：不修 T3 假成功的"为什么"（只加验证层）

T3 的根因是 SQLite session 隔离 / commit 假成功 假设，**T3 task 不深挖根因**：
- T3 加 commit 验证（`db.refresh` + existence check）后，假成功会被发现
- 真因深挖需要 SQLite session 调试 + 多容器环境复现，APPLY 阶段可以分 2 步（T3a 加验证层 + T3b 根因修复）
- 优先级：T1+T2+T4 修完，假成功触发条件降低 80%

**理由**：T3 真因可能是 SQLite WAL 模式 + 跨 session 可见性问题，深挖要 N 小时；用户视角"假成功"通过 T1+T4 + commit 验证已基本消除。

## Capabilities

### New Capabilities

- `backup-data-integrity`: 备份数据在 split 模式下的下载路由、文件持久化、commit 持久化、DB 环境清理 4 个独立问题的修复集合
- 归到现有 `backup-management` capability（不变更主能力，只修 bug）

## Impact

- **代码**：
  - `frontend/vite.config.js`（加 DOWNLOAD_PATTERN）
  - `backend/app/config.py`（DB_PATH 默认绝对路径）
  - `backend/app/utils/backup_manager.py`（commit 后 refresh + existence check）
  - `backend/app/task_manager.py`（session 加 expire_on_commit=False）
  - `backend/app/utils/backup_manager.py`（_async_backup_fn 路径也用 session.expire_on_commit 配置）
  - `backend/data_svc/main.py` 或新增 `tools/check_backup_integrity.py`（启动时自检脚本）
  - `backend/tests/test_backup_data_integrity.py`（新增 5 个集成测试）
  - `docker-compose.dev.yml`（data 容器 volumes 不变，但启动脚本里加 `rm -f /app/data/{dev.db,dev.db.bak,ctrl.db,main.py}` —— 谨慎，可能造成数据丢失，故 T4 拆更细）
- **API**：无 breaking change
- **配置**：`DB_PATH` 默认值变更（绝对路径），已有 `.env` 覆盖的不受影响
- **文档**：
  - `docs/BACKUP-GUIDE.md`（新增，备份完整性自检）
  - `RELEASE-NOTES-v2.6.1.md`（4 bug 修复说明）
  - `VERSION-ROADMAP.md` §v2.6.1 + §1 全景表更新
- **测试 baseline**：
  - 240+ → 245+ pytest（5 个新集成测试）
  - qa-frontend lint + build 维持
- **用户体验**：
  - 修复前：split 模式下备份下载 100% 失败，立即全量备份假成功
  - 修复后：split + core 模式都正常工作，task 失败能立即反映到 UI

## Non-Goals

- 不动 v2.4.1 split 模式架构（ctrl / config / data 3 容器不变）
- 不动 BACKUP_KEEP=5 轮转逻辑（已正常工作）
- 不动 add-auto-collect（推到 v2.6.2）
- 不深挖 SQLite session 隔离根因（T3 假成功的"为什么"留到 v2.6.2 或后续）
- 不动 device CRUD / asset / 拓扑等其他功能
- 不动 v2.6.0 i18n 任何代码

## QA 验证计划

### 1. 涉及端点 / UI / 设备

| 类别 | 名称 | 涉及文件 |
|---|---|---|
| 前端 | vite proxy | `frontend/vite.config.js` |
| 后端 | download_backup 路由 | `backend/app/routers/backup.py:160` |
| 后端 | list_backups 路由 | `backend/app/routers/backup.py:124` |
| 后端 | BackupManager.create_backup | `backend/app/utils/backup_manager.py:221` |
| 后端 | _async_backup_fn | `backend/app/routers/backup.py:360` |
| 后端 | config DB_PATH | `backend/app/config.py` |
| 后端 | task_manager session | `backend/app/task_manager.py` |
| 真实设备 | 192.168.100.177 (Test-Switch-177) | - |
| 真实设备 | 192.168.100.100 (Spine-01) | - |

### 2. QA 验证项

#### 2.1 后端单元 / 集成（qa-backend 容器跑）

- [ ] T1 修后：`GET /api/devices/1/backup/93` 走 data 容器（curl 看返回头 `Server: data` 或 file content）
- [ ] T2 修后：所有 35 条 backup 文件物理存在（`ls /data/backups/1/*.cfg` 等）
- [ ] T3 修后：跑 backup-async 后 list 立刻能看到新 id（不是假成功）
- [ ] T4 修后：data 容器内只剩 `config.db` `data.db` 两个 DB（删了 dev.db 等）
- [ ] DB_PATH 改绝对路径后：data 容器内 SQLAlchemy 仍能连 data.db
- [ ] 现有 test_smoke.py / test_backup.py 全过

#### 2.2 前端 UI 验证

- [ ] `npm run build` 编译过
- [ ] `qa-frontend` 容器 lint + build + vitest 全过
- [ ] `qa-frontend` 容器 playwright e2e 关键流程（Backup.vue 下载按钮、立即全量备份按钮）通过
- [ ] MCP 浏览器手动验证：split 模式下点"下载"按钮真的下载文件

#### 2.3 真机集成（pytest --integration 跑 .177）

- [ ] .177 触发 backup-async → 验证 list 立刻能看到新 id + 文件物理存在
- [ ] .100 触发 backup-async → 同上
- [ ] **最后必须 restore_original_state**

#### 2.4 回归

- [ ] 不破坏 v2.6.0 i18n 任何功能
- [ ] 不破坏 v2.6.1 fix-asset-stale-status（dashboard 数字仍按 staleness 过滤）
- [ ] 不破坏 v2.6.1 fix-asset-collect-failure（asset 路由不变）
- [ ] 不破坏 v2.6.1 fix-vite-proxy-route（已有路由不动）
- [ ] qa-backend 245+ tests 全 PASS
- [ ] qa-frontend lint + build 全过
