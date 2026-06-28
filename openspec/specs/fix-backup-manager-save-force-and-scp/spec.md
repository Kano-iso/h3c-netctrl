# fix-backup-manager-save-force-and-scp Specification

## Purpose

修复 v2.1.x patch 灰度的 backup 后端在 H3C V7 真机验证时暴露的 2 个阻塞 bug，并确立"全文本 + SCP 统一回滚"的备份恢复方案。

## Background

v2.1.x patch（`archive/2026-06-28-v21x-patch-backup-backend`）完成 backup 后端能力，但**真机验证从未完成**（task 7.1-7.8 全 `[ ]`）。v2.2 backup-frontend 真机验证（192.168.100.4 Leaf-03）暴露多个 bug，多轮修复演进：

| 轮次 | 方案 | 真机问题 |
|---|---|---|
| 1 | SFTP 拉 + `save force` 非交互 | H3C V7 SFTP 子系统默认禁用 + `save force` 需 Y 确认卡死 |
| 2 | SCP 推 + 交互式 shell `save force` | H3C V7 SCP server 默认禁用 |
| 3 | 全 NETCONF：`<get-config>` 拉 + `<edit-config>` 推 | 回滚时大量不可写元素（VCF / Domain / Login / RBAC 等系统配置） |
| 4 | NETCONF + 业务白名单 + 逐元素降级 | **白名单无底洞**：A 设备有 XYZ，B 设备有 ABC，厂商升级结构又变 |
| 5（最终） | **全文本 + SCP 统一回滚** | 业界主流：RANCID / Oxidized / Ansible Network / NAPALM / 华为 eSight / H3C iMC 都是"文件级全量替换 + 人工确认 reload"，不维护白名单 |

## Requirements

### Requirement: 备份存储纯文本

`POST /api/devices/{id}/backup` 创建的备份文件 MUST 是纯文本配置：

- **startup 备份**：通过 paramiko SSH + scp 库拉 `flash:/startup.cfg`（H3C V7 是文本，H3C V5 才是 binary）
- **running 备份**：通过 `SSHExecutor` 跑 `screen-length 0` + `display current-configuration` 拉文本（自动处理 H3C 分页）
- 文件扩展名统一为 `.cfg`
- 命名格式：`{ISO8601_ts}__{type}.cfg`，例如 `20260628T144239__running.cfg`

### Requirement: 备份存储路径

备份文件 MUST 存于 `{BACKUP_DIR}/{device_id}/{filename}.cfg`：

- `BACKUP_DIR` 由 `settings.BACKUP_DIR` 注入（环境变量 `BACKUP_DIR`）
- Docker volume 挂载 `BACKUP_DIR` 实现持久化
- 设备 ID 子目录隔离，避免跨设备冲突

### Requirement: 备份轮转

`POST /api/devices/{id}/backup` 完成后 MUST 触发轮转：

- 仅轮转 `locked=False` 的备份
- 保留最新 N 份（`settings.BACKUP_KEEP`，默认 5）
- 删除超出 N 份的最旧非锁定备份
- 锁定备份 MUST NOT 被轮转删除

### Requirement: 备份锁定 / 取消锁定

`POST /api/devices/{id}/backup/{bid}/lock` 切换 `locked` 字段：

- 锁定备份 MUST 不参与自动轮转
- 锁定备份的删除 MUST 被拒绝（`DELETE /api/devices/{id}/backup/{bid}` 在 `locked=True` 时返回 `success=False`）
- 锁定 / 取消锁定操作 MUST 记录到操作日志

### Requirement: 备份下载

`GET /api/devices/{id}/backup/{bid}` MUST 返回备份文件原文（`.cfg`）：

- 响应头 `Content-Disposition: attachment; filename=...` 触发浏览器下载
- 不解密、不修改，原文输出

### Requirement: 备份回滚（统一一条路）

`POST /api/devices/{id}/backup/{bid}/restore` MUST 执行以下流程：

**步骤 1（必做）：推 backup + set as startup**
1. SSH 22 连接设备
2. SCP 推本地 `.cfg` → 设备 flash（remote=`recover_<backup_id>.cfg`）
3. `startup saved-configuration recover_<backup_id>.cfg`（设备返回 `Done` 即视为成功）

**步骤 2（可选 `with_reboot=true`）：reboot + retry + verify**
1. SSH invoke_shell 触发 `reboot`，完整交互（`N` save + `Y` continue，避免覆盖 startup）
2. retry SSH 180s 等设备就绪（每次 5s）
3. retry 5 次 verify（每次 10s）跑 `display current-configuration`，对比 sysname + vlan 列表是否与备份一致

**返回值**：
```json
{
  "success": true,
  "method": "scp",
  "message": "配置已推回设备 + reboot 完成 + 验证生效（running-config == 备份内容）",
  "rebooted": true,
  "verified": true
}
```

**`with_reboot` 决策**：
- 业界主流（Oxidized / Ansible Network / NAPALM / H3C iMC）都是"工具不负责 reboot"
- v2.2 用户场景"页面点一下就完成回滚" → `with_reboot=true` 走端到端
- 默认 `false`（仅步骤 1），前端可按需传 `true`

### Requirement: 不维护 NETCONF 元素白名单

回滚 MUST NOT 依赖 NETCONF 元素白名单（`<Device>` / `<VLAN>` / `<Ifmgr>` 等业务元素的逐项配置）：

- 白名单方案在不同设备 / 不同 H3C 版本上**无底洞**
- 全文本 + SCP 文件级替换与设备 NETCONF 元素解耦
- 业界主流：RANCID / Oxidized / Ansible Network / NAPALM / H3C iMC 都用文件级替换

### Requirement: H3C V7 适配（H3C V7 已知约束）

- SFTP 子系统默认禁用 → **不**用 SFTP
- SCP server 默认禁用 → **但** Python `scp` 库基于 paramiko SSH 通道，**不依赖**设备 SCP server，可用
- H3C V7 `startup.cfg` 是纯文本（H3C V5 是 binary）→ 文件级替换是文本
- H3C V7 `save` 命令默认保存到 `recover_N.cfg`（不是 `startup.cfg`），**当 startup 指向 recover_N.cfg 时** → 备份工具的 reboot 交互**不**调 `save`，避免覆盖 A' 内容
- H3C V7 `startup saved-configuration` 是 user-view 命令（无需 system-view）→ 跑命令时不要进 system-view

### Requirement: local-user 保护（实测特性）

H3C V7 `startup saved-configuration` + SCP 全量替换 MUST NOT 覆盖 `local-user` 配置：

- 实测：reboot 后 SSH 仍能用原 db password 登 → 运维不会被锁在设备外
- **不**需要在备份时剥离 `local-user` / `password-recovery` 等敏感行

## 真机验证

设备：192.168.100.4 (Leaf-03, H3C V7)

| 验证项 | 结果 |
|---|---|
| 4.5a 回滚操作（推 + set as startup） | ✅ success |
| 4.5b 端到端（with_reboot=true） | ✅ rebooted=True, verified=True, 57s |
| 4.6 startup / running 备份回滚路径统一 | ✅ |
| 4.7 列表 / 锁定 / 删除 / 轮转 | ✅ |
| 4.8 全量备份 `POST /api/backups` | ✅ < 60s |
| 4.9 无 `RESTORE_*_WHITELIST` / `lxml` 引用 | ✅ |
| 4.10 local-user 不被覆盖（推断推翻） | ✅ |

## 修改文件

```
backend/app/utils/backup_manager.py   # 主要：拉取 + 轮转 + 锁定 + 回滚 + reboot + verify
backend/app/routers/backup.py         # 路由：7 个 API + with_reboot body
backend/requirements.txt              # 移除 lxml（backup 不再需要 XML 解析）
```

## 关联

- 父 change：`v21x-patch-backup-backend`（已 archive）
- 阻塞 change：`backup-frontend`（前端 UI 留作 v2.2.1 follow-up）

## Rollback

- `git revert` 本次修改
- 数据库无 schema 变更
- 不破坏旧 backup 库
