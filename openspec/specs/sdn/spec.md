# sdn Specification

## Purpose

提供 v3.0 SDN/VPC 资源（tenant + VPC）的基础数据模型、编号自动分配、CRUD API 及对应单测，作为后续 v3.0 SDN 各层（端口绑定 / 设备配置模板 / 配置下发 / 状态采集 / 可视化校验）的数据骨架。
## Requirements
### Requirement: 5 张 SDN 数据表

`backend/app/models.py` MUST 定义以下 5 张 ORM 模型：

| 表名 | 关键字段 | 关联 |
|---|---|---|
| `sdn_tenants` | id / name (unique) / rd (unique) / import_rt / export_rt / l3_vni (unique) / auto_assigned / description / created_at / updated_at | 1:N → sdn_vpcs |
| `sdn_vpcs` | id / name / tenant_id (FK) / cidr / gateway_ip / gateway_mac / vni (unique) / vsi_name / vsi_interface / vlan_id / auto_assigned / status / description | 1:N → sdn_port_bindings, sdn_deployments, sdn_validation_snapshots |
| `sdn_port_bindings` | id / device_id (FK) / tenant_id (FK) / vpc_id (FK) / if_index / interface_name / access_vlan / service_instance / status | — |
| `sdn_deployments` | id / vpc_id (FK) / device_id (FK) / action / planned_config / status / error | — |
| `sdn_validation_snapshots` | id / vpc_id (FK) / device_id (FK) / snapshot_data / validation_result / validation_details | — |

CASCADE 行为：
- 删除 `sdn_tenants` 行 → CASCADE 删除其下所有 vpcs / port_bindings / deployments / snapshots
- 删除 `sdn_vpcs` 行 → CASCADE 删除其下所有 port_bindings / deployments / snapshots

#### Scenario: 删除 tenant 级联清理

- **WHEN** 调用 `DELETE /api/sdn/tenants/{id}` 删 tenant
- **AND** 该 tenant 下有 2 个 vpc，每个 vpc 有 port_bindings / deployments
- **THEN** tenant 行被删
- **AND** 2 个 vpc 全部被删
- **AND** 6 个 port_bindings 全部被删
- **AND** 6 个 deployments 全部被删
- **AND** 0 个孤儿记录残留

### Requirement: SdnAllocator 编号自动分配

`backend/app/utils/sdn_allocator.py` MUST 提供以下静态方法：

| 方法 | 返回 | 起点 |
|---|---|---|
| `allocate_rd(tenant_id)` | `f"{SDN_RD_BASE}:{tenant_id}"` | env `SDN_RD_BASE`（默认 100）|
| `allocate_rt(tenant_id)` | `(import_rt, export_rt) = (f"{SDN_RT_BASE}:{tenant_id}", f"{SDN_RT_BASE}:{tenant_id}")` | env `SDN_RT_BASE`（默认 100）|
| `allocate_l3vni(db)` | `max(l3_vni) + 1` 不小于 `SDN_L3VNI_START` | env `SDN_L3VNI_START`（默认 10000）|
| `allocate_l2vni(db)` | `max(vni) + 1` 不小于 `SDN_L2VNI_START` | env `SDN_L2VNI_START`（默认 20000）|
| `allocate_vsi_interface(db)` | `max(vsi_interface) + 1` 起步 1 | 硬编码 |
| `allocate_vlan(db)` | `max(vlan_id) + 1` 起步 2 | 硬编码 |
| `derive_gateway_ip(cidr)` | CIDR 末位可用地址 | — |
| `derive_gateway_mac(vni)` | `f"00-00-00-00-{vni:04x}-01"` | — |
| `build_vsi_name(tenant_name, vpc_name)` | `f"vpc{vpc_id:04d}"` | — |

唯一性保证：
- L2VNI / L3VNI / Vsi-interface / VLAN 走 DB max+1 递增 + DB `unique` 约束
- 名称 / RD 走业务层 pre-check

#### Scenario: 创建 2 个 VPC 后 L2VNI 递增

- **WHEN** 先后创建 vpc1（VNI=20000）、vpc2（VNI=20001）、vpc3（VNI=20002）
- **THEN** 三个 vpc 的 `vni` 字段分别等于 20000、20001、20002
- **AND** DB 记录中无 VNI 重复

#### Scenario: L2VNI 起点回退保护

- **WHEN** 现有 DB 中 `max(vni) = 19999`
- **AND** env `SDN_L2VNI_START = 20000`
- **THEN** 下一次 allocate_l2vni 返回 20000
- **AND** 不返回 20000 以下值

### Requirement: 8 个 CRUD 端点

`backend/app/routers/sdn.py` MUST 暴露以下端点（注册到 `/api/sdn`）：

| Method | Path | 入参 | 返回 |
|---|---|---|---|
| POST | `/tenants` | `SdnTenantCreate` | `SdnTenantResponse` |
| GET | `/tenants` | `?skip=0&limit=100` | `{total, tenants: []}` |
| GET | `/tenants/{id}` | — | `SdnTenantResponse` |
| PATCH | `/tenants/{id}` | `SdnTenantUpdate` | `SdnTenantResponse` |
| DELETE | `/tenants/{id}` | — | `{deleted: id}` |
| POST | `/vpcs` | `SdnVpcCreate` | `SdnVpcResponse` |
| GET | `/vpcs` | `?tenant_id=&skip=&limit=` | `{total, vpcs: []}` |
| GET | `/vpcs/{id}` | — | `SdnVpcResponse` |

错误返回：
- 名称已存在 → 400 + `SDN_TENANT_NAME_EXISTS`
- RD 已存在 → 400 + `SDN_VPC_RD_EXISTS`（理论不该出现，预留）
- tenant 不存在 → 400 + `SDN_VPC_TENANT_NOT_FOUND`
- vpc 不存在 → 400 + `SDN_VPC_NOT_FOUND`

#### Scenario: 成功创建 tenant

- **WHEN** `POST /api/sdn/tenants` body `{"name": "t1", "description": "first"}`
- **THEN** 200 + `{success: true, data: {id, name: "t1", rd: "100:1", import_rt: "100:1", export_rt: "100:1", l3_vni: 10000, ...}}`

#### Scenario: 名称重复创建 tenant 失败

- **WHEN** 已存在 tenant name=`t1`
- **AND** `POST /api/sdn/tenants` body `{"name": "t1"}`
- **THEN** 200 + `{success: false, error_key: "SDN_TENANT_NAME_EXISTS", error_params: {name: "t1"}}`

### Requirement: Pydantic Schema 校验

`SdnTenantCreate` MUST 校验：
- `name`: 1-100 字符，必填
- `description`: ≤500 字符，可空

`SdnVpcCreate` MUST 校验：
- `name`: 1-100 字符，必填
- `tenant_id`: int > 0
- `cidr`: IPv4 CIDR 格式（如 `10.0.1.0/24`）
- `gateway_ip`: 可空（自动派生），IPv4 格式
- `gateway_mac`: 可空（自动派生），MAC 格式
- `description`: ≤500 字符

#### Scenario: VPC 名称超长被拒

- **WHEN** `POST /api/sdn/vpcs` body `{"name": "x" * 101, ...}`
- **THEN** 422（FastAPI 自动校验）

### Requirement: i18n 错误码

`backend/app/i18n_keys.py` MUST 注册 9 个 SDN 错误码（`err` 对象）：

- `SDN_TENANT_NAME_EXISTS`
- `SDN_TENANT_RD_EXISTS`
- `SDN_TENANT_NOT_FOUND`
- `SDN_VPC_TENANT_NOT_FOUND`
- `SDN_VPC_VNI_EXISTS`
- `SDN_VPC_NOT_FOUND`
- `SDN_ALLOCATION_FAILED`
- `SDN_INVALID_CIDR`
- `SDN_INVALID_GATEWAY`

中英双语翻译文件 `frontend/src/i18n/zh-CN.js` 和 `en-US.js` MUST 各有对应条目。

#### Scenario: SDN 错误码具备中英翻译

- **WHEN** 后端返回 `SDN_VPC_NOT_FOUND`
- **THEN** 前端 zh-CN 翻译文件中存在对应中文文案
- **AND** 前端 en-US 翻译文件中存在对应英文文案

### Requirement: Alembic 迁移 007

`backend/migrations/versions/007_add_sdn_tables.py` MUST：
- 幂等守卫：`if "sdn_tenants" in insp.get_table_names(): return`
- 顺序创建 5 张表（先 tenants → vpcs → port_bindings → deployments → validation_snapshots，遵循外键依赖）
- downgrade MUST 顺序 drop（反向顺序）

#### Scenario: 重复升级幂等

- **WHEN** 已运行 007 迁移
- **AND** 再次 `alembic upgrade head`
- **THEN** 不抛异常，不重复建表

### Requirement: 单测覆盖

`backend/tests/test_sdn_api.py` MUST 包含 19 个测试用例：
- tenant CRUD（创建成功 / 名称重复 / 列表 / 详情 / 更新 / 删除 / 列表分页 / 空描述）
- vpc CRUD（创建成功 / tenant 不存在 / 列表 / 列表按 tenant 过滤 / 详情 / 名称超长 / vni 重复）
- allocator 边界（L2VNI 递增 / L3VNI 递增 / L2VNI 起点保护 / vlan 起点保护）

跑通标准：19/19 通过。

#### Scenario: SDN 单测全量通过

- **WHEN** 运行 `backend/tests/test_sdn_api.py`
- **THEN** tenant CRUD、vpc CRUD、allocator 边界测试全部通过
- **AND** 不需要连接真实设备

### Requirement: split 容器兼容

`backend/app/main.py` 注册 sdn router 时 MUST 满足：
- `SERVICE_NAME=core`（monolith）→ 注册
- `SERVICE_NAME=config`（split）→ 注册
- `SERVICE_NAME=ctrl` / `SERVICE_NAME=data` → 不注册（按 split 职责划分，sdn 属于 config）
- Alembic 007 迁移由 config 容器持有

#### Scenario: ctrl 容器启动不报 404 / 500

- **WHEN** `SERVICE_NAME=ctrl` 启动
- **AND** 前端 / 内部 API 调 `/api/sdn/*`
- **THEN** 不应返 500（要么路由不存在 404，要么路由存在 200）
- **AND** ctrl 容器不持有 sdn 表是预期行为

### Requirement: 凭据与安全

本 change MUST：
- 任何代码、commit message、测试数据**不**包含 `DEVICE_USERNAME` / `DEVICE_PASSWORD` / SSH 密码
- `.env.example` 仅写变量名（不写明文值）
- 真实凭据走 `env_file: - .env`（v2.6.1 规范）

#### Scenario: 代码库不包含真实设备凭据

- **WHEN** 检查 SDN change 相关代码、测试数据和提交内容
- **THEN** 不存在真实 SSH 用户名或密码明文
- **AND** `.env.example` 只暴露变量名和说明

### Requirement: 不依赖真机

本 change MUST：
- 不调用 `paramiko` / `NetconfClient` / `display *` 等设备交互 API
- 单测全部 mock（mock NETCONF / mock DB）
- 不跑 `pytest -m integration`（默认 skip，符合 v2.3+ 规范）

#### Scenario: 默认测试不访问设备

- **WHEN** 运行本 change 的默认单元测试
- **THEN** 测试不建立 SSH 或 NETCONF 连接
- **AND** 所有设备交互均由 mock 或 fixture 提供

### Requirement: VPC Deployment Withdraw Actions

The SDN backend MUST support user actions beyond initial VPC creation:

- `delete`: withdraw one VPC from one device using the VPC delete template.
- `redeploy`: restore one VPC to one Leaf using a VPC `create` deployment and the saved VPC definition.
- `gateway_delete`: withdraw only the VPC L3 gateway from one device by deleting the Vsi-interface unit.
- `gateway_deploy`: restore only the VPC L3 gateway on one device using a `create` deployment with the Vsi-interface unit from the saved VPC definition.
- `port_bind`: bind one device interface to one VPC.
- `port_unbind`: remove one device interface binding from one VPC.

#### Scenario: Whole VPC withdraw is executable

- **WHEN** a pending deployment has action `delete`
- **AND** its planned config contains valid template units
- **THEN** applying the deployment executes the units through the platform-specific channel
- **AND** marks the deployment `success` when all units succeed
- **AND** marks the VPC status `withdrawn`

#### Scenario: Whole VPC withdraw does not recreate an empty VSI

- **WHEN** a VPC withdraw plan is generated
- **THEN** the EVPN/RD cleanup unit MUST run before the final VSI delete unit
- **AND** the final VSI delete unit MUST NOT be followed by commands that enter the same `vsi <name>` view
- **AND** post-withdraw device config MUST NOT retain an empty VSI shell for the withdrawn VPC

#### Scenario: Gateway-only withdraw does not delete L2 units

- **WHEN** a user requests gateway withdraw for one VPC on one device
- **THEN** the backend creates a `gateway_delete` deployment
- **AND** the planned config contains only the `vsi-l3` unit
- **AND** no `vsi-l2` or `evpn` unit is included

#### Scenario: Single Leaf VPC redeploy uses the saved VPC definition

- **WHEN** a user requests redeploy for one VPC on one Leaf
- **THEN** the backend creates a VPC `create` deployment
- **AND** the planned config contains the full VPC create unit set
- **AND** RD/VNI/gateway parameters are read from the saved VPC definition

#### Scenario: Gateway-only deploy does not recreate L2 units

- **WHEN** a user requests gateway deploy for one VPC on one Leaf
- **THEN** the backend creates a `create` deployment with unit `vsi-l3`
- **AND** the planned config contains only the `vsi-l3` unit
- **AND** no `vsi-l2` or `evpn` unit is included

### Requirement: Port Binding Lifecycle API

The SDN backend MUST expose port binding operations from a VPC/user perspective:

- Create a port binding record for `{device_id, vpc_id, if_index, interface_name}`.
- List and read port bindings.
- Generate a `port_bind` deployment for a binding.
- Generate a `port_unbind` deployment for a binding.
- Reject binding to a protected interface.
- Reject duplicate active/planned bindings on the same device interface.

#### Scenario: Port bind deployment references binding

- **WHEN** a user creates a port binding and requests deploy
- **THEN** the backend creates a deployment with action `port_bind`
- **AND** the deployment references `port_binding_id`
- **AND** successful apply marks the binding `active`

#### Scenario: Port unbind deployment updates binding state

- **WHEN** a user requests undeploy for an existing binding
- **THEN** the backend creates a deployment with action `port_unbind`
- **AND** successful apply marks the binding `unbound`

### Requirement: Existing VPC Expansion Workflow

The SDN backend MUST support adding a new access interface to an existing VPC from a user-oriented expansion workflow.

- The expansion target MUST be a Leaf device.
- The expansion MUST inherit the existing VPC CIDR, gateway, VNI, and VSI; the user MUST NOT provide a new subnet mask for the expansion.
- The expansion MAY accept an expected host IP for completion validation.
- Starting an expansion MUST create a port binding and a `port_bind` deployment.
- If the deployment is applied successfully, the port binding and VPC MUST enter `expanding`.
- Completing an expansion MUST optionally ping the expected host IP from the VPC gateway and MUST collect a display validation snapshot.
- Successful completion MUST mark the port binding and VPC `active`.
- Failed completion MUST mark the binding `failed` and the VPC `degraded`.

#### Scenario: Start expansion only accepts Leaf targets

- **WHEN** a user starts VPC expansion on a non-Leaf device
- **THEN** the backend rejects the request
- **AND** no port binding is created

#### Scenario: Start expansion enters expanding after apply

- **WHEN** a user starts VPC expansion on a Leaf device and the generated `port_bind` deployment succeeds
- **THEN** the backend marks the port binding `expanding`
- **AND** marks the VPC `expanding`

#### Scenario: Complete expansion validates host reachability

- **WHEN** a user completes VPC expansion with an expected host IP
- **THEN** the backend pings that host from the VPC gateway
- **AND** forces a display validation sync
- **AND** marks the expansion active only when both checks pass

### Requirement: Fabric Level VPC Operations

The SDN backend MUST expose VPC-level deployment and withdraw operations that expand one user action into per-device deployment records.

- `POST /api/sdn/vpcs/{vpc_id}/deploy` MUST create VPC `create` deployments for all target EVPN Fabric devices.
- `POST /api/sdn/vpcs/{vpc_id}/withdraw` MUST create `port_unbind` deployments before VPC `delete` deployments when active bindings exist.
- If `device_ids` is omitted, the backend MUST select default EVPN Fabric candidates.
- If `device_ids` is provided, the backend MUST use the explicit target list only after validating that every target is an EVPN Fabric member.
- A device MUST be considered an EVPN Fabric member only when its trusted `sdn_role` is `evpn_leaf`.
- Device names, inferred model support, and `platform=LSTN/RSTN` MUST NOT be used as SDN/VPC target eligibility.
- `auto_apply` MUST default to `false`; the default behavior is pending change creation, not device modification.

#### Scenario: Default VPC deploy expands to all EVPN Fabric devices

- **WHEN** a VPC deploy request omits `device_ids`
- **AND** two EVPN Fabric candidates exist
- **AND** one access-only device name contains `Leaf` and has `platform=LSTN`
- **THEN** the backend creates one VPC `create` deployment per EVPN Fabric candidate
- **AND** excludes the access-only device
- **AND** includes planned/pending port bindings for matching EVPN Fabric devices after each VPC `create` deployment

#### Scenario: Explicit non-EVPN device is rejected

- **WHEN** a VPC deploy or withdraw request includes a device whose `sdn_role` is not `evpn_leaf`
- **THEN** the backend rejects the operation
- **AND** no deployment is created for that device
