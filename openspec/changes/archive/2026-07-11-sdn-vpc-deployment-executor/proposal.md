# sdn-vpc-deployment-executor — 业务配置下发的 backend NETCONF 执行器

## Why

sdn-vpc-device-templates change（已 archive 2026-07-10）实现了 `SdnDeviceAdapter` / `VPCConfigPlanner` / `SdnPreflight`，并在 ops-toolkit 里加了 `vpc-apply.sh` / `vpc-reset.sh` / `vpc-show.sh` 三个脚本，**但犯了架构错位**：

- **业务配置下发（写设备）** 被放进了 `ops-toolkit`（排错工具容器）
- 前端要触发下发时，**没有 backend API 端点可调**，只能让用户在 ops-toolkit 容器里手跑 `vpc-apply.sh`
- 排错工具容器的运维职责 = 设备诊断 / 抓配置 / 排错，**不是业务配置下发**

**用户反馈原话**："业务代码为什么不用 NETCONF？而且这都是啥方式啊？咱这个联动是用这玩意儿联动的，这东西怎么说呢？你想哈，我点一下前端，难道还能去联动一下这个叫什么来着？排错排错容器吗？那不可能啊。"

**正解**：
1. 删除 `vpc-apply.sh` / `vpc-reset.sh`（业务脚本不属于排错工具）
2. 在 backend 实现 `SdnDeploymentExecutor`，通过 `NetconfClient.edit_config` 下发 `planned_config` 中的命令
3. 新增 `POST /api/sdn/deployments/{id}/apply` 端点，让前端 → config 容器 → NETCONF → 设备形成端到端链路
4. `vpc-show.sh` **保留**（只读排错，符合 ops-toolkit 定位）

## What Changes

### 主线 1：删除业务脚本（**已删，待 commit**）

- 删除 `ops-toolkit/scripts/vpc-apply.sh`
- 删除 `ops-toolkit/scripts/vpc-reset.sh`
- 修改 `docs/ops-toolkit.md`：删 vpc-apply / vpc-reset 章节，重写 vpc-show 章节定位为"排错工具"
- 修改 `ops-toolkit/scripts/vpc-show.sh`：注释说明"业务下发走 backend 端点"

### 主线 2：SdnDeploymentExecutor（backend service）

新文件 `backend/app/services/sdn_deployment_executor.py`：

```python
class SdnDeploymentExecutor:
    """读 SdnDeployment.planned_config → NETCONF edit-config → 写回 status

    设计要点：
    - 走 NetconfClient（已有：backend/app/netconf_client.py）
    - 单 deployment 串行下发（避免 H3C V7 max-session 限制）
    - 失败时立即停 + 记录 error_message + status=failed
    - 成功时 status=success
    - 设备级：仅 .5 / .6（Leaf-04/05）允许下发，.2 / .3 拒绝
    """

    def execute(self, db: Session, deployment_id: int) -> SdnDeployment:
        # 1. 读 deployment + 校验（状态为 pending）+ 设备白名单（.5/.6）
        # 2. 解密设备密码
        # 3. 解析 planned_config JSON → List[ConfigCommand]
        # 4. NetconfClient context manager → 逐条 edit_config
        # 5. 失败：status=failed, error_message=...
        # 6. 成功：status=success
        # 7. 返回 deployment 对象
```

### 主线 3：POST /api/sdn/deployments/{id}/apply 端点

`backend/app/routers/sdn.py` 新增：

- `POST /api/sdn/deployments/{id}/apply` — 调 `SdnDeploymentExecutor.execute()`，返回最新 deployment 状态
- 仅允许 `action=create` 的 deployment 调用（delete 用 reset change，不在本 change）
- 业务规则：
  - deployment.status 必须为 `pending`（不允许重放已完成的）
  - device 必须在白名单（仅 Leaf-04/05 = .5/.6）
  - 失败时返回中文 i18n 错误码 + deployment.error_message

### 主线 4：单测

`backend/tests/test_sdn_deployment_executor.py`：
- 成功路径：pending → success，mock NetconfClient
- 失败路径：NETCONF 抛异常 → status=failed，error_message 写入
- 设备白名单：.2 / .3 直接拒绝（SDN 参考机）
- 状态校验：非 pending 状态拒绝（如 success / failed 不允许重放）

`backend/tests/test_sdn_apply_endpoint.py`：
- 200：POST apply 成功
- 404：deployment_id 不存在
- 409：deployment.status ≠ pending
- 422：device 不在白名单

## 不在本 change 范围

- **SdnPortBinding API + 端口绑定执行器**：留 `sdn-vpc-port-binding-api`（下个 change）
- **SdnValidationSnapshot 采集**：留 `sdn-vpc-validation-api`（状态采集）
- **SdnDeployment 删 VPC（action=delete）的执行**：留 `sdn-vpc-reset-executor`（VPC 删除链路）
- **UI 按钮 / 状态显示**：留 `sdn-frontend-vpc-page`（v3.0 UI）

## 影响范围

| 文件 | 改动 |
|---|---|
| `ops-toolkit/scripts/vpc-apply.sh` | **删除** |
| `ops-toolkit/scripts/vpc-reset.sh` | **删除** |
| `ops-toolkit/scripts/vpc-show.sh` | 注释更新（说明排错定位） |
| `docs/ops-toolkit.md` | 删 vpc-apply/vpc-reset 章节，重写 vpc-show |
| `backend/app/services/sdn_deployment_executor.py` | **新增** |
| `backend/app/routers/sdn.py` | 新增 POST apply 端点 |
| `backend/app/schemas.py` | 新增 SdnDeploymentApplyResponse（如需要） |
| `backend/app/i18n_keys.py` | 新增 SDN_DEPLOYMENT_NOT_PENDING / SDN_DEVICE_NOT_WRITABLE 等错误码 |
| `backend/tests/test_sdn_deployment_executor.py` | **新增** |
| `backend/tests/test_sdn_apply_endpoint.py` | **新增** |

## 验收标准

- [ ] `vpc-apply.sh` / `vpc-reset.sh` 已删除，git log 中无残留
- [ ] `ops-toolkit/scripts/` 仅保留 `vpc-show.sh`（只读工具）
- [ ] `docs/ops-toolkit.md` vpc-show 章节定位为"排错工具"，对比表指向 backend 端点
- [ ] `SdnDeploymentExecutor.execute()` 单元测试全过（4+ 场景）
- [ ] `POST /api/sdn/deployments/{id}/apply` 端点测试全过（4+ 场景）
- [ ] `qa-backend` 全量 pytest 通过（与 baseline 对比无 regression）
- [ ] 真机验证（.5 设备）：`POST /apply` 真实下发后 `display l2vpn vsi` 能看到对应 VSI
- [ ] `.2 / .3`（SDN 参考机）调用 apply 直接 422
