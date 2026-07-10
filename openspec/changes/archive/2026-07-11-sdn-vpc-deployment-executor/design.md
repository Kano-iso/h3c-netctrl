# sdn-vpc-deployment-executor — Design

## 架构定位

```
┌──────────┐     POST /api/sdn/deployments/{id}/apply     ┌──────────────┐
│ Frontend │ ─────────────────────────────────────────► │ config 容器  │
└──────────┘                                              │  (FastAPI)   │
                                                          │              │
                                                          │  sdn.py      │
                                                          │  router      │
                                                          └──────┬───────┘
                                                                 │
                                                                 ▼
                                                          ┌──────────────┐
                                                          │ SdnDeployment│
                                                          │   Executor   │
                                                          └──────┬───────┘
                                                                 │
                                                                 ▼
                                                          ┌──────────────┐
                                                          │ NetconfClient│
                                                          │ (existing)   │
                                                          └──────┬───────┘
                                                                 │ edit-config
                                                                 ▼
                                                          ┌──────────────┐
                                                          │   设备 .5    │
                                                          │  (Leaf-04)   │
                                                          └──────────────┘
```

**关键约束**：
- 业务下发**只走 backend**，前端不直接连设备
- ops-toolkit **不参与业务下发**（只做只读排错）
- 单 deployment 串行下发（H3C V7 max-session 限制）

## 类图

```
┌────────────────────────────┐
│  SdnDeploymentExecutor     │
├────────────────────────────┤
│ - db: Session              │
│ - netconf_factory: Callable│
├────────────────────────────┤
│ + execute(                 │
│     db, deployment_id      │
│   ) -> SdnDeployment       │
│                            │
│ + _validate_deployment(    │
│     db, deployment         │
│   ) -> None                │
│                            │
│ + _validate_device(        │
│     device                 │
│   ) -> None                │
│                            │
│ + _parse_planned_config(   │
│     planned_config: str    │
│   ) -> List[ConfigCommand] │
│                            │
│ + _apply_commands(         │
│     commands, host,        │
│     port, user, password   │
│   ) -> None                │
└────────────────────────────┘
         │
         │ uses
         ▼
┌────────────────────────────┐
│  NetconfClient             │
│  (backend/app/             │
│   netconf_client.py)       │
├────────────────────────────┤
│ + edit_config(xml: str)    │
│ + get_config(filter)       │
│ + get(filter)              │
└────────────────────────────┘
```

## 数据流

### POST /api/sdn/deployments/{id}/apply

```
1. router 接收 request
   ├─ 校验 body（空 body，无参数）
   └─ 查 deployment by id
       ├─ 404 → return error
       └─ 校验 status == 'pending'
           ├─ ≠ 'pending' → 409
           └─ OK 继续
2. 调 SdnDeploymentExecutor.execute(db, deployment.id)
3. Executor.execute:
   a. _validate_deployment
      - status 校验
      - action 校验（仅 create）
   b. _validate_device
      - 查 device + 解密密码
      - device.host 白名单校验（仅 .5/.6）
      - 失败 → 422
   c. 解析 planned_config (JSON 字符串)
      - JSONDecodeError → 500
   d. 构造 NetconfClient(host, port, user, password)
      - context manager 进入
      - 逐条 edit_config
        - 失败立即 raise → executor catch → status=failed
      - 全部成功 → status=success
      - context manager 自动关闭
   e. 写回 db（commit + refresh）
4. 返回 SdnDeploymentResponse（最新状态）
```

## 关键决策

### 决策 1：业务执行器放 backend，不用 ops-toolkit

**理由**：
- 前端 → backend → 设备的链路完整，权限/审计/状态都在 backend
- ops-toolkit 是排错工具，不应承担业务职责
- H3C V7 max-session 限制可通过 backend 串行化处理（executor 内部队列）

**已弃用方案**：用 ops-toolkit 写 `vpc-apply.sh` 业务脚本（**已删除**）

### 决策 2：单 deployment 串行下发

**理由**：
- H3C V7 SSH max-session = 6（已知约束，project_memory.md 已记录）
- 并发下发会触发认证队列超时
- 串行足够，VPC 创建命令数 14-20 条，单次下发 < 10s

**未来扩展**：如需并发，每个 executor 实例独立 NETCONF session + 全局 semaphore 限制 ≤ 3

### 决策 3：planned_config 用 JSON 字符串存储

**理由**：
- `VPCConfigPlanner.serialize()` 已用 JSON（`SdnDeployment.planned_config: Text`）
- executor 解析后用 `ConfigCommand(mode, command)` dataclass 还原
- 简单、可序列化、人类可读

### 决策 4：设备白名单（仅 .5/.6）

**理由**：
- .2 / .3 是 SDN 参考机器（仅读，禁止改配置）
- .177 是 test 设备但 NOT production-grade 下发目标
- .5 / .6 是 Leaf-04/05，本次 v3.0 下发目标

**实现**：
- 白名单通过 `device.host` 后缀匹配（192.168.100.5 / 192.168.100.6）
- 不写死在代码里，而是从 `Device.name` 读（如 "Leaf-04" / "Leaf-05"）
- 这样新增可写设备时改 CMDB 即可

### 决策 5：失败立即停 + 不自动回滚

**理由**：
- H3C V7 没有 transaction 概念，命令一旦下发就生效
- 自动回滚可能引发更大问题（半状态）
- 失败时把已成功的命令记在 `error_message`，人工决定是否手动 undo

## 命令下发格式

`planned_config` 序列化的 JSON 形如：
```json
[
  {"mode": "merge", "command": "vsi vpc0001"},
  {"mode": "merge", "command": "  vxlan 20000"},
  ...
]
```

`mode` 对应 NETCONF `default-operation`：
- `merge` → `<config>` 标签内（default-operation=merge）
- `replace` → `<config replace="replace">` 标签
- `delete` → `<config><Interface xmlns="..." operation="delete">`

但目前 H3C V7 大多数配置都是 `merge`，executor 实现简化为：
- 构造 `<config>` XML 包含所有命令（用 H3C 命名空间）
- 调 `NetconfClient.edit_config(xml)`
- 设备会按顺序处理子元素

**简化方案（v1）**：把每条命令作为单独 `<config>` 调用 `edit_config`：
- 优点：单条失败立即停，错误定位准
- 缺点：每条 edit-config 有 SSH 开销（~0.5s × 14 条 = 7s）

**未来优化（v2）**：批量 `<config>` 一次下发：
- 优点：性能好
- 缺点：定位失败命令难
- v3.0 不做，v3.1 优化

## 错误码（i18n_keys.py 新增）

| key | 中文 | 触发场景 |
|---|---|---|
| `SDN_DEPLOYMENT_NOT_FOUND` | 部署记录 {id} 不存在 | POST /apply 时 deployment_id 不存在 |
| `SDN_DEPLOYMENT_NOT_PENDING` | 部署记录 {id} 状态为 {status}，不允许重放 | 已 success / failed 的 deployment 不允许再次 apply |
| `SDN_DEVICE_NOT_WRITABLE` | 设备 {name} 不在可写白名单（仅 .5/.6）| .2/.3/.177 等不允许下发 |
| `SDN_PLANNED_CONFIG_INVALID` | planned_config 格式错误 | JSON 解析失败 |
| `SDN_DEPLOY_EXECUTE_FAILED` | 配置下发失败：{error} | NETCONF edit_config 抛异常 |

## 数据模型（无 schema 变更）

`SdnDeployment` 表已有字段（来自 sdn-vpc-model-and-foundation）：
- `id` (PK)
- `vpc_id` (FK)
- `device_id` (FK)
- `action` ('create' / 'delete')
- `planned_config` (Text, JSON 字符串)
- `status` ('pending' / 'running' / 'success' / 'failed')
- `error_message` (Text, nullable)
- `created_at` / `updated_at` (DateTime)

`status` 状态机：
```
pending ──apply──► running ──ok──► success
                       │
                       └─error──► failed
```

`error_message` 在 status=failed 时填写（中文，含 NETCONF 错误码 + 命令索引）

## 边界与不做的事

- ❌ 不做并发 executor（v3.1 优化）
- ❌ 不做自动回滚（人工决定）
- ❌ 不做 delete 链路（留 sdn-vpc-reset-executor）
- ❌ 不做 status=running 的轮询（同步执行，apply 返回即终态）
- ❌ 不做 WebSocket 实时进度（同步阻塞调用）
- ❌ 不做 dry-run API（前端可调 GET deployment 看 planned_config）
- ❌ 不做权限校验（v3.0 个人项目，无 RBAC）
- ❌ 不做 audit log 写 ctrl（v3.0 暂不集成，留 v3.1）

## 与既有模块的关系

| 依赖 | 用途 |
|---|---|
| `app.netconf_client.NetconfClient` | NETCONF 连接 + edit_config（已有，直接复用）|
| `app.services.vpc_config_planner.VPCConfigPlanner` | 已生成 planned_config，本 change 不调用 |
| `app.services.sdn_preflight.SdnPreflight` | 预检（apply 前调？v1 不调，v2 引入）|
| `app.models.SdnDeployment` | ORM 模型（直接查）|
| `app.utils.device_access.get_device_with_password` | 查 device + 解密密码（已有）|
| `app.i18n_keys.err` | 错误码（新增 5 个）|
| `app.schemas.SdnDeploymentResponse` | 响应（已有，直接复用）|

## pytest 覆盖

`backend/tests/test_sdn_deployment_executor.py`（新增）：
- `test_execute_success`：mock NetconfClient，14 条命令全成功 → status=success
- `test_execute_netconf_error`：mock NetconfClient 第 5 条 raise → status=failed, error_message 含"第 5 条"
- `test_execute_invalid_json`：planned_config 是非法 JSON → status=failed
- `test_validate_device_rejects_readonly`：device.host = .2 → 抛 SDN_DEVICE_NOT_WRITABLE
- `test_validate_deployment_rejects_success`：status=success → 抛 SDN_DEPLOYMENT_NOT_PENDING
- `test_validate_deployment_rejects_delete`：action=delete → 抛 SDN_DEPLOYMENT_ACTION_NOT_SUPPORTED（本 change 仅支持 create）

`backend/tests/test_sdn_apply_endpoint.py`（新增）：
- `test_apply_200_success`：POST → 200，response 含 status=success
- `test_apply_404_not_found`：deployment_id 不存在 → 404
- `test_apply_409_not_pending`：status=success → 409
- `test_apply_422_device_readonly`：device=.2 → 422
