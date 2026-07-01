# v24-bugfix-interface-display-100

## Why

v2.3.1 (2026-07-01) 发版后用户实测发现：
- **192.168.100.100**（关键生产设备）：能列出**所有**接口，包括未 up 的
- 其他生产 / 测试设备：只能看到 up 的接口

用户原话："除了这个其他生产、测试都不行，我不觉得这台机器有什么特别之处啊，难道说我们 IP 难道？也没有任何没有看到任何的。说实话没看到任何的他，不一样的地方都在同一个二层网段里"

## 假设（debug 假设，待验证）

为什么 100.100 能看到所有接口？3 个可能：
1. **Ifmgr filter 不一致**：100.100 设备返回全表，其他设备 filter 默认只回 up
2. **设备配置差异**：100.100 上了 `display interface` 命令后实际接口都"存在"，但其他设备 down 的接口直接被 NETCONF filter 过滤
3. **客户端代码 bug**：parse 时漏解析 down 接口字段（如 `ifAdminStatus=down`），其他设备只是没字段→跳过了；100.100 可能**真返回**了所有字段但 parse 时漏判

## What Changes

### Debug 阶段（先做）
- 加 debug 日志：在 `get_interfaces` 路由打印 NETCONF filter + 原始返回 XML 大小
- 100.100 跑一次 + 一台普通生产跑一次，对比 XML 数据量
- 定位是 filter 问题 / 设备问题 / parse 问题

### 修复阶段（按 debug 结果分支）
- **分支 A（filter 不一致）**：用统一 NETCONF filter 查询所有接口（不 filter AdminStatus），parse 阶段只过滤无 Name 的接口
- **分支 B（设备配置差异）**：100.100 设备 NETCONF 默认就回全表，其他设备需要显式请求——统一加上 `display interface` 风格 filter
- **分支 C（parse 漏判）**：检查 `_parse_interface_response` 是否有 "down 跳过" 逻辑，移除或修正

### 决策点
- debug 后再决定修复方案
- 加单测覆盖"down 接口也应列出"场景

## Impact

- **后端**：netconf_client.py / interface.py 的 query / parse 逻辑
- **前端**：0 改动（设备列表 API 返回全接口，前端自然显示）
- **测试**：1 单测 + 100.100 真机 + 普通生产真机对比
- **不破坏**：v2.3.1 现有功能
- **可回退**：独立 revert

## 真机验证

- **设备**：192.168.100.100（特例）+ 192.168.100.4 / 192.168.100.5（普通生产）
- **debug**：
  - 100.100 跑 `GET /api/devices/{id}/interfaces` → 抓 NETCONF filter + 原始 XML
  - 普通生产跑同样 → 对比 XML 大小 / 字段差异
- **验证**：修完后两边都返回所有接口（无论 up/down），前端列表数量一致
- **回归**：v2.3.1 archive 8 change 不能破坏

## Out of Scope

- 不改前端"已连接" / "未连接"状态展示
- 不动 netconf filter 语法本身（H3C 标准）
- 不改数据库模型

## 关联

- 现有 query 路径：[backend/app/routers/interface.py:319-440 `get_interfaces`](file:///root/workpace/h3c-netctrl/backend/app/routers/interface.py#L319-L440)
- v2.4-roadmap：[openspec/changes/v24-roadmap/proposal.md](../v24-roadmap/proposal.md)
