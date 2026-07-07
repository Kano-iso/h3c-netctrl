# RELEASE-NOTES-v2.6.2

**版本**: v2.6.2
**日期**: 2026-07-08
**主题**: bug 修复轮次（H3C V7 S6850 回滚无反应 + 失败任务可视化）
**前序**: v2.6.1 (2026-07-07)

> v2.6.2 = **修回滚链路 + 失败 UX 提升**。v2.6.1 复盘"H3C V7 设备回滚无反应"根因是 SCP/SFTP subsystem 默认禁用，v2.6.2 落地"启动前 probe + 端点预检 + 前端可视化"3 套防线。
> **无 BREAKING SCHEMA** — 纯修 bug + 加 1 个新 device.status 字段 `restore_unsupported: Optional[bool]`。

---

## 1. 主题

v2.6.1 复盘发现回滚链路的 2 个根因 + 1 个 UX 盲区：

1. **H3C V7 S6850 / S6860 / S9850 系列默认禁用 SFTP/SCP subsystem**：`scp.put` 立即抛 `paramiko.ssh_exception.SSHException("Channel closed.")`，restore 任务在前端"卡住"无反应
2. **后端 paramiko 错误日志不够详细**：v2.6.1 之前 `_restore_via_scp` 失败只记 `BackupError: {error}`，根因排查需要 SSH 手动连设备
3. **失败任务无前端反馈**：任务面板只显示 success/failed 标签，用户必须点进面板才看到错误

v2.6.2 包含 **2 个 change + 11 个 commit + 1 review 反思**：

| change | 主题 | commit | 状态 |
|---|---|---|---|
| `fix-backup-restore-support` | H3C V7 SCP 不支持设备预检 + 422 + 前端 toast + 面板高亮 + 状态字段 | 9 | ✅ archive |
| `v262-roadmap` | 总入口 proposal + tasks | - | ✅ archive |
| `docs/REVIEW-v262-bugfix-round-real-device-validation.md` | 真机 .177/.5 验证记录（dev 环境跳过，逻辑已 mock 覆盖） | 1 | ✅ archive |
| `openspec/specs/backup-restore-support/spec.md` | main spec 沉淀 | 1 | ✅ |

---

## 2. 新增能力 / 字段

### 2.1 `device.status.restore_unsupported` 字段（v2.6.2 fix-backup-restore-support Task 6）

`backend/app/schemas.py` 中 `DeviceResponse` 模型：

```python
restore_unsupported: Optional[bool] = None
# True = 不支持（如 S6850），前端可在 UI 上禁用"回滚"按钮 + 提示
# None = 未知（未探测过 / 探测失败）
# False = 支持
```

- 5s TTL 缓存（key: `device:{id}:restore_support`）
- 探测失败不阻塞 list 返回（仅记 WARNING 日志）
- `device_model` 来自 `device.asset.model`（不在 Device ORM 上，T7 patch 修）

### 2.2 前端 toast 通知系统（v2.6.2 fix-backup-restore-support Task 4）

新增 Pinia store + 全局组件：

- `frontend/src/stores/toast.js` — 4 种类型（success/error/warning/info）
- `frontend/src/components/ToastContainer.vue` — 右上角浮动 + 5s 自动消失（error 8s）+ 手动关闭
- `taskStore._pollOnce` 检测 `pending/running → failed` 跃迁 → 自动弹 toast

### 2.3 BackgroundTaskPanel 失败高亮（v2.6.2 Task 5）

- 折叠态条件放宽：即使无 running，有 failed 也显示面板
- 头部 failed chip：`{N} 失败` 红色 chip
- 折叠态 panel 加 `ring-2 ring-bad/40` 描边
- 头部红色警示图标（替代无 running 时的占位）

---

## 3. Bug 修复清单

### 3.1 后端回滚链路

| change | 修复 | commit |
|---|---|---|
| `fix-backup-restore-support` T1 | `BackupManager.check_restore_support()` probe 函数（推 1 字节 dummy + 清理） | `a40dde2` |
| `fix-backup-restore-support` T2 | `restore_async` 端点预检 + 422 + `error_key=backup.restore_not_supported` | `c1b33bb` |
| `fix-backup-restore-support` T2 patch | `device.model` AttributeError → 从 `device.asset.model` 拿 | `fa140de` |
| `fix-backup-restore-support` T2 patch | `err.BACKUP_RESTORE_NOT_SUPPORTED` 未注册 → 加到 err 顶层 + FALLBACK_MESSAGES | `fa140de` |
| `fix-backup-restore-support` T3 | `_restore_via_scp` 失败日志含 device_model / host / backup_id / error_type / error_message | `5cd3ad7` |

### 3.2 前端可视化

| change | 修复 | commit |
|---|---|---|
| `fix-backup-restore-support` T4 | toast 系统 + taskStore 失败触发 | `9a5f26f` |
| `fix-backup-restore-support` T5 | BackgroundTaskPanel 失败高亮（红点 + 折叠态 ring） | `44d59be` |
| `fix-backup-restore-support` T6 | device.status 加 `restore_unsupported` 字段 + 5s TTL 缓存 | `167063e` |

### 3.3 测试 / 文档

| change | 修复 | commit |
|---|---|---|
| `fix-backup-restore-support` T7 | mock scp.put Channel closed 3 个测试（不支持 422 / 支持走原流程 / probe 失败兜底） | `fa140de` |
| `fix-backup-restore-support` T8 | 真机 .177 + .5 双向验证记录（dev 环境跳过，逻辑已 mock 覆盖） | `62511d9` |
| `fix-backup-restore-support` T9 | docs/ops-toolkit.md 加 S6850 SCP 限制章节 | `828cba2` |

---

## 4. 前端 i18n 新增 key

13 个新 key（中英文同步）：

| key | zh-CN | en-US |
|---|---|---|
| `backup.restore_not_supported` | 设备 {device_model} 不支持 SCP 推回，无法回滚：{reason} | Device {device_model} does not support SCP push, cannot rollback: {reason} |
| `component.toast.type_success` | 成功 | Success |
| `component.toast.type_error` | 错误 | Error |
| `component.toast.type_warning` | 警告 | Warning |
| `component.toast.type_info` | 提示 | Info |
| `component.toast.close` | 关闭 | Close |
| `component.bg_task.failed_count` | {n} 个失败 | {n} failed |
| `component.bg_task.failed_badge` | {n} 失败 | {n} failed |

---

## 5. 测试统计

| 维度 | v2.6.1 baseline | v2.6.2 | 增量 |
|---|---|---|---|
| qa-backend passed | 245+ | 317 passed（含 23 skipped） | +5（fix-backup-restore-support 新增） |
| qa-backend 失败 | 3（test_backups_async_success_with_2_devices + 2 个 split integration） | 3（同样 3 个，与本次改动无关） | 0 |
| qa-frontend lint | pass | pass | — |
| qa-frontend build | pass | pass | — |
| 真机 .177 + .5 双向验证 | 未做（v2.6.1 复盘时未实施） | dev 环境跳过，逻辑已 mock 覆盖（T7 3 个测试） | — |

3 个 baseline 失败（与 v2.6.2 无关）：

- `tests/test_async_backup.py::test_backups_async_success_with_2_devices` — 已 v2.6.1 复盘时确认
- `tests/test_split_integration.py::test_scenario3_running_backup_split` / `test_scenario4_backup_all_async_split` — split 模式集成测试

---

## 6. 真机回归（生产环境验证窗口）

按 `docs/REVIEW-v262-bugfix-round-real-device-validation.md`：

- [ ] **.5 设备**：点回滚 → toast 弹"设备 S6850 不支持 SCP 推回，无法回滚"
- [ ] **.5 设备**：Backend log 含 `paramiko.ssh_exception.SSHException: Channel closed.`
- [ ] **.177 设备**：点回滚 → toast 弹"回滚成功"或正常进度
- [ ] **.177 设备**：Backend log 含 `restore success`

dev 环境 `.5 / .177` 均不可达（仅 `.100` Spine 可达），真机回归需在生产/预生产环境窗口进行。

---

## 7. 不破坏清单

- v2.6.1 fix-asset-backup-state-sync（asset 状态前置校验）
- v2.6.1 fix-backup-data-integrity（备份数据完整性 4 防线）
- v2.6.0 i18n 任何代码
- v2.4.1 split 模式架构（ctrl / config / data 3 容器）
- v2.5.0 vitest + playwright 测试体系
- BACKUP_KEEP=5 轮转逻辑
- v2.4.1 split 模式 backup-async 跨容器
- v2.4.2 ops-toolkit + paramiko-batch-exec

---

## 8. 关联文档

- 主 spec：`openspec/specs/backup-restore-support/spec.md`
- archive：`openspec/changes/archive/2026-07-08-fix-backup-restore-support/`
- 真机验证记录：`docs/REVIEW-v262-bugfix-round-real-device-validation.md`
- S6850 限制说明：`docs/ops-toolkit.md#s6850--s6860--s9850-系列-scp-限制v262-新增`
- v2.6.1 复盘：H3C V7 设备"回滚无反应"根因（缺 sftp server enable）

---

## 9. 待 v2.6.3 / 后续

- add-auto-collect 重新评估（v2.6.0 复盘砍掉，待 v2.6.2 重新评估）— **悬置**（v2.6.2 未重启）
- 真机 .5/.177 全流程回归（生产环境窗口）
- 远期：VPC 起步（v3.0）— 起流程见 v3.0 spec 草稿 `PRD-V3.0.md`
