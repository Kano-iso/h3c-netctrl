# sdn Spec Deltas (sdn-vpc-model-and-foundation)

> 本 change 在 [sdn](../../../../specs/sdn/spec.md) 之上 **ADDED**：
> 新增 sdn spec 定义，作为 v3.0 SDN 数据骨架的稳定规格。

---

## ADDED Requirements

### Requirement: 5 张 SDN 数据表

（详见 [sdn spec](../../../../specs/sdn/spec.md) §Requirement: 5 张 SDN 数据表）

- `sdn_tenants` / `sdn_vpcs` / `sdn_port_bindings` / `sdn_deployments` / `sdn_validation_snapshots`
- CASCADE 删除：tenant → vpcs → port_bindings / deployments / snapshots
- split 容器：5 张表由 config 容器持有

#### Scenario: 删除 tenant 级联清理

- **WHEN** 调用 `DELETE /api/sdn/tenants/{id}` 删 tenant
- **AND** 该 tenant 下有 2 个 vpc，每个 vpc 有 port_bindings / deployments
- **THEN** 全部 CASCADE 清理，0 个孤儿记录

### Requirement: SdnAllocator 编号自动分配

（详见 [sdn spec](../../../../specs/sdn/spec.md) §Requirement: SdnAllocator 编号自动分配）

- 9 个静态方法覆盖 tenant / vpc / port 编号
- env vars：`SDN_RD_BASE=100` / `SDN_RT_BASE=100` / `SDN_L3VNI_START=10000` / `SDN_L2VNI_START=20000`
- L2VNI / L3VNI / Vsi-interface / VLAN 走 DB max+1 递增 + DB `unique` 约束

### Requirement: 8 个 CRUD 端点

（详见 [sdn spec](../../../../specs/sdn/spec.md) §Requirement: 8 个 CRUD 端点）

- 5 个 tenant 端点 + 3 个 vpc 端点
- 注册到 `main.py` 的 `/api/sdn` prefix
- 错误返 i18n error_key

### Requirement: Pydantic Schema 校验

（详见 [sdn spec](../../../../specs/sdn/spec.md) §Requirement: Pydantic Schema 校验）

- `SdnTenantCreate` / `SdnTenantUpdate` / `SdnTenantResponse`
- `SdnVpcCreate` / `SdnVpcResponse`

### Requirement: i18n 错误码

（详见 [sdn spec](../../../../specs/sdn/spec.md) §Requirement: i18n 错误码）

- 9 个 error_key + 中英双语翻译

### Requirement: Alembic 迁移 007

（详见 [sdn spec](../../../../specs/sdn/spec.md) §Requirement: Alembic 迁移 007）

- 幂等守卫
- 顺序建表（先 tenants → vpcs → port_bindings → deployments → snapshots）
- downgrade 反向

### Requirement: 单测覆盖

（详见 [sdn spec](../../../../specs/sdn/spec.md) §Requirement: 单测覆盖）

- 19 个测试用例（tenant CRUD 8 + vpc CRUD 7 + allocator 边界 4）
- 全部 mock，不跑真机

### Requirement: split 容器兼容

（详见 [sdn spec](../../../../specs/sdn/spec.md) §Requirement: split 容器兼容）

- `SERVICE_NAME=core/config` 注册 sdn router
- `SERVICE_NAME=ctrl/data` 不注册
- Alembic 007 由 config 容器持有

### Requirement: 凭据与安全

（详见 [sdn spec](../../../../specs/sdn/spec.md) §Requirement: 凭据与安全）

- 无明文凭据
- `.env.example` 仅写变量名

### Requirement: 不依赖真机

（详见 [sdn spec](../../../../specs/sdn/spec.md) §Requirement: 不依赖真机）

- 不调用 `paramiko` / `NetconfClient` / `display *`
- 不跑 `--integration`
