## Context

当前接口管理使用 SSH (paramiko) 实现，VLAN 管理使用 NETCONF (ncclient) 实现。两套协议并存导致：
- 接口配置需要处理 H3C 分页、命令兼容性等 SSH 特有问题
- SSH 连接频率高（每次请求新建/关闭连接），交换机日志产生大量登录记录
- 不符合项目使用 NETCONF 的初衷

H3C Comware NETCONF 支持 Ifmgr 命名空间进行接口管理，XML 结构：
- 查询：`get-config` + `<Ifmgr><Interfaces/></Ifmgr>` filter
- 配置：`edit-config` + `<Ifmgr xc:operation="merge"><Interfaces><Interface>...` XML
- 关键字段：IfIndex（接口索引）、LinkType（1=access, 2=trunk, 3=hybrid）、PVID、TrunkVLANs

## Goals / Non-Goals

**Goals:**
- 接口查询和配置统一使用 NETCONF，消除 SSH 命令兼容性问题
- 减少不必要的设备连接（DeviceDetail 页面去掉自动加载）
- 保持 SSH 仅用于运维终端和资产信息采集（display 命令类操作）

**Non-Goals:**
- 不做 SSH 连接池（当前规模不需要）
- 不改资产信息采集（display 命令只能用 SSH）
- 不改运维终端（交互式命令只能用 SSH）

## Decisions

### D1: 接口查询改用 NETCONF get-config

**选择**：用 NETCONF `get-config` + Ifmgr filter 替代 SSH `display interface brief`

**理由**：
- 结构化数据，不需要正则解析
- 和 VLAN 查询使用同一连接方式
- 避免分页处理问题

**注意**：NETCONF 返回的 IfIndex 是数字索引，需要映射为接口名。可通过 Ifmgr 的 Name 字段获取。

### D2: 接口配置改用 NETCONF edit-config

**选择**：用 NETCONF `edit-config` + Ifmgr XML 替代 SSH execute_commands

**理由**：
- 结构化配置，不存在 `port link-mode bridge` 兼容性问题
- NETCONF edit-config 原子操作，要么成功要么失败
- 和 VLAN 配置使用同一方式

**XML 结构**：
```xml
<config>
  <top xmlns="http://www.h3c.com/netconf/config:1.0">
    <Ifmgr>
      <Interfaces>
        <Interface>
          <IfIndex>接口索引</IfIndex>
          <LinkType>2</LinkType>  <!-- 1=access, 2=trunk, 3=hybrid -->
          <PVID>100</PVID>
          <TrunkVLANs>VLAN列表</TrunkVLANs>
        </Interface>
      </Interfaces>
    </Ifmgr>
  </top>
</config>
```

### D3: 接口名到 IfIndex 的映射

**选择**：查询接口列表时，同时获取 IfIndex 和 Name，前端展示 Name、后端配置时用 IfIndex

**理由**：NETCONF 配置需要 IfIndex，但用户看到的是接口名。查询时一起获取即可。

### D4: DeviceDetail 去掉自动加载

**选择**：onMounted 只加载设备基本信息和 VLAN，接口和资产改为手动刷新

**理由**：每次进入详情页自动加载接口+资产会产生 3 次 SSH 连接，改为手动刷新后只在用户需要时才连接。

## Risks / Trade-offs

- [IfIndex 获取失败] → 如果设备不支持 Ifmgr 查询，回退到 SSH 方式（保留 SSH 查询作为 fallback）
- [NETCONF XML 格式因设备型号不同] → 需要在实际设备上测试验证，可能需要微调 XML 结构
