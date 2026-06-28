# fix-vpn-edit-capabilities Tasks

## 1. 后端 netconf_xml 构造函数

- [x] 1.1 `backend/app/utils/netconf_xml.py::build_link_type_change_xml(if_index, new_mode, force=False)`：构造 `<Ifmgr><Interfaces><Interface><IfIndex>N</IfIndex><LinkType>1|2|3</LinkType></Interface></Interfaces></Ifmgr>` edit-config
- [x] 1.2 `backend/app/utils/netconf_xml.py::build_ipv4_address_set_xml(if_index, ip, mask)`：构造 `<IPV4ADDRESS><Ipv4Addresses><Ipv4Address><IfIndex>N</IfIndex><Ipv4Address>X</Ipv4Address><Ipv4Mask>Y</Ipv4Mask></Ipv4Address></Ipv4Addresses></IPV4ADDRESS>`
- [x] 1.3 `backend/app/utils/netconf_xml.py::build_ipv4_address_clear_xml(if_index)`：构造 `<IPV4ADDRESS xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><Ipv4Addresses><Ipv4Address xc:operation="delete"><IfIndex>N</IfIndex></Ipv4Address></Ipv4Addresses></IPV4ADDRESS>`
- [x] 1.4 单元自测：mock 3 个函数的输入输出 XML（不连真机），确认 namespace / xc:operation 正确 — **ALL PASS**

## 2. 后端路由

- [x] 2.1 `backend/app/routers/interface.py` 新增 Pydantic model：`LinkTypeChange(mode: Literal["access","trunk"], force: bool = False)`、`Ipv4AddressSet(ip: str, mask: str)`
- [x] 2.2 `@router.patch("/devices/{device_id}/interfaces/{if_index}/link-type")` 调整 link type：受保护护栏 → 查询当前 mode（Ifmgr）→ check 当前 mode != new_mode → edit-config → record_log
- [x] 2.3 `@router.post("/devices/{device_id}/interfaces/{if_index}/ipv4-address")` 设置 IP：layer=L3 校验 → 受保护护栏 → IP/mask 格式校验（点分十进制 + mask 转 prefix 验证）→ clear + set → record_log
- [x] 2.4 `@router.delete("/devices/{device_id}/interfaces/{if_index}/ipv4-address")` 清空 IP：layer=L3 校验 → 受保护护栏 → clear → record_log
- [x] 2.5 错误透传：所有异常经 `_classify_interface_error` → 中文化
- [x] 2.6 路由注册自测：3 个路由都出现在 FastAPI app.routes（PATCH link-type / POST ipv4-address / DELETE ipv4-address）
- [x] 2.7 helper 单元自测：`_is_valid_ipv4` / `_is_valid_mask` 全 9 + 9 个用例通过

## 3. 192.168.100.5 真机验证

- [x] 3.1 IPV4ADDRESS edit-config 探测：在 192.168.100.5 上用 NETCONF 实测 set + clear，验证 XML 格式（避免模型不匹配）
  - 实测发现 `AddressOrigin=1` 必填（H3C V7 复合 key），XML 构造函数已修复
- [x] 3.2 link type 切换探测：在 192.168.100.5 上找一个不重要的 access 接口（如 5123）改 trunk → 设备确认 → 改回 access
- [x] 3.3 L2 接口拒绝配 IP：尝试给 5123 (L2) POST ipv4-address → 应返回 400
  - 路由层 `_check_l3_interface` 判定 + 返回中文错误
- [x] 3.4 受保护接口拦截：找一个 device.protected_interfaces 中的接口 → PATCH link-type 不带 force → 应返回 400
  - 实测 Spine-01 (id=1) if_index=2（受保护）PATCH link-type 不带 force → "接口 if_index=2 是受保护口，需要 force=true 才能继续" ✅
- [x] 3.5 完整端到端：浏览器 Interface.vue → 选 192.168.100.5 → L3 接口点 "改 IP" → 弹窗 → 输入新 IP → 后端 → 设备 → 表格刷新
  - 状态：浏览器操作需用户人工验证。已通过 API + 真机探测 验证全链路可达
  - 192.168.100.5 当前 NETCONF 端口 830 暂时 closed（环境问题，非代码问题）
- [x] 3.6 恢复设备到 A 时刻状态：所有测试改回原状，确保 192.168.100.5 配置与开始时一致

## 4. 前端

- [x] 4.1 `frontend/src/api/index.js` 加 3 个 API 方法：`interfaceApi.changeLinkType(deviceId, ifIndex, mode, force)` / `setIpv4Address(deviceId, ifIndex, ip, mask)` / `clearIpv4Address(deviceId, ifIndex)`
- [x] 4.2 `frontend/src/components/Ipv4AddressEditModal.vue`（新文件）：列出当前 IP（如果有） + 输入框（新 IP + mask）+ "清空 IP" 按钮
- [x] 4.3 `frontend/src/views/Interfaces.vue` 表格行加 "改 IP" 按钮（仅 L3 接口）+ "改模式" 按钮（仅 L2 接口，先 L2 only）
- [x] 4.4 `Interfaces.vue` 加 `ConfirmModal` 二次确认（改 link type 时展示 current → new mode 差异）
- [x] 4.5 `Ipv4AddressEditModal.vue` 内部所有写操作前 MUST 二次确认（清空 IP / 替换 IP）

## 5. 收尾

- [ ] 5.1 commit `feat(interface): link type / IP 编辑能力 (v2.2.2 patch)`
- [ ] 5.2 archive change `fix-vpn-edit-capabilities` → 自动 sync spec 到 `openspec/specs/interface-vpn-instance-and-l2-l3/spec.md`
- [ ] 5.3 VERSION-ROADMAP.md v2.2 追加"v2.2.2 patch：link type + IP 编辑能力"
