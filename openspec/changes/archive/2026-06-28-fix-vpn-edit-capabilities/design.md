# fix-vpn-edit-capabilities Design

## Background

v2.2 第一项 `interface-vpn-instance-and-l2-l3` + v2.2.1 patch 修完 UX bug 后，剩 2 个能力缺失型 bug：
1. L2/L3 link type 不可调
2. 三层接口不能配 IP

这 2 个 bug 涉及新增 IPV4ADDRESS edit-config 能力 + LinkType edit-config 能力，工作量 2-3h 集中做。

## Goals

- 让用户能在前端把 L2 接口改 trunk、trunk 改 access
- 让用户能在前端给 L3 接口加 IP、改 IP、删 IP
- 改 link type 强制二次确认，告知破坏性影响
- 真机验证完整跑通

## Non-Goals（v2.2 范围外）

- 多个 L3 接口批量改 IP
- IPv6 配置
- 子接口（sub-interface）的 parent/child 关系管理
- IP 地址格式的多样化（只支持 IPv4 点分十进制 + 点分十进制 mask）

## Decisions

### Decision 1: IPV4ADDRESS edit-config 用 clear + set 模式（不是 replace）

H3C V7 实际行为（待真机确认）：`edit-config` 一个 `Ipv4Address` 条目（同 IfIndex）会**替换**原条目，但**不会**自动删除其他条目。如果同 IfIndex 下已有 IP，set 一个新 IP 不会清空旧 IP。

**选择**：
- **clear + set**：先 `xc:operation="delete"` 清空 IfIndex 下所有 Ipv4Address，再 `create` 新条目 → "替换"语义
- **replace（model 内的 replace operation）**：H3C V7 探测下来不支持 netconf:base:1.0 的 `replace` 操作，会报 `Unknown operation`

**选择 clear + set** 原因：H3C NETCONF 实现普遍支持 `xc:operation="delete"` 和 `merge/None`，不支持 `replace`。两步操作保证"原子性"（设备层面两步之间窗口期 < 1s，业务风险可接受）。

### Decision 2: 改 link type 不做"会清空什么"的预测

**考虑过的方案**：
- A. 后端查询当前接口完整配置，预计算"切换会清空 X"，返回给前端展示
- B. 前端只展示"此操作会清空 access_vlan"等固定提示文字
- C. 后端不下发，前端弹"建议改用 CLI 手工 `port link-mode xxx`"

**选 B**：原因
- A 实现复杂（要解析 Ifmgr 完整配置 + 模拟切换），且 H3C V7 实际行为下"会清空什么"不只是 access_vlan/allowed_vlans，还有 description 等其他配置项
- C 用户明确反对（"为什么不让我在界面上做"）
- B 是务实折中：前端 modal 用"current mode → new mode"对照表，**让用户自己看**当前是什么 + 切到新 mode 会丢什么字段（v2.2.2 范围，固定文字即可）

### Decision 3: 受保护接口护栏

`device.protected_interfaces` 是上行/管理口，**默认拒绝**改 link type / IP，需要 `force=true` 才能继续。
- 改 link type 受保护 → 返回 400，错误信息："接口 if_index=N 是受保护口，需要 force=true 才能继续"
- 配 IP 受保护 → 同上

原因：与 v2.2 第一项的 access/trunk 受保护护栏保持一致，避免散弹枪改设备配置。

### Decision 4: LinkType 字段值映射

H3C V7 LinkType 模型（待真机确认）：
- `1` = access
- `2` = trunk
- `3` = hybrid（H3C 特有；v2.2 暂不支持，UI 也不暴露）

**实现**：`build_link_type_change_xml` 内部用字典 `{"access": 1, "trunk": 2}` 映射，调用方传字符串。

### Decision 5: IP 地址的"清空 vs 单删"

H3C V7 IPV4ADDRESS 模型（待真机确认）：一个接口下可以有多个 Ipv4Address 条目。

**问题**：如果用户想删一个 IP 中的某一个，能否 NETCONF 单删？
**答案**：理论上能，用 `xc:operation="delete"` 带完整子元素（IfIndex + Ipv4Address + Ipv4Mask）唯一定位条目。
**实际**：v2.2 范围内 DELETE 端点只做"清空"（删全部），不做"单删"。

**选清空而非单删的原因**：
- 单删业务语义不明确（用户到底是删 192.168.1.1 还是 192.168.1.2？）
- 清空更安全（用户点确认前能预览"将清空 X 个 IP"）
- 业务场景上"清空重配"比"挑一个删"更常见

前端 IP 编辑 modal 也按"清空"设计：列出当前所有 IP + 输入新 IP + "清空所有 IP"按钮。

### Decision 6: 路由命名 + 路径

- `PATCH /api/devices/{id}/interfaces/{if_index}/link-type` — 改 link type
- `POST /api/devices/{id}/interfaces/{if_index}/ipv4-address` — 配 IP（set/clear + set 一步走）
- `DELETE /api/devices/{id}/interfaces/{if_index}/ipv4-address` — 清空 IP

不用 `PUT`（语义上是 replace 全 IP，与 set 模式不符）。

## Risks & Mitigations

| 风险 | 影响 | 缓解 |
|------|------|------|
| H3C V7 不同固件 LinkType 字段值不同 | 设备返回 RPC error | 真机探测；如果失败 fallback 到 hybrid=3 |
| IPV4ADDRESS edit-config 模式探测错 | set 不生效 | 真机先用 5123 测，确认 set 替换原条目 |
| 改 link type 误清空 description | 用户体验差 | 前端 modal 提示"会清空什么"，强二次确认 |
| 受保护接口护栏误伤 | 用户改不上下行口 IP | force=true 允许，错误信息明确 |
| clear + set 两步之间窗口期 | 1s 业务断网 | 接受；业务上"换 IP"必然有断网 |

## Migration

无。本 change 是新增能力，不修改现有能力。

## Validation Plan

1. **Task 1 单元自测**：`netconf_xml.py` 三个新函数的输入输出 XML（mock 数据，不连真机）
2. **Task 3 真机验证**：
   - 192.168.100.5 找一个不重要的 access 接口（如 5123）→ 改 trunk → 设备 `display this` 确认 → 改回 access
   - 192.168.100.5 L3 接口（如 5121/5128）→ POST ipv4-address → 设备 `display ip interface brief` 确认 → 恢复
   - L2 接口尝试 POST ipv4-address → 应 400
   - 受保护接口尝试 PATCH link-type 不带 force → 应 400
3. **Task 4 前端实测**：浏览器完整跑一遍（端到端）
4. **Task 5 收尾**：commit + archive + VERSION-ROADMAP
