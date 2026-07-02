# v24-bugfix-ui-feedback-and-loopback

## Why

v2.3.1 (2026-07-01) 发版后用户实测发现 3 个 bug：
1. **Bug 1（后端下发？UI 不同步？）**：用户改 L2/L3 接口 / IPv4 / link-mode，后端日志显示"执行成功"，但前端页面没同步显示。用户怀疑"后端根本没下发"——这是 v2.3.1 archive 之前没暴露的问题（QA 用 mock 跑，没真机改过 mode）。
2. **Bug 3（Loopback 仍显示 L2）**：v2.3.1 修了 `_check_l3` + 加了 `_enrich_interface_names`，但用户实测 LoopBack0 仍显示 L2。根因（已定位）：`_detect_layer` 用 `L3_NAME_PATTERN = ^(Vlan-interface|LoopBack|Vsi-interface)\d+` 匹配，**但 H3C V7 Ifmgr 对 Loopback 兜底成 Description（如 `Loopback_VTEP_ID`）时 Pattern 不匹配**，判 L2。
3. **Bug 4（改层级按钮无反馈）**：用户点 link-mode 改 L2↔L3 后没反应，Loopback 这种禁止改的应给明确提示（不是默默无反应）。用户原话："如果点了三层，如果你的预期是让他就是不能不让他改三次，或者说他就是没法变的话，那我觉得就应该比如像微lan if这种端口，那我觉得就应该就是你去点改三层的时候，他就应该有报错，或者你就干脆就不让它有这个选项"。

3 个 bug 一起修（共享设备交互层修复）。

## What Changes

### 修复 1：后端是否真下发（debug-first）
- 加 `OperationLog` 的 `result` 字段（success / failed / not_submitted）区分"真下发" vs "护栏拒"
- 后端在护栏拒时**不**记"成功"，改记"护栏拒绝 + 原因"
- 这样用户看日志能区分"真改了" vs "前端误判同步"
- **决策点**：debug 后再决定要不要改前端自动 refresh

### 修复 2：Loopback L3 兜底（修 Bug 3）
- 扩 `_detect_layer`：增加 Description 弱匹配规则
  - name 包含 `Loopback` / `Vsi` / `Vlan-interface`（不区分大小写，不要求紧跟数字）→ L3
- 加单测 `test_detect_layer_with_description_loopback_fallback`
- 192.168.100.5 真机验证：LoopBack0 → 显示 L3

### 修复 3：link-mode 改层级按钮无反馈（修 Bug 4）
- 路由 `PATCH /api/devices/{id}/interfaces/{if_index}/link-mode` 增强：
  - 护栏拒时**不**只返回 success:false，额外带 `reason_code` + `suggested_action`
  - reason_code: `L3_INTERFACE` / `PHYSICAL_ONLY` / `IFACE_NOT_FOUND` / `MGMT_PROTECTED` / `DEVICE_OFFLINE`
  - suggested_action: 文案 + 跳转链接（如"在 L3 配置 IP"按钮）
- 前端 `LinkModeSwitchModal.vue` / `Interfaces.vue`：
  - 收到 reason_code 后展示对应提示（不是默不作声）
  - Loopback 这种 L3 端口：直接**不显示** "改层级" 按钮（不隐藏但禁用，而是直接不渲染，避免误点）
  - Vlan-interface 同样不显示
  - 物理口保留按钮，点击有二次确认
- 加单测：reason_code 映射 + 前端按钮渲染条件
- 192.168.100.5 真机验证：LoopBack0 上不显示"改层级"按钮 / 物理口上保留

## Impact

- **后端**：interface.py `_detect_layer` 扩规则 + link-mode 路由加 reason_code + OperationLog 加 result 字段
- **前端**：LinkModeSwitchModal / Interfaces.vue 改按钮渲染条件 + reason_code 处理
- **测试**：3 单测 + 1 真机 case
- **数据库**：OperationLog 表加 result 列（migration 兼容老数据）
- **不破坏**：现有 link-mode 流程 / L3 检测逻辑（仅扩展，不改既有）
- **可回退**：每个修复独立 revert

## 真机验证

- **设备**：192.168.100.5（生产 Leaf-04，含 LoopBack0 / Vsi-interface2 / Vlan-interface 各种）
- **Bug 1 debug**：抓一次操作日志（用户改 link-mode）→ 看 result 字段值 → 决定后续
- **Bug 3 验证**：改完后看 GET /api/devices/5/interfaces → LoopBack0 layer="L3" ✓
- **Bug 4 验证**：前端刷新 → LoopBack0 行无"改层级"按钮 ✓ / 物理口仍有按钮 + 二次确认 ✓
- **回归**：v2.3.1 archive 的 8 change 不能破坏（qa-backend 跑 127 passed）

## Out of Scope

- 不重写 link-mode 业务逻辑
- 不动护栏（仅加 reason_code 增强返回）
- 不动 OperationLog 其他字段

## 关联

- 根因：[backend/app/routers/interface.py:228-255 `_detect_layer`](file:///root/workpace/h3c-netctrl/backend/app/routers/interface.py#L228-L255)
- v2.3.1 修复：[openspec/changes/archive/2026-07-01-fix-loopback-vsi-ipv4/proposal.md](../archive/2026-07-01-fix-loopback-vsi-ipv4/proposal.md)
- v2.4-roadmap：[openspec/changes/v24-roadmap/proposal.md](../v24-roadmap/proposal.md)
