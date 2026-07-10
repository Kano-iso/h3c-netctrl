# sdn-vpc-deployment-executor — Tasks

| # | Task | 状态 | Commit |
|---|------|------|--------|
| 1 | 文档：proposal / design / tasks / specs（OpenSpec Propose 阶段） | ✅ | c3e4f06 docs(openspec): sdn-vpc-deployment-executor propose |
| 2 | 回滚：删 vpc-apply.sh / vpc-reset.sh + 修 docs/ops-toolkit.md + 修 vpc-show.sh 注释 | ✅ | 515430d fix(ops-toolkit): 撤销 vpc-apply.sh / vpc-reset.sh（业务下发错位） |
| 3 | service 层：SdnDeploymentExecutor（NETCONF edit_config 串行下发） | ✅ | fc7f179 feat(sdn): add SdnDeploymentExecutor (NETCONF 业务下发执行器) |
| 4 | router 层：POST /api/sdn/deployments/{id}/apply 端点 + i18n 错误码 | ✅ | 038d052 feat(sdn-router): add POST /api/sdn/deployments/{id}/apply 端点 |
| 5 | 单测：test_sdn_deployment_executor.py + test_sdn_apply_endpoint.py + error_key 透传补丁 | ✅ | ea7f6e3 test(sdn): executor 单测 + apply 端点测试 (Task 5) |
| 6 | qa-backend 全量 pytest 跑通（与 baseline 对比无 regression） | ✅ | （无 commit，跑测试任务） |
| 7 | Archive 闭环：git mv 到 archive/ + 写 archive 备注 | ⏳ | 待执行 |

## 验收

- [x] `ops-toolkit/scripts/` 不再含 vpc-apply.sh / vpc-reset.sh
- [x] `docs/ops-toolkit.md` vpc-show 章节定位为"排错工具"
- [x] `SdnDeploymentExecutor.execute()` 单元测试 10 用例全过
- [x] `POST /api/sdn/deployments/{id}/apply` 端点测试 9 用例全过
- [x] `qa-backend` 跑全量 pytest：394 passed, 3 failed（pre-existing，见下）
- [x] i18n 错误码 5 个新增 key 在 err 字典中（DEPLOYMENT_NOT_PENDING / DEPLOYMENT_ACTION_NOT_SUPPORTED / DEVICE_NOT_WRITABLE / PLANNED_CONFIG_INVALID / DEPLOY_EXECUTE_FAILED）
- [ ] 真机验证（.5）：POST apply → display l2vpn vsi 看到 vpc0001（**用户在场时执行**）

## qa-backend 跑通情况

```
394 passed, 3 failed, 23 skipped, 40 warnings in 70.25s
```

### SDN 相关测试（67/67 全过）

| 文件 | 用例 | 状态 |
|---|---|---|
| test_sdn_apply_endpoint.py | 9 | ✅ |
| test_sdn_deployment_executor.py | 10 | ✅ |
| test_sdn_deployment_api.py | 13 | ✅ |
| test_sdn_api.py | 19 | ✅ |
| test_sdn_device_adapter.py | 10 | ✅ |
| test_sdn_preflight.py | 6 | ✅ |
| **小计** | **67** | **✅** |

### 3 个 pre-existing 失败（与本 change 无关）

| 失败测试 | 最后改动 | 与 SDN 关系 |
|---|---|---|
| test_async_backup.py::test_backups_async_success_with_2_devices | 360d8fc (v2.4 async-backup) | 无关（backup 链路） |
| test_split_integration.py::test_scenario3_running_backup_split | 7580761 (split 测试) | 无关（backup 链路） |
| test_split_integration.py::test_scenario4_backup_all_async_split | 7580761 (split 测试) | 无关（backup 链路） |

**验证方式**：
- `git log --oneline 515430d^..ea7f6e3 --stat` 只动 `sdn.py / sdn_deployment_executor.py / i18n_keys.py / 4 个 test_sdn_*.py` + ops-toolkit 脚本
- 无 backup 业务代码改动
- 3 个失败是 `success_count == 0 vs 4`（async 任务未完成 / split 模式 task_manager 时序问题），与 SDN deployment 链路无关

**处理**：本 change 不修这 3 个失败（越界改动）。如要修，新建 change 跟进。

## 依赖

- 上游 change：`sdn-vpc-model-and-foundation`（已有 SdnDeployment 表）
- 上游 change：`sdn-vpc-device-templates`（已有 VPCConfigPlanner / SdnPreflight / DeviceAdapter）
- 上游 change：`sdn-vpc-deployment-api`（已有 POST/GET/PATCH deployment 端点）

## 风险

| 风险 | 缓解 |
|---|---|
| H3C V7 max-session 限制导致并发失败 | 单 deployment 串行下发（v1）|
| NETCONF edit_config 半失败（部分成功部分失败）| 失败立即停 + error_message 记录已成功的命令索引 |
| planned_config 格式不对（JSON 损坏）| 解析时 try/except → status=failed |
| 设备白名单漏配（如新增 Leaf-06 需下发）| 写文档说明：白名单从 `Device.name` 读，改 CMDB 即可 |
| 真机下发后状态不一致 | error_message 含 NETCONF 原始错误 + 命令索引，人工决定 undo |
