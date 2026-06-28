## 1. 后端 XML 构造器

- [x] 1.1 `backend/app/utils/netconf_xml.py` 新建：`build_vpn_instance_create_xml` / `build_vpn_instance_delete_xml` / `build_interface_bind_vpn_xml` / `build_interface_unbind_vpn_xml` / `build_vpn_instance_filter_xml` / `build_interface_extended_filter_xml` + `parse_vpn_instances` 解析辅助
- [x] 1.2 验证：6 个 XML 构造器输出全部能被 ET 重新解析，parse_vpn_instances 正确解析 mock 响应

## 2. 后端 L2/L3 解析扩展

- [x] 2.1 `backend/app/routers/interface.py::_parse_interface_response` 增强：解析 `Ipv4Address` / `IpBindVrfInstance` / `Vlan-interface` 命名
- [x] 2.2 `GET /api/devices/{id}/interfaces` 返回值增加 `ip_addresses` 和 `vpn_instance` 字段
- [x] 2.3 兼容老字段：`mode` / `pvid` / `allowed_vlans` 行为不变

## 3. 后端 VPN instance 端点

- [x] 3.1 `GET /api/devices/{id}/vpn-instances`：列设备所有 VPN instance（NETCONF get-config）
- [x] 3.2 `POST /api/devices/{id}/vpn-instances` body `{"name": "X", "rd": "auto"}`：创建 VPN instance，名称字符校验
- [x] 3.3 `DELETE /api/devices/{id}/vpn-instances/{name}`：删除前预校验绑定数
- [x] 3.4 每个端点写 `record_log`（vpn_instance_create / delete）

## 4. 后端接口绑 VPN instance 端点

- [x] 4.1 `POST /api/devices/{id}/interfaces/{if_index}/vpn-instance` body `{"name": "MGMT"}`：接口绑 VPN instance
- [x] 4.2 `DELETE /api/devices/{id}/interfaces/{if_index}/vpn-instance`：解绑（预校验已绑定）
- [x] 4.3 受保护接口（`protected_interfaces` JSON 列表中）禁止绑 VPN
- [x] 4.4 接口与 VPN instance 同设备（device_id 校验）

## 5. 设备能力探测（延后到 v2.3 follow-up）

> **决策（2026-06-28）**：本 change **不**实现能力探测与缓存。
>
> 理由：H3C V7 支持 NETCONF VPN 概率高、UX 可接受、SSH fallback 是 v3.0 的事。

- [ ] 5.1 ~~第一次 VPN instance 端点调用时探测 NETCONF 支持~~ → v2.3
- [ ] 5.2 ~~缓存到 capability_cache.py~~ → v2.3
- [ ] 5.3 ~~NETCONF 失败降级走 SSH CLI~~ → v2.3
- [ ] 5.4 ~~UI 提示降级状态~~ → v2.3

## 6. 前端 Interface.vue 表格列扩展

- [x] 6.1 表格加 `layer` 列：badge "二层"（灰） / "三层"（蓝）
- [x] 6.2 表格加 `ip` 列（合并到 IP/VPN 列）：L3 时显示 IP 地址列表
- [x] 6.3 表格加 `vpn_instance` 列（合并到 IP/VPN 列）：显示绑定名
- [x] 6.4 表格加 `vpn_action` 列：操作按钮（"绑 VPN" / "解绑 VPN" / "+ VPN"）

## 7. 前端 Modal 组件

- [x] 7.1 `frontend/src/components/VpnInstanceBindModal.vue` 新建：
  - 模式 'create'：填名 + 创建 + 自动绑定
  - 模式 'bind'：选已有 VPN instance + 绑定
  - 集成 vpnApi（list / create / bindInterface）
  - 错误处理 + 二次确认

## 8. 真实设备验证（192.168.100.4 Leaf-03）

> 用户决策：本 change commit 不阻塞 archive。真实设备验证需要用户现场配合，**留作 follow-up**，本会话不执行。

- [ ] 8.1 查询接口列表：确认 M-GigabitEthernet0/0/0 识别为 L3 + 绑了 MGMT
- [ ] 8.2 创建 VPN `TEST_VPN` → 设备 `display ip vpn-instance` 能看到
- [ ] 8.3 绑 TEST_VPN 到 GigabitEthernet0/0/1（未用口）→ NETCONF get-config 能查到
- [ ] 8.4 解绑 GigabitEthernet0/0/1
- [ ] 8.5 删 TEST_VPN（无绑定）→ 设备 display 看不到
- [ ] 8.6 尝试删 MGMT（带绑定）→ 后端返回 400 错误，UI 提示
- [ ] 8.7 切网络：拔掉设备网线 → 端点返回"设备不可达"

## 9. 收尾

- [x] 9.1 commit 代码 `feat(interface): VPN instance 联动 + L2/L3 展示`
- [ ] 9.2 回归：现有 VLAN CRUD / 接口 access-trunk 配置功能不变（需真实设备验证）
- [ ] 9.3 archive change（v2.2 真实设备验证通过后）

## 10. 文档

- [x] 10.1 `VERSION-ROADMAP.md` v2.2 章节添加此 change 完成标记
- [ ] 10.2 如有 NETCONF 模型差异，更新 `docs/implementation.md`（待真实设备验证）

## 当前进度摘要

- ✅ 后端 6 端点 + L2/L3 解析
- ✅ 前端 4 列 + 联动 Modal
- ✅ 边界场景"设备不存在 / 名称字符非法"验证通过
- ⏸️ 真实设备验证（需用户现场）
- ⏸️ archive（等真实设备验证）
