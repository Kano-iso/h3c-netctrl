# sdn-deployment-execution Spec Deltas (sdn-vpc-deployment-executor)

> 本 change 在 [sdn-device-templates](../../../../specs/sdn-device-templates/spec.md) 之上 **ADDED**：
> 新增 sdn-deployment-execution spec，定义 backend NETCONF 业务配置下发链路（替代之前用 ops-toolkit 排错工具实现业务下发的错误架构）。

---

## ADDED Requirements

### Requirement: SdnDeploymentExecutor 通过 NETCONF 下发配置

`SdnDeploymentExecutor.execute(db: Session, deployment_id: int) -> SdnDeployment` MUST：

1. 从 `SdnDeployment.id = deployment_id` 读取记录
2. 校验 `status == 'pending'` → 否则抛 `SDN_DEPLOYMENT_NOT_PENDING`
3. 校验 `action == 'create'` → 否则抛 `SDN_DEPLOYMENT_ACTION_NOT_SUPPORTED`（本 change 仅支持 create）
4. 通过 `get_device_with_password(db, device_id)` 取设备 + 解密密码
5. 校验设备 host 后缀 ∈ {`.5`, `.6`}（仅 Leaf-04 / Leaf-05 允许下发）→ 否则抛 `SDN_DEVICE_NOT_WRITABLE`
6. 解析 `planned_config` JSON 字符串为 `List[ConfigCommand]`
7. 用 `NetconfClient(host, port, user, password)` context manager 串行调 `edit_config`
8. 全部成功 → `status = 'success'`
9. 任一失败 → `status = 'failed'` + `error_message` 含失败命令索引和原始错误

#### Scenario: pending → success

- **WHEN** deployment.status = 'pending'
- **AND** device.host = '192.168.100.5'
- **AND** planned_config 含 14 条命令
- **AND** 所有 NETCONF edit_config 成功
- **THEN** deployment.status = 'success'
- **AND** deployment.error_message = None

#### Scenario: NETCONF 第 5 条失败

- **WHEN** deployment.status = 'pending'
- **AND** planned_config 含 14 条命令
- **AND** 第 5 条 NETCONF edit_config 抛 RPCError
- **THEN** deployment.status = 'failed'
- **AND** deployment.error_message 包含 "第 5 条" + 原始错误信息

#### Scenario: 设备不在白名单（.2）

- **WHEN** device.host = '192.168.100.2'
- **AND** 调用 `SdnDeploymentExecutor.execute(db, deployment_id)`
- **THEN** 抛 `SDN_DEVICE_NOT_WRITABLE` 错误
- **AND** deployment.status 保持 'pending'（未变更）

#### Scenario: deployment.status = success 重放拒绝

- **WHEN** deployment.status = 'success'
- **AND** 调用 `SdnDeploymentExecutor.execute(db, deployment_id)`
- **THEN** 抛 `SDN_DEPLOYMENT_NOT_PENDING` 错误

### Requirement: POST /api/sdn/deployments/{id}/apply 端点

`POST /api/sdn/deployments/{id}/apply` MUST：

- 接收空 body（无参数）
- 调 `SdnDeploymentExecutor.execute(db, id)`
- 成功 → 200 + 返回最新 `SdnDeploymentResponse`
- deployment_id 不存在 → 404 + `SDN_DEPLOYMENT_NOT_FOUND`
- deployment.status ≠ 'pending' → 409 + `SDN_DEPLOYMENT_NOT_PENDING`
- device 不在白名单 → 422 + `SDN_DEVICE_NOT_WRITABLE`
- executor 内部 NETCONF 失败 → 200 + `status='failed'`（业务视为已完成，错误详情在 response）

#### Scenario: 正常 apply

- **WHEN** `POST /api/sdn/deployments/1/apply`
- **AND** deployment 1 状态为 pending
- **AND** device 在白名单
- **THEN** response.status_code = 200
- **AND** response.data.status = 'success'

#### Scenario: deployment 不存在

- **WHEN** `POST /api/sdn/deployments/9999/apply`
- **THEN** response.status_code = 404
- **AND** response.error.error_key = 'SDN_DEPLOYMENT_NOT_FOUND'

### Requirement: ops-toolkit 不承担业务下发

`ops-toolkit/scripts/` MUST NOT 含：
- `vpc-apply.sh`（业务配置下发）
- `vpc-reset.sh`（业务 VPC 清理）
- 任何与 SdnDeployment / SdnVpc 表写操作相关的脚本

`ops-toolkit/scripts/vpc-show.sh` MAY 保留（只读排错，符合 ops-toolkit 定位）。

#### Scenario: ops-toolkit scripts 目录检查

- **WHEN** 列出 `ops-toolkit/scripts/` 目录
- **THEN** 不含 `vpc-apply.sh` 和 `vpc-reset.sh`
- **AND** 可选含 `vpc-show.sh`（仅读）

### Requirement: 业务执行器不在 ops-toolkit 容器

`SdnDeploymentExecutor` 实现 MUST 位于 `backend/app/services/sdn_deployment_executor.py`（config 容器内），NOT 在 ops-toolkit 容器内。

执行链路 MUST 为：
`frontend → config 容器 (FastAPI) → SdnDeploymentExecutor → NetconfClient → 设备`

ops-toolkit 容器 MUST NOT 出现在该链路中。

#### Scenario: 业务执行器在 backend

- **WHEN** 前端调用 `POST /api/sdn/deployments/1/apply`
- **THEN** 请求被 config 容器的 `backend/app/routers/sdn.py` 接收
- **AND** 调 `backend/app/services/sdn_deployment_executor.py` 中 `SdnDeploymentExecutor.execute()`
- **AND** 走 `NetconfClient` 调设备
- **AND** ops-toolkit 容器不参与
