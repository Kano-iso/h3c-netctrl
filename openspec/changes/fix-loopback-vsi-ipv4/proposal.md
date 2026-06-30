# fix-loopback-vsi-ipv4

## Why

v2.3 用户实测 192.168.100.5 报：
- if_index=5128 (LoopBack0) 改 L3 / 配 IP **失败**（_check_l3 判 L2 → 路由层 400）
- if_index=5131 (Vsi-interface2) 改 IP `192.168.2.254 → 192.168.2.253` **失败**：`An indexical column or data of some indexical columns is missed`
- if_index=5128 改 link-mode bridge **未拦截**（之前 link-mode 早期拒逻辑反了，LoopBack0 实际被放行）

> **重要说明（v2.3 实测版）**：v2.3.0 tag (`c6df368`) 打 tag 时**没有真机验证**（仅 mock 推断）。
> 本 change 补 v2.3.0 的真机修复。所有验证项下面均带"真机 192.168.100.5 实测"标记。

## What Changes

修复 3 个 bug：

### Bug A：`_check_l3_interface` 判 5128 / 5131 为 L2

- **症状**：`if_index=5128` / `5131` 实际是 L3 接口（LoopBack0 / Vsi-interface2），但 `_check_l3_interface` 判 L2 → 路由层 400 拒绝配 IP
- **根因（v2.3 真机探测 192.168.100.5）**：
  1. H3C V7 Ifmgr 对 Loopback / Vsi / Vlan-interface **不返回 `<Name>` 字段**（物理口才有 Eth1/0/1）
  2. `_parse_interface_response` 用 `<Description>` 兜底当 name，5128 错成 "Loopback_VTEP_ID"（实际是 description），不匹配 `LoopBack\d+` 正则
  3. 5131 连 Description 也没，兜底成 `If-5131`
  4. **`<PortLayer>` 字段 H3C V7 实际不返回**（v2.3 推断错误，已删除该规则）
- **修（真机验证版）**：
  1. 抽公共函数 `_enrich_interface_names(client, interfaces)`：对 name 不像物理口的接口，**额外**调 `get_interface_name_by_index` 拿真实 name，重算 layer
  2. `get_interfaces` 路由 + `_check_l3_interface` **都用**这个补查（避免 list 看是 L3 但 _check_l3 仍是 L2）
  3. `_looks_like_physical_port` 启发判断：name 是 `If-N` 兜底 OR 不匹配物理口正则 → 触发补查
  4. 补查后 5128 name=LoopBack0, 5131 name=Vsi-interface2 → `_detect_layer` 走 L3 正则 → L3 ✅

### Bug B：IPv4 clear XML key 用错

- **症状**：POST `/devices/5/interfaces/5131/ipv4-address` body `{"ip":"192.168.2.253","mask":"255.255.255.0"}` → 设备 `indexical column missed`
- **根因（v2.3 真机探测 192.168.100.5 #5131）**：
  - H3C V7 IPV4ADDRESS 真实 **key = `(IfIndex, Ipv4Address)`**（2 元组）
  - Ipv4Mask 和 AddressOrigin 是**非索引列**，不能出现在 delete 操作里
  - v2.2.2 / v2.3 之前用 `(IfIndex, AddressOrigin=1)` 错（缺 Ipv4Address）
  - v2.3 试 `(IfIndex, AddressOrigin=1)` + `(IfIndex, AddressOrigin=2)` 双发，还是错（缺 Ipv4Address）
  - 真机测试 3 种 key 形式的 delete：
    - `(IfIndex, AddressOrigin=1)` ❌ `indexical column missed`
    - `(IfIndex, Ipv4Address, Ipv4Mask, AddressOrigin)` 完整 ❌ `data cannot be assigned to non-index columns`
    - `(IfIndex, Ipv4Address)` ✅ 成功
- **修（真机验证版）**：
  1. 重写 `build_ipv4_address_clear_entries_xml(if_index, ip_list)`：接受路由层先 `parse_ipv4_addresses(client.get_config(IPV4ADDRESS))` 拿到的 IP 列表，逐条生成 `<Ipv4Address xc:operation="delete"><IfIndex>X</IfIndex><Ipv4Address>ip</Ipv4Address></Ipv4Address>`
  2. `set_interface_ipv4` 路由：先 `parse_ipv4_addresses` 拿 IP → 剥 CIDR → 调新函数生成 clear XML → set 新 IP
  3. `clear_interface_ipv4` 路由：同样"先查 + 逐条 delete"
  4. 旧函数 `build_ipv4_address_clear_xml(if_index)` 标记 NotImplementedError（v2.4 移除）

### Bug C：link-mode 早期拒逻辑反了

- **症状**：`PATCH /devices/5/interfaces/5128/link-mode {"mode":"bridge"}` 之前能放行（实际 LoopBack 不支持 link-mode）
- **根因（v2.3 真机探测 192.168.100.5 #5128）**：
  - 旧逻辑：`if nc_name and not L3_NAME_PATTERN.match(nc_name): ...`
  - `LoopBack0` 实际**匹配** `L3_NAME_PATTERN`（`^(Vlan-interface|LoopBack|Vsi-interface)\d+`）→ 外层 `not match` 假 → 跳过内层 check → 放行
- **修（真机验证版）**：重写为正向判断
  - 如果 name 匹配 L3 正则（LoopBack/Vsi/Vlan）→ 拒（"L3 类型不支持 link-mode"）
  - 如果 name 不像物理口（_looks_like_physical_port）→ 拒（"非物理口"）
  - 物理口（GE/TE 等）→ 放行（继续走二次确认/SSH CLI）

## Verification（v2.3 真机实测 192.168.100.5）

### mock 单元测试（11 case 全过）

```
tests/test_fix_loopback_vsi_ipv4.py
✓ test_build_ipv4_address_clear_entries_xml_with_ips
✓ test_build_ipv4_address_clear_entries_xml_multiple_ips
✓ test_build_ipv4_address_clear_entries_xml_empty
✓ test_build_ipv4_address_clear_xml_deprecated
✓ test_looks_like_physical_port
✓ test_parse_interface_response_loopback_uses_description_fallback
✓ test_parse_interface_response_vsi_interface
✓ test_detect_layer_with_name_loopback
✓ test_detect_layer_with_name_vsi
✓ test_detect_layer_with_ip_vsi_no_name
✓ test_detect_layer_loopback_no_name_no_ip
```

### 真机 192.168.100.5 实测（[x] = 真机跑过）

- [x] **1.** if_index=5128 (LoopBack0) — `_check_l3_interface` 判 L3
  - 修复前：False（name=Loopback_VTEP_ID 兜底错）
  - 修复后：True（补查后 name=LoopBack0，匹配 L3 正则）
- [x] **2.** if_index=5131 (Vsi-interface2) — `_check_l3_interface` 判 L3
  - 修复前：True（因为有 IP 兜底）
  - 修复后：True（补查后 name=Vsi-interface2 双重确认）
- [x] **3.** if_index=5131 — POST `/api/devices/5/interfaces/5131/ipv4-address` body `{"ip":"192.168.2.253","mask":"255.255.255.0"}`
  - 修复前：设备 `indexical column missed`（clear XML key 错）
  - 修复后：API success + 设备实际 `192.168.2.253/24`（用 `(IfIndex, Ipv4Address)` key）
- [x] **4.** if_index=5131 — 改回 `.254`（生产恢复）
  - 结果：设备 `192.168.2.254/24`（VXLAN 隧道恢复）
- [x] **5.** if_index=5128 (LoopBack0) — POST `/api/devices/5/interfaces/5128/ipv4-address` body `{"ip":"10.99.99.1","mask":"255.255.255.255"}`
  - 修复前：路由层 400 "不是 L3 接口"
  - 修复后：API success + 设备实际 `10.99.99.1/32`
- [x] **6.** if_index=5128 — DELETE IP
  - 结果：设备无 IP（恢复原状）
- [x] **7.** if_index=5128 — PATCH `/api/devices/5/interfaces/5128/link-mode` body `{"mode":"bridge","force":true}`
  - 修复前：放行（实际 LoopBack 不支持 link-mode）
  - 修复后：`{"success":false,"error":"接口 LoopBack0（if_index=5128）是 L3 类型，不支持 link-mode（H3C V7 仅物理接口支持）"}`
- [x] **8.** if_index=2 (Eth1/0/1) — PATCH link-mode `{"mode":"route","force":false}`
  - 结果：API 返回二次确认 `{"confirmed":false,"message":"即将切换接口 if_index=2 到 route 模式..."}`（护栏不拦物理口，二次确认走通）

### 真机回滚验证

- [x] 5131 最终状态：`192.168.2.254/24` ✓
- [x] 5128 最终状态：无 IP ✓

## Files Changed

- `backend/app/routers/interface.py`：
  - 抽公共函数 `_enrich_interface_names(client, interfaces)`（Bug A 修复）
  - 新增 `_looks_like_physical_port(name)` 启发
  - `get_interfaces` 路由：调 `_enrich_interface_names`（list 页面 layer 显示正确）
  - `_check_l3_interface`：调 `_enrich_interface_names`（配 IP 校验用对 layer）
  - `set_interface_ipv4` + `clear_interface_ipv4`：先 `parse_ipv4_addresses` 拿 IP → `build_ipv4_address_clear_entries_xml`（Bug B 修复）
  - `switch_link_mode`（link-mode 路由）：重写早期拒逻辑，LoopBack/Vsi/Vlan → 拒，非物理口 → 拒（Bug C 修复）
- `backend/app/utils/netconf_xml.py`：
  - 旧 `build_ipv4_address_clear_xml(if_index)` → NotImplementedError（v2.4 移除）
  - 新 `build_ipv4_address_clear_entries_xml(if_index, ip_list)` 接受 IP 列表，逐条 delete（Bug B 修复）
- `backend/tests/test_fix_loopback_vsi_ipv4.py`：11 个 mock 单元测试

## Lessons Learned

- **理论推断打 [x] 是禁止的**——v2.3.0 tag 时 proposal 写了 4 条"修复后"全是推断，**没有真机跑过**就 tag。用户实测发现两个都没生效。
- **H3C V7 IPV4ADDRESS key 是 2 元组**（不是 3 元组 / 4 元组）——必须真机探测
- **H3C V7 Ifmgr 不返回 L3 接口的 `<Name>`**——必须补查 `get_interface_name_by_index`
- **H3C V7 不返回 `<PortLayer>` 字段**——之前推测错，已删除该规则
- **H3C V7 非索引列不能出现在 delete 操作里**——必须先查完整 key 再 delete
- **Link-mode 护栏逻辑要正向判断**（L3 类型 / 非物理口都拒），不能用嵌套 `not`
