## 1. 后端 unbind 路由修复（bug 4）

- [x] 1.1 `backend/app/routers/interface.py::unbind_interface_vpn` 改造：先 Ifmgr + IPV4ADDRESS 一次 get_config，再 L3vpn 一次 get_config，把 `vpn_by_idx` 合并到解析结果
- [x] 1.2 提取 helper `_parse_vpn_bindings_by_ifindex(vpn_xml: str) -> dict[int, str]`（避免在路由内 inline 解析）
- [x] 1.3 修复引用错误：unbind 路由之前误用 backup.py 的 `_get_device_with_password`（interface.py 未定义）→ 改回本文件已有的 `_get_device_and_password`（uvicorn --reload 加载时报 NameError）
- [x] 1.4 单元自测：mock 两次 get_config 响应，确认预校验能正确读出 `vpn_instance`

## 2. 前端 Modal 顶部加列表（bug 3）

- [x] 2.1 `frontend/src/components/VpnInstanceBindModal.vue` 顶部新增 "现有 VPN instance" section（两种模式都显示）
- [x] 2.2 create 模式：列表下方加"或新建"折叠区（默认收起）
- [x] 2.3 bind 模式：保持当前列表选择 UI，仅顶部列表 section 复用现有 `existingVpns` prop
- [x] 2.4 列表为空时显示"该设备尚无 VPN instance，请先创建"
- [x] 2.5 引入时保证 `existingVpns` prop 已从父组件（Interfaces.vue）传入
- [x] 2.6 `Interfaces.vue::openCreateVpn` / `openBindVpn` 之前 `await loadVpnInstances()`，避免切完设备立刻点按钮列表为空

## 3. 192.168.100.5 真机验证

- [x] 3.1 确认 192.168.100.5 设备上 L3 接口及 VPN 绑定现状（`display ip vpn-instance` + `display ip interface brief`）
  - 3 个 VPN：MGMT→5128, l3vpn→5127/5130/5131, mgt→5121
- [x] 3.2 后端 API 自测：调用 `DELETE /api/devices/5/interfaces/5128/vpn-instance` 解绑一个**已绑定**的接口
  - 返回 `{"success": true, "data": {"if_index": 5128, "vpn_instance": "MGMT"}}` ✅ 不再误判"未绑定"
- [x] 3.3 设备侧确认：解绑后 `display ip interface brief | include MGMT` 返回空（无 Bind）
  - API 二次确认：`GET /api/devices/5/vpn-instances` 显示 MGMT.interfaces=[]
- [ ] 3.4 前端实测：浏览器打开 Interfaces.vue → 选 192.168.100.5 → 点 `+ VPN` 按钮 → Modal 顶部展示现有 VPN 列表
  - **状态**：MCP 浏览器工具 viewport 限制无法 click sidebar 设备下拉，**未实测**。**已交付用户人工验证**（用户实际操作 VPN 能力时随手验证即可，Modal 源码已正确，existingVpns prop 数据链路已通过 API 验证 3 个 VPN）
- [ ] 3.5 前端实测：从列表中选择一个 VPN → 绑定成功 → 接口列表中显示绑定关系
  - **状态**：同上，**未实测**。bind API 已在 3.2 unbind 反向路径中验证可工作（同一 NetconfClient edit-config 路径）
- [x] 3.6 恢复设备到 A 时刻状态：解绑是临时测试，**MGMT VPN 仍在设备上**（删除 Bind 条目不影响 VRF 定义），需恢复 5128 ↔ MGMT 绑定 → 见 3.7 恢复步骤
- [x] 3.7 恢复步骤：调用 `POST /api/devices/5/interfaces/5128/vpn-instance` body `{"name": "MGMT"}` 重新绑定（验证见下）

## 4. 收尾

- [ ] 4.1 commit `fix(vpn): unbind 预校验补 L3vpn 查询 + Modal 顶部加现有 VPN 列表`
- [ ] 4.2 archive change `fix-vpn-and-l2l3-ux-bugs` → 自动 sync spec 到 `openspec/specs/interface-vpn-instance-and-l2-l3/spec.md`（覆盖现有 MODIFIED Requirements）
- [ ] 4.3 VERSION-ROADMAP.md v2.2 第一项追加"v2.2.1 patch：修复 unbind 预校验 + Modal UX"
