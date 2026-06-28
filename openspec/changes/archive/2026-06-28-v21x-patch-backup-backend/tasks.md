## 1. 数据库 / 配置

- [x] 1.1 `backend/app/models.py`：新增 `Backup` 表（id, device_id FK CASCADE, filename, file_path, backup_type, size, content_hash, locked, created_at）
- [x] 1.2 alembic migration：`alembic revision --autogenerate -m "add backups table"` → `d201cd0389d1_add_backups_table.py`
- [x] 1.3 跑 `alembic upgrade head`（容器内），确认表创建（启动时由 `app/main.py::on_startup` 自动跑）
- [x] 1.4 `.env.example` 新增 `BACKUP_DIR=/data/backups`、`BACKUP_KEEP=5`
- [x] 1.5 `docker-compose.dev.yml` 加 `volumes: h3c-netctrl-backups:/data/backups`，backend 服务 mount 该 volume

## 2. 后端 BackupManager 工具类

- [x] 2.1 `backend/app/utils/backup_manager.py` 新建：`BackupManager` 类
  - [x] `__init__(device_id, host, port, username, password)`
  - [x] `pull_file(remote_path, local_path)`：用 `paramiko.SSHClient` + `open_sftp()` 拉文件
  - [x] `create_backup(types=["startup","running"])`：拉文件 + 落盘 + 写 Backup 记录 + 触发轮转
  - [x] `rotate(device_id, keep=N)`：保留最新 N 份非锁定，删最旧非锁定
  - [x] `restore(backup_id)`：NETCONF load-config 优先，SSH 推送 fallback
  - [x] `_hash_file(path)`：SHA256 计算

## 3. 后端 API 路由

- [x] 3.1 `backend/app/routers/backup.py` 新建：
  - [x] `POST /api/devices/{id}/backup` 单设备
  - [x] `GET /api/devices/{id}/backup` 列表
  - [x] `GET /api/devices/{id}/backup/{bid}` 下载
  - [x] `DELETE /api/devices/{id}/backup/{bid}` 删除（锁定 403）
  - [x] `POST /api/devices/{id}/backup/{bid}/lock` 锁定/解锁
  - [x] `POST /api/devices/{id}/backup/{bid}/restore` 回滚
  - [x] `POST /api/backups` 全量
- [x] 3.2 每个 API 写 `record_log`（action='backup_create' / 'backup_restore' / 'backup_delete' / 'backup_lock'）
- [x] 3.3 `app/main.py` 引入 backup router

## 4. 前端 API 客户端

- [ ] 4.1 ~~`frontend/src/api/index.js` 新增 `backupApi`~~ ⏸️ **延后到 v2.2（前端留）**

## 5. 前端 Modal 组件

- [ ] 5.1 ~~`frontend/src/components/BackupListModal.vue` 新建~~ ⏸️ **延后到 v2.2（前端留）**

## 6. 前端接入

- [ ] 6.1 ~~`frontend/src/views/Devices.vue` 表格行操作列加"备份"按钮~~ ⏸️ **延后到 v2.2**
- [ ] 6.2 ~~`frontend/src/views/CMDB.vue` 顶部加"全量备份"按钮~~ ⏸️ **延后到 v2.2**
- [ ] 6.3 ~~Devices.vue / CMDB.vue 引入 BackupListModal~~ ⏸️ **延后到 v2.2**

## 7. 真实设备验证（192.168.100.4 Leaf-03）

> 用户决策：本次不发版 v2.2，本 change 作为 v2.1.x patch 灰度收尾。真实设备验证需要用户现场配合，**留作可选 follow-up**，不在本 change 完成。

- [ ] 7.1 单设备备份：192.168.100.4 → 2 个文件落地到 `/data/backups/4/`
- [ ] 7.2 列表：API 返回 2 条记录
- [ ] 7.3 锁定：锁定 1 个 → 状态切换
- [ ] 7.4 轮转：触发 7 次非锁定备份 → 验证只留 5 份 + 1 份锁定的
- [ ] 7.5 比对：备份 A → 改设备配置 → 当前 hash ≠ A hash
- [ ] 7.6 回滚：从 A 还原 → 当前 hash = A hash
- [ ] 7.7 全量备份：6 台并发，结果聚合
- [ ] 7.8 重启容器：备份文件保留（volume 验证）

## 8. 收尾

- [x] 8.1 提交代码 `feat(backup): 手动备份 + 回滚 + 轮转`（后端）
- [x] 8.2 同步推送 volume 挂载说明到 .env.example / docker-compose.dev.yml
- [x] 8.3 archive change（标注：**v2.1.x patch 灰度，不发版 v2.2**，前端 v2.2 完成后再起新 change 合并）

## 9. 文档

- [x] 9.1 `VERSION-ROADMAP.md` 新增"v2.1.x patch 灰度"章节
- [x] 9.2 `README.md` 版本路线图章节更新（指向 VERSION-ROADMAP.md）
