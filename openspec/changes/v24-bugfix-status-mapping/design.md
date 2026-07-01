## Context

`_parse_interface_response` 在 Pass 1 (Ifmgr) 处理 XML 元素时，把 `AdminStatus` 和 `OperStatus` 字段分别映射成 "up"/"down" 字符串。原作者意图是：

- `admin_status` = 是否被 admin shutdown（1=up / 2=down）
- `oper_status` = 链路层实际状态（1=up / 2=down）
- `status` = 优先以 oper_status 为准（链路层才是用户真正关心的"通没通"），admin 兜底

这是**正确的设计思路**，但 commit `c012051`（v2.4-bugfix-interface-display-100 change）把 OperStatus 的编码写反了，注释也跟着错，导致整个 status 列反。

**为什么 v2.3.0 / v2.3.1 没问题？** 那两个版本 `OperStatus` 字段根本不存在（commit `c012051` 才加），只处理 `AdminStatus` 字段。AdminStatus 的 `==1 → up` 是对的，所以"admin 没 shutdown 的口全显 up"是预期行为，碰巧也是正确链路状态（admin 决定通断）。

**为什么 v2.4-bugfix-interface-display-100 引入反的？** 看 git blame：commit `c012051` 是改 netconf data namespace + 引入 OperStatus 的合并提交，作者可能误以为 OperStatus 编码与 AdminStatus 相反（H3C 旧文档有这种错记），没做真机对照就把代码写反了。

## Goals / Non-Goals

**Goals:**
- 修对 OperStatus 编码（1=UP 2=DOWN）
- 加 1 个新单测文件覆盖编码边界（1/2/3）+ AdminStatus 边界（1/2）+ 组合
- 真机 4 个 1Gbps UP 链路口 + 1 个空载 DOWN 口对照金标准回归
- 修正 spec 里 status 字段的明确语义

**Non-Goals:**
- 不动 admin_status 字段（保持 "是否被 shutdown" 语义）
- 不动 statusChip / statusText 前端逻辑（它本来就 up→chip-good / down→chip-bad，依赖后端字段正确即可）
- 不重写 netconf_xml 模块
- 不动 OperationLog（status 字段不参与 record_log）

## Decisions

### 决策 1：只改 1 行 + 注释，admin_status 字段保留作辅助

**选择**：把 `iface["oper_status"] = "up" if child.text == "2" else "down"` 改成 `iface["up" if child.text == "1"] else "down"`，上方注释改为：

```python
# H3C V7 / IF-MIB (RFC 2863): AdminStatus 和 OperStatus 都是 1=UP 2=DOWN (3=testing 等)
# OperStatus 反映链路层实际状态（用户真正关心的"通没通"），AdminStatus 反映 admin 意图（是否 shutdown）
# RFC: https://www.rfc-editor.org/rfc/rfc2863 (ifAdminStatus / ifOperStatus)
```

**理由**：
- 物理上 OperStatus 跟 AdminStatus 编码完全一致（IF-MIB 标准），不需要特殊处理
- 注释引用 RFC 2863，下次改动有据可查
- 1 行代码改动 + 2 行注释，最小化影响面

**备选方案**：
- 用 enum/dict 映射（OPER_STATUS_MAP = {1: "up", 2: "down", 3: "testing"}）—— 增加代码量，OperStatus 3 在 H3C V7 实际不出现，过度设计
- 把 admin_status 和 oper_status 合并成一个 `status` 字段 —— 破坏现有 API 兼容性，前端 `vpn_instance` 链路可能用到 admin_status 字段（需查）

### 决策 2：单测边界覆盖 1/2/3（OperStatus）和 1/2（AdminStatus）

**选择**：测试矩阵：

| AdminStatus | OperStatus | 期望 admin_status | 期望 oper_status | 期望 status |
|---|---|---|---|---|
| 1 | 1 | up | up | up |
| 1 | 2 | up | down | down |
| 2 | 1 | down | up | up |
| 2 | 2 | down | down | down |
| 1 | (缺) | up | (缺) | up |
| (缺) | 1 | (缺) | up | up |
| (缺) | 2 | (缺) | down | down |
| 1 | 3 | up | down | down（3=testing 兜底 down） |

**理由**：
- 覆盖 v2.4-bugfix-interface-display-100 当年没测的边界（v2.3.0 / v2.3.1 根本没这字段）
- 矩阵 8 个 case 足够覆盖组合，少而全
- 3 兜底 down 是保守选择（实测 H3C V7 不返 3，但 RFC 2863 定义了 3=testing, 4=unknown, 5=dormant, 6=notPresent, 7=lowerLayerDown，5/6/7 都接近 "down"）

**备选方案**：
- parametrize 8 case 写一个测试函数 —— 实际更紧凑，但出错时只显示 1 个 case 不够定位
- mock NetconfClient 走完整 _parse_interface_response 链路 —— 与 qa-backend 框架（conftest.py + mock_netconf fixture）对齐，最实用

### 决策 3：真机金标准对照 5 个口

**选择**：用 NetconfClient 直拉 `<Ifmgr>` 看原始 XML，提取 `OperStatus` / `ActualSpeed` 作为金标准。然后调 `GET /api/devices/{id}/interfaces` 看后端 status 字段，断言 1:1 一致。

5 个对照口（从 v2.4-bugfix-interface-display-100 修复后状态分布）：
- 192.168.100.5 Leaf-04 GE1/0/1 (if_index=2): OperStatus=1, 1Gbps → status="up"（修复前是 "down"）
- 192.168.100.5 Leaf-04 GE1/0/2 (if_index=3): OperStatus=2, 无 ActualSpeed → status="down"（修复前是 "up"）
- 192.168.100.100 Spine-01 GE1/0/1 (if_index=2): OperStatus=1, 1Gbps → status="up"
- 192.168.100.100 Spine-01 GE1/0/5 (if_index=6): OperStatus=1, 1Gbps → status="up"

**理由**：
- 4 个 UP 链路 + 1 个 DOWN，刚好覆盖 up/down 两种状态
- 跨设备（Leaf + Spine）确保编码问题不是某台设备特例
- 用 `NetconfClient` 直拉是金标准（不经 `_parse_interface_response` 处理），不会被 bug 影响

**备选方案**：
- SSH 22 跑 `display interface brief` 抓 OperStatus —— 设备 CLI 输出格式因版本而异，解析容易踩坑
- 只测 1 个设备 —— 跨设备覆盖更稳

### 决策 4：spec 修改走 delta 文件，不动原 spec

**选择**：在 `openspec/changes/v24-bugfix-status-mapping/specs/interface-vpn-instance-and-l2-l3/spec.md` 加一个 delta 文件，描述 ADDED Requirements（status 编码正确性 + 金标准对照 scenario）。

**理由**：
- OpenSpec delta 模式：原 spec 不动，change 内追加 ADDED Requirements，archive 时合并
- 现有 spec 里 "现有字段（...status...）行为不变" 太宽泛，没明确编码，delta 补充明确语义
- 单一 spec 来源（v2.4-bugfix-ui-feedback-and-loopback 也用 interface-vpn-instance-and-l2-l3），不引入新的 spec 文件

**备选方案**：
- 改原 spec 直接覆盖 "行为不变" —— 违反 OpenSpec delta 模式，且 archive 时无追溯记录
- 新建 spec `interface-operational-status` —— 单一字段级别的 spec 太细，未来 link-mode / 备份等也可能用 oper_status，分散

## Risks / Trade-offs

**[风险 1] 修复后，老截图 / 老文档里的 status 描述都错了** → 缓解：v24-bugfix-ui-feedback-and-loopback §3.10 截图是错的（"当前状态" 列），需要在 commit message 里说明，等真机重测时刷新

**[风险 2] 单测 mock `_parse_interface_response` 需要构造 OperStatus/AdminStatus XML，与 v2.4-bugfix-interface-display-100 当年缺这块测试是同一原因** → 缓解：直接 mock NetconfClient.get 返回的 XML 字符串，覆盖所有边界

**[风险 3] 修好之后如果 AdminStatus 也存在 bug（如 H3C V7 某些设备 admin 编码不同），会把链路层 status 弄错** → 缓解：本次只改 oper_status 映射，admin_status 维持 v2.3.0/v2.3.1 行为（`==1 → up`），保持 admin 字段语义不变

**[风险 4] 真机 192.168.100.5 / .100 在测试期间网络抖动导致 OperStatus 临时变 down** → 缓解：连续 2 次拉取 OperStatus 与 ActualSpeed，确保 2 次一致再断言

## Migration Plan

无需数据迁移，无需版本兼容：
- API 字段（status / admin_status / oper_status）类型与值域不变（"up" / "down" / "unknown"）
- 前端 statusChip / statusText 已有 up→good / down→bad 正确逻辑，依赖后端字段正确即可
- 部署：后端 reload 即可，**无需清缓存或迁移数据**
- 回滚：git revert + 后端 reload，1 分钟内回退到当前 bug 状态

## Open Questions

无。修复方案已与用户确认（v2.4.0 收尾合并，新开 change v24-bugfix-status-mapping）。
