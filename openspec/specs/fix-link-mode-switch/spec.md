# spec: fix-link-mode-switch

## 能力

修复 v2.3 link-mode 切换的 4 个 bug + 补充真机集成测试。

## 范围

### Bug 修复
1. `_parse_if_name_for_cli()` 错误：H3C V7 if_index 不能数字解析为接口名
2. SSH 端口错误：device.port=830 不支持 invoke_shell，强制走 SSH 22
3. `r['command']` KeyError：实际是 `r['cmd']`
4. `NetconfClient.close()` 不存在：用 `disconnect()`

### 新增能力
- `NetconfClient.get_interface_name_by_index()`：if_index → name 真实查询
- `test_link_mode_switch_real_device`：真机 192.168.100.5 集成测试

## 设计决策

- **link-mode 强制走 SSH 22**（不是 device.port=830 的 NETCONF）
- **if_index → name 用 NETCONF 查**（不靠数字解析）
- **真机测试必备**：H3C V7 协议差异无法 mock 覆盖

## 验收标准

- [x] 单元测试 100 passed（不 mock 设备的部分）
- [x] 真机集成测试 PASS（n → n+1 → n 闭环）
- [x] link-mode 切换时间 < 10s

## 关联 change
- `openspec/changes/archive/2026-06-29-fix-link-mode-switch/`
