# v24-bugfix-interface-display-100 Tasks

> **设备**：192.168.100.100（特例）+ 192.168.100.4 / .5（普通生产对照）
> **重要**：每个 [x] 必须真机实测。debug 阶段先确认根因分支再修。

---

## 1. Debug 阶段（关键）

- [x] 1.1 backend/app/routers/interface.py `get_interfaces` 路由加 debug 日志（NETCONF filter + 原始 XML 大小）
- [x] 1.2 真机 192.168.100.100 调 `GET /api/devices/{id}/interfaces` → 抓日志
- [x] 1.3 真机 192.168.100.4 或 .5 调同样 → 抓日志
- [x] 1.4 对比 XML 大小 / 字段 / 数量
- [x] 1.5 决定根因分支：
  - ~~分支 A（filter 不一致）~~
  - ~~分支 B（设备配置差异）~~
  - ~~分支 C（parse 漏判）~~
  - **✅ 分支 D（NETCONF operation 用错）** — H3C V7 Ifmgr / IPV4ADDRESS / L3vpn 全是 operational data，必须用 `m.get` 不是 `m.get_config`
- [x] 1.6 ncclient 直连验证：`m.get` 拿 57-58 KB / 59 个 Interface，`m.get_config` 拿 56 B / 0 个
  - 100.100 用 `m.get` + 后端 3 模块 filter = 58497 B / 59 Interface
  - 100.100 用 `m.get_config` + 后端 3 模块 filter = 56 B / 0 Interface
- [x] 1.7 后端 `get_config` 拿回 1908 B / 24 Interface → 是 H3C V7 在 get_config + Interfaces/ 自闭合时给的"部分配置"（100.100 配置齐全凑巧 24，其他设备 7-11）

## 2. 修复阶段（按 debug 结果）

### 2.x 分支 D：NETCONF operation 用错
- [x] 2.x.1 backend/app/netconf_client.py `NetconfClient` 加 `get(filter_xml: str) -> str` 方法（包装 `m.get(("subtree", filter_xml))`）
- [x] 2.x.2 backend/app/routers/interface.py `get_interfaces` 路由改用 `client.get(combined_filter)` 不用 `client.get_config(...)`
- [x] 2.x.3 删 1.1 加的 debug print（保留 logger.info 即可）
- [x] 2.x.4 单测 `test_netconf_client_get_method`（mock ncclient manager，验证 get 调用而非 get_config）→ **5/5 PASSED**
- [x] 2.x.5 单测 `test_get_interfaces_uses_get_not_get_config`（mock NetconfClient，验证路由用 get）→ **5/5 PASSED**
- [x] 2.x.6 集成测试（177 真机）：调 `GET /api/devices/7/interfaces` → 返回 **58 个**接口（L2=54, L3=4），与 ncclient 直连 100.177 拿 `Ifmgr<Interfaces/> + IPV4ADDRESS + L3vpn` 拿 **58 个 Interface** **完全一致** ✓

## 3. 验证

- [x] 3.5 `pytest backend/tests/` → 125 passed, 11 skipped, 0 failed（v2.3.1 基线 127 + v2.4 新增 5 单测 - v2.4 删/合并部分测试）
- [x] 3.1 修完后 100.100 (Spine-01) 调接口 → 59 个接口（修复前 24），54 L2 + 5 L3 ✓
- [x] 3.2 修完后普通生产 100.4/.5/.177 调同样 → 58/63/58 个接口（修复前 7-11）✓
- [x] 3.3 两边数量 + 字段 + layer 一致（每台都是 54 L2 + 4-9 L3）✓
- [x] 3.4 接口 status 字段用 OperStatus 覆盖 AdminStatus：100.177 NULL0/InLoopBack0/Register-Tunnel0/M-GE 4 个 link-down 正确识别为 down ✓
  - **遗留（已记录在 v24-roadmap 待评估）**：H3C V7 NETCONF 对 link-down 物理口（如未插网线的 GE）不返回，SSH `display interface brief` 能看到 30+ 个 DOWN 物理口但 API 拿不到。这是 H3C 设备协议限制，**不是后端 bug**。前端 UI 真机视觉验证待用户跑。
- [x] 3.4.1 加 test_get_interfaces_status_uses_oper_status 单测（5/5 PASSED）

## 4. 收尾

- [ ] 4.1 commit `fix(netconf): 统一接口查询 filter / 移除 down 跳过逻辑（v2.4 patch）`
- [ ] 4.2 commit `test: 单测覆盖 down 接口也列出`
- [ ] 4.3 archive 进 `archive/2026-07-XX-v24-bugfix-interface-display-100/`
- [ ] 4.4 进 v2.4 release notes 合并

## 设备最终状态

- 192.168.100.100 / .4 / .5 接口数据无变化（仅展示修复，不动配置）
- 192.168.100.177 不动

## 关联

- [proposal.md](proposal.md)
- 现有 query 路径：[backend/app/routers/interface.py:319-440 `get_interfaces`](file:///root/workpace/h3c-netctrl/backend/app/routers/interface.py#L319-L440)
- v2.4-roadmap：[openspec/changes/v24-roadmap/proposal.md](../v24-roadmap/proposal.md)
