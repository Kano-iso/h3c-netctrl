# fix-loopback-vsi-ipv4 Tasks

> **重要**：所有 [x] = 真机 192.168.100.5 实测通过 / 单元测试 11 case 通过
> v2.3.0 tag (`c6df368`) 时**没有**真机验证（仅 mock 推断），用户实测发现 2 个 bug
> 都没修好。本 change 补 v2.3.0 的真机修复。

---

## 阶段 1：探针（无 commit）

- [x] 1.1 真机拉 192.168.100.5 Ifmgr 看 5128 / 5131 XML 实际数据
  - 结果：5128 = `<IfIndex>5128</IfIndex><Description>Loopback_VTEP_ID</Description>`，**无 `<Name>`，无 `<PortLayer>`**
  - 结果：5131 = `<IfIndex>5131</IfIndex><MAC>00-02-00-02-00-02</MAC>`，**无 `<Name>`，无 `<Description>`，无 `<PortLayer>`**
- [x] 1.2 真机拉 192.168.100.5 IPV4ADDRESS 看 5131 IP 完整字段
  - 结果：`<Ipv4Address><IfIndex>5131</IfIndex><Ipv4Address>192.168.2.254</Ipv4Address><Ipv4Mask>255.255.255.0</Ipv4Mask><AddressOrigin>1</AddressOrigin></Ipv4Address>`
  - **AddressOrigin=1**（不是 DHCP auto = 2）
- [x] 1.3 真机探测 3 种 key 形式的 delete
  - 简化 key `(IfIndex, AddressOrigin=1)` ❌ `An indexical column or data of some indexical columns is missed`
  - 完整 key `(IfIndex, Ipv4Address, Ipv4Mask, AddressOrigin)` ❌ `When the delete or remove operation is issued, data cannot be assigned to non-index columns`
  - **简化 key `(IfIndex, Ipv4Address)`** ✅ delete 成功
- [x] 1.4 跑回滚脚本一次（5131=.254, 5128 无 IP）作为基线状态

## 阶段 2：修代码

- [x] 2.1 修 Bug A（_check_l3 判错 L2）：
  - 抽 `_enrich_interface_names(client, interfaces)` 公共函数
  - 加 `_looks_like_physical_port(name)` 启发
  - `get_interfaces` 路由 + `_check_l3_interface` **都调** `_enrich_interface_names`
  - 后端 reload 后验证：`_check_l3_interface(5128) = True` ✓ / `(5131) = True` ✓
- [x] 2.2 修 Bug B（IPv4 clear XML key 错）：
  - 旧 `build_ipv4_address_clear_xml(if_index)` → NotImplementedError
  - 新 `build_ipv4_address_clear_entries_xml(if_index, ip_list)` 接受 IP 列表
  - `set_interface_ipv4` + `clear_interface_ipv4` 路由：先 `parse_ipv4_addresses` 拿 IP → 调新函数
- [x] 2.3 修 Bug C（link-mode 早期拒逻辑反了）：
  - 重写 `switch_link_mode` 早期拒逻辑
  - LoopBack / Vsi / Vlan（匹配 L3_NAME_PATTERN）→ 拒
  - 非物理口（_looks_like_physical_port=False）→ 拒
  - 物理口（GE/TE 等）→ 放行（二次确认）

## 阶段 3：单元测试

- [x] 3.1 写 `tests/test_fix_loopback_vsi_ipv4.py` 11 case
  - `test_build_ipv4_address_clear_entries_xml_with_ips` ✓
  - `test_build_ipv4_address_clear_entries_xml_multiple_ips` ✓
  - `test_build_ipv4_address_clear_entries_xml_empty` ✓
  - `test_build_ipv4_address_clear_xml_deprecated` ✓
  - `test_looks_like_physical_port` ✓
  - `test_parse_interface_response_loopback_uses_description_fallback` ✓
  - `test_parse_interface_response_vsi_interface` ✓
  - `test_detect_layer_with_name_loopback` ✓
  - `test_detect_layer_with_name_vsi` ✓
  - `test_detect_layer_with_ip_vsi_no_name` ✓
  - `test_detect_layer_loopback_no_name_no_ip` ✓
- [x] 3.2 `pytest tests/test_fix_loopback_vsi_ipv4.py -v` → **11 passed**

## 阶段 4：真机端到端验证（192.168.100.5）

- [x] 4.1 **5131 改 IP `.254 → .253`**（用户的核心场景）
  - `POST /api/devices/5/interfaces/5131/ipv4-address {"ip":"192.168.2.253","mask":"255.255.255.0"}`
  - API 返回 `{"success":true,"data":{"if_index":5131,"ip":"192.168.2.253","mask":"255.255.255.0"}}`
  - 设备实际 IP = `192.168.2.253/24` ✓
- [x] 4.2 **5131 改回 `.254`**（生产恢复）
  - 用回滚脚本（跑新 `build_ipv4_address_clear_entries_xml`）
  - 设备实际 IP = `192.168.2.254/24` ✓
- [x] 4.3 **5128 配 IP `10.99.99.1/32`**（用户的"改不过来 L3"核心场景）
  - `POST /api/devices/5/interfaces/5128/ipv4-address {"ip":"10.99.99.1","mask":"255.255.255.255"}`
  - API 返回 `{"success":true,"data":{"if_index":5128,"ip":"10.99.99.1","mask":"255.255.255.255"}}`
  - 设备实际 IP = `10.99.99.1/32` ✓
- [x] 4.4 **5128 删 IP**（恢复原状）
  - `DELETE /api/devices/5/interfaces/5128/ipv4-address`
  - API 返回 `{"success":true,"data":{"if_index":5128}}`
  - 设备实际 = 无 IP ✓
- [x] 4.5 **5128 改 link-mode bridge**（验证护栏正确拒）
  - `PATCH /api/devices/5/interfaces/5128/link-mode {"mode":"bridge","force":true}`
  - API 返回 `{"success":false,"error":"接口 LoopBack0（if_index=5128）是 L3 类型，不支持 link-mode（H3C V7 仅物理接口支持）"}` ✓
- [x] 4.6 **物理口 if_index=2 改 link-mode route**（验证护栏不误拦物理口）
  - `PATCH /api/devices/5/interfaces/2/link-mode {"mode":"route","force":false}`
  - API 返回 `{"success":true,"data":{"if_index":2,"mode":"route","confirmed":false,"message":"即将切换接口 if_index=2 到 route 模式..."}}` ✓
  - **不真改**（只验证护栏不误拦，避免生产接口重启）
- [x] 4.7 **最终回滚脚本**（保险）
  - 5131 = `192.168.2.254/24` ✓
  - 5128 = 无 IP ✓

## 阶段 5：清理 + 文档

- [x] 5.1 删临时调试脚本（_verify_*.py / _rollback_*.py / _probe_*.py / _inspect_*.py）
- [x] 5.2 proposal.md 加"v2.3 真机实测"标记、删 PortLayer 错误推测、修正 IPv4 key 描述
- [x] 5.3 tasks.md（本文档）所有 [x] 都标"真机 192.168.100.5 实测"
- [ ] 5.4 git add + commit（**待用户确认推不推**）
- [ ] 5.5 git push（**待用户确认**）

---

## 设备最终状态（验证结束）

| 接口 | if_index | 名称 | IP | Layer | 状态 |
|---|---|---|---|---|---|
| LoopBack0 | 5128 | LoopBack0 | 无 | L3 | 恢复原状 ✓ |
| Vsi-interface2 | 5131 | Vsi-interface2 | 192.168.2.254/24 | L3 | 恢复原状 ✓ |

## 下一步

- commit 时分 3 个（按 Bug A / B / C 拆），不攒一起
- 推不推给用户决定（按个人开发规则"需要确认后再推"）
