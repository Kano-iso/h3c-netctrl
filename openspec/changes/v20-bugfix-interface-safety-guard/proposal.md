## Why

真实设备测试中，AI 自动选择了 if_index=2（G1/0/1）做测试，把管理上行口改成了 access 模式，直接导致设备到本机链路中断、NETCONF 不可达。

这是**高风险操作的典型事故**：网络设备管理口/上行口/Trunk 口被误配置，可能导致：
- 设备脱管
- 链路中断
- 业务流量丢失

必须加安全护栏，禁止 AI 或用户误改关键接口。

## What Changes

- Device 模型新增 `protected_interfaces` 字段（JSON 列表），存储受保护接口的 if_index
- 接口配置前检查 if_index 是否在保护列表中，是则拒绝并给出明确错误
- 前端设备管理页面提供接口保护配置 UI
- 接口保护有 `force` 标志位，强制配置需要二次确认
- API 文档中明确哪些设备是"敏感设备"

## Capabilities

### New Capabilities

- `interface-safety-guard`: 接口保护机制，禁止误改关键接口

### Modified Capabilities

- `device-management`: 设备模型增加 protected_interfaces 字段
- `interface-management`: 接口配置增加保护检查

## Impact

- 后端：models.py (新字段) + migrations/versions/004_add_protected_interfaces.py
- 前端：DeviceManagement.vue (配置 UI) + DeviceDetail.vue (配置前确认)
- 体验：高风险操作需要二次确认
