## Context

v2.1.x patch 完成 backup 后端但没真机验证。backup-frontend 真机时暴露 2 个 bug：交互式 save force + SFTP 未启用。本 change 修这 2 个 bug。

### Bug 1 根因分析

```python
# 当前 (backup_manager.py:198-213)
def _force_save_on_device(self, types: list[str]):
    if "running" in types:
        return
    client = self._connect_ssh()
    try:
        stdin, stdout, stderr = client.exec_command("save force", timeout=15)
        stdout.channel.recv_exit_status()  # 这里卡死
        ...
```

**H3C V7 行为**：
```
<H3C> save force
Start to save current configuration to the device.
Save the configuration to the device? [Y/N]:    # 等用户输入
```

`exec_command` 是非交互式，无 stdin 喂 `Y`，设备等 15s timeout → 主动关闭 channel。

### Bug 2 根因分析

```python
# 当前 (backup_manager.py:102-118)
def pull_file(self, remote_path: str, local_path: str) -> int:
    client = self._connect_ssh()
    sftp = client.open_sftp()  # 报 "SFTP server is disabled"
    sftp.get(remote_path, local_path)
```

**H3C V7 默认配置**：`sftp server enable` 命令未执行（默认禁 SFTP 子系统）。

**项目 memory 红线**（2026-06-28）："Avoid implementing FTP server for backup storage; use SCP-based methods instead"

### 方案对比

| 方案 | Bug 1 修法 | Bug 2 修法 | 评估 |
|---|---|---|---|
| A. 设备开 SFTP | 不动 | 设备 `sftp server enable` | 违反项目 memory，**不采用** |
| **B. SCP 推送 + 交互式 shell** | SSHExecutor 发送 save force + 喂 Y | paramiko SCPClient | **采用**（遵循 memory） |
| C. 全改 NETCONF | 改 NETCONF save | NETCONF copy（V7 不支持） | 不可行 |

### 关键决策

1. **save force 走 `SSHExecutor.execute_commands()`**：现有分页 / 错误指示符检测逻辑已就绪，添加 `Y/N` 响应逻辑
2. **SFTP 改 SCP**：用 `scp` 包（paramiko 官方推荐），`SCPClient(client.get_transport()).get()`
3. **`scp>=0.14.0` 加到 requirements.txt**：pip 安装
4. **不引入新 SSH 连接**：复用现有 `_connect_ssh` 的 client（节省连接开销）
5. **错误处理**：保存失败 → 抛 BackupError（与现状一致）；SCP 失败 → 抛 BackupError 带详细错误

### SSHExecutor 是否需要扩展

查看 `ssh_executor.py` 的 `execute_commands`：逐条发命令 + 读输出 + 检测错误指示符。**不直接支持"检测提示 + 自动回复"**。

**决定**：在 `backup_manager.py` 里直接用 `paramiko.invoke_shell()` 实现 `_force_save_via_ssh_shell()`，不污染 SSHExecutor（避免过度抽象）。代码量 ~20 行。

## Goals / Non-Goals

**Goals:**
- 单设备备份端到端可用（save force + 拉取 + 写库 + 轮转）
- 192.168.100.4 上 < 30s 完成
- 不破坏现有恢复（NETCONF 路径）
- 不破坏 API 行为

**Non-Goals:**
- 不动 SSHExecutor（避免改通用组件）
- 不动前端（backup-frontend 维持）
- 不动 backup API 路由
- 不引入新数据库表

## File Changes

### 修改

- `backend/app/utils/backup_manager.py`：
  - 新增 `_force_save_via_ssh_shell()` 方法：invoke_shell + 发 `save force` + 喂 `Y` + 等待 "successfully"
  - 替换 `_force_save_on_device` 内部调用
  - `pull_file`：用 `SCPClient` 替代 `open_sftp`
  - 增加 `logger.info` 业务日志
- `backend/requirements.txt`：加 `scp>=0.14.0`
- `backend/Dockerfile`：检查 pip install（应该不用改，requirements 已 install）

### 新增

- `openspec/specs/fix-backup-manager-save-force-and-scp/spec.md`（archive 时创建）

### 不改

- `frontend/`：维持 backup-frontend 5 个 commit
- `backend/app/routers/backup.py`：API 路由不动
- `backend/app/utils/ssh_executor.py`：通用 SSH 工具不动

## Test Strategy

### 单元

- `_force_save_via_ssh_shell`：在 mock 设备上测试（不依赖真机）
- `pull_file` 用 SCP：mock SSH client

### 真机（192.168.100.4 Leaf-03）

- [ ] `_force_save_via_ssh_shell` < 5s 完成
- [ ] 单设备 backup < 30s 完成
- [ ] `/data/backups/4/` 落盘 startup.cfg + running.cfg
- [ ] 列表返回 2 条
- [ ] 锁定切换 OK
- [ ] 轮转：触发 6 次非锁定备份 → 留 5 份
- [ ] 全量备份 < 60s（6 台串行）
- [ ] 设备日志确认 save force 成功

## Risk

- **scp 协议 vs SFTP**：scp 在大文件（>100MB）上慢，但 startup.cfg 通常 < 100KB
- **save force 失败兜底**：若设备版本不识别 `save force`，fallback 到 `save`（不带 force）
- **设备密码安全**：SCPClient 走 SSH 通道，无明文泄露风险
- **向后兼容**：现有 backup 库不删除（旧的 backup id 不变）

## Rollback

- 本 change 只改后端 1 个文件 + requirements
- 回滚 `git revert`
- 不需要数据库迁移

## 关联

- 父 change：`v21x-patch-backup-backend`（提供 backup 后端能力，本 change 修复其真机 bug）
- 阻塞 change：`backup-frontend`（本 change 完成后才能 archive）
- 同版本 v2.2 已完成：`interface-vpn-instance-and-l2-l3`
