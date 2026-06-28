## 1. 数据库 / 配置

- [ ] 1.1 `backend/app/models.py`：新增 `Backup` 表（id, device_id FK CASCADE, filename, file_path, backup_type, size, content_hash, locked, created_at）
- [ ] 1.2 alembic migration：`alembic revision --autogenerate -m "add backups table"`
- [ ] 1.3 跑 `alembic upgrade head`（容器内），确认表创建
- [ ] 1.4 `.env.example` 新增 `BACKUP_DIR=/data/backups`、`BACKUP_KEEP=5`
- [ ] 1.5 `docker-compose.dev.yml` 加 `volumes: h3c-netctrl-backups:/data/backups`，backend 服务 mount 该 volume

## 2. 后端 BackupManager 工具类

- [ ] 2.1 `backend/app/utils/backup_manager.py` 新建：`BackupManager` 类
  - `__init__(device_id, host, port, username, password)`
  - `pull_file(remote_path, local_path)`：用 `paramiko.SSHClient` + `open_sftp().open(remote, 'rb')` 拉文件
  - `create_backup(types=["startup","running"])`：拉文件 + 落盘 + 写 Backup 记录 + 触发轮转
  - `rotate(device_id, keep=N)`：保留最新 N 份非锁定，删最旧非锁定
  - `restore(backup_id)`：NETCONF load-config 优先，SSH 推送 fallback
  - `_hash_file(path)`：SHA256 计算

## 3. 后端 API 路由

- [ ] 3.1 `backend/app/routers/backup.py` 新建：
  - `POST /api/devices/{id}/backup` 单设备
  - `GET /api/devices/{id}/backup` 列表
  - `GET /api/devices/{id}/backup/{bid}` 下载
  - `DELETE /api/devices/{id}/backup/{bid}` 删除（锁定 403）
  - `POST /api/devices/{id}/backup/{bid}/lock` 锁定/解锁
  - `POST /api/devices/{id}/backup/{bid}/restore` 回滚
  - `POST /api/backups` 全量
- [ ] 3.2 每个 API 写 `record_log`（action='backup_create' / 'backup_restore' / 'backup_delete' / 'backup_lock'）
- [ ] 3.3 `app/main.py` 引入 backup router

## 4. 前端 API 客户端

- [ ] 4.1 `frontend/src/api/index.js` 新增 `backupApi`：`list / create / download / delete / lock / restore / all`

## 5. 前端 Modal 组件

- [ ] 5.1 `frontend/src/components/BackupListModal.vue` 新建：
  - 列表（时间 / 类型 / 大小 / 锁定 / 操作）
  - 顶部"新建备份"按钮（弹小弹窗选 startup / running / 两者）
  - 删除/锁定/回滚/下载按钮（回滚用 ConfirmModal）
  - `v-model:open` + `deviceId` + `deviceName` props

## 6. 前端接入

- [ ] 6.1 `frontend/src/views/Devices.vue` 表格行操作列加"备份"按钮，调 `backupModalOpen.value = true`
- [ ] 6.2 `frontend/src/views/CMDB.vue` 顶部加"全量备份"按钮，调 `backupApi.all()`，结果用 banner 展示
- [ ] 6.3 Devices.vue / CMDB.vue 引入 BackupListModal

## 7. 真实设备验证（192.168.100.4 Leaf-03）

- [ ] 7.1 单设备备份：192.168.100.4 → 2 个文件落地到 `/data/backups/4/`
- [ ] 7.2 列表：API 返回 2 条记录
- [ ] 7.3 锁定：锁定 1 个 → 状态切换
- [ ] 7.4 轮转：触发 7 次非锁定备份 → 验证只留 5 份 + 1 份锁定的
- [ ] 7.5 比对：备份 A → 改设备配置 → 当前 hash ≠ A hash
- [ ] 7.6 回滚：从 A 还原 → 当前 hash = A hash
- [ ] 7.7 全量备份：6 台并发，结果聚合
- [ ] 7.8 重启容器：备份文件保留

## 8. 收尾

- [ ] 8.1 提交代码 `feat(backup): 手动备份 + 回滚 + 轮转`
- [ ] 8.2 同步推送 volume 挂载说明到 .env.example
- [ ] 8.3 archive change
