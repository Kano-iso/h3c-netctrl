# fix-backup-restore-no-response — Proposal

## Why

备份回滚（restore）端点"无响应"：**实际是后端真失败 + 前端没显示错误**。

**问题表现**（用户原话）：
> .5 我有两份配置，都上锁了... 尝试把旧配置回滚，在前端点回滚，发现并没有任何反应。

**真实情况**（MCP 浏览器 + DB 排查后定位）：
- ✅ 后端**有响应**（`POST /api/devices/5/backup/36/restore-async 200`）
- ✅ 后端**真执行了**（task 71 创建，progress=90）
- ❌ **SCP 推阶段失败**（error: `回滚失败: SCP 推回失败: Channel closed.`）
- ❌ **前端无任何提示**（BackgroundTaskPanel 折叠条件 `v-if="hasRunning || expanded"`，任务 < 1s 失败后面板不可见；失败时无 toast）

## 根因（已定位）

### 根因 A（最根本）：.5 设备 H3C S6850 (CMW 7.1.070) 不支持 SCP/SFTP subsystem

- `ops-toolkit paramiko-batch-exec leaf-04 dir` ✅ OK（exec channel 工作）
- `scp.put(...)` ❌ `SSHException: Channel closed.`
- `sftp.put(...)` ❌ `SSHException: Channel closed.`
- H3C V7 S6850 系列：**SFTP/SCP subsystem 默认禁用**（与 backup_manager.py 顶部注释"scp 库基于 SSH 通道，不依赖设备 SCP server"不一致——`.177` 测试设备能跑通 SCP，纯属偶然）

### 根因 B：backup_manager.py `_restore_via_scp` 用 paramiko scp 库，对 .5 设备不可用

- 当前实现：`SCPClient(client.get_transport()).put(backup.file_path, remote_name)`
- paramiko scp 库走 SCP 协议（基于 SSH exec channel 跑 scp 命令），但 H3C V7 的 scp 命令路径/参数与 OpenSSH 不兼容
- 备份拉取走 `_fetch_startup_via_scp` 同样路径，但 leaf-04 的 `display startup` 文本已经包含 startup.cfg 内容，**拉取用的实际是 SSH exec channel 读命令**——所以备份拉取不依赖 SCP subsystem
- **回滚推回需要真上传文件**，必须走设备能接受的协议

### 根因 C：前端 BackgroundTaskPanel 折叠条件让失败任务不可见

- `v-if="hasRunning || expanded"`：仅在有 running 任务或用户主动展开时显示
- task 71 在 < 1s 内从 running → failed（progress 30 → 90 → failed），期间 `hasRunning` 短暂 true
- 失败后 `hasRunning=false`，面板自动折叠，user 看不到任务记录
- 即使用户主动看 dashboard "最近操作"，也要滚动找到失败记录

## What Changes

### 修复 A：后端回滚走 NETCONF（绕开 SCP subsystem）

- **方案 1（推荐）**：用 NETCONF `edit-config` 把配置直接推送（前提：H3C V7 支持 NETCONF 推送文本配置；待验证）
- **方案 2**：把回滚改成 2 步：先用 NETCONF/CLI `delete /unreserved flash:/recover_<id>.cfg`，再用 CLI `startup saved-configuration <url>`（H3C V7 支持从 HTTP/TFTP 拉，但本项目没装）
- **方案 3（兜底）**：用 `display current-configuration` 抓现网配置做对比，明确告诉用户"该设备暂不支持回滚"

### 修复 B：前端 restore 失败时弹 toast / alert

- 改造 `BackgroundTaskPanel.vue` / `taskStore._pollOnce`：当任务从 running 变 failed 时，触发全局 toast
- 失败时除了面板折叠/展开，还要弹一个明确错误提示（不依赖面板展开状态）

### 修复 C：把"不支持 SCP 推"明确暴露给用户

- 前端备份列表：device.status 字段加 "restore_unsupported" 标记（基于后端 `check_restore_support`）
- 后端在 restore_async 启动前跑一次 `check_restore_support`，失败立即返回明确错误（避免等几秒后报 SCP 推错）

## 设计决策

### 决策 1：方案 1（NETCONF）优先验证，不行走方案 3

- **理由**：H3C V7 设备普遍支持 NETCONF（同备份拉取走 NETCONF 成功），是项目已有协议栈
- **风险**：NETCONF edit-config 推送 startup.cfg 是非常规用法（H3C 文档少），可能不被支持
- **兜底**：方案 3 在备份历史 UI 显示"该设备暂不支持回滚"，避免用户点了无反应

### 决策 2：方案 3 必须在方案 1 之前落地

- **理由**：用户已经反映"无反应"是严重 UX 问题；方案 3 即使不能回滚也至少给明确提示
- **实施**：检测逻辑 `check_restore_support`（try paramiko scp.put 一个 1 字节文件）→ 失败则标记 unsupported

## Apply 拆细（待 tasks.md）

- T1 后端：`check_restore_support(device)` 检测函数（probe 1 字节文件推送）
- T2 后端：restore_async 端点启动前先 check，不支持直接 422 + 明确错误
- T3 后端：`BackupManager._restore_via_scp` 失败时记录更详细的 paramiko 错误（含 device info）
- T4 前端：taskStore._pollOnce 失败时弹全局 toast（用现有 toast 系统）
- T5 前端：BackgroundTaskPanel 加 "最近失败" 高亮（即使折叠也有红点提示）
- T6 前端：device.status 加 "restore_unsupported" 字段（基于 check 结果）
- T7 测试：mock scp.put 抛 Channel closed → 验证后端返回 422 + 前端 toast
- T8 真机：.177 (支持 scp) + .5 (不支持 scp) 双向验证
- T9 文档：更新 docs/ops-toolkit.md 说明 .5 / S6850 设备的 SCP 限制

## 报告（用户原始反馈）

> .5 我有两份配置，都上锁了... 尝试把旧配置回滚，在前端点回滚，发现并没有任何反应。
> 回滚操作，我离虽然我知道 qa 不应该做回滚操作的这个内容，因为它太大了，但是现在确实有问题，我来指指出来这个问题了。

## 排查记录

```
# 1. 前端点"回滚" → POST /api/devices/5/backup/36/restore-async 200
# 2. task 71: status=failed, progress=90, error="回滚失败: SCP 推回失败: Channel closed."
# 3. ops-toolkit paramiko 直测 .5 设备:
#    - exec_command("dir")    ✅ OK
#    - sftp.put(...)           ❌ SSHException: Channel closed
#    - scp.put(...)            ❌ SSHException: Channel closed
# 4. 设备型号：H3C S6850, CMW 7.1.070, Alpha 7170, FLASH 1024M (free ~1GB)
# 5. 设备空间充足，排除"满盘"假设
# 6. 设备 SFTP/SCP subsystem 均不可用（H3C V7 S6850 默认禁用）
```

## 状态

- ✅ 根因已定位（设备 SCP subsystem 不可用 + 前端无 toast）
- ⏳ Apply 阶段：v2.6.1 push 后启动，按 T1-T9 串行
- 影响范围：v2.6.x 全部 S6850 / S6860 / S9850 等 H3C V7 设备都可能受影响
