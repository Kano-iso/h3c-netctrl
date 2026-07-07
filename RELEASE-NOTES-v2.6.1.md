# RELEASE-NOTES-v2.6.1

**版本**: v2.6.1
**日期**: 2026-07-07
**主题**: bug 修复轮次（资产陈旧 + 备份数据完整性 + 备份状态同步）
**前序**: v2.6.0 (2026-07-06)

> v2.6.1 = **修 bug + 健壮性补全**。v2.6.0 i18n 上线后用户回归发现 dashboard 陈旧数据 + 备份/恢复链路多个问题，QA 套件盲区反思 + 集中修 6 类问题。
> **无 BREAKING SCHEMA** — 纯修 bug + 加 1 个新审计字段 `backups.forced`。

---

## 1. 主题

v2.6.0 i18n 上线后用户回归发现以下问题：

1. **Dashboard 陈旧数据**：assets 表 `status='online'` 是采集时刻快照，超过 24h 仍算 online；不主动修复错误数据（设计漏洞）
2. **备份链路多个问题**：
   - 备份下载 404（vite proxy 路由缺失）
   - 备份物理文件丢失后 DB 仍保留"幽灵行"，list 仍显示但下载 410
   - backup-async 任务报告假成功（commit 后 id 与 list 不一致）
   - 未采集/离线设备仍可强制备份（缺状态校验）
3. **回滚链路 SFTP/SCP 缺**：H3C V7 设备未默认开启 `sftp server enable`，导致 restore "无响应"
4. **QA 套件盲区**：pytest 不覆盖"数据陈旧"等业务时间敏感场景，发版 archive 时未做"线上数据 sanity check"

v2.6.1 包含 **6 个 change + 22 个 commit + 1 review 反思**：

| change | 主题 | commit | 状态 |
|---|---|---|---|
| `fix-asset-stale-status` | assets 表 `updated_at` 阈值自动降级 + dashboard 按阈值过滤 | 8 | ✅ archive |
| `fix-asset-collect-failure` | 采集链路失败可读化（错误信息准确 + 中文化） | 8 | ✅ archive |
| `fix-asset-split-password-decrypt` | split 模式密码二次解密修 | 3 | ✅ archive |
| `fix-vite-proxy-route` | vite proxy 用正则精确分发修端点 404 | 1 | ✅ archive |
| `fix-backup-data-integrity` | 下载路由 + 启动自检 + 配置/数据一致性 + 环境清理 | 6 | ✅ archive |
| `fix-asset-backup-state-sync` | 未采集/离线设备备份按钮 disabled + force 逃生通道 + `backups.forced` 审计字段 | 5 | ✅ archive |
| `fix-backup-restore-no-response` | 根因定位（设备缺 `sftp server enable`）+ 修复方案文档（不需代码修复） | 1 (docs) | ✅ archive |
| `v261-roadmap` | 总入口 proposal | - | ✅ archive |
| `docs/REVIEW-v261-bugfix-round.md` | QA 套件盲区反思 + 后续如何补"数据陈旧"场景测试 | 1 | ✅ archive |

---

## 2. 新增能力 / 字段

### 2.1 `backups.forced` 审计字段（v2.6.1 fix-asset-backup-state-sync）

`backend/app/models.py` 中 `Backup` 模型：

```python
forced: Mapped[bool] = mapped_column(default=False, server_default="0", nullable=False)
# True = 经由 force=true 强制备份（绕过 asset 状态校验）
# False = 正常备份（asset online）
# 不参与业务逻辑（不影响下载/回滚/删除/轮转），仅供审计查询
```

Alembic 迁移：`backend/migrations/versions/006_add_forced_to_backups.py`（带 IF EXISTS 守卫，split 容器兼容）

### 2.2 资产陈旧自动降级（v2.6.1 fix-asset-stale-status）

- `ASSET_STALE_HOURS` 环境变量（默认 24h）控制降级阈值
- `ASSET_STALE_ENABLED=True` 启用自动降级（默认 True，调试用 False 关闭）
- data 容器启动时跑一次降级：超阈值 `online → offline`
- dashboard 读取 assets 时按阈值过滤，过期数据不计入 online 统计
- `/internal/assets` 返回每个 asset dict 加 `is_stale: bool` 字段

### 2.3 tools/dump_db.py 工具（v2.6.1 fix-backup-data-integrity Task 4）

```bash
python3 tools/dump_db.py <db_path> [--output <output_path>]
# 默认输出：data/<dbname>_dump_<时间戳>.json
```

用途：把 SQLite DB 全部表 dump 成 JSON，供清理前人肉验证 + 离线性回退。

---

## 3. Bug 修复清单

### 3.1 资产相关

| change | 修复 | commit |
|---|---|---|
| `fix-asset-stale-status` | assets 表超阈值自动降级 + dashboard 按阈值过滤 | 8 commits（见 archive） |
| `fix-asset-collect-failure` | 采集失败错误信息可读化（error_key + 中文 fallback） | 8 commits |
| `fix-asset-split-password-decrypt` | split 模式 password 二次解密修 | 3 commits |
| `fix-asset-backup-state-sync` | 未采集/离线设备备份按钮 disabled + force 逃生 | 5 commits |

### 3.2 备份相关

| change | 修复 | commit |
|---|---|---|
| `fix-vite-proxy-route` | vite proxy 用正则精确分发（execute/interfaces/vlans/assets 不破） | `843a302` |
| `fix-backup-data-integrity` T1 | 加 `DOWNLOAD_PATTERN` 修 `backup/{id}` GET 404 | `72ae439` |
| `fix-backup-data-integrity` T2 | 启动时 backup 物理文件自检 + 清理幽灵行 | `435bdad` |
| `fix-backup-data-integrity` T3a | `DB_PATH` 默认值改绝对路径，跨 cwd 稳定 | `a3a809f` |
| `fix-backup-data-integrity` T3b | commit 后 `db.refresh(backup)` + 真实 id 验证防假成功 | `6547d74` |
| `fix-backup-data-integrity` T3c | `SessionLocal(expire_on_commit=False)` 防长任务属性 reload | `c383f8c` |
| `fix-backup-data-integrity` T4 | dump_db.py 工具 + 删 dev.db/dev.db.bak/main.py 残留 + dump 临时文件挪到 `.archive/` | `4cf4b2b` + 本地操作 |
| `fix-asset-backup-state-sync` | 资产状态校验（`check_asset_online`） + 同步/异步/全量端点 + 前端 force 勾选 + 二次确认弹窗 + 10 个 i18n key | `5d72a15` / `52de2b2` / `b5e7b3e` / `3489546` / `c4456ef` |
| `fix-backup-restore-no-response` | 根因定位文档：H3C V7 缺 `sftp server enable`（用户已配设备修复，不需代码改动） | `14331a6` |

---

## 4. 前端 i18n 新增 key（v2.6.1 fix-asset-backup-state-sync）

10 个新 key（中英文同步）：

| key | zh-CN | en-US |
|---|---|---|
| `button.disabled.asset_offline` | 资产未采集，无法备份 | Asset not collected, cannot backup |
| `backup.force_label` | 强制 | Force |
| `backup.force_confirm_title` | 强制备份确认 | Force Backup Confirmation |
| `backup.force_confirm_msg` | 设备资产未采集/离线，继续备份可能获取到陈旧配置。是否继续？ | Device asset is uncollected/offline, backup may get stale config. Continue? |
| `backup.force_confirm_btn` | 强制备份 | Force Backup |
| `backup.force_success` | 强制备份已启动（审计已记录 forced=1） | Force backup started (forced=1 audit logged) |
| `backup.force_failed` | 强制备份失败 | Force backup failed |
| `cmdb.full_backup_force` | 强制全量备份（含离线/未采集设备） | Force full backup (including offline/uncollected) |
| `cmdb.full_backup_force_hint` | 勾选后将跳过资产状态校验，备份可能获取到陈旧配置 | Skip asset status check, backup may get stale config |
| `error.backup.device_offline` | 设备 {device_id} 资产未采集/离线 | Device {device_id} asset uncollected/offline |

---

## 5. QA 验证

### 5.1 后端

- **qa-backend pytest**：baseline 309 → 313+ passed（含 4 个新 force 场景 case）
- **启动 data 容器**：自检 warn 日志就位 + 幽灵行已清理
- **真机 backup-async**：`/api/devices/7/backup-async` 任务报告 id 与 list 接口 id 一致

### 5.2 前端

- **qa-frontend lint + type-check + build + 53/53 vitest + 42/42 playwright e2e**：全过
- **MCP 浏览器**：
  - Devices.vue 第 5/8 行（offline 设备）显示"强制"checkbox + 备份按钮 disabled ✓
  - 勾选 force → 备份按钮变 enabled ✓
  - 点击备份 → 弹"强制备份确认"弹窗（取消/强制备份）✓
  - 中英文切换 10 个 i18n key 全部正确翻译 ✓

### 5.3 真机集成

| 设备 | 测试 | 结果 |
|---|---|---|
| 192.168.100.5 (Leaf-04) | 临时 asset=offline → 无 force 备份 422 → force=true 备份成功 + DB.forced=1 | ✅ |
| 192.168.100.177 (Test-Switch-177) | online 备份成功（API 默认路径，无 force 不入强制分支） | ✅ |
| 192.168.100.5 (Leaf-04) | 已配 `sftp server enable` → SFTP restore 验证（用户手动配置，不在代码范围） | ✅ |

### 5.4 追验后清理

- `.5` asset 状态已从 offline 恢复为 online（生产数据未被污染）
- 新增 DB 记录 backup `id=78/79 forced=1`（force 流程审计样本，可保留）
- `data/dev_dump_20260706T121722.json` 临时 dump 输出移至 `data/.archive/`（保留为历史快照）

---

## 6. 升级步骤

```bash
# 1. 拉代码
git pull origin main

# 2. 重新构建 + 启动（split 3 容器，默认模式不变）
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d

# 3. Alembic 迁移自动跑（006_add_forced_to_backups）
docker exec h3c-ctrl alembic upgrade head
docker exec h3c-config alembic upgrade head
docker exec h3c-data alembic upgrade head
# 注：006 迁移带 IF EXISTS 守卫，仅 data 容器有 backups 表才会执行
#     ctrl/config 容器无 backups 表 → 跳过（split 容器兼容）

# 4. 验证 force 流程
# 浏览器访问 http://localhost:5173/ → 设备管理
# 找一个 offline 设备行 → 应看到"强制"checkbox + 备份按钮 disabled
# 勾选 force → 备份按钮变 enabled → 点击 → 二次确认 → 强制备份

# 5. 验证陈旧资产降级
# 改一个设备的 asset.updated_at 为 25h 前 → 重启 data 容器 → 该设备应自动降为 offline
docker exec h3c-data python3 -c "
import sqlite3
c = sqlite3.connect('/app/data/data.db')
c.execute(\"UPDATE assets SET updated_at = datetime('now', '-25 hours') WHERE device_id=1\")
c.commit()
"
docker compose -f docker-compose.dev.yml restart data
# 重启后 GET /api/assets/device/1 应返回 status=offline
```

---

## 7. 兼容性

- **后端 API**：`APIResponse` schema 不变（`forced` 仅是 `backups` 表新列，不影响 API 响应字段）
- **数据库**：`backups` 表加 `forced` 列（Alembic 自动迁移），`assets` 表无 schema 变更（仅程序逻辑用 `updated_at`）
- **前端**：Devices.vue / CMDB.vue 加 force 勾选 UI，无破坏性变更
- **i18n**：zh-CN.js / en-US.js 加 10 个 key（向后兼容）

---

## 8. 反思（v2.6.0 review）

> 详见 [docs/REVIEW-v261-bugfix-round.md](docs/REVIEW-v261-bugfix-round.md)

v2.6.0 archive 时 qa-backend 全量 pytest + qa-frontend lint+build 都过，但用户立刻发现 dashboard online=7 陈旧数据 bug。**QA 套件不覆盖"业务时间敏感"场景（如数据陈旧、过期降级）**，所以没发现。

**改进方向**：
- Archive 前必须做"线上数据 sanity check"（curl 真实 endpoints 看返回是否符合业务预期），不只是 qa 容器自动化测试
- 加"时间敏感"测试 fixture（mock 旧时间戳 → 验证降级逻辑）
- 真机集成测试必跑 .177（不能跳过 switch down 的借口）

---

## 9. 文件清单

### 9.1 新增

- `backend/app/utils/asset_guard.py`（check_asset_online 函数）
- `backend/app/utils/backup_integrity.py`（启动自检）
- `backend/migrations/versions/006_add_forced_to_backups.py`（带 IF EXISTS 守卫）
- `tools/dump_db.py`（SQLite dump 工具）
- `docs/REVIEW-v261-bugfix-round.md`（QA 反思）

### 9.2 修改

- `backend/app/models.py`（Backup.forced 字段）
- `backend/app/routers/backup.py`（force 校验 + 全量端点）
- `backend/app/routers/asset.py`（split 模式密码解密）
- `backend/app/routers/dashboard.py`（陈旧资产过滤）
- `backend/app/utils/backup_manager.py`（commit+refresh 验证）
- `backend/app/database.py`（SessionLocal expire_on_commit=False）
- `backend/app/config.py`（DB_PATH 绝对路径 + ASSET_STALE_*）
- `frontend/src/views/Devices.vue`（force 勾选 + 二次确认）
- `frontend/src/views/CMDB.vue`（全量备份 force 选项）
- `frontend/src/i18n/zh-CN.js` / `en-US.js`（10 个新 key）
- `frontend/vite.config.js`（DOWNLOAD_PATTERN + 精确分发）
- `frontend/src/App.vue`（activeGroup computed .value 修复）

### 9.3 清理

- 删 `data/dev.db` / `data/dev.db.bak` / `data/main.py`（monolith 残留）
- 移 `data/dev_dump_*.json` → `data/.archive/`（dump 临时输出保留为历史快照）

---

## 10. 关联

- [VERSION-ROADMAP.md §v2.6.1 章节](VERSION-ROADMAP.md)
- [v261-roadmap proposal](openspec/changes/archive/2026-07-07-v261-roadmap/)（总入口）
- [docs/REVIEW-v261-bugfix-round.md](docs/REVIEW-v261-bugfix-round.md)（QA 反思）
- 6 个子 change：见 `openspec/changes/archive/2026-07-07-*` 目录
