# sdn-vpc-model-and-foundation

> **版本定位**：v3.0 第一个 change — **数据层 + CRUD 骨架**
> **范围**：纯数据层 / API 层 / 编号分配，**不涉及任何设备配置下发**
> **不依赖**：7 commit 之前已先存在 5 张表（VPC SDN 资源模型）

---

## Why

v2.6.2 闭环后，v3.0 VPC/SDN 整体目标已通过 PRD-V3.0.md 明确。但要落地到工程实现，第一步必须先有**数据骨架**：

1. **没有持久化模型** → 用户创建的 VPC/租户没法存盘，重启即丢
2. **没有 CRUD API** → 前端没法做管理界面（增删改查）
3. **没有编号分配器** → 多个 VPC 必撞 VNI/RD/RT/VLAN
4. **没有可测试骨架** → 后续 device-templates / deploy / collect 都没法 mock

但同时：

- 7 commit 之前**已有 5 张表**（`sdn_tenants` / `sdn_vpcs` / `sdn_port_bindings` / `sdn_deployments` / `sdn_validation_snapshots`）作为 v3.0 资源模型被引入
- 现有 `backend/app/models.py` 已经在 #126-#280 行承载 5 个 SDN 模型类
- 没有 ORM 模型 = 后续所有 change 没法动工

本 change = **把"已有 5 张表"补齐到完整可用的数据层 + CRUD**，**不引入新表 / 不修改旧模型字段**。

## What Changes

### 主线 1：编号自动分配器（`SdnAllocator`）

- 新增 `backend/app/utils/sdn_allocator.py`
- 提供静态方法：`allocate_rd` / `allocate_rt` / `allocate_l3vni` / `allocate_l2vni` / `allocate_vsi_interface` / `allocate_vlan` / `derive_gateway_ip` / `derive_gateway_mac` / `build_vsi_name`
- 所有起始值走 env vars（`SDN_RD_BASE=100` / `SDN_RT_BASE=100` / `SDN_L3VNI_START=10000` / `SDN_L2VNI_START=20000`）
- L2VNI/VLAN/Vsi-interface 走 DB max+1 递增，**保证全局唯一**
- RD/RT/L3VNI 走 ID/DB max 直接派生

### 主线 2：CRUD API（8 端点）

新增 `backend/app/routers/sdn.py`，注册到 main.py（prefix=`/api/sdn`）：

| # | Method | Path | 功能 |
|---|---|---|---|
| 1 | POST | `/api/sdn/tenants` | 创建租户（自动分配 RD/RT/L3VNI）|
| 2 | GET | `/api/sdn/tenants` | 租户列表（分页 + vpc_count）|
| 3 | GET | `/api/sdn/tenants/{id}` | 租户详情 |
| 4 | PATCH | `/api/sdn/tenants/{id}` | 更新 description |
| 5 | DELETE | `/api/sdn/tenants/{id}` | 删除租户（CASCADE 清理）|
| 6 | POST | `/api/sdn/vpcs` | 创建 VPC（自动分配 VNI/Vsi-interface/VLAN/gateway）|
| 7 | GET | `/api/sdn/vpcs` | VPC 列表（可按 tenant_id 过滤）|
| 8 | GET | `/api/sdn/vpcs/{id}` | VPC 详情 |

### 主线 3：Pydantic Schemas

- 新增 `SdnTenantCreate` / `SdnTenantUpdate` / `SdnTenantResponse`
- 新增 `SdnVpcCreate` / `SdnVpcResponse`
- 注册到 `backend/app/schemas.py`

### 主线 4：i18n error_key

- 新增 9 个 i18n 错误码（`SDN_TENANT_NAME_EXISTS` / `SDN_TENANT_RD_EXISTS` / `SDN_TENANT_NOT_FOUND` / `SDN_VPC_TENANT_NOT_FOUND` / `SDN_VPC_VNI_EXISTS` / `SDN_VPC_NOT_FOUND` / `SDN_ALLOCATION_FAILED` 等）
- 中英双语翻译
- 注册到 `backend/app/i18n_keys.py`

### 主线 5：Alembic 迁移

- 新增 `backend/migrations/versions/007_add_sdn_tables.py`
- 创建 5 张 SDN 表（幂等守卫：`if "sdn_tenants" in insp.get_table_names(): return`）
- split 容器兼容（config 容器唯一持有 SDN 表）

### 主线 6：单测

- 新增 `backend/tests/test_sdn_api.py`
- 19 个测试用例：tenant CRUD（8）+ vpc CRUD（7）+ allocator 边界（4）
- mock NETCONF 跑通

### 主线 7：env vars 文档

- 更新 `.env.example`，加 `SDN_RD_BASE` / `SDN_RT_BASE` / `SDN_L3VNI_START` / `SDN_L2VNI_START` 4 项

## 不在本 change 范围（后续 change 处理）

- ❌ 端口绑定（`SdnPortBinding` 表已建但**无 CRUD 端点**）→ `sdn-port-binding` change
- ❌ 设备配置下发（H3C V7 vsi/vxlan/evpn/bgp 模板）→ `sdn-vpc-device-templates` change
- ❌ 部署执行（plan → NETCONF/SSH → 回滚）→ `sdn-deploy` change
- ❌ 状态采集 / 校验（display 拉回 + 解析 + 比对）→ `sdn-validate` change
- ❌ 前端 VPC 管理 UI → `sdn-frontend` change

## 影响范围

| 类型 | 文件 |
|---|---|
| 新增 | `backend/app/utils/sdn_allocator.py` |
| 新增 | `backend/app/routers/sdn.py` |
| 新增 | `backend/migrations/versions/007_add_sdn_tables.py` |
| 新增 | `backend/tests/test_sdn_api.py` |
| 修改 | `backend/app/schemas.py`（追加 4 个 Schema 类）|
| 修改 | `backend/app/i18n_keys.py`（追加 9 个 error_key）|
| 修改 | `backend/app/main.py`（注册 sdn router + split 容器兼容）|
| 修改 | `backend/config/main.py`（Alembic 触发点）|
| 修改 | `.env.example`（4 个 SDN env vars）|

## 验收标准

- [ ] `pytest backend/tests/test_sdn_api.py` 19/19 通过
- [ ] `pytest backend/tests/ -q` 全量通过（不影响其他模块）
- [ ] alembic upgrade head 应用 007 迁移幂等成功
- [ ] `curl -X POST /api/sdn/tenants` 返回带 RD/RT/L3VNI 的 tenant
- [ ] `curl -X POST /api/sdn/vpcs` 返回带 VNI/Vsi-interface/VLAN 的 vpc
- [ ] 删除 tenant 时其下 vpc CASCADE 清理
- [ ] 重建 vpc 时 VNI/VLAN 不会与历史冲突（递增）
