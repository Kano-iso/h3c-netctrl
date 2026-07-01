# v24-feat-bridge-button

## Why

v2.3 给物理口加了"改三层"按钮（L2→route），但**反向"改二层"（route→bridge）没做**。

现场痛点：物理口误切成 route 后，前端**无法回退**，只能 SSH 上手敲 `port link-mode bridge`。违反"前端能配就能回退"原则。

用户原话："你这个普通的那种非 low back 非微 lan 的端口，你三层不得能改回二层吗？怎么没有这个按钮啊？"

后端 API `PATCH /devices/{id}/interfaces/{if_index}/link-mode` **早已双向支持**（`mode=bridge|route`），护栏对双向都生效（L3_NAME_PATTERN 拒虚接口、protected 拦保护口）。缺的只是前端按钮。

## What Changes

### 前端（唯一改动点）
- `frontend/src/views/Interfaces.vue`：
  - 新增"改二层"按钮，仅对 **L3 物理口**显示（`layer === 'L3'` 且 name 不是 LoopBack/Vsi/Vlan 虚接口）
  - 改造 `requestSwitchLinkMode(iface)` → `requestSwitchLinkMode(iface, targetMode)`，支持 `'route'` / `'bridge'` 两个方向
  - 新增 `isL3VirtualInterface(name)` 判断函数（与后端 `L3_NAME_PATTERN` + 弱匹配一致：name 含 loopback / vsi / vlan-interface → 虚接口，不显示按钮）
  - 二次确认弹窗文案根据方向动态显示（切到二层 / 切到三层）

### 后端
- **无改动**。API 已双向支持，护栏已双向生效。

## Impact

- **前端**：1 文件改动（Interfaces.vue）
- **后端**：0 改动
- **数据库**：0 改动
- **测试**：前端构建 + 浏览器端到端验证
- **不破坏**：现有"改三层"按钮逻辑（L2 物理口仍显示）
- **可回退**：revert 单文件

## 真机验证

- **设备**：192.168.100.100（Spine-01）GE1/0/5（if_index=6，非保护口）
- **步骤**：
  1. 当前 GE1/0/5 是 bridge（4.2b 回归已恢复）→ 前端显示"改三层"按钮
  2. 点"改三层"切到 route → 前端刷新后显示"改二层"按钮（layer=L3, name=GE 物理口）
  3. 点"改二层"切回 bridge → 前端刷新后恢复"改三层"按钮
  4. SSH `display current-configuration interface GE1/0/5` 验证无 `port link-mode route`（已回 bridge）
  5. 补回 `port access vlan 100`（H3C V7 切 link-mode 会清 L2 配置）
- **护栏验证**：LoopBack0 / Vsi-interface / Vlan-interface 行**不显示**"改二层"按钮（isL3VirtualInterface 拦）

## Out of Scope

- 不动后端 API / 护栏逻辑
- 不动 SSH Executor（[Y/N] 自动应答已在 v24-bugfix-ui-feedback-and-loopback 4.2b 修复）
- 不改"改三层"按钮现有行为

## 关联

- 后端 API（已双向支持）：[backend/app/routers/interface.py `switch_link_mode`](../../backend/app/routers/interface.py)
- 前端待改：[frontend/src/views/Interfaces.vue](../../frontend/src/views/Interfaces.vue)
- v2.3 link-mode 原始 change：[openspec/changes/archive/2026-06-29-add-interface-l2-l3-switch/](../archive/2026-06-29-add-interface-l2-l3-switch/)
- v24-bugfix-ui-feedback-and-loopback（含 [Y/N] 修复 + reason_code）：[proposal.md](../v24-bugfix-ui-feedback-and-loopback/proposal.md)
- v2.4-roadmap：[openspec/changes/v24-roadmap/proposal.md](../v24-roadmap/proposal.md)
