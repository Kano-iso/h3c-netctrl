# sdn-vpc-deployment-executor — Tasks

| # | Task | 状态 | Commit |
|---|------|------|--------|
| 1 | 文档：proposal / design / tasks / specs（OpenSpec Propose 阶段） | ⏳ | 待提交 |
| 2 | 回滚：删 vpc-apply.sh / vpc-reset.sh + 修 docs/ops-toolkit.md + 修 vpc-show.sh 注释 | ⏳ | 待提交 |
| 3 | service 层：SdnDeploymentExecutor（NETCONF edit_config 串行下发） | ⏳ | 待提交 |
| 4 | router 层：POST /api/sdn/deployments/{id}/apply 端点 + i18n 错误码 | ⏳ | 待提交 |
| 5 | 单测：test_sdn_deployment_executor.py + test_sdn_apply_endpoint.py | ⏳ | 待提交 |
| 6 | qa-backend 全量 pytest 跑通（与 baseline 对比无 regression） | ⏳ | 待执行 |
| 7 | Archive 闭环：git mv 到 archive/ + 写 archive 备注 | ⏳ | 待执行 |

## 验收

- [ ] `ops-toolkit/scripts/` 不再含 vpc-apply.sh / vpc-reset.sh
- [ ] `docs/ops-toolkit.md` vpc-show 章节定位为"排错工具"
- [ ] `SdnDeploymentExecutor.execute()` 单元测试 6+ 用例全过
- [ ] `POST /api/sdn/deployments/{id}/apply` 端点测试 4+ 用例全过
- [ ] `qa-backend` 跑全量 pytest（baseline 225+ passed 无 regression）
- [ ] i18n 错误码 5 个新增 key 在 err 字典中
- [ ] 真机验证（.5）：POST apply → display l2vpn vsi 看到 vpc0001

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
