## Why

v2.1.x patch (`archive/2026-06-28-v21x-patch-backup-backend`) 完成 backup 后端，**但真机验证从未完成**（task 7.1-7.8 全 `[ ]` 留作 follow-up）。

今天 v2.2 backup-frontend 真机验证（192.168.100.4 Leaf-03）发现 **2 个阻塞 bug**：

### Bug 1: `_force_save_on_device` 卡住
- 实现：`paramiko.exec_command("save force", timeout=15)` + `stdout.channel.recv_exit_status()`
- 现象：H3C V7 上 `save force` 是**交互式**命令（需 `Y` 确认），非交互式调用 → 设备等输入 → channel closed
- 实际日志：`Channel closed.` → `save force 失败: Channel closed.`

### Bug 2: SFTP 不可用
- 实现：`paramiko.SSHClient.open_sftp().get(remote, local)`
- 现象：192.168.100.4 报 `The SFTP server is disabled or the SFTP service type is not supported.`
- 实际：H3C V7 默认 **SFTP 子系统未启用**（需要 `sftp server enable` 显式开启）

### 演进过程（多轮真机验证暴露的更多问题）

| 轮次 | 方案 | 真机问题 |
|---|---|---|
| 1 | SFTP 拉 + `save force` | SFTP 不可用 / `save force` 卡死 |
| 2 | SCP 推 + 交互式 shell `save force` | H3C V7 SCP server 默认禁（`scp` 协议失败） |
| 3 | 全 NETCONF：`get-config` 拉 + `edit-config` 推 | 回滚时大量不可写元素（VCF/Domain/Login/RBAC 等系统配置） |
| 4 | NETCONF + 业务白名单 + 逐元素降级 | **白名单无底洞**：A 设备有 XYZ，B 设备有 ABC，厂商升级结构又变 |

### 关键转折（2026-06-28）

用户提出"**去市面上看看大家怎么做的**"。业界主流做法（RANCID / Oxidized / Ansible Network / NAPALM / 华为 eSight / H3C iMC）：

- **拉取**：SSH CLI `display current-configuration` 或 SCP 拉 `startup.cfg`（文本）
- **回滚**：SCP 推 startup + `startup saved-configuration` + **人工确认 reload**
- **不做逐元素合并 / 白名单维护**——回滚是"全量文件替换"

用户指出：NETCONF edit-config 白名单方案"无底洞"，新设备有新元素就要重适配。

## What Changes

### 新方向：全文本 + SCP 统一回滚

**核心**：备份存**纯文本**配置，回滚一律**推 startup.cfg + 提示重启**，不分 startup/running 走两条路。

```
备份：
  startup  → paramiko SSH + scp 库 → 设备 flash:/startup.cfg → 本地 .cfg（文本）
  running  → SSH CLI 跑 `display current-configuration`（自动 screen-length 0 关分页）→ 本地 .cfg（文本）

恢复（统一一条路，startup / running 备份都走这个）：
  1. SCP 推本地 .cfg → 设备 flash（remote=recover_<id>.cfg）
  2. user-view 跑 `startup saved-configuration recover_<id>.cfg`
  3. 提示用户：下次 reload 生效（不自动 reload，断网风险由运维评估）
```

**关键决策**：
1. **不依赖白名单**：回滚是"全量文件替换"，与设备模块结构 / 元素列表解耦
2. **不自动 reload**：reload 断网，UI 二次确认让运维手动执行
3. **running 备份改 SSH CLI 文本**：与 startup 备份统一格式与回滚路径
4. **不引入新依赖**：复用现有 `paramiko` + `scp` 库 + `SSHExecutor`（带分页处理）
5. **不依赖设备 SFTP/SCP server**：`scp` Python 库基于 paramiko SSH 通道，不需设备开 SCP server

### 修改

- `backend/app/utils/backup_manager.py`：
  - `_fetch_running_via_netconf` → `_fetch_running_via_ssh_cli`（用 SSHExecutor 跑 `screen-length 0` + `display current-configuration`）
  - 移除 `_restore_running_via_netconf` 和所有 `RESTORE_*_WHITELIST` 常量
  - 合并 `_restore_startup_via_scp` + `_restore_running_via_netconf` → 统一 `_restore_via_scp`（startup/running 备份共用）
  - 移除 `save force` 相关代码（拉 startup 不需要 save force）

- `backend/app/routers/backup.py`：
  - `_make_manager` 统一用 SSH 端口 22（不再为 running 传 830）
  - `restore` 路由简化：不再分 startup/running 路径

- `backend/requirements.txt`：
  - 移除 `lxml>=4.9.0`（backup_manager 不再需要 XML 解析）

### 不改

- `frontend/`：backup-frontend 已实现的 UI 不动
- 数据库 schema
- 备份文件命名：`{ts}__{type}.cfg`（统一文本，扩展名都是 .cfg）
- 其他使用 `lxml` 的代码（无）

## 验收标准

- [ ] `display current-configuration` 在 192.168.100.4 上能拉完整文本（>1000 bytes，< 60s）
- [ ] running 备份 `POST /api/devices/4/backup` types=["running"] < 60s
- [ ] startup 备份 `POST /api/devices/4/backup` types=["startup"] < 10s（实测 ~3s）
- [ ] 端到端真机：备份 A → 改 HostName + VLAN 999 → 备份 B → 回滚 A → 设备配置恢复
- [ ] running 备份的回滚路径与 startup 备份完全相同（统一 `_restore_via_scp`）
- [ ] 后端代码无 `RESTORE_TOP_WHITELIST` / `RESTORE_SUB_WHITELIST` / `lxml` 引用
- [ ] 全量备份 `POST /api/backups` 完成 < 60s
- [ ] UI 提示"已设为启动配置，请手动 reload 设备（断网风险）"

## 关联

- 父 change：`v21x-patch-backup-backend`（已 archive）
- 阻塞 change：`backup-frontend`（本 change 完成后 archive）
- 同版本 v2.2 已完成：`interface-vpn-instance-and-l2-l3`

## Rollback

- `git revert` 本次修改
- 数据库无 schema 变更
- 不破坏旧 backup 库
