## Why

真实设备测试发现三个问题：
1. **配置前 VLAN 不存在**：用户配置 access vlan 200 时，VLAN 200 未创建，设备返回 "The VLAN does not exist"
2. **设备 NETCONF 状态未知**：H3C NETCONF 失败后端口可能不可达，错误信息只有"连接被拒绝"或"No route to host"，无法快速定位是 ping 不通还是端口关了
3. **没有重试机制**：NETCONF 连接瞬时失败时直接报错，不重试
4. **日志不友好**：后端日志缺少关键错误信息（error_message），前端看到"操作失败"但不知道原因

## What Changes

- 引入渐进式设备诊断：先 ping → 再 nc 端口 → 再 NETCONF 连接
- 接口配置前预校验 VLAN 是否存在，不存在时给出明确提示
- NETCONF 连接失败时自动重试 2-3 次（指数退避）
- 后端日志增强：所有失败操作必须记录可读的错误信息到 log 表
- 错误信息分类：连接类、认证类、协议类、业务类，每类对应不同提示

## Capabilities

### Modified Capabilities

- `device-management`: 设备连接增加渐进式诊断和重试
- `interface-management`: 接口配置增加 VLAN 预校验

## Impact

- 后端：netconf_client.py（重试+诊断）、interface.py（VLAN 预校验）、device.py（连接测试用渐进式诊断）
- 前端：日志页面错误展示（已有，验证可用）
- 体验：用户能快速定位是网络问题还是配置问题
