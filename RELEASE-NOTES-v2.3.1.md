# RELEASE-NOTES-v2.3.1

**版本**: v2.3.1
**日期**: 2026-07-01
**主题**: v2.3.0 真机回归修复 patch（个人轻量级补丁）
**前序**: v2.3.0 (`c6df368`, 2026-06-29)

---

## 1. 主题

v2.3.0 tag 时**没有真机验证**（仅 mock 推断），发版后用户实测发现 2 个核心 bug：
- Loopback / Vsi 接口被错判 L2，IP 配置改不成功
- 备份轮转"保留 5 份"实际保留 7 份

v2.3.1 在 **192.168.100.5**（生产 Leaf-04）和 **192.168.100.177**（用户提供的测试机）上完成真机端到端验证。

**不是新功能大版本**——仅修 bug + 测试加固，沿用 v2.3.0 路线。

## 2. 包含的 Changes（3 个 patch）

| Change | 状态 | commit | 备注 |
|---|---|---|---|
| `fix-loopback-vsi-ipv4` | ✅ 闭环 | `b1e7d08` + `96a0bc8` + `76a96d5` | 3 bug + 11 单测 + 192.168.100.5 真机端到端 |
| `fix-rotation-total-keep` | ✅ 闭环 | `dfd3166` + `8262086` | BACKUP_KEEP 语义改总份数含锁定 + 7 单测 + 177 真机 |
| `v2.3-roadmap` | ✅ 闭环 | `c4d070d` 等 7 个 | 聚合 0.1-0.10 + v2.3.1 patch 8.1-8.8 全闭环 + archive |

## 3. 修复的 2 个核心 bug

### Bug A: `_check_l3` 错判 Loopback / Vsi 为 L2

- **现象**：192.168.100.5 上
  - if_index=5128 (LoopBack0) → 后端判 L2 → API 拒配 IP："不是 L3 接口"
  - if_index=5131 (Vsi-interface2) → 同上
- **根因**：H3C V7 Ifmgr 返回 Loopback / Vsi 接口时**不带 `<Name>` 字段**，只带 `<Description>`。原 `_check_l3_interface` 拿不到 name，无法用 `L3_NAME_PATTERN` 匹配
- **修**：
  - 抽 `_enrich_interface_names(client, interfaces)` 公共函数：循环对缺 name 的接口再发一次 `get-interface-by-index` 查真实 name
  - 加 `_looks_like_physical_port(name)` 启发（GE/XGE/...）
  - `get_interfaces` 路由 + `_check_l3_interface` **都调** `_enrich_interface_names`
- **验证**：192.168.100.5 后端 reload → `_check_l3_interface(5128) = True` / `(5131) = True` ✓

### Bug B: H3C V7 IPV4ADDRESS clear XML key 用错

- **现象**：192.168.100.5 上 `DELETE /api/devices/5/interfaces/5131/ipv4-address` → 报 `An indexical column or data of some indexical columns is missed`
- **根因**：H3C V7 `IPV4ADDRESS` 表的 index column 是 `(IfIndex, Ipv4Address)`（**不是** AddressOrigin），但旧 `build_ipv4_address_clear_xml(if_index)` 缺 `Ipv4Address` 列
- **真机探测 3 种 key**：
  - 简化 key `(IfIndex, AddressOrigin=1)` → ❌ `An indexical column or data of some indexical columns is missed`
  - 完整 key `(IfIndex, Ipv4Address, Ipv4Mask, AddressOrigin)` → ❌ `When the delete or remove operation is issued, data cannot be assigned to non-index columns`
  - **简化 key `(IfIndex, Ipv4Address)`** → ✅ delete 成功
- **修**：
  - 旧 `build_ipv4_address_clear_xml(if_index)` → NotImplementedError
  - 新 `build_ipv4_address_clear_entries_xml(if_index, ip_list)` 接受 IP 列表
  - `set_interface_ipv4` + `clear_interface_ipv4` 路由：先 `parse_ipv4_addresses` 拿 IP → 调新函数
- **验证**：5131 `.254 → .253 → .254` 端到端 PASS

### Bug C: link-mode 早期拒逻辑反了（Bug A 的连锁 bug）

- **现象**：修完 Bug A 后，link-mode 改不过去 LoopBack0
- **根因**：旧护栏 `if 物理口: 拒` 逻辑写反，LoopBack0（name=LoopBack0）走完启发后**被认为不是物理口**但代码放行了
- **修**：重写 `switch_link_mode` 早期拒逻辑
  - LoopBack / Vsi / Vlan（匹配 L3_NAME_PATTERN）→ 拒
  - 非物理口（`_looks_like_physical_port=False`）→ 拒
  - 物理口（GE/TE 等）→ 放行（二次确认）
- **验证**：192.168.100.5 上 `PATCH /api/devices/5/interfaces/5128/link-mode {"mode":"bridge","force":true}` → 返回 `接口 LoopBack0（if_index=5128）是 L3 类型，不支持 link-mode` ✓

### Bug D: BACKUP_KEEP 实际保留 7 份（语义错误）

- **现象**：192.168.100.4 上 BACKUP_KEEP=5，实际 2 锁定 + 5 非锁定 = **7 份** 备份
- **根因**：v2.2 `rotate()` 把 `keep` 解释为"非锁定保留数"，锁定数不计入。直觉上"保留 5 份"应该是"总份数 5 份"
- **修**：
  - `rotate()` 改逻辑：查所有备份（不 filter locked）→ 分离 locked / unlocked → 锁定数 ≥ keep 不删（用户锁太多属预期）→ 否则 to_delete = 总 - keep，从最旧非锁定删
  - `BACKUP_KEEP` 注释 + `.env.example` 注释改"每设备保留总份数（含锁定）"
- **验证**：
  - 单元 7 case 全 PASS（"5+2 → 5"、"3+0 → 3 不删"、"5+2 → 7 锁定优先"、"0+7 → 5" 等边界）
  - 192.168.100.177 真机 6 份 → 验证留 5 份 PASS

## 4. 集成测试加固（v2.3.1 patch 8.3-8.8）

### 8.3 集成测试选口加固
- 抽 `_filter_safe_ifaces` 公共函数，三重防护：
  1. `if_index ∈ [32, 4095)` — 排除 mgmt (1) + GE1/0/1~30 接入口 (2-31) + LoopBack/Vsi/Vlan 逻辑口 (≥4096)
  2. `name` 包含 `GigabitEthernet/Ten-GigabitEthernet/...` 等物理口关键字
  3. 物理口启发 `_looks_like_physical_port`
- 应用到 4 个集成测试，避免误改用户线上配置

### 8.4 集成测试稳定性
- `vpn_name` 加 `id+ts` 后缀（如 `test_vpn_bind_1_43956`），避免重跑冲突
- `_check_netconf_reachable` 加 3 次重试 + 5s 间隔，扛过 177 抖动（实测 33% 丢包）

### 8.5 + 8.8 真机残留清理
- 177 真机累计清 7 个 `test_vpn_bind_1_XXXXX` 残留（4 + 3）
- 原因：旧 test 失败时 try/except 吞错，无 try/finally 兜底

### 8.6 + 8.7 集成测试代码修复
- `test_link_mode_switch_real_device` 硬编码 `if_index=2`（GE1/0/1）→ **真机事故**：切 bridge→route 清掉该口所有 L2 配置（VLAN/trunk/子接口），切回 bridge 不恢复，导致用户接入端口 IP/VPN 一起被摧毁
  - 改：查接口 + 过滤 `[32, 4095)` 物理 L2 口
- `test_create_vpn_instance` / `test_delete_vpn_instance` / `test_bind_unbind_vpn` 加 `vpn_created` / `vpn_bound` flag + try/finally 兜底，避免 VPN 残留

## 5. 端到端实测状态

| 测试类型 | 数量 | 状态 |
|---|---|---|
| 单元（mock） | 118 | ✅（v2.3.0 105 + v2.3.1 11 fix-loopback + 7 fix-rotation + ...）|
| 集成（真机 192.168.100.5 + 192.168.100.177） | 11 | ✅ 全部 PASS（127 passed, 4 skipped, 0 failed in `pytest --integration`）|
| 前端组件（vitest） | 0 | ⏸️ BLOCKED by EACCES node_modules（v2.3.0 沿用）|

## 6. 关键能力清单（用户视角）

| 能力 | v2.3.0 | v2.3.1 |
|---|---|---|
| Loopback / Vsi 接口配 IP | ❌ 错判 L2 | ✅ 真机端到端 |
| 备份轮转"保留 5 份" | ❌ 实际 7 份 | ✅ 真机 6→5 验证 |
| 集成测试选口 | ❌ 硬编码 if_index=2 摧毁生产口 | ✅ 动态选 + 三重防护 |
| 集成测试清理 | ❌ 失败吞错，177 残留 7 个 VPN | ✅ try/finally + flag 兜底 |
| 集成测试稳定性 | ❌ 单次 connect，扛不住 177 抖动 | ✅ 3 次重试扛抖动 |

## 7. 已知问题 / 限制

| ID | 问题 | 影响 | 解决方案 |
|---|---|---|---|
| #001 | vitest EACCES | 前端组件测试无法运行 | `sudo chown -R $(whoami) node_modules`（v2.3.0 沿用）|
| #002 | ops-toolkit build 慢 | 第一次 build 5+ min | 后续缓存可秒级（v2.3.0 沿用）|
| #003 | 容器解耦未实施 | monolith 资源争抢 | **v3.0 实施**（拆 3 容器：SDN/数据/监控）|
| #004 | 集成测试偶发需要真机 | CI 跑不到 177 集成 | `--integration` 标志显式开启，本地/CI 跑单元 |

## 8. 升级 / 部署注意

- **从 v2.3.0 升级**：无 schema 变更，无破坏性 API 变更
- **设备兼容性**：仅 H3C V7 验证通过（NETCONF + SSH CLI）
- **测试机**：192.168.100.177 凭据 `python / Admin123!@#` 已入库
- **数据库**：SQLite 不变（v3.0 才迁 Postgres）
- **集成测试跑法**：`docker compose --profile qa run qa-backend -- --integration`（默认 skip 真机）

## 9. 关键 commit 序列

```
7a146ac docs(fix-rotation-total-keep): 任务勾选 + 收尾阶段占位
f8b63cb docs(v2.3-roadmap): 8.6/8.7/8.8 任务追踪（test 漏改 + 真机残留再清）
692c14e fix(test): VPN 集成测试 try/finally + vpn_created/vpn_bound 标记
45d199f fix(test): test_link_mode_switch_real_device 改查接口 + 动态选 [32,4095) 物理 L2 口
6801b85 fix(integration): vpn_name 加 ts 后缀 + _check_netconf_reachable 加重试
d8bb1bd fix(integration): _filter_safe_ifaces 排除 Vsi/LoopBack/Vlan 逻辑口
5ea044a fix(integration): 集成测试选口跳过 if_index<32（避开 mgmt + 低 GE 接入口）
e2cf275 test(backend): 集成测试默认 target 改 192.168.100.177 测试用交换机
8262086 test(backend): 修 conftest mock + 3 个 rotation 测试适配 v2.3.1 新 BACKUP_KEEP 语义
c03ee54 chore(v2.3-roadmap): 用户决策——asset 容器拆推 v3.0 + 删 interface-linked-config
dfd3166 fix(backup-rotate): 改 BACKUP_KEEP 语义为总份数含锁定
76a96d5 test+docs(fix-loopback-vsi-ipv4): 11 mock 单测 + OpenSpec proposal/tasks
96a0bc8 fix(interface): 修 _check_l3 错判 L2 + link-mode 护栏逻辑反
b1e7d08 fix(netconf-xml): 修 H3C V7 IPV4ADDRESS clear key 用错
c4d070d docs(openspec): archive 3 个 v2.3.1 patch change（2026-07-01）
```

## 10. 关联

- [RELEASE-NOTES-v2.3.0.md](RELEASE-NOTES-v2.3.0.md)
- [VERSION-ROADMAP.md](VERSION-ROADMAP.md)
- [docs/QA-GUIDE.md](docs/QA-GUIDE.md)
- [docs/CONTAINER-DECOUPLING.md](docs/CONTAINER-DECOUPLING.md)
- [openspec/specs/](../specs/)
- [openspec/changes/archive/2026-07-01-fix-loopback-vsi-ipv4/](../changes/archive/2026-07-01-fix-loopback-vsi-ipv4/)
- [openspec/changes/archive/2026-07-01-fix-rotation-total-keep/](../changes/archive/2026-07-01-fix-rotation-total-keep/)
- [openspec/changes/archive/2026-07-01-v2.3-roadmap/](../changes/archive/2026-07-01-v2.3-roadmap/)
