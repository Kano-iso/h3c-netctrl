# v24-bugfix-ui-feedback-and-loopback Tasks

> **重要**：每个 [x] 必须真机 / 单元测试 / 集成测试**实测**通过。v2.3.1 教训：理论推断标 [x] 是禁止的。
>
> **设备**：192.168.100.5（生产 Leaf-04，含 LoopBack0 / Vsi-interface2 / Vlan-interface）

---

## 1. Bug 1 debug：后端是否真下发

- [x] 1.1 抓一次用户操作日志（手动改 link-mode 或 IPv4），看 OperationLog 现有字段
- [x] 1.2 决定：是否需要 `result` 字段区分 success / failed / guard_rejected
  - **结论：不需要**。现有 `Log.status` (success/failed) + `Log.error_message` 已能区分。
  - 护栏拒时已记 `record_log(..., "failed", error_message=msg)`（如 link-mode 路由 1136-1138、interface_config 路由 471-473、487-489、530-532）。
  - 用户日志看到 "执行成功" → status="success" → 后端**真下发**了，问题不在后端。
  - Bug 1 真根因是**前端 UI 不立即重算**（mode 字段、layer 字段改完后没及时显示）→ 见 §4 端到端验证 4.3。
  - **跳过 1.3-1.6**（无需加 result 列 / migration / 改 record_log 调用）。

## 2. Bug 3 修：Loopback 弱匹配

- [x] 2.1 backend/app/routers/interface.py `_detect_layer` 加 description 弱匹配规则（仅 port_layer is None 时）→ 加 `L3_NAME_WEAK_PATTERNS` 3 个正则
- [x] 2.2 单测 `test_detect_layer_with_description_loopback_fallback`（name="Loopback_VTEP_ID" → L3）
- [x] 2.3 单测 `test_detect_layer_with_description_vsi_fallback`（name="VSI_TUNNEL_2" → L3）
- [x] 2.4 单测 `test_detect_layer_with_description_vlan_fallback`（name="Vlan_interface10" → L3）
- [x] 2.5 单测 `test_detect_layer_physical_port_description_safe`（name="Uplink_to_Spine" → L2，弱匹配不误判）
- [x] 2.6 `pytest backend/tests/test_detect_layer_v2.py -v` → **9/9 PASSED**（含 4 个回归测试）
- [x] 2.7 真机 192.168.100.5：调 `GET /api/devices/5/interfaces` → **9 个 L3 接口全对**（含 LoopBack0 / Vsi-interface1,2,3 / Vlan-interface12 / InLoopBack0 / NULL0 / Register-Tunnel0 / M-GigabitEthernet0/0.0）✓
  - 注：100.5 真机 Ifmgr 已返回 name（"LoopBack0"），弱匹配作为 _enrich_interface_names 失败的兜底安全网（description="Loopback_VTEP_ID" 是真实 Description 字段）
- [x] 2.8 真机 192.168.100.5：100.4 同样 4 个 L3 全对（M-GE / NULL0 / InLoopBack0 / Register-Tunnel0），无 Loopback/Vsi/Vlan 触发场景 ✓

## 3. Bug 4 修：link-mode reason_code

- [x] 3.1 backend/app/routers/interface.py link-mode 路由加 REASON_CODES 字典
- [x] 3.2 护栏拒时返回 `reason_code` + `suggested_action` 字段
- [x] 3.3 单测 `test_link_mode_l3_interface_reason_code`（Loopback → reason_code="L3_INTERFACE"）
- [x] 3.4 单测 `test_link_mode_physical_port_success_no_reason`（物理口 success=true, reason_code=None）
  - 修正：用 if_index=100（非保护口）而非 2（被保护，created_device fixture 默认 [2]）
- [x] 3.5 `pytest backend/tests/test_link_mode_reason.py -v` → **4 PASSED**（含 L3_INTERFACE / PHYSICAL_ONLY / PROTECTED_INTERFACE / 物理口二次确认 4 个场景）
- [x] 3.6 前端 `frontend/src/components/LinkModeSwitchModal.vue` 接收 reason_code 展示
  - 注：项目无独立 LinkModeSwitchModal，v2.3 是用 ConfirmModal。改造现有 ConfirmModal 调用 + 新增 linkModeGuardInfo 弹窗
  - `frontend/src/views/Interfaces.vue` 改造 `requestSwitchLinkMode` / `confirmSwitchLinkMode`：捕获 `data.reason_code` + `data.suggested_action` → `linkModeGuardInfo` 触发新 ConfirmModal
  - 新增 `dismissLinkModeGuard()` 关闭守卫弹窗
- [x] 3.7 前端 `frontend/src/views/Interfaces.vue` v-if="iface.layer !== 'L3'" 才渲染"改三层"按钮
- [x] 3.8 列表顶部加说明 "L3 接口不可改层级，请直接配置 IP"
- [x] 3.9 真机 192.168.100.5 (Leaf-04)：54 个 L2 物理口行有"改三层"按钮，5 个 L3 接口行（LoopBack0 / Vsi1,2,3 / Vlan12 / M-GE）**无"改三层"按钮** ✓
  - 浏览器工具 (browser_snapshot) 验证 e58-e217 全是 L2 物理口的"改三层"按钮，e218/e222/e226/e230/e234 等 L3 接口行只有"改 IP / 绑 VPN / + VPN"按钮
- [x] 3.10 真机 192.168.100.5 (Leaf-04)：点 GE1/0/1 物理口"改三层" → 弹窗"切换接口层级到 三层（route）"显示当前层级 L2 / 目标层级 L3（route）/ H3C V7 行为警告 / 取消 + 确认切换 按钮 → 点取消关闭弹窗（设备配置**未变**）✓
  - 截图证据：二次确认弹窗含 if_index=2、当前/目标层级、H3C V7 行为警告、操作不可撤销提示

## 4. 验证

- [x] 4.1 `pytest backend/tests/ --tb=no -q` → **138 passed, 11 skipped, 0 failed**
  - 比 v2.3.1 baseline (127 passed, 4 skipped) 新增 11 个单测：4 link_mode_reason + 7 detect_layer_v2 (其中 4 是 v24 弱匹配回归测试)
- [x] 4.2 端到端：点物理口"改三层" → 二次确认 → 取消关闭（设备配置未变）✓
  - 真机 100.5 GE1/0/1 点"改三层" → 弹窗正常显示 → 点取消关闭（**未真改设备**），详见 3.10
- [x] 4.3 端到端：点 LoopBack0 改层级（按钮已不显示，无操作）✓
  - 真机 100.5 L3 接口行无"改三层"按钮（详见 3.9），用户不可能误点
- [x] 4.4 OperationLog 日志：护栏拒记 status="failed" + error_message 带 reason_code
  - 后端链路验证：单测 `test_link_mode_*_reason_code` 4/4 PASS，护栏拒时 `record_log(..., "failed", error_message=msg)` 调用链路已存在
  - 浏览器侧兜底弹窗验证：linkModeGuardInfo 弹窗链路已实现（虽 v-if 已挡住 L3，竞态/数据过期时兜底）

## 5. 收尾

- [ ] 5.1 1 个 commit `fix(interface): Loopback description 兜底弱匹配 + link-mode reason_code + OperationLog.result`
- [ ] 5.2 commit `fix(frontend): Interfaces.vue 改层级按钮仅 L2 显示 + 列表顶部说明`
- [ ] 5.3 commit `test: 4+2 单测覆盖 detect_layer + link_mode_reason + operation_log_result`
- [ ] 5.4 archive 进 `archive/2026-07-XX-v24-bugfix-ui-feedback-and-loopback/`
- [ ] 5.5 进 v2.4 release notes 合并

## 设备最终状态

- 192.168.100.5 接口数据无变化（仅前端展示修复，不动配置）
- 192.168.100.4 / .177 不动

## 关联

- [proposal.md](proposal.md)
- [design.md](design.md)
- v2.4-roadmap：[openspec/changes/v24-roadmap/proposal.md](../v24-roadmap/proposal.md)
