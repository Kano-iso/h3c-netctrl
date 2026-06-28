## MODIFIED Requirements

### Requirement: 接口解绑 VPN instance

`DELETE /api/devices/{id}/interfaces/{if_index}/vpn-instance` MUST 解绑：

- 预校验：接口未绑定 → 400 "接口未绑定 VPN instance"
- **预校验数据源 MUST 包含 L3vpn 模块**：路由在判断 `target.vpn_instance` 之前，必须通过 `get_config` 拉取 L3vpn filter 并将 `vpn_by_idx` 合并到接口解析结果中——**不能**只依赖 Ifmgr 单模块查询
- 成功 → `record_log`

**实施**：NETCONF edit-config 移除 `L3vpnIf/Bind` 对应条目。

#### Scenario: 正确读取已绑 VPN 的接口

- **WHEN** 接口在设备上**已**绑定 VPN instance（如 L3vpn/Bind/IfIndex = N）
- **AND** 调用 `DELETE /api/devices/{id}/interfaces/N/vpn-instance`
- **THEN** 后端预校验必须正确读到 `target.vpn_instance` 不为 null
- **AND** 调用 NETCONF edit-config 删除 Bind
- **AND** 返回 `{"success": true, "data": {"if_index": N}}`

#### Scenario: 误判修复（之前会报"未绑定"）

- **WHEN** 接口在设备上**已**绑定 VPN instance
- **AND** 调用 unbind 路由
- **THEN** 后端**不**返回 "接口未绑定 VPN instance" 错误
- **AND** 设备的 L3vpnIf/Bind 条目被成功删除

### Requirement: 前端联动 Modal

`frontend/src/components/VpnInstanceBindModal.vue` MUST 支持两种模式：
- 模式 1（create）：填写名称 → 创建 VPN → 自动绑定到当前接口
- 模式 2（bind）：从已有 VPN instance 列表选择 → 直接绑定
- **Modal 顶部 MUST 展示"现有 VPN instance"section**：
  - 列表项显示 name / rd / 绑定接口数
  - 两种模式（create / bind）下都显示
  - create 模式下，列表下方有"或新建"折叠区
  - 列表为空时显示"该设备尚无 VPN instance，请先创建"

所有写操作前 MUST 经过 `ConfirmModal` 二次确认。

#### Scenario: create 模式可见现有 VPN 列表

- **WHEN** 用户在 Interfaces.vue 上点击 L3 接口的 `+ VPN` 按钮
- **AND** 设备上已有 VPN instance（如 `mgt`）
- **THEN** Modal 顶部展示"现有 VPN instance"列表（含 `mgt` 等）
- **AND** 列表下方有"或新建"折叠区
- **AND** 用户可选择列表中的项直接绑定，或展开折叠区新建

#### Scenario: bind 模式可见现有 VPN 列表

- **WHEN** 用户在 Interfaces.vue 上点击 L3 接口的 `绑 VPN` 按钮
- **AND** 设备上有 N 个 VPN instance
- **THEN** Modal 展示全部 N 个 VPN instance 供选择
- **AND** 选中后点击"绑定"按钮

#### Scenario: 列表为空时引导用户

- **WHEN** 设备上**没有**任何 VPN instance
- **AND** 用户打开 Modal（create 或 bind 模式）
- **THEN** 列表区显示"该设备尚无 VPN instance，请先创建"
- **AND** create 模式下"或新建"折叠区默认展开
