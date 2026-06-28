## Why

v2.1.x patch 完成 backup 后端但没真机验证。v2.2 backup-frontend 真机时（192.168.100.4 Leaf-03）暴露多个 bug，多轮修复演进：

| 轮次 | 方案 | 真机问题 |
|---|---|---|
| 1 | SFTP 拉 + `save force` 非交互 | SFTP 子系统禁 / `save force` 需 Y 确认卡死 |
| 2 | SCP 推 + 交互式 shell `save force` | H3C V7 SCP server 默认禁 |
| 3 | 全 NETCONF：`<get-config>` 拉 + `<edit-config>` 推 | 回滚时大量不可写元素（VCF/Domain/Login/RBAC 等系统配置） |
| 4 | NETCONF + 业务白名单 + 逐元素降级 | **白名单无底洞**：A 设备有 XYZ，B 设备有 ABC，厂商升级结构又变 |

### 关键转折（2026-06-28）

用户提出"**去市面上看看大家怎么做的**"。调研业界主流做法（RANCID / Oxidized / Ansible Network / NAPALM / 华为 eSight / H3C iMC）：

- **拉取**：SSH CLI `display current-configuration` 或 SCP 拉 `startup.cfg`（文本）
- **回滚**：SCP 推 startup + `startup saved-configuration` + **人工确认 reload**
- **不做逐元素合并 / 白名单维护**——回滚是"全量文件替换"

用户进一步指出：NETCONF edit-config 维护白名单"无完没了"，每台设备元素不同就要重适配。

## What Changes

### 新方向：全文本 + SCP 统一回滚

**核心**：备份存**纯文本**配置，回滚一律**推 startup + 提示重启**，不分 startup/running 两条路。

```
备份：
  startup  → paramiko SSH + scp 库 → flash:/startup.cfg → 本地 .cfg
  running  → SSH CLI（screen-length 0 关分页）→ `display current-configuration` → 本地 .cfg

恢复（startup / running 备份都走这一条）：
  1. SCP 推本地 .cfg → 设备 flash（remote=recover_<id>.cfg）
  2. user-view 跑 `startup saved-configuration recover_<id>.cfg`
  3. 提示用户：下次 reload 生效（不自动 reload，断网风险由运维评估）
```

### 修改

- `backend/app/utils/backup_manager.py`：
  - `_fetch_running_via_netconf` → `_fetch_running_via_ssh_cli`（用 SSHExecutor 处理分页）
  - 移除 `_restore_running_via_netconf` 和所有 `RESTORE_*_WHITELIST` 常量
  - 合并 `_restore_startup_via_scp` + `_restore_running_via_netconf` → 统一 `_restore_via_scp`
  - 移除 `save force` 相关代码（拉 startup 不需要）

- `backend/app/routers/backup.py`：
  - `_make_manager` 统一用 SSH 端口 22
  - `restore` 路由简化：不再分 startup/running 路径

- `backend/requirements.txt`：
  - 移除 `lxml>=4.9.0`（backup_manager 不再需要 XML 解析）

### 不改

- `frontend/`：backup-frontend 已实现的 UI 不动
- 数据库 schema
- 备份文件命名：`{ts}__{type}.cfg`（统一文本，扩展名都是 .cfg）
- 其他使用 `lxml` 的代码（无）

## 关键决策

1. **`scp` Python 库**：基于 paramiko SSH 通道，不依赖设备 SCP server
2. **`SSHExecutor` 复用**：跑 `display current-configuration`，自动处理 H3C 分页
3. **不自动 reload**：reload 断网，UI 提示让运维手动执行
4. **统一回滚路径**：startup 和 running 备份的恢复逻辑完全相同——"推回去 + set as startup"
5. **不维护白名单**：回滚是文件级全量替换，与设备模块结构 / 元素列表解耦

## 验收标准

- [ ] `display current-configuration` 192.168.100.4 拉完整文本（>1000 bytes，< 60s）
- [ ] running 备份 `POST /api/devices/4/backup` types=["running"] < 60s
- [ ] startup 备份 `POST /api/devices/4/backup` types=["startup"] < 10s
- [ ] 端到端真机：备份 A → 改 HostName + VLAN 999 → 备份 B → 回滚 A → 设备配置恢复
- [ ] running 备份的回滚路径与 startup 备份完全相同
- [ ] 后端代码无 `RESTORE_TOP_WHITELIST` / `RESTORE_SUB_WHITELIST` / `lxml` 引用
- [ ] 全量备份 `POST /api/backups` 完成 < 60s
- [ ] UI 提示"已设为启动配置，请手动 reload 设备（断网风险）"

## 文件改动

```
backend/app/utils/backup_manager.py   # 主要修改
backend/app/routers/backup.py         # 简化
backend/requirements.txt              # 移除 lxml
```

## 关联

- 父 change：`v21x-patch-backup-backend`（已 archive）
- 阻塞 change：`backup-frontend`（本 change 完成后 archive）
- 同版本 v2.2 已完成：`interface-vpn-instance-and-l2-l3`

## Rollback

- `git revert` 本次修改
- 数据库无 schema 变更
- 不破坏旧 backup 库
