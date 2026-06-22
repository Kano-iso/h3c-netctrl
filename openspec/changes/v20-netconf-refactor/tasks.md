## 1. NETCONF 接口查询

- [x] 1.1 在 netconf_client.py 中新增 get_interfaces 方法（get-config + Ifmgr filter）
- [x] 1.2 实现 Ifmgr XML 响应解析（提取 IfIndex、Name、LinkType、PVID、TrunkVLANs）
- [x] 1.3 重写 interface.py 的 get_interfaces 路由，从 SSH 改为 NETCONF

## 2. NETCONF 接口配置

- [x] 2.1 在 netconf_client.py 中新增 configure_interface 方法（edit-config + Ifmgr XML）
- [x] 2.2 实现 LinkType 映射（access=1, trunk=2）和 TrunkVLANs XML 构建
- [x] 2.3 重写 interface.py 的 configure_interface 路由，从 SSH 改为 NETCONF
- [x] 2.4 移除 InterfaceConfig 中的 interface_name 字段，改用 IfIndex

## 3. 前端适配

- [x] 3.1 DeviceDetail.vue 去掉 onMounted 自动加载接口和资产，改为手动刷新
- [x] 3.2 接口列表增加 IfIndex 字段传递（配置时需要）
- [x] 3.3 接口配置弹窗适配 IfIndex

## 4. 验证与提交

- [x] 4.1 自测：接口查询、接口配置（access/trunk）、日志记录
- [ ] 4.2 提交代码并推送 + Archive 闭环
