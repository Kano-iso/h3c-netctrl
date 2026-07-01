# v24-bugfix-ui-feedback-and-loopback Tasks

> **重要**：每个 [x] 必须真机 / 单元测试 / 集成测试**实测**通过。v2.3.1 教训：理论推断标 [x] 是禁止的。
>
> **设备**：192.168.100.5（生产 Leaf-04，含 LoopBack0 / Vsi-interface2 / Vlan-interface）

---

## 1. Bug 1 debug：后端是否真下发

- [ ] 1.1 抓一次用户操作日志（手动改 link-mode 或 IPv4），看 OperationLog 现有字段
- [ ] 1.2 决定：是否需要 `result` 字段区分 success / failed / guard_rejected
  - 如需要，进入 1.3
  - 如不需要，跳到第 2 阶段
- [ ] 1.3 backend/app/models.py `OperationLog` 加 `result` 列（String, default="success"）
- [ ] 1.4 alembic migration：`alembic revision --autogenerate -m "add_operation_log_result"` + `alembic upgrade head`
- [ ] 1.5 护栏拒的 record_log 调用全部加 `result="guard_rejected"`
- [ ] 1.6 单测：`test_operation_log_result_guard_rejected`（构造护栏拒场景，验证 result 字段）

## 2. Bug 3 修：Loopback 弱匹配

- [ ] 2.1 backend/app/routers/interface.py `_detect_layer` 加 description 弱匹配规则（仅 port_layer is None 时）
- [ ] 2.2 单测 `test_detect_layer_with_description_loopback_fallback`（name="Loopback_VTEP_ID" → L3）
- [ ] 2.3 单测 `test_detect_layer_with_description_vsi_fallback`（name="VSI_TUNNEL_2" → L3）
- [ ] 2.4 单测 `test_detect_layer_with_description_vlan_fallback`（name="Vlan_interface10" → L3）
- [ ] 2.5 单测 `test_detect_layer_physical_port_description_safe`（name="Uplink_to_Spine" → L2，弱匹配不误判）
- [ ] 2.6 `pytest backend/tests/test_detect_layer_v2.py -v` → 4 PASS
- [ ] 2.7 真机 192.168.100.5：调 `GET /api/devices/5/interfaces` → LoopBack0 layer="L3" ✓
- [ ] 2.8 真机 192.168.100.5：Vsi-interface2 / Vlan-interface10 同样 L3 ✓

## 3. Bug 4 修：link-mode reason_code

- [ ] 3.1 backend/app/routers/interface.py link-mode 路由加 REASON_CODES 字典
- [ ] 3.2 护栏拒时返回 `reason_code` + `suggested_action` 字段
- [ ] 3.3 单测 `test_link_mode_l3_interface_reason_code`（Loopback → reason_code="L3_INTERFACE"）
- [ ] 3.4 单测 `test_link_mode_physical_port_success_no_reason`（物理口 success=true, reason_code=None）
- [ ] 3.5 `pytest backend/tests/test_link_mode_reason.py -v` → 2 PASS
- [ ] 3.6 前端 `frontend/src/components/LinkModeSwitchModal.vue` 接收 reason_code 展示
- [ ] 3.7 前端 `frontend/src/views/Interfaces.vue` v-if="iface.layer === 'L2'" 才渲染"改层级"按钮
- [ ] 3.8 列表顶部加说明 "L3 接口不可改层级，请直接配置 IP"
- [ ] 3.9 真机 192.168.100.5：LoopBack0 行无"改层级"按钮 ✓
- [ ] 3.10 真机 192.168.100.5：物理口 GE1/0/30 行有按钮 + 二次确认 ✓

## 4. 验证

- [ ] 4.1 `pytest backend/tests/ --integration` → 127 passed, 4 skipped, 0 failed
- [ ] 4.2 端到端：点物理口"改层级" → 二次确认 → 改成功 → 页面刷新显示 L3
- [ ] 4.3 端到端：点 LoopBack0 改层级（按钮已不显示，无操作）
- [ ] 4.4 OperationLog 日志：护栏拒记 result="guard_rejected" ✓

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
