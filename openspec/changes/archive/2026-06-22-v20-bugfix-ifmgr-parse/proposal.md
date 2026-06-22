## Why

上一个变更（v20-netconf-refactor）将接口查询改为 NETCONF 后，真实设备测试发现接口列表为空。

根因：H3C Ifmgr 实际响应中 `<Interface>` 元素不一定包含全部字段。设备返回的 23 个接口中，部分接口（如设置了 PVID 的）只包含 IfIndex 和 PVID，没有 Name 和 LinkType。原解析代码用 `if iface.get("name") and iface.get("if_index"):` 把这些接口全部过滤掉了。

## What Changes

- 放宽解析过滤条件：只要有 IfIndex 就保留，缺失字段用合理默认值填充
- Name 缺失时用 IfIndex 生成默认名（If-2、If-3）
- LinkType 缺失时默认为 access（1）
- 通过真实设备验证接口列表不为空

## Capabilities

### Modified Capabilities

- `interface-management`: 接口查询解析逻辑修复，必须能处理字段缺失的响应

## Impact

- 后端：interface.py 的 _parse_interface_response 函数
- 用户体验：前端接口列表能正确展示真实设备的接口
