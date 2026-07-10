# sdn-vpc-deployment-api — Tasks

| # | Task | 状态 | Commit |
|---|------|------|--------|
| 1 | schemas.py 扩展（SdnDeploymentCreate + SdnDeploymentResponse） | ⏳ | 待提交 |
| 2 | sdn.py router 扩展（POST/GET/GET-list/PATCH deployment） | ⏳ | 待提交 |
| 3 | 单测 test_sdn_deployment_api.py（5+ 测试） | ⏳ | 待提交 |
| 4 | Archive 闭环 | ⏳ | 待执行 |

## 验收

- [ ] POST /api/sdn/deployments 返回 14 条命令
- [ ] GET /api/sdn/deployments/{id} 返回完整 deployment
- [ ] vpc-apply --deployment {id} --device .5 --dry-run 端到端跑通
