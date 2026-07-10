# sdn-vpc-deployment-api — SDN/VPC 部署记录 API

## Why

sdn-vpc-device-templates change（已 archive 2026-07-10）实现了 SdnDeviceAdapter / VPCConfigPlanner / SdnPreflight 和 ops-toolkit 脚本（vpc-apply / vpc-reset / vpc-show），但**漏掉了关键的 deployment API 端点**——vpc-apply.sh 设计上要 `GET /api/sdn/deployments/{id}` 读取 `planned_config`，但后端没这个端点。

v3.0 启动期真机验证（.5 设备）发现：openapi.json 仅有 `/api/sdn/tenants` 和 `/api/sdn/vpcs`，没有 deployment 端点 → vpc-apply 实际跑不起来。

**正解**：补 deployment API（POST 创建 / GET 读取 / PATCH 更新状态），让 vpc-apply 端到端跑通。

## What Changes

### 主线 1：schemas 扩展

`backend/app/schemas.py` 新增：
- `SdnDeploymentCreate` — POST 请求（vpc_id, device_id, action）
- `SdnDeploymentResponse` — 响应（id, vpc_id, device_id, action, planned_config, status, error, created_at, updated_at）

### 主线 2：router 扩展

`backend/app/routers/sdn.py` 新增 4 个端点：
- `POST /api/sdn/deployments` — 创建 deployment + 调 `VPCConfigPlanner` 生成 `planned_config`
- `GET /api/sdn/deployments` — 列表（按 vpc_id / device_id / action 过滤）
- `GET /api/sdn/deployments/{id}` — 读详情（vpc-apply 用）
- `PATCH /api/sdn/deployments/{id}` — 更新 status / error（vpc-apply 下发后回写）

### 主线 3：单测

`backend/tests/test_sdn_deployment_api.py`：
- POST 创建 → 自动调 planner 生成 planned_config
- GET 单个
- GET 列表过滤
- PATCH 更新 status
- 异常：vpc 不存在 / device 不存在

## 不在本 change 范围

- **SdnPortBinding API** — 端口绑定 CRUD 留 `sdn-vpc-port-binding-api`（下个 change），本次只做 deployment
- **SdnValidationSnapshot API** — 状态采集快照 API 留 `sdn-vpc-validation-api`（再下个 change）
- **GET /api/sdn/devices** — vpc-apply 凭据走 .env 注入，不需要这个端点
- **前端** — v3.0 前端大屏优先级靠后，后端先闭环

## 影响范围

| 类别 | 数量 |
|---|---|
| 改 schemas | 1 文件 + 2 类 |
| 改 router | 1 文件 + 4 端点 |
| 改 model 字段 | 0（沿用 SdnDeployment 现有字段）|
| 新单测 | 1 文件 + 5+ 测试 |

## 验收标准

- [ ] `POST /api/sdn/deployments` 创建成功，自动生成 planned_config（14 条命令）
- [ ] `GET /api/sdn/deployments/{id}` 返回完整 deployment
- [ ] `GET /api/sdn/deployments?vpc_id=1&action=create` 过滤正常
- [ ] `PATCH /api/sdn/deployments/{id}` 更新 status="success" 正常
- [ ] 单测 5+ 全过
- [ ] vpc-apply --deployment 1 --device .5 --dry-run 端到端跑通
- [ ] 真机验证：BGP neighbor 起来后 vpc-apply 真实下发成功

## 关联

- **前序 change**：[archive/2026-07-10-sdn-vpc-model-and-foundation](../archive/2026-07-10-sdn-vpc-model-and-foundation/) — 5 个 SDN 模型
- **前序 change**：[archive/2026-07-10-sdn-vpc-device-templates](../archive/2026-07-10-sdn-vpc-device-templates/) — 设备适配 + 配置计划 + 预检 + ops-toolkit
- **后续 change**：`sdn-vpc-port-binding-api` + `sdn-vpc-validation-api`
