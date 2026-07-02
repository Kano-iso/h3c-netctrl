# v24-bugfix-status-mapping Tasks

> **重要**：每个 [x] 必须真机 / 单元测试 / 集成测试**实测**通过。v2.3.1 教训：理论推断标 [x] 是禁止的。
>
> **设备**：192.168.100.5 (Leaf-04) + 192.168.100.100 (Spine-01)

---

## 1. 修代码

- [x] 1.1 修 `backend/app/routers/interface.py:150` `iface["oper_status"]` 映射：`child.text == "2"` → `child.text == "1"`
- [x] 1.2 修上方注释（[interface.py:144-145](file:///root/workpace/h3c-netctrl/backend/app/routers/interface.py#L144-L145)）：明确 "1=UP 2=DOWN"，引用 RFC 2863
- [x] 1.3 OperStatus 兜底逻辑：取 3/4/5/6/7 非 1/2 值时 oper_status = "down"（保守处理）

## 2. 单测

- [x] 2.1 新建 `backend/tests/test_status_mapping.py`，mock NetconfClient.get 返回的 XML
- [x] 2.2 9 个 case 矩阵覆盖（AdminStatus × OperStatus × status 优先级 + 兜底 + 回归）
- [x] 2.3 跑 `pytest backend/tests/test_status_mapping.py -v` → **9 PASSED**

## 3. 回归

- [x] 3.1 `pytest backend/tests/ --tb=no -q` → **147 passed, 11 skipped, 0 failed**（比 v2.3.1 baseline 127+4 新增 9 个新单测 + 1 修正）
- [x] 3.2 真机 192.168.100.5: GE1/0/1 (if=2) OperStatus=1, 1Gbps → status="up" ✓
- [x] 3.3 真机 192.168.100.5: GE1/0/2 (if=3) OperStatus=2, 无 ActualSpeed → status="down" ✓
- [x] 3.4 真机 192.168.100.100: GE1/0/1 (if=2) OperStatus=1, 1Gbps → status="up" ✓
- [x] 3.5 真机 192.168.100.100: GE1/0/5 (if=6) OperStatus=1, 1Gbps → status="up" ✓
- [x] 3.6 4 个口都用 NetconfClient 直拉原始 XML（不经 `_parse_interface_response`）对照金标准 ✓

## 4. 收尾

- [x] 4.1 commit `fix(interface): OperStatus 映射修正 (1=UP 2=DOWN) + 9 case 单测` → `d9ce9d4`
- [x] 4.2 检查 v24-bugfix-ui-feedback-and-loopback §3.10 截图
  - **结论：link-mode 弹窗只用 `iface.layer`（L2/L3 层级），不显示 status 字段**
  - 详见 [Interfaces.vue requestSwitchLinkMode](file:///root/workpace/h3c-netctrl/frontend/src/views/Interfaces.vue#L271-L322)：传 `data.message` 和 `iface.layer`，不引用 `iface.status`
  - status 修复**不**影响 link-mode 弹窗文案，§3.10 截图无需刷新
- [ ] 4.3 archive 进 `archive/2026-07-XX-v24-bugfix-status-mapping/`（v2.4.0 发版时统一 archive）

## 5. 设备最终状态

- 192.168.100.5 / 192.168.100.100 接口数据无变化（仅修正 status 字段映射，不动配置）
- 192.168.100.4 / 177 / 其他设备不动

## 6. 提交记录

| commit | 描述 |
|---|---|
| TBD | fix(interface): OperStatus 映射修正 (1=UP 2=DOWN) + 8 case 单测 |

## 关联

- [proposal.md](proposal.md)
- [design.md](design.md)
- [specs/interface-vpn-instance-and-l2-l3/spec.md](specs/interface-vpn-instance-and-l2-l3/spec.md)
- v2.4-roadmap：[openspec/changes/v24-roadmap/proposal.md](../v24-roadmap/proposal.md)
