# sdn-vpc-netconf-schema-xml — H3C V7 业务 NETCONF 双套 payload 架构

## Why

v3.0 SDN/VPC 业务下发要解决 H3C V7 L2VPN/VSI/VXLAN/EVPN 业务在**不同 platform** 设备上 NETCONF 行为不一致的问题：

**问题 1：L2VPN schema 化 NETCONF 在 LSTN 老芯片平台不可达**
- `.5` S6850 R6555（LSTN）schema 化 NETCONF L2VPN **不可达**（"Unexpected element" 错误，T1.13a/d 探针）
- `.26` V9850 R7643P02（RSTN）schema 化 NETCONF L2VPN **完整可写**（T1.13d 探针）
- `.177` S6850 T7064P15（LSTN）schema 化 NETCONF L2VPN **同样不可达**（T1.13e 探针）
- **真根因 = device platform（LSTN 老芯片 vs RSTN 新芯片），不是 software version**

**问题 2：LSTN 设备 CLI-over-NETCONF 真实可写**
- T1.13f 探针：`.5` 设备用 `<Configuration>vsi vpc9999</Configuration>` 走 NETCONF edit-config 成功 + `display l2vpn vsi verbose` 验证 + undo 干净
- 推翻 T1.13a 错误结论（namespace 错误，不是通道错误）
- 正确 namespace = `http://www.h3c.com/netconf/config:1.0`

**问题 3：当前 v3.0 模板只输出单一 CLI 文本，无法满足多平台需求**
- `H3cV7VpcCreateTemplate.render()` 返回 `List[{mode, command}]` —— 单一 CLI 文本列表
- 业务下发通道**未**与 device platform 关联
- `SdnDeploymentExecutor._apply_commands` 用单一 `<Configuration>{cli}</Configuration>` 通道 —— 对 LSTN 设备**碰巧**能 work，但对 RSTN 设备**完全不适用**

**问题 4：device.model 与 platform 关系未建索引**
- 业务下发每次都需 `get_platform_for_model(device.asset.model)` 推算
- 推算结果应缓存到 `Device.platform` 字段

## What Changes

### 主线 1：H3C V7 模板双套 payload 改造

**`backend/app/services/templates/h3c_v7_vpc_create.py`**：
- 新增 `H3cV7VpcCreateTemplate.render()` 返回 `List[TemplateUnit]`（5 unit × 4 字段）
  - VSI-L2 / EVPN / L3VPN / VSI-L3 / Global
  - 每个 unit 含 `cli_commands`（LSTN 走 CLI 文本）+ `xml_payloads`（RSTN 走 schema XML）+ `undo_cli` + `undo_xml`
- 新增 `H3cV7VpcDeleteTemplate.render()` 返回 3 unit（VSI-L2-undo / EVPN-undo / VSI-L3-undo）
  - 不删 L3VPN（vpn-instance 共享，末 VPC 才删）
  - 不删 Global（设备级共享）

**`backend/app/services/templates/h3c_v7_port_bind.py`**：
- `H3cV7PortBindTemplate.render()` 返回 1 unit（service_instance / access_vlan 2 模式）
- `H3cV7PortUnbindTemplate.render()` 返回 1 unit

### 主线 2：设备 adapter 双套 payload 框架

**`backend/app/services/sdn_device_adapter.py`**：
- 新增 `H3C_V7_PLATFORM_BY_MODEL` 映射（LSTN / RSTN 型号）
- 新增 `PLATFORM_LSTN` / `PLATFORM_RSTN` / `PLATFORM_UNKNOWN` 常量
- 新增 `get_platform_for_model()` 函数（lru_cache 缓存）
- 新增 `TemplateUnit` dataclass（cli_commands / xml_payloads / undo_cli / undo_xml）
- 新增 `UNIT_VSI_L2` / `UNIT_EVPN` / `UNIT_L3VPN` / `UNIT_VSI_L3` / `UNIT_PORT_BIND` / `UNIT_GLOBAL` / `UNIT_PORT_UNBIND` / `UNIT_VPC_CREATE_ALL` 常量
- 改 `VPCConfigTemplate` ABC：`render()` 返回 `List[TemplateUnit]` 而非 `List[{mode, command}]`
- 新增 `serialize_template_units` / `deserialize_template_units` 序列化 helper
- `H3cV7Adapter.get_platform()` 委托给 `get_platform_for_model()`

### 主线 3：VPCConfigPlanner 适配新 TemplateUnit

**`backend/app/services/vpc_config_planner.py`**：
- `plan_vpc_create()` / `plan_vpc_delete()` / `plan_port_bind()` / `plan_port_unbind()` 返回 `List[TemplateUnit]`
- `serialize()` / `deserialize()` 委托给 adapter 层 helper

### 主线 4：SdnDeploymentExecutor 按 device.platform 路由

**`backend/app/services/sdn_deployment_executor.py`**：
- 改 `_apply_commands()` → `_apply_units()`：
  - LSTN 设备：每个 unit 的 `cli_commands` 用 `<Configuration>{cli}</Configuration>` 包裹后 NETCONF edit-config
  - RSTN 设备：每个 unit 的 `xml_payloads` 直接 NETCONF edit-config
  - UNKNOWN 设备：拒绝下发（不静默走错通道）
- 新增 `_resolve_platform()` 方法：优先 `device.platform` 字段，否则用 `get_platform_for_model(asset.model)` 推算

### 主线 5：Device 模型 + 数据迁移

**`backend/app/models.py`**：
- `Device` 加 `platform: Mapped[Optional[str]]` 字段（nullable, indexed）

**`backend/migrations/versions/009_add_device_platform.py`**（新增）：
- alembic 迁移：幂等添加 `platform` 字段 + 索引
- 用 `insp.get_columns()` 守卫
- downgrade 也幂等

### 主线 6：schema + i18n 同步

**`backend/app/schemas.py`**：
- `DeviceResponse` 加 `platform: Optional[str]` 字段

**`backend/app/i18n_keys.py`**：
- 新增 `SDN.DEVICE_PLATFORM_UNKNOWN` 错误码
- 加 fallback 中文消息

### 主线 7：单测

**`backend/tests/test_templates_h3c_v7.py`**（新增）：
- 5 unit × 4 字段断言 + 顺序 + namespace + XML 合法性
- VpcDelete 3 unit 断言（不含 L3VPN/Global）
- PortBind 2 模式断言
- PortUnbind 兼容 2 种模式
- 序列化往返一致 + .2/.3 VNI=10 → RD=1:1 现状回推

**`backend/tests/test_vpc_config_planner.py`**（重写）：
- 5 unit 输出 + 顺序 + 内容断言
- VpcDelete 3 unit 断言
- PortBind / PortUnbind 2 模式断言
- serialize/deserialize roundtrip

**`backend/tests/test_sdn_deployment_api.py`**（重写）：
- POST 创建 deployment 返 5 unit planned_config
- POST action=delete 返 3 unit planned_config
- GET / PATCH 路径不变

**`backend/tests/test_sdn_deployment_executor.py`**（重写）：
- `_resolve_platform()` 双路径（field / asset.model）
- LSTN 设备走 `<Configuration>` 通道
- RSTN 设备走 xml_payloads 直接 edit_config
- UNKNOWN 设备拒绝
- 失败路径（NETCONF 抛异常 → status=failed + 立即停）

**`backend/tests/test_sdn_apply_endpoint.py`**（重写）：
- LSTN 走 `<Configuration>` 通道
- RSTN 走 xml_payloads 通道
- platform=None 但 asset.model=S6850 → 推算 LSTN
- 链路验证：apply 端点不调 ops-toolkit

## 设备 Platform 映射

| Platform | 芯片 | 设备型号 | L2VPN NETCONF 通道 |
|---|---|---|---|
| **LSTN** | 老芯片 | S6850 / S6850-56HF / S6850-54HF / S6805 / S6825 / S5560X / S6520X | **CLI 文本**走 NETCONF `<Configuration>` 通道 |
| **RSTN** | 新芯片 | V9850 / S9820 / S12500R / S6890 | **schema 化 NETCONF XML** |

## 业务下发通道定稿（应用户 2026-07-15 验证）

| 业务 | LSTN（.5/.177 S6850）| RSTN（.26 V9850）|
|---|---|---|
| **L3vpn/VRF/RD/RT** | schema 化 NETCONF XML（v2.4 已验）| schema 化 NETCONF XML |
| **L2vpn/VSI/VXLAN/EVPN** | CLI 文本走 NETCONF `<Configuration>` | schema 化 NETCONF XML |
| **SSH 22 CLI** | fallback | fallback |
| **RESTful / gRPC / Ansible** | ❌ 不投入（业务 API 缺失 / 平台不支持）| ❌ 不投入 |

## 不在本 change 范围

- **action=delete 的 executor 完整实现**：留 `sdn-vpc-reset-executor`（VPC 删除链路）
- **真机验证**（.5 设备 CLI 真实可写 + .26 设备 schema 真实可写）：留 T6
- **SdnPortBinding 端点**：留 `sdn-vpc-port-binding-api`
- **undo 链路完整性测试**：留 T7
- **UI 按钮 / 状态显示**：留 `sdn-frontend-vpc-page`（v3.0 UI）

## 影响范围

| 文件 | 改动 |
|---|---|
| `backend/app/services/sdn_device_adapter.py` | **重写**（platform 识别 + TemplateUnit + 序列化 helper）|
| `backend/app/services/templates/h3c_v7_vpc_create.py` | **重写**（双套 payload 5 unit）|
| `backend/app/services/templates/h3c_v7_port_bind.py` | **重写**（双套 payload）|
| `backend/app/services/vpc_config_planner.py` | **重写**（返回 List[TemplateUnit]）|
| `backend/app/services/sdn_deployment_executor.py` | **重写**（_apply_units + platform 路由）|
| `backend/app/models.py` | 加 `platform` 字段 |
| `backend/app/schemas.py` | `DeviceResponse` 加 `platform` |
| `backend/app/i18n_keys.py` | 加 `SDN.DEVICE_PLATFORM_UNKNOWN` |
| `backend/migrations/versions/009_add_device_platform.py` | **新增**（幂等 alembic 迁移）|
| `backend/tests/test_templates_h3c_v7.py` | **新增**（双套 payload 单测）|
| `backend/tests/test_vpc_config_planner.py` | **重写**（TemplateUnit 断言）|
| `backend/tests/test_sdn_deployment_api.py` | **重写**（5 unit planned_config 断言）|
| `backend/tests/test_sdn_deployment_executor.py` | **重写**（platform 路由 + LSTN/RSTN 路径）|
| `backend/tests/test_sdn_apply_endpoint.py` | **重写**（apply 端点 platform 路由）|

## 验收标准

### 1. 模板层验证

- [x] `H3cV7VpcCreateTemplate.render()` 返回 `List[TemplateUnit]`，长度 = 5
- [x] 5 个 unit name ∈ {vsi-l2, evpn, l3vpn, vsi-l3, global}
- [x] 每个 unit 的 cli_commands 非空
- [x] 每个 unit 的 xml_payloads 非空（global 例外）
- [x] xml_payloads 中 namespace 正确：`http://www.h3c.com/netconf/config:1.0`
- [x] xml_payloads 中每个 payload 是 well-formed XML

### 2. Planner 层验证

- [x] `VPCConfigPlanner.plan_vpc_create()` 返回 `List[TemplateUnit]`，长度 = 5
- [x] `VPCConfigPlanner.serialize(units)` 输出 JSON 字符串
- [x] `VPCConfigPlanner.deserialize(json_str)` 还原 `List[TemplateUnit]`
- [x] serialize → deserialize 往返一致

### 3. 数据层验证

- [x] `Device.platform` 字段存在
- [x] alembic 009 幂等（重跑不报错）
- [x] `DeviceResponse` 包含 `platform: Optional[str]`
- [x] `get_platform_for_model("S6850")` 返回 `"LSTN"`
- [x] `get_platform_for_model("V9850-256H")` 返回 `"RSTN"`
- [x] `get_platform_for_model("UnknownModel")` 返回 `"UNKNOWN"`

### 4. Executor 层验证

- [x] `SdnDeploymentExecutor` 解析 planned_config 为 `List[TemplateUnit]`
- [x] device.platform = LSTN → 每条 unit.cli_commands 走 `<Configuration>` 通道 NETCONF edit-config
- [x] device.platform = RSTN → 每条 unit.xml_payloads 直接 NETCONF edit-config
- [x] device.platform = UNKNOWN → 拒绝下发
- [x] 失败立即停 + 错误定位（op_index + unit name + error）

### 5. 回归验证

- [x] qa-backend 单测全过（含新平台路由单测）
- [x] config 容器 `alembic current` = `009 (head)`

### 6. 真机验证（**T6 范围**，不在本 change 验收）

- [ ] .5 (LSTN) CLI-over-NETCONF 真实可写（vsi-l2 → evpn → l3vpn → vsi-l3 → global 顺序）
- [ ] .26 (RSTN) schema NETCONF 真实可写
- [ ] .5 / .26 跨平台 running-config 业务命令 union 一致
- [ ] .5 业务效果（`display current-configuration | include vpc`）验证通过
- [ ] undo 链路验证通过（.5 + .26 双向清理）
