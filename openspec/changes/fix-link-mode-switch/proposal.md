# fix-link-mode-switch

## Why

v2.3 `add-interface-l2-l3-switch` 部署后用户实测 link-mode 失败：
- 后端 500 错误（无业务错误返回）
- 实际 SSH 端点上没把命令送达

测试覆盖缺失：单元测试只跑 mock，真机集成测试未做。

## What Changes

修复 4 个 bug + 补充真机集成测试：

### Bug 1：`_parse_if_name_for_cli()` 错误算法
- **原代码**：`if_index // 100 = slot, if_index % 100 = port` → `GigabitEthernet{slot}/0/{port}`
- **错**：H3C V7 的 if_index 编码不是「百位拆 slot」，5123 ≠ GigabitEthernet51/0/23
- **修**：用 NETCONF 真实查 name，再走 SSH CLI

### Bug 2：SSH 端口错误
- **原代码**：`port=device.port`（=830，NETCONF 端口）
- **错**：830 上 invoke_shell 被 H3C V7 关闭（"Channel closed"）
- **修**：link-mode 强制走 SSH 22（device.port=830 只用于 NETCONF）

### Bug 3：`r['command']` KeyError
- **原代码**：`for r in results: ... r['command']`
- **错**：`SSHExecutor.execute_commands()` 用 `cmd` 键，不是 `command`
- **修**：`r.get('cmd', '?')` + 容错 `r.get('error')`

### Bug 4：`NetconfClient.close()` 不存在
- **原代码**：`nc.close()` 调 close()
- **错**：NetconfClient 用 disconnect()，没 close()
- **修**：用 `nc.disconnect()`

### 新增能力
- `NetconfClient.get_interface_name_by_index()`：if_index → name 真实查询
- `test_link_mode_switch_real_device`：真机 192.168.100.5 集成测试

## Verification

### 单元测试
```
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
→ 100 passed, 11 skipped in 2.68s
```

### 真机集成测试（已 PASS）
```
docker compose -f docker-compose.dev.yml --profile qa run --rm \
  --entrypoint "pytest --integration tests/test_smoke.py::test_link_mode_switch_real_device" qa-backend
→ 1 passed in 11.52s
```

**真机 n → n+1 → n 验证**：
- 初始：GigabitEthernet1/0/1 (if_index=2) L2/bridge
- 切 route：`success=true, 4.7s`
- 切 bridge（恢复）：`success=true, 3.7s`
- 设备状态完全恢复

## Files Changed
- `backend/app/routers/interface.py`（修 Bug 1-4 + 重构）
- `backend/app/netconf_client.py`（新增 `get_interface_name_by_index` + import Optional）
- `backend/tests/test_smoke.py`（新增 `test_link_mode_switch_full_flow` + 真机集成 `test_link_mode_switch_real_device`）

## 影响面
- 只影响 link-mode 端点
- 不影响其他接口操作
- 不影响 NETCONF 其他功能
