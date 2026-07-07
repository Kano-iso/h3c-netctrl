# v262-roadmap — v2.6.2 总入口

## Why

v2.6.1 闭环时留下 2 项 backlog，明确推 v2.6.2：

1. **`fix-backup-restore-no-response`** 实施（🟡 部分完成 → ✅ 实施）
   - 根因已 v2.6.1 定位，9 task 推到 v2.6.2
   - 详见 [archive/2026-07-07-fix-backup-restore-no-response/STATUS.md](../archive/2026-07-07-fix-backup-restore-no-response/STATUS.md)
2. **`add-auto-collect`** 重新评估（⛔ 取消 → 按需重启）
   - v2.6.0 复盘砍掉，v2.6.1 已用 ASSET_STALE_HOURS 自动降级替代
   - 重新评估条件：dashboard online 计数严要求 / 定时采集合规需求
   - **默认不做**（v2.6.2 实施时如无新需求，跳过；新建 change 需明示"v2.6.2 add-auto-collect"）

**v2.6.2 主题**：**修复 v2.6.1 遗留的 UX 关键 bug**（回滚无反应）。backlog 完结后才开 v3.0（VPC）。

## What Changes

### 范围（v2.6.2 做 1 个，砍 1 个默认不做）

| 子 change | 来源 | v2.6.2 行动 | 状态 |
|---|---|---|---|
| `fix-backup-restore-support` | v2.6.1 STATUS.md 9 task | **✅ 实施** | 🟢 主项 |
| `add-auto-collect` | v2.6.1 CANCELLED.md | ⏸️ 默认不做，重新评估时再起 | ⚪ 悬置 |

### `fix-backup-restore-support` — 9 task 概要

v2.6.1 已定位 3 根因：

| 根因 | 说明 | v2.6.2 修法 |
|---|---|---|
| **A** | H3C V7 S6850 SFTP/SCP subsystem 默认禁用 | 后端 probe 检测 + 422 明确错误 |
| **B** | `_restore_via_scp` 用 paramiko scp 库对 .5 设备不可用 | 失败时记录详细 paramiko 错误 |
| **C** | 前端 `BackgroundTaskPanel` 折叠让失败任务不可见 | taskStore 失败时弹 toast + 面板高亮 |

**9 task 实施时序**：

| Task | 内容 | 依赖 |
|---|---|---|
| T1 | 后端 `check_restore_support(device)` 检测函数 | — |
| T2 | restore_async 端点预检，不支持直接 422 | T1 |
| T3 | `_restore_via_scp` 失败时记录详细 paramiko 错误 | — |
| T4 | 前端 taskStore 失败时弹全局 toast | — |
| T5 | BackgroundTaskPanel 加"最近失败"高亮 | T4 |
| T6 | device.status 加 `restore_unsupported` 字段 | T1 |
| T7 | mock scp.put 抛 Channel closed → 422 + toast 单测 | T1, T2, T4 |
| T8 | 真机 .177 + .5 双向验证 | T1, T2 |
| T9 | docs/ops-toolkit.md 加 S6850 设备 SCP 限制说明 | T1, T8 |

**实施顺序**（按 T1+T2 优先）：

```
T1 → T2 (最小修复：probe + 422)
T3, T4, T5 平行（错误可读化）
T6 (状态字段)
T7, T8 (测试 + 真机)
T9 (文档收尾)
```

**最小可用发版线**：T1 + T2 + T3 + T4 + T7 + T8 + T9 = **7 task** 必做
**可优化线**：+ T5（面板高亮） + T6（status 字段） = **9 task** 完整

→ **v2.6.2 默认 9 task 完整做**（v2.6.1 闭环时已承诺 9 task 全闭环）

### `add-auto-collect` — 重新评估条件

按 v2.6.1 CANCELLED.md 复盘：

- 重新评估条件：用户对 dashboard online 计数有更严格要求 / 定时采集成为合规需求
- 重新评估时：从 v2.6.1 已跑通的 backup-internal-api 路径出发，**只补 proposal → Apply 链路**
- 重做原则：单 task = 1 commit + 1 qa-backend 真跑 + 1 报告

**v2.6.2 默认跳过 add-auto-collect**。如中途评估需要，新建 `add-auto-collect` change（不与 fix-backup-restore-support 混）。

## 设计决策

### 决策 1：最小修复（T1+T2）必须在 v2.6.2 落地

- **理由**：用户已明确反映"无反应"是严重 UX 问题，v2.6.1 没做就推到 v2.6.2
- **实施**：检测 + 422 即使用户点回滚也立刻明确失败，不再让"无反应"重现
- **T3-T9 是错误可读化 + 体验优化**，v2.6.2 一起做（9 task 体量与 v2.6.1 22 commit 相比不超范围）

### 决策 2：9 task 全部串行（不并行）

- **理由**：T1 是 T2/T6/T7/T8 的依赖基础；T4 是 T5 基础；T7 依赖 T2；T8 依赖所有代码
- **不并行原因**：避免 T3/T4 改了 `_restore_via_scp` / taskStore 后 T1/T2 commit 时冲突
- **节奏**：1 task = 1 commit + qa-backend 通过（按需 qa-frontend lint + build）

### 决策 3：add-auto-collect 默认不做

- v2.6.1 自动降级已替代 dashboard online 陈旧问题
- v2.6.2 加 fix-backup-restore-support 已够体量（9 commit + archive 文档 + 真机验证）
- v2.6.2 闭环时如无新需求，add-auto-collect 保持 CANCELLED 状态，不进 v2.6.2 archive

### 决策 4：toast 系统新建（不复用第三方）

- 项目当前无 toast 组件，新建 `frontend/src/components/ToastContainer.vue` + `frontend/src/stores/toast.js`
- **理由**：v2.6.1 全面走自定义设计（`bg-canvas-*` / `text-ink-*`），不引第三方 ui 库
- 5 个 i18n key（zh-CN + en-US）入 v2.6.2
- 应用范围：T4（taskStore 失败 toast） + 后续其他 failure 也可复用

## 影响范围

| 模块 | 影响 |
|---|---|
| `backend/app/utils/backup_manager.py` | T1 check_restore_support + T3 错误详情 |
| `backend/app/routers/backup.py` | T2 restore_async 预检 + T6 状态字段 |
| `backend/app/schemas/backup.py` | T6 字段（device.status） |
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

- 上游：[archive/2026-07-07-fix-backup-restore-no-response/STATUS.md](../archive/2026-07-07-fix-backup-restore-no-response/STATUS.md)（v2.6.1 根因定位）
- 下游：[fix-backup-restore-support](./fix-backup-restore-support/proposal.md)（子 change）
- 前置：v2.6.1 已发版（✅ 2026-07-07）
- 后续：v2.6.2 闭环后起 v3.0（VPC / SDN 起步）
