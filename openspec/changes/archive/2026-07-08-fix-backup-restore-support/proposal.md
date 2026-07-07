# fix-backup-restore-support — Proposal

## Why

v2.6.1 闭环时定位的 3 根因未实施，**"回滚无反应"是严重的 UX 关键 bug**：

> 用户原话（v2.6.1 复盘）：
> > .5 我有两份配置，都上锁了... 尝试把旧配置回滚，在前端点回滚，发现并没有任何反应。

**真实情况**（v2.6.1 已定位）：
- 后端**有响应**（`POST /api/devices/5/backup/36/restore-async 200`）
- 后端**真执行了**（task 71 创建，progress=90）
- **SCP 推阶段失败**（error: `回滚失败: SCP 推回失败: Channel closed.`）
- **前端无任何提示**（BackgroundTaskPanel 折叠条件让失败任务不可见）

**v2.6.2 必须做**：用户已明确"操作没反应"是 bug 反馈，v2.6.1 已承诺 v2.6.2 闭环。

## 根因（v2.6.1 已定位）

### 根因 A（最根本）：.5 设备 H3C S6850 (CMW 7.1.070) 不支持 SCP/SFTP subsystem

- `ops-toolkit paramiko-batch-exec leaf-04 dir` ✅ OK（exec channel 工作）
- `scp.put(...)` ❌ `SSHException: Channel closed.`
- `sftp.put(...)` ❌ `SSHException: Channel closed.`
- H3C V7 S6850 系列：**SFTP/SCP subsystem 默认禁用**（`backup_manager.py` 顶部注释"scp 库基于 SSH 通道"与 `.5` 设备实际行为不一致）

### 根因 B：`_restore_via_scp` 用 paramiko scp 库对 .5 设备不可用

- 当前：`SCPClient(client.get_transport()).put(backup.file_path, remote_name)`
- paramiko scp 库走 SCP 协议（基于 SSH exec channel 跑 scp 命令），H3C V7 scp 命令路径/参数与 OpenSSH 不兼容
- **备份拉取**走 `_fetch_startup_via_scp` 实际是 SSH exec channel 读 `display startup` 文本（绕开 SCP subsystem）
- **回滚推回**需要真上传文件，绕不开设备协议

### 根因 C：前端 `BackgroundTaskPanel` 折叠让失败任务不可见

- `v-if="hasRunning || expanded"`：仅在有 running 任务或用户主动展开时显示
- task 71 在 < 1s 内从 running → failed，期间 `hasRunning` 短暂 true
- 失败后 `hasRunning=false`，面板自动折叠，user 看不到任务记录

## What Changes

### 修复 A：后端 probe 检测 + 422 明确错误（最小修复）

- **T1**：新建 `check_restore_support(device)` — 在 SSH 连接上 probe 1 字节文件推送
  - supported: true → 正常走 `_restore_via_scp`
  - supported: false → 标记 `restore_unsupported=true`
- **T2**：`restore_backup_async` 端点启动前先 check
  - 失败立即返回 422 + error_key=`RESTORE_NOT_SUPPORTED`
  - 错误信息含"设备 {model} 不支持 SCP 推回，无法回滚"

### 修复 B：后端详细错误日志（T3）

- `_restore_via_scp` 失败时记录：
  - paramiko 异常类型
  - device 型号 / IP
  - 完整 error_message（不只 `"Channel closed"`）

### 修复 C：前端 toast 系统（T4）

- 新建 `frontend/src/components/ToastContainer.vue` + `frontend/src/stores/toast.js`
- `taskStore._pollOnce` 在 task 从 running 变 failed 时，触发 toast
- 5 个 i18n key 入 zh-CN / en-US
- 应用范围：T4（taskStore 失败 toast） + 后续其他 failure 也可复用

### 修复 D：BackgroundTaskPanel 失败高亮（T5）

- 任务面板即使折叠，右下角显示红点 "1 个失败"
- 折叠态红点 + 展开态列表中失败任务加 `text-bad` 高亮

### 修复 E：device.status 字段扩展（T6）

- `restore_unsupported: bool` 字段
- 前端 CMDB / 设备列表 / Backup 模态：标记"该设备不支持回滚"标识
- 后端 `/api/devices/{id}/status` 返回此字段

## 设计决策

### 决策 1：方案 1（probe 检测 + 422）优先落地

- **理由**：用户已反映"无反应"是严重 UX 问题
- **实施**：`check_restore_support` 在 SSH 连接上 probe 1 字节文件推送
- **风险**：probe 1 字节文件在 .177 设备可能"成功"（与 .5 失败行为不同）；这正是我们想要的——区分两设备

### 决策 2：方案 2（NETCONF edit-config 推配置）v2.6.2 不实施

- **理由**：H3C V7 文档对 NETCONF 推送 startup.cfg 支持不明确，验证工作量大
- **兜底**：probe + 422 + 明确错误已足够解决"无反应"问题
- **后续**：v3.x 评估 NETCONF edit-config 推配置（如有需要）

### 决策 3：toast 系统新建（不复用第三方）

- 项目当前无 toast 组件
- v2.6.1 全面走自定义设计（`bg-canvas-*` / `text-ink-*`），不引第三方 ui 库
- 5 个 i18n key（zh-CN + en-US）入 v2.6.2

### 决策 4：设备 status 字段 T6 单独做

- `device.status` 涉及多个 schema 路由
- 单独 1 commit 隔离 schema 变更与 probe 逻辑变更
- T7 mock 测试可以晚于 T6 提交

## Apply 拆细（详见 tasks.md）

| Task | 内容 | 文件 | commit |
|---|---|---|---|
| T1 | 后端 probe 函数 | `backend/app/utils/backup_manager.py` 新方法 | 1 commit |
| T2 | 端点预检 | `backend/app/routers/backup.py` | 1 commit |
| T3 | 详细错误日志 | `backend/app/utils/backup_manager.py` | 1 commit |
| T4 | toast 系统（组件 + store） | `frontend/src/components/ToastContainer.vue` + `frontend/src/stores/toast.js` + `frontend/src/App.vue` + 2 i18n | 1 commit |
| T5 | 面板失败高亮 | `frontend/src/components/BackgroundTaskPanel.vue` | 1 commit |
| T6 | device.status 字段 | `backend/app/schemas/backup.py` 或 `device.py` + 相关 router | 1 commit |
| T7 | mock scp.put 测试 | `backend/tests/test_backup_api.py` | 1 commit |
| T8 | 真机双向验证 | （不开新代码，用 MCP 浏览器 + qa-backend） | 1 commit（验证记录） |
| T9 | 文档收尾 | `docs/ops-toolkit.md` | 1 commit |

**总计**：9 commit + v262-roadmap archive commit + 发版 commit = ~12 commit

## 影响范围

| 模块 | 影响 |
|---|---|
| `backend/app/utils/backup_manager.py` | T1 check_restore_support + T3 错误详情 |
| `backend/app/routers/backup.py` | T2 restore_async 预检 + T6 状态字段 |
| `backend/app/schemas/*.py` | T6 字段（device.status） |
| `frontend/src/stores/task.js` | T4 toast 触发 |
| `frontend/src/components/BackgroundTaskPanel.vue` | T5 失败高亮 |
| `frontend/src/components/ToastContainer.vue` | T4 新建 |
| `frontend/src/stores/toast.js` | T4 新建 |
| `frontend/src/App.vue` | T4 挂载 ToastContainer |
| `frontend/src/i18n/zh-CN.js` + `en-US.js` | T4 + T5 i18n key（10 个） |
| `backend/tests/test_backup_api.py` | T7 mock 测试 |
| `docs/ops-toolkit.md` | T9 S6850 SCP 限制说明 |

## 验收标准

- [ ] T1 单测：`check_restore_support` 在 mock scp.put 抛 Channel closed 时返回 `{supported: false}`
- [ ] T2 真机 .5 调 restore_async 立即 422，error_key 明确 "RESTORE_NOT_SUPPORTED"
- [ ] T3 失败日志含 paramiko 异常类型 + device 型号 + error_message 全量
- [ ] T4 真机 .5 触发 restore 失败，前端弹 toast "设备 S6850 不支持 SCP 推回，无法回滚"
- [ ] T5 任务面板即使折叠，右下角显示红点 "1 个失败"
- [ ] T6 device.status 含 `restore_unsupported: bool` 字段
- [ ] T7 qa-backend pytest 全过（新增 mock 测试 ≥ 1 个）
- [ ] T8 qa-frontend lint + build 全过
- [ ] T9 真机双向验证：.177 restore 成功；.5 restore 拒绝并明确错误
- [ ] T9 文档：ops-toolkit.md 加"S6850 系列 SCP 限制"小节

## 关联

- 上游：[archive/2026-07-07-fix-backup-restore-no-response/STATUS.md](../../archive/2026-07-07-fix-backup-restore-no-response/STATUS.md)（v2.6.1 根因定位）
- 上游：[archive/2026-07-07-fix-backup-restore-no-response/proposal.md](../../archive/2026-07-07-fix-backup-restore-no-response/proposal.md)（v2.6.1 proposal 详细排查记录）
- 上游：[v262-roadmap](../v262-roadmap/proposal.md)（v2.6.2 总入口）
- 下游：[openspec/specs/backup-restore-support/spec.md](./specs/backup-restore-support/spec.md)（实施后主 spec 沉淀）
