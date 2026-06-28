## Why

v2.1.x patch (`archive/2026-06-28-v21x-patch-backup-backend`) 完成 backup 后端，**但真机验证从未完成**（task 7.1-7.8 全 `[ ]` 留作 follow-up）。

今天 v2.2 backup-frontend 真机验证（192.168.100.4 Leaf-03）发现 **2 个阻塞 bug**：

### Bug 1: `_force_save_on_device` 卡住
- 实现：`paramiko.exec_command("save force", timeout=15)` + `stdout.channel.recv_exit_status()`
- 现象：H3C V7 上 `save force` 是**交互式**命令（需 `Y` 确认），非交互式调用 → 设备等输入 → channel closed
- 实际日志：`Channel closed.` → `save force 失败: Channel closed.`
- 影响：每台设备备份白白浪费 15s 等待；`create_backup` 用 `try/except` 吞掉后继续 SFTP

### Bug 2: SFTP 不可用
- 实现：`paramiko.SSHClient.open_sftp().get(remote, local)`
- 现象：192.168.100.4 报 `The SFTP server is disabled or the SFTP service type is not supported.`
- 实际：H3C V7 默认 **SFTP 子系统未启用**（需要 `sftp server enable` 显式开启，但项目 memory 明确"避免实现 FTP server for backup storage；use SCP-based methods instead"）
- 影响：**整个 backup 功能在当前设备上无法工作**

### 影响范围

- backup-frontend 已完成 5 个 commit（API 客户端 / Modal / Backup.vue / Devices.vue / CMDB.vue）
- 前端已就绪，但**真机备份跑不通**
- 用户已明确说"备份是上线的必要项"（v2.2 备份前端专项）

### 关键决策

- **SFTP 改 SCP 推送**：项目 memory 红线 + H3C 默认禁 SFTP
- **save force 改交互式 shell**：用 `ssh_executor.SSHExecutor.execute()` 或 `execute_commands()`，检测 `Y/N` 提示后发送 `Y`
- **依赖增加 `scp` 包**（paramiko 配套的纯 Python SCP 实现）
- **拉取 + 推送都用 SCP 通道**

## What Changes

### 修改

- `backend/app/utils/backup_manager.py`：
  - `_force_save_on_device`：用 `SSHExecutor.execute_commands()` 发 `save force` + 交互式发送 `Y`；或新写 `_force_save_via_ssh_shell()`
  - `pull_file`：`open_sftp().get()` → `SCPClient(client.get_transport()).get(remote, local)`
  - `_restore_via_ssh` 已经发 SSH 命令，不需要大改

- `backend/requirements.txt`：新增 `scp>=0.14.0`（paramiko 官方推荐搭档）
- `backend/Dockerfile`：无需改（pip install 走 requirements）
- `backend/app/utils/ssh_executor.py`：**不改**（已支持交互式 + 分页）

### 不改

- `frontend/`：backup-frontend 5 个 commit 维持
- `openspec/changes/backup-frontend/`：前端 change 维持，等后端修好再 archive
- 数据库：schema 不动
- `backup-frontend` tasks.md：标注"阻塞于本 change 完成"

## Capabilities

### 新增能力

- `fix-backup-manager-save-force-and-scp`：backup 后端真机可跑（save force 交互式 + SFTP 改 SCP）

### 影响的能力

- `v21x-patch-backup-backend` 的 spec 需要追加修订：本 change 落实后才算完整
- `backup-frontend` 的依赖：本 change 是前置

## 验收标准

- [ ] `save force` 在 192.168.100.4 上 5s 内返回（不是 15s 超时）
- [ ] `pull_file` 在 192.168.100.4 上成功，文件落盘到 `/data/backups/{device_id}/`
- [ ] 单设备备份 `POST /api/devices/4/backup` 总耗时 < 30s
- [ ] 列表 `GET /api/devices/4/backup` 返回 2 条记录（startup + running）
- [ ] 备份文件可用 `cat` 查看，startup.cfg 包含设备启动配置
- [ ] restore 用 NETCONF 推送成功（之前的方案不动）
- [ ] 全量备份 `POST /api/backups` 完成 < 60s（6 台串行）
- [ ] 后端日志显示 backup 成功记录（增加 logger.info 业务日志）
