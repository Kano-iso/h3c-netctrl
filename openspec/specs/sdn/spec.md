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

### Requirement: 不依赖真机

本 change MUST：
- 不调用 `paramiko` / `NetconfClient` / `display *` 等设备交互 API
- 单测全部 mock（mock NETCONF / mock DB）
- 不跑 `pytest -m integration`（默认 skip，符合 v2.3+ 规范）
