## Context

v2.2 第一项 `interface-vpn-instance-and-l2-l3` 在 192.168.100.4 设备上 archive 时，真机验证任务 8.3 / 8.4 (bind / unbind) 因设备拓扑约束（只有 1 个 L3 接口 5121 且已绑 mgt）被标 N/A。

用户切到 192.168.100.5 实测发现：

- **bug 4**（逻辑错误）：unbind 操作时，后端从 `build_interface_extended_filter_xml()` 拉接口 + VPN 绑定数据，但实际上该函数只查 Ifmgr（**不查 L3vpn**），导致 `_parse_interface_response` 中 Pass 3 (Bind 解析) 永远拿不到数据 → 预校验判断 `target.vpn_instance` 永远为 None → 后端报"未绑定 VPN instance"。**这会让运维误判设备状态、误以为解绑成功（实际未执行 NETCONF 写操作）**。
- **bug 3**（UX 缺陷）：Interfaces.vue 上 `+ VPN` 按钮触发 `VpnInstanceBindModal` 的 create 模式，create 模式不显示 `existingVpns` 列表只让填新名字 → 用户在不知道设备已有 VPN 名称时易创建重名/冲突实例。

## Goals / Non-Goals

**Goals：**
- 修复 unbind 预校验的逻辑错误（让 `vpn_instance` 字段能被正确读到）
- 在 Modal 顶部展示现有 VPN instance 列表（两种模式都显示）
- 在 192.168.100.5 上做端到端真机验证（解绑实际带 VPN 的接口 + 验证列表展示）

**Non-Goals：**
- **不**实现 IPV4ADDRESS edit-config（bug 1+2，留作 v2.2.1 follow-up）
- **不**调整 L2/L3 派生规则
- **不**修改 list / create / delete / bind 端点行为（archive 时已实测通过）
- **不**做 NETCONF 能力探测 / SSH CLI fallback（v2.3 follow-up）

## Decisions

### 决策 1：bug 4 修复用"两次 get + 合并"代替"单次多根 filter"

**问题**：H3C filter schema 严格，不接受多根元素（[netconf_xml.py:42](file:///root/workpace/h3c-netctrl/backend/app/utils/netconf_xml.py#L42) 注释已说明），所以无法在一个 `get_config` 里同时拿 Ifmgr + L3vpn。

**方案 A（推荐）**：在 `unbind_interface_vpn` 路由内做**两次 `get_config`**：
1. 一次拉 Ifmgr + IPV4ADDRESS（现有 `_build_interface_filter_xml` 不动）
2. 一次拉 L3vpn（用 `build_vpn_instance_filter_xml`）
3. 解析 L3vpn 响应拿到 `vpn_by_idx` dict
4. 把 `vpn_by_idx` 注入到 `_parse_interface_response` 解析结果（**复用现有解析逻辑**）

**方案 B**：扩展 `_parse_interface_response` 接受外部 `vpn_by_idx` 参数，让调用方控制数据源。

**方案 C**：废弃 `build_interface_extended_filter_xml`，改用纯 L3vpn filter + 简单 Bind XML 解析（去掉 Ifmgr 依赖）。

**选 A 的理由**：
- 改动最小（只在 unbind 路由里加一次 get_config + 合并）
- 不破坏现有 `_parse_interface_response` 的可复用性
- 其它路由（如 `get_interfaces`）已经走合并 filter 路径，无需改

**选 A 的代价**：
- `unbind_interface_vpn` 路由需要第二次 get_config（多 ~1s 延迟），可接受

### 决策 2：bug 3 修复 Modal 顶部加列表 section，保留两种模式切换

**方案 A（推荐）**：保留 create / bind 两种模式入口，**Modal 顶部新增"现有 VPN instance"section**（两种模式都显示）：
- 列表项：name + rd + 绑定接口数
- create 模式下，列表下方有"或新建"折叠区
- bind 模式下，整张 Modal 都是列表 + 选择

**方案 B**：完全合并 create + bind 为单一界面（"选已有 / 输入新名"两选一）。

**选 A 的理由**：
- 向后兼容：现有 Interfaces.vue 的 `+ VPN` / `绑 VPN` 按钮调用 mode 不变
- UX 更清晰：用户先看列表，决定选还是建
- 改动局部：只改 VpnInstanceBindModal.vue 一个组件

### 决策 3：不在 `unbind` 路由中删除"硬编码预期 N/A"的注释

archive tasks.md 里 8.3 / 8.4 标 N/A 是因为 192.168.100.4 拓扑约束，不是代码不可用。本次 192.168.100.5 真机验证可以补完这一项。

## Risks / Trade-offs

- **[风险 1] 两次 get_config 之间的状态不一致**：第一次查 Ifmgr 后设备有改动，第二次查 L3vpn 时 Bind 已不存在 → 预校验误判"未绑定" → 解绑失败
  - **缓解**：H3C V7 上 VPN 绑定是即时生效的串行操作，单次 API 调用内两次 get_config（间隔 < 1s）发生状态变更的概率极低；如果发生，用户可重试
- **[风险 2] 192.168.100.5 设备配置/型号与 192.168.100.4 不完全一致**：H3C V7 跨设备可能 model 微差
  - **缓解**：archive 任务用 100.5 做真机验证（用户已确认设备能力正常）
- **[风险 3] Modal 顶部加列表导致高度增加，移动端溢出**
  - **缓解**：列表用 `max-h-64 overflow-y-auto`（现有实现已有此样式），移动端可滚动
- **[风险 4] bug 4 修复后，`unbind` 路由的预校验逻辑变严 → 之前在 100.4 上"未绑定"错误消失，但实际用户操作场景下可能误判**
  - **缓解**：保留 NETCONF 异常透传（设备返回 RPC 错误时仍按 `classify_netconf_error` 分类）

## Migration Plan

1. **阶段 1**（task 1.x）：修后端 `unbind_interface_vpn` 路由（双查询 + 合并）
2. **阶段 2**（task 2.x）：修前端 `VpnInstanceBindModal.vue`（顶部列表 section）
3. **阶段 3**（task 3.x）：在 192.168.100.5 上真机验证（unbind 实际带 VPN 的接口 + Modal 展示列表）
4. **回滚**：单 git revert 即可（无 DB migration，无 schema 变化）
