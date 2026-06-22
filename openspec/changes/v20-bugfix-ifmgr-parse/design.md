## Context

v20-netconf-refactor 变更将接口查询改为 NETCONF get-config + Ifmgr filter。真实设备测试发现 API 返回 `data: []`，但实际设备有 23 个接口。

H3C Ifmgr 实际响应格式（从 192.168.100.100 探测）：
```xml
<Ifmgr>
  <Interfaces>
    <Interface><IfIndex>2</IfIndex><PVID>100</PVID></Interface>
    <Interface><IfIndex>3</IfIndex><PVID>100</PVID></Interface>
    ...
    <Interface><IfIndex>5123</IfIndex><MAC>00-00-00-00-00-00</MAC></Interface>
  </Interfaces>
</Ifmgr>
```

H3C 的 Ifmgr 是"按需返回"模型——只返回配置过的字段。未配置的接口可能只有 IfIndex（其他字段都不存在）。

## Goals / Non-Goals

**Goals:**
- 修复 _parse_interface_response，使其能处理字段缺失的响应
- 只要 IfIndex 存在就保留接口记录
- 缺失字段用合理默认值

**Non-Goals:**
- 不修改 filter XML
- 不改其他路由

## Decisions

### D1: 过滤条件改为只检查 IfIndex

**选择**：`if iface.get("if_index"):` 替代 `if iface.get("name") and iface.get("if_index"):`

**理由**：H3C 部分接口的 Interface 元素可能只有 IfIndex，必须保留。

### D2: Name 缺失时用 IfIndex 生成

**选择**：`iface["name"] = f"If-{if_index}"` 当 Name 缺失时

**理由**：前端需要展示名称，不能为空。用 If- 前缀标识是 NETCONF 推断的。

### D3: LinkType 缺失时默认为 access

**选择**：`iface["mode"] = "access"` 当 LinkType 缺失时

**理由**：H3C 千兆口默认就是 access，缺失 LinkType 表示未配置，使用默认值。

## Risks / Trade-offs

- 用 IfIndex 推断 Name 可能与实际接口名不一致 → 用户点击配置时使用 if_index 真实定位，不影响
- 默认 mode=access 可能误判 → 用户在配置弹窗可手动选择实际模式
