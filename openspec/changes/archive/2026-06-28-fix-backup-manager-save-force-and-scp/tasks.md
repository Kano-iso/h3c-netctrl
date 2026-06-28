## 1. 后端依赖

- [x] 1.1 `backend/requirements.txt` 保留 `scp>=0.14.0`
- [x] 1.2 重建 backend 镜像
- [x] 1.3 验证 `from scp import SCPClient` 在容器内可用
- [x] 1.4 `backend/requirements.txt` 移除 `lxml>=4.9.0`（backup_manager 不再需要 XML 解析）

## 2. backup_manager.py 改造（新方向：全文本 + SCP 统一回滚）

### 2.1 拉取

- [x] 2.1.1 `_fetch_startup_via_scp`：保留（paramiko SSH + scp 库拉 flash:/startup.cfg）
- [x] 2.1.2 `_fetch_running_via_ssh_cli`：新增（SSHExecutor 跑 `screen-length 0` + `display current-configuration`，自动处理分页）
- [x] 2.1.3 移除 `_fetch_running_via_netconf`（不再走 NETCONF 拉 running）
- [x] 2.1.4 移除 `save force` 相关代码（拉 startup 不需要）

### 2.2 备份创建

- [x] 2.2.1 `create_backup(types=["startup"])`：调 `_fetch_startup_via_scp`
- [x] 2.2.2 `create_backup(types=["running"])`：调 `_fetch_running_via_ssh_cli`
- [x] 2.2.3 文件扩展名统一为 `.cfg`（两种类型都是文本）

### 2.3 统一回滚

- [x] 2.3.1 新增 `_restore_via_scp(backup)`：推 backup → 设备 flash → `startup saved-configuration`
- [x] 2.3.2 `restore(backup_id)` 调用统一的 `_restore_via_scp`（不再分 startup/running 路径）
- [x] 2.3.3 移除 `_restore_running_via_netconf`
- [x] 2.3.4 移除 `RESTORE_TOP_WHITELIST` / `RESTORE_SUB_WHITELIST` / `NON_EDITABLE_TOP_CHILDREN` 常量
- [x] 2.3.5 移除 `_restore_startup_via_scp`（被统一方法替代）

## 3. routers/backup.py 简化

- [x] 3.1 `_make_manager` 统一用 SSH 端口 22（不再为 running 传 830）
- [x] 3.2 注释简化（startup/running 内部都走 SSH 22）

### 4.1-4.4：拉取与备份 API（实测通过）

- [x] 4.1 SCP 拉 startup.cfg 成功（>1000 bytes 文本）
- [x] 4.2 SSH CLI 拉 running-config 成功（`display current-configuration` 全文，>1000 bytes）
- [x] 4.3 startup 备份 `POST /api/devices/4/backup` types=["startup"] < 10s
- [x] 4.4 running 备份 `POST /api/devices/4/backup` types=["running"] < 60s

### 4.5-4.6：回滚路径（统一一条路，全文本 + SCP + 可选 reboot + verify）

- [x] 4.5a 回滚操作执行成功：调用 `_restore_via_scp` → SCP 推 backup → 设备 flash 成功 → `startup saved-configuration` 设备返回 `Done`
- [x] 4.5b **回滚端到端实测通过**（with_reboot=True）
  - 实测脚本：`_e2e_with_reboot.py`
  - 流程：备份 A' → 改 N+1（sysname=LEAF03_N1_RB + VLAN 600）→ 备份 B' → `restore(A_BID, with_reboot=True)` → 设备 reboot → retry SSH 180s → verify running-config == 备份内容（sysname + vlan 列表）→ 设备最终 = A'
  - 实测结果：rebooted=True, verified=True, 用时 57s, 设备保持原样（n → n+1 → n）
  - 关键改进：verify 内部 retry 5 次（每次间隔 10s），处理 reboot 后 SSH 已就绪但 CLI 还没 ready 的情况
  - **设计决策**：`with_reboot` 参数控制（默认 False）。业界主流（Oxidized / Ansible Network / NAPALM / H3C iMC）都是"工具不负责 reboot"，但 v2.2 用户场景是"页面点一下就完成回滚"，所以提供 `with_reboot=True` 走端到端流程。
- [x] 4.6 startup / running 备份的回滚路径完全相同（统一调 `_restore_via_scp`），且 with_reboot=True 也都生效
- [x] 4.6b running 备份的端到端也实测通过（4.5b 跑的是 running 备份）

### 4.7-4.9：辅助功能（实测通过）

- [x] 4.7 列表/锁定/删除/轮转功能正常
- [x] 4.8 全量备份 `POST /api/backups` 完成 < 60s
- [x] 4.9 后端代码无 `RESTORE_*_WHITELIST` / `lxml` 引用（grep 验证）

### 4.10：local-user 推断（实测推翻）

- [x] 4.10 **"回滚会同时回滚用户账号" 推断错误**（实测推翻）
  - 实测：reboot 后 SSH 仍能用原 db password 登 → H3C V7 `startup saved-configuration` + SCP 全量替换**不**覆盖 `local-user` 配置
  - 4.5b 端到端实测中验证
  - 运维不会被锁在设备外 ✅

### 4.11：设备当前状态（完好）

- [x] 4.11 192.168.100.4 设备已恢复 A' 状态（sysname=LEAF03_TEST, vlan=[1, 200]），未被破坏

## 5. 收尾

- [ ] 5.1 删除临时测试脚本
- [ ] 5.2 commit 代码
- [ ] 5.3 archive change
- [ ] 5.4 archive `backup-frontend` change（本 change 是其前置）

## 6. 文档

- [ ] 6.1 `openspec/specs/fix-backup-manager-save-force-and-scp/spec.md` 规范化
- [ ] 6.2 VERSION-ROADMAP v2.2 状态推进 (3/3 完成)

## 7. 重要教训（写入 project memory）

- **任务未达标必须立即高优通知用户，不能继续推进下一步**
- **回滚 / reload 类验证必须 sleep + retry 等待设备就绪，不能用一次 15s timeout 失败就推断结果**
- **凭理论推断打 [x] 是禁止的——实测 vs 推断必须区分**
