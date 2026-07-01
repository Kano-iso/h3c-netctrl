# v24-feat-bridge-button Tasks

> **重要**：每个 [x] 必须真机 / 单元测试 / 集成测试**实测**通过。v2.3.1 教训：理论推断标 [x] 是禁止的。
>
> **设备**：192.168.100.100（Spine-01）GE1/0/5（if_index=6，非保护口）

---

## 1. 前端改造

- [x] 1.1 `frontend/src/views/Interfaces.vue` 新增 `isPhysicalPort(name)` 函数
  - 与后端 `_looks_like_physical_port` 正则一致（GigabitEthernet / TenGigabit / FortyGigE / M-GigabitEthernet 等）
  - **设计变更**：原 design.md 用 `isL3VirtualInterface`（含 loopback/vsi/vlan-interface 判断），但浏览器验证发现 NULL0 / Register-Tunnel0 这类虚接口不含这些关键字会误显按钮。改为反向判断 `isPhysicalPort` 更准确
- [x] 1.2 改造 `requestSwitchLinkMode(iface)` → `requestSwitchLinkMode(iface, targetMode='route')`
  - 支持 'route'（改三层）| 'bridge'（改二层）两个方向
  - 二次确认弹窗文案根据 targetMode 动态生成（三层 route / 二层 bridge）
  - 预检逻辑：改三层拦 L3 接口，改二层拦非物理口（reason_code=PHYSICAL_ONLY）
- [x] 1.3 模板加"改二层"按钮
  - v-if="i.layer === 'L3' && isPhysicalPort(i.name)"
  - @click="requestSwitchLinkMode(i, 'bridge')"
- [x] 1.4 "改三层"按钮调用改为 `requestSwitchLinkMode(i, 'route')`（显式传参，保持行为不变）
- [x] 1.5 顶部说明文案更新（L2 物理口改三层 / L3 物理口改二层 / L3 虚接口不可切）

## 2. 自测

- [x] 2.1 `docker exec h3c-netctrl-frontend sh -c 'cd /app && npm run build'` → ✓ built in 2.48s，0 报错
- [x] 2.2 浏览器端到端（Chrome DevTools MCP snapshot 验证）：
  - L2 物理口行（GE1/0/1~GE1/0/48, TE, FGE）显示"改三层"按钮（现有行为不变）✓
  - L3 物理口行（M-GigabitEthernet0/0/0）显示"改二层" + "改 IP"按钮 ✓
  - L3 虚接口行（NULL0 / InLoopBack0 / Register-Tunnel0 / Vlan-interface100）只显示"改 IP"按钮（无"改二层"）✓
  - **初版用 isL3VirtualInterface 时 NULL0 / Register-Tunnel0 误显"改二层"**，改为 isPhysicalPort 后修复

## 3. 真机验证

- [x] 3.1 192.168.100.100 GE1/0/5（当前 bridge）调 API `PATCH /api/devices/1/interfaces/6/link-mode mode=route force=true` → 返 `confirmed:true` ✓
  - 浏览器刷新后 GE1/0/5 行 layer=L3 + 显示"改二层"按钮（isPhysicalPort("GigabitEthernet1/0/5")=true）✓
- [x] 3.2 调 API `PATCH /api/devices/1/interfaces/6/link-mode mode=bridge force=true` → 返 `confirmed:true` ✓
  - 浏览器刷新后 GE1/0/5 行 layer=L2 + 恢复"改三层"按钮 ✓
- [x] 3.3 SSH `display current-configuration interface GigabitEthernet1/0/5` 验证：
  ```
  interface GigabitEthernet1/0/5
   port link-mode bridge    ← 已回 bridge ✓
   combo enable fiber
  #
  return
  ```
  无 `port link-mode route` ✓
- [x] 3.4 LoopBack0 / Vsi-interface / Vlan-interface / NULL0 / Register-Tunnel0 行无"改二层"按钮（isPhysicalPort 拦）✓
- [~] 3.5 补回 `port access vlan 100`（H3C V7 切 link-mode 清 L2 配置）
  - **用户指示跳过**："补回 vlan 的动作不一定要做，不用做"

## 4. 收尾

- [x] 4.1 commit `feat(frontend): L3 物理口加"改二层"按钮，补全 link-mode 双向切换`
- [ ] 4.2 archive 进 `archive/2026-07-XX-v24-feat-bridge-button/`
  - **延后到 v2.4.0 发版时统一 archive**
- [ ] 4.3 进 v2.4 release notes 合并
  - **v2.4.0 发版时引用**

## 关联

- [proposal.md](proposal.md)
- [design.md](design.md)
- v2.4-roadmap：[openspec/changes/v24-roadmap/proposal.md](../v24-roadmap/proposal.md)
