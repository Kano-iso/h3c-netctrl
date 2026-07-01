## Why

`backend/app/routers/interface.py` 的 `_parse_interface_response` 把 H3C V7 Ifmgr 返回的 `<OperStatus>` 字段映射写反了——注释声称 "H3C V7 OperStatus 1=down 2=up"，代码用 `child.text == "2"` 判 up，但实际 IF-MIB RFC 2863 与 H3C V7 真机返回都是 **1=UP 2=DOWN**（与 `<AdminStatus>` 编码一致）。这导致 `GET /api/devices/{id}/interfaces` 返回的 `status` 字段全列反：链路层 up 的口显示 down，down 的口显示 up。

**根因**：v2.4-bugfix-interface-display-100 change（commit `c012051`，2026-07-02 01:42）引入 `OperStatus` 概念时把编码写反，同时 admin_status 用对的 `==1` 判 up、oper_status 用错的 `==2` 判 up，后者覆盖前者。v2.3.0 / v2.3.1 没有 OperStatus 概念，链路层状态完全没取，所以"所有 admin 没 shutdown 的口全显 up"——v2.4 这次想修对但写反，引入了一个**比老版本更隐蔽**的 bug。

**影响范围**：所有设备、所有接口的前端 status 显示都是错的。OperationLog / SSH 22 / backup 等链路不依赖该字段，**只影响前端展示**，无功能损坏。但前端"改 link-mode"二次确认时显示的 status 是错的（v24-bugfix-ui-feedback-and-loopback §3.10 验证截图里的"当前状态"也是错的）。

## What Changes

- **后端**：`_parse_interface_response` 中 `OperStatus` 映射从 `==2 → up` 改为 `==1 → up`，并修正上方注释（写明 RFC 2863 / H3C V7 实际是 1=UP 2=DOWN）。`admin_status` 映射（`==1 → up`）保持不变，作为"是否被 shutdown"的辅助字段。
- **单测**：新增 `backend/tests/test_status_mapping.py`，覆盖 OperStatus 1/2 边界、AdminStatus 1/2 边界、二者组合（admin=up/oper=up/down、admin=down/oper=up/down）、Unknown (3) 兜底成 "down"。
- **真机回归**：4 个 1Gbps UP 链路口 + 1 个空载 DOWN 口，对照 NetconfClient 直拉的 `<OperStatus>` 与 `ActualSpeed` 金标准。
- **spec**：在 `interface-vpn-instance-and-l2-l3` 加一个 Requirement 明确 status 编码正确性（修改现有 capability）。
- **BREAKING**：无。`status` 字段值类型不变（仍是 "up"/"down"/"unknown"），只修正反的值。

## Capabilities

### New Capabilities
无

### Modified Capabilities
- `interface-vpn-instance-and-l2-l3`: 现有 spec 中 "现有字段（...status...）行为不变" 需细化，新增 Requirement 明确 `status` 字段必须正确反映 H3C V7 Ifmgr 的 `<OperStatus>`（1=UP, 2=DOWN），并提供金标准对照 scenario。

## Impact

- **代码改动**：`backend/app/routers/interface.py` 1 行 + 注释 2 行
- **新增测试**：`backend/tests/test_status_mapping.py`
- **前端**：无改（`statusChip` / `statusText` 已有正确 up/down 映射，只依赖后端 status 字段正确）
- **数据库**：无改
- **文档**：`openspec/changes/v24-bugfix-ui-feedback-and-loopback` 中 §3.10 截图里的"当前状态"描述需更新（现在所有图都是错的）
- **发版**：v2.4.0 发版时合并本 change + 更新 RELEASE-NOTES

## QA 验证计划

1. **单测**：`pytest backend/tests/test_status_mapping.py -v` → 全 PASS（含 OperStatus 1/2/3 边界 + AdminStatus 1/2 + 组合）
2. **回归测试**：`pytest backend/tests/ --tb=no -q` → 不破现有 138+11 跳过测试
3. **真机 192.168.100.5 (Leaf-04)**：
   - `GET /api/devices/5/interfaces` GE1/0/1 (if_index=2) OperStatus=1, 1Gbps → status="up"（之前是 "down"）
   - `GET /api/devices/5/interfaces` GE1/0/2 (if_index=3) OperStatus=2, 无 ActualSpeed → status="down"（之前是 "up"）
4. **真机 192.168.100.100 (Spine-01)**：
   - `GET /api/devices/1/interfaces` GE1/0/1 (if_index=2) OperStatus=1, 1Gbps → status="up"（之前是 "down"）
   - `GET /api/devices/1/interfaces` GE1/0/5 (if_index=6) OperStatus=1, 1Gbps → status="up"（之前是 "down"）
5. **前端截图**（可选）：在 `Interfaces.vue` 选中设备 5 / 1，肉眼对照 status 列与 ActualSpeed（1Gbps=up）
6. **后端日志无 ERROR**：NETCONF get 4 次 success，record_log 0 异常
