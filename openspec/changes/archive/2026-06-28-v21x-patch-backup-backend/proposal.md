## Why

v2.2 网控增强三大目标之一：**配置备份 + 回滚**。当前系统只有 NETCONF edit-config 实时下发能力，**无任何配置存档机制**——一旦误操作（如误改 VLAN/接口）就**无回滚路径**，是生产环境的真实风险。

### 用户需求（user feedback v2.2 规划）

- **手动备份**（非定时）：运维人员主动触发，预期会备份当时设备的 `startup.cfg` / `running.cfg`
- **全量备份 + 单设备备份** 两种粒度
- **备份文件可管理**：在设备详情页可看历史备份（文件 + 时间戳），可锁定不被轮转
- **轮转策略**：每设备保留最多 5 份**未锁定**的备份；锁定备份**不参与轮转**（永久保留或直到用户主动解锁/删除）
- **存储形式**：Docker volume 挂载，跨容器重启持久化
- **拉取形式**：后端 SFTP 主动拉（paramiko SFTPClient），无需设备侧起 SCP server
- **回滚能力**：从备份文件还原到设备（NETCONF load-config 或 SSH 推送 startup.cfg）

### 关键设计约束（user feedback）

- **不做定时备份**（"定时备份的机制我觉得可以不要了"）
- **不做"今日份/最近一次"快查**等非核心参数
- **不另起 FTP/SCP server**（避免运维链路复杂化）
- **测试目标设备**：192.168.100.4 (Leaf-03)，用户明确指定为 v2.2 验证节点

### 风险

误操作后无回滚 = 数据丢失级别风险。在生产网中，一个误配置（如误 `shutdown` 核心接口、误删 VLAN 1）可能导致整网中断。

## What Changes

### 后端（`backend/app/routers/backup.py` 新建）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/devices/{id}/backup` | POST | 单设备备份（拉 startup.cfg） |
| `/api/devices/{id}/backup` | GET | 列该设备所有备份（id/file/created_at/locked/size） |
| `/api/devices/{id}/backup/{bid}` | GET | 下载备份文件（Content-Disposition 触发下载） |
| `/api/devices/{id}/backup/{bid}` | DELETE | 删除备份（锁定的不允许删） |
| `/api/devices/{id}/backup/{bid}/lock` | POST | 锁定（body: `{"locked": true/false}`） |
| `/api/devices/{id}/backup/{bid}/restore` | POST | 从指定备份回滚（NETCONF load-config） |
| `/api/backups` | POST | 全量备份（并发对所有设备） |
| `/api/backups/rotate` | POST | 触发轮转（每设备保留 5 份未锁，超出的最旧非锁定删） |

### 新增组件

- `backend/app/utils/backup_manager.py`：封装 SFTP 拉取 + 轮转逻辑
- `backend/app/models.py` 新增 `Backup` 表：`id, device_id, filename, file_path, size, created_at, locked, content_hash`
- `backend/app/database.py` 升级：alembic migration

### 前端

- `frontend/src/views/Devices.vue` 表格行加"备份"按钮（与"连接测试/资产/编辑/删除"并列）
- `frontend/src/components/BackupListModal.vue` 新组件：列出该设备所有备份，含下载/删除/锁定/回滚操作
- `frontend/src/components/ConfirmModal.vue` 复用（已存在）用于"删除备份"和"回滚配置"二次确认
- `frontend/src/views/CMDB.vue`（可选）顶部加"全量备份"按钮

### 配置 / 部署

- `docker-compose.dev.yml` 新增 volume：`h3c-netctrl-backups:/data/backups`
- 后端启动时自动创建目录、设置权限
- `.env.example` 新增 `BACKUP_DIR=/data/backups`、`BACKUP_KEEP=5`

## Capabilities

### New Capabilities
- `manual-backup`：手动配置备份（单设备 + 全量）
- `backup-rotation`：轮转策略（5 份未锁 + 锁定保护）
- `config-rollback`：从备份还原到设备
- `backup-management-ui`：前端备份列表 / 锁定 / 下载 / 删除 UI

### Modified Capabilities
- （无现有 spec 修改）

## Impact

- **代码**：
  - 新增 `backend/app/routers/backup.py`（~200 行）
  - 新增 `backend/app/utils/backup_manager.py`（~150 行）
  - 新增 `backend/app/models.py::Backup`（~30 行）
  - 新增 `frontend/src/components/BackupListModal.vue`（~180 行）
  - 改 `frontend/src/views/Devices.vue`（+ 2 处按钮 + Modal 引入）
  - 改 `docker-compose.dev.yml`（+ 1 volume）
  - 改 `.env.example`（+ 2 env）
- **API 兼容性**：纯增量，不影响现有 CRUD/NETCONF/SSH 路径
- **数据库**：新增 `backups` 表 + alembic 迁移
- **依赖**：
  - 后端：paramiko 已有（用于 SFTPClient），无需新增
  - 前端：无新增
- **回归**：现有所有 change 行为不变
- **回退**：git revert + alembic downgrade
- **测试设备**：192.168.100.4 (Leaf-03)
- **持久化**：Docker volume 跨容器重启保留
- **不做**：定时备份（cron）、"今日份"快查、FTP server

## Open Questions（待解决）

1. **回滚机制**：NETCONF `load-config` (RFC 6241) 在 H3C 设备上是否完整支持？需要实地探测（192.168.100.4）。**fallback**：用 SSH 推送 startup.cfg 后执行 `startup saved-configuration` + `reboot`（不优雅但兼容）
2. **拉取哪个文件**：`startup.cfg`（下次启动用）vs `running.cfg`（当前运行）？**默认建议**：备份两者（filename 后缀区分）
3. **并发备份锁**：同一设备并发触发备份如何处理？**建议**：同设备短时间内互斥（5 秒内）

## 状态：v2.1.x patch 灰度（不发版 v2.2）

**决策记录（2026-06-28）**：本 change **只发后端能力，前端延后到 v2.2**。

- **本次不发版 v2.2**，作为 v2.1.x patch 灰度发布（commit 上 main 分支，但不重打 tag）。
- **后端能力已完成**：Backup 模型 / BackupManager / 7 个 API 端点 / Alembic 迁移 / 部署配置（volume + env）全部就绪。
- **API 验证通过**：5 个 backup 路由全部注册（`/api/devices/{id}/backup*` + `/api/backups`），边界场景"设备不存在"返回标准 APIResponse 错误格式。
- **真实设备验证留作 follow-up**：192.168.100.4 (Leaf-03) 验证需要用户现场配合，本 change 不阻塞 archive。
- **前端延后部分**将在 v2.2 起新 change：
  - `backup-ui`：Devices.vue 加"备份"按钮 + BackupListModal + CMDB 全量备份按钮
  - 当前 task 4.1 / 5.1 / 6.1-6.3 / 7.1-7.8 留作 v2.2 跟进。
