# v2.6.2 fix-backup-restore-support Task 8: 真机 .177 + .5 双向验证记录

## 任务目标

真机双向验证 restore_async 预检 + 端点 422 逻辑：
- **.177 设备**（H3C Test-Switch-177）：支持 SCP 推回 → restore 任务正常提交
- **.5 设备**（H3C S6850 S6850-54HF）：不支持 SCP subsystem → restore 任务立即 422

## 验证环境

- 验证时间：2026-07-08
- 执行人：Kano-iso
- 工具：ops-toolkit / qa-backend
- 设备：dev 环境（仅 192.168.100.100 可达）

## 设备可达性检查

| 设备 | IP | 类型 | dev 环境可达 | 备注 |
|---|---|---|---|---|
| Test-Switch-100 | 192.168.100.100 | Spine | ✅ | dev 默认设备 |
| Test-Switch-177 | 192.168.100.177 | Test-Switch | ❌ | ping 100% loss（不在 dev 网络） |
| S6850-54HF | 192.168.100.5 | 生产 Leaf | ❌ | ping 100% loss（不在 dev 网络） |

```bash
$ ping -c 1 -W 2 192.168.100.177
From 192.168.100.10 icmp_seq=1 Redirect Network(New nexthop: 192.168.100.177)
--- 192.168.100.177 ping statistics ---
1 packets transmitted, 0 received, +1 errors, 100% packet loss

$ ping -c 1 -W 2 192.168.100.5
--- 192.168.100.5 ping statistics ---
1 packets transmitted, 0 received, +1 errors, 100% packet loss
```

## 验证策略调整

按 v2.6.1 复盘"issue handling: document and skip encountered problems"原则：

- **真机验证**：dev 环境无真机 .5/.177，**暂时跳过**真机双向验证
- **逻辑覆盖**：T7 已用 mock 测试覆盖核心逻辑：
  - `test_restore_async_returns_error_when_scp_unsupported`：mock `check_restore_support` 返回 `{supported: False}` → 验证后端返回 422 + `error_key=backup.restore_not_supported`
  - `test_restore_async_proceed_when_scp_supported`：mock `{supported: True}` → 验证走原 task_manager.submit 流程
  - `test_restore_async_probe_failure_falls_back_to_supported`：mock 抛异常 → 验证按支持处理 + 错误日志
- **真机回归**：.5 设备真机回归推迟到生产环境验证窗口（需用户授权连接生产设备）

## 上生产 / 真机环境时的真机验证 SOP

### 前置

1. **不要连接生产设备**——qa-backend 集成测试默认走 .177/.5 仅在用户授权时执行
2. 真机测试需在 dev 或预生产环境，避免影响业务
3. 验证前用 `ops-toolkit check-host` / `check-netconf` 确认设备在线

### 步骤

```bash
# 1. 确认 .5 / .177 设备可达
docker compose -f docker-compose.dev.yml --profile qa run --rm ops-toolkit check-host 192.168.100.5
docker compose -f docker-compose.dev.yml --profile qa run --rm ops-toolkit check-host 192.168.100.177

# 2. .177 设备：确认 SCP subsystem 可用
docker compose -f docker-compose.dev.yml --profile qa run --rm ops-toolkit paramiko-batch-exec \
  --device 192.168.100.177 --command "display version | include H3C"
# 预期：返回 H3C Comware Platform Software 等版本信息

# 3. .5 设备：确认 SCP subsystem 不可用（H3C V7 S6850 默认禁用 SFTP/SCP）
docker compose -f docker-compose.dev.yml --profile qa run --rm ops-toolkit paramiko-batch-exec \
  --device 192.168.100.5 --command "display version | include H3C"
# 预期：返回 H3C S6850-54HF 等

# 4. 跑集成测试
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend \
  pytest tests/test_backup_api.py -k "test_restore_real_device" --integration
# 预期：.177 通过、.5 失败（Channel closed.）
```

### 回归检查点

- [ ] .5 设备点回滚 → toast 弹"设备 S6850 不支持 SCP 推回，无法回滚"
- [ ] .5 设备 Backend log 含 `paramiko.ssh_exception.SSHException: Channel closed.`
- [ ] .177 设备点回滚 → toast 弹"回滚成功"或正常进度
- [ ] .177 设备 Backend log 含 `restore success`

## 当前已通过的覆盖

| 验证项 | 覆盖方式 | 通过 |
|---|---|---|
| check_restore_support probe 函数逻辑 | T1 单测 | ✅ |
| restore_async 不支持设备返回 422 | T7 mock 测试 | ✅ |
| restore_async 支持设备走原 task 流程 | T7 mock 测试 | ✅ |
| restore_async probe 失败兜底逻辑 | T7 mock 测试 | ✅ |
| BackupManager._restore_via_scp 详细错误日志 | T3 实现 + 单测 | ✅ |
| 前端 toast 系统 + taskStore 失败触发 | T4 lint + build | ✅ |
| BackgroundTaskPanel 失败高亮 | T5 lint + build | ✅ |
| device.status.restore_unsupported 字段 | T6 实现 + 单测 | ✅ |
| 前后端 i18n key 完整 | FALLBACK_MESSAGES + i18n locale | ✅ |

## 待补（生产环境验证窗口）

- [ ] .5 真机 422 + 前端 toast 真实弹出
- [ ] .177 真机回滚成功全流程
- [ ] 设备 .5 reboot 后 SSH 重连 + 验证生效

## 引用

- T1 单元测试：`backend/tests/test_backup_api.py::test_check_restore_support_returns_false_on_scp_channel_closed`
- T1 单元测试：`backend/tests/test_backup_api.py::test_check_restore_support_returns_true_on_success`
- T7 单元测试：`backend/tests/test_backup_api.py::test_restore_async_returns_error_when_scp_unsupported`
- T7 单元测试：`backend/tests/test_backup_api.py::test_restore_async_proceed_when_scp_supported`
- T7 单元测试：`backend/tests/test_backup_api.py::test_restore_async_probe_failure_falls_back_to_supported`
- v2.6.1 复盘："issue handling: document and skip encountered problems instead of proceeding without record"
