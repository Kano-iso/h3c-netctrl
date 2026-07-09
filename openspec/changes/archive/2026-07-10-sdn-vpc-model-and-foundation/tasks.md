# sdn-vpc-model-and-foundation — Tasks

> 每个 Task = 1 commit，符合 OpenSpec "小步增量" 规范

---

## Task 1: SDN ORM 模型 + Alembic 迁移 007

- [ ] `backend/app/models.py` 追加 5 个 SDN 模型类（`SdnTenant` / `SdnVpc` / `SdnPortBinding` / `SdnDeployment` / `SdnValidationSnapshot`）
- [ ] 关联关系（cascade / back_populates）
- [ ] 索引（tenant_id / device_id / vpc_id / created_at）
- [ ] Alembic 迁移 007：建 5 张表，幂等守卫
- [ ] `alembic upgrade head` 验证可重入
- [ ] commit: `feat(sdn): add 5 SDN ORM models + Alembic migration 007`

## Task 2: SdnAllocator 编号自动分配器

- [ ] `backend/app/utils/sdn_allocator.py` 新增
- [ ] 静态方法：`allocate_rd` / `allocate_rt` / `allocate_l3vni` / `allocate_l2vni` / `allocate_vsi_interface` / `allocate_vlan` / `derive_gateway_ip` / `derive_gateway_mac` / `build_vsi_name`
- [ ] env vars 读取（`SDN_RD_BASE` / `SDN_RT_BASE` / `SDN_L3VNI_START` / `SDN_L2VNI_START`）
- [ ] DB max+1 递增逻辑（保证唯一性）
- [ ] commit: `feat(sdn): add SdnAllocator with RD/RT/VNI/VLAN auto-allocation`

## Task 3: Pydantic Schemas

- [ ] `backend/app/schemas.py` 追加 4 个 Schema 类
- [ ] `SdnTenantCreate` / `SdnTenantUpdate` / `SdnTenantResponse`
- [ ] `SdnVpcCreate` / `SdnVpcResponse`
- [ ] Field 约束（name length / CIDR 格式 / gateway_ip 格式）
- [ ] commit: `feat(sdn): add SdnTenantCreate/Response, SdnVpcCreate/Response schemas`

## Task 4: i18n error_key 注册

- [ ] `backend/app/i18n_keys.py` 追加 9 个 SDN 错误码
- [ ] `SDN_TENANT_NAME_EXISTS` / `SDN_TENANT_RD_EXISTS` / `SDN_TENANT_NOT_FOUND`
- [ ] `SDN_VPC_TENANT_NOT_FOUND` / `SDN_VPC_VNI_EXISTS` / `SDN_VPC_NOT_FOUND`
- [ ] `SDN_ALLOCATION_FAILED` 等
- [ ] 中英双语翻译（zh-CN.json / en-US.json）
- [ ] commit: `feat(sdn): add 9 i18n error_key for tenant/VPC CRUD`

## Task 5: CRUD API 端点（8 个）

- [ ] `backend/app/routers/sdn.py` 新增
- [ ] tenant CRUD（POST/GET/GET single/PATCH/DELETE）
- [ ] vpc CRUD（POST/GET/GET single）
- [ ] 路由注册到 `backend/app/main.py`（prefix=`/api/sdn`）
- [ ] split 容器兼容（SERVICE_NAME 守卫）
- [ ] 内部辅助函数（`_tenant_to_response` / `_vpc_to_response`）
- [ ] commit: `feat(sdn): add tenant + VPC CRUD endpoints (8 endpoints)`

## Task 6: env vars 文档

- [ ] `.env.example` 追加 4 项 SDN env vars
- [ ] `SDN_RD_BASE=100` / `SDN_RT_BASE=100` / `SDN_L3VNI_START=10000` / `SDN_L2VNI_START=20000`
- [ ] commit: `feat(sdn): add SDN env vars to .env.example`

## Task 7: 单测

- [ ] `backend/tests/test_sdn_api.py` 新增
- [ ] 19 个测试用例：
  - tenant CRUD（8 个）
  - vpc CRUD（7 个）
  - allocator 边界（4 个）
- [ ] mock NETCONF / DB fixture
- [ ] 跑通：19/19 通过
- [ ] commit: `test(sdn): add 19 test cases for tenant/VPC CRUD + allocator`

## 验收 checklist

- [ ] 7 个 commit 顺序与 task 顺序一致
- [ ] 每个 commit 跑 `pytest backend/tests/test_sdn_api.py` 通过
- [ ] `pytest backend/tests/ -q` 全量通过
- [ ] alembic upgrade head 幂等
- [ ] CASCADE 行为符合 design.md §2
- [ ] ADR-001 ~ ADR-004 在 code / doc 体现
- [ ] no debug print / no TODO
- [ ] no hardcoded credentials
