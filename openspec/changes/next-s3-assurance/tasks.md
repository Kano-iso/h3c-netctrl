# Tasks

- [x] 1. 数据模型：SdnAssurancePolicy（每 VPC 至多一条）+ SdnAssuranceRun（追加式历史），
       SdnVpc 级联关联；Alembic migration 014（幂等、唯一索引/CHECK 约束、空库与 013 旧库可升可降）
- [x] 2. i18n error keys：assurance_policy_version_conflict / assurance_invalid_policy /
       assurance_invalid_cadence / assurance_invalid_response_mode / assurance_invalid_trigger /
       assurance_run_not_found（含 FALLBACK_MESSAGES 注册，test_i18n 一致性通过）
- [x] 3. 纯评估服务 app/services/sdn_assurance.py：overall 四态 + 白名单项 +
       确定性 recommendation 码 + 例外边界（deferred 不吞 blocking）+ facts 白名单快照
- [x] 4. sdn.py 重构：get_vpc_state_projection 载荷抽为 build_projection_payload（行为保持，
       S2-001/004/012/014/016 回归全绿）
- [x] 5. 新路由 app/routers/sdn_assurance.py（prefix /api/sdn）+ main.py 注册：
       策略 GET/PUT（版本乐观并发）、manual run POST、run list（limit/before 分页）/ detail
- [x] 6. 测试 test_s3_001_assurance.py（含原子并发 CAS、脏历史递归白名单与证据不足语义，见 §QA）+ test_sdn_migration.py 增 014 三条
       （建表/约束/索引、幂等、降级）+ test_i18n 一致性
- [x] 7. 前端 API client：getAssurancePolicy / putAssurancePolicy / createAssuranceRun /
       listAssuranceRuns / getAssuranceRun（typed 调用入口，不做页面）
- [x] 8. OpenSpec change next-s3-assurance（proposal/design/spec/tasks/readiness）+
       review-manifest 更新（S3-001 / baseline 3be43b4）+ collaboration.md 索引更新
- [x] 9. 门禁：openspec validate --strict next-s3-assurance、manifest JSON、git diff --check

## QA（全部走隔离 qa-backend 容器）

- 新增 + 受影响回归：test_s3_001_assurance + test_sdn_migration（含 014 三条）+
  test_i18n + S2 state/scope/attention（S2-001/004/012/014/016 + sdn_api）= 全绿。
- 全量后端套件：792 passed / 59 skipped；13 failed 均为 test_ops_toolkit_paramiko
  预存在环境缺口（`ops-toolkit/scripts/_paramiko_batch_exec` 未挂载进 qa 镜像，
  ModuleNotFoundError；该文件上次改动 62df6d0，与本包无关）。
- 前端 API client 变更：lint / build 通过（stack QA 容器内）。

## 明确未实现（如实声明）

- scheduler / scheduled / event 触发；cadence 仅记录产品意图。
- 自动修复 / 根因结论；设备采集/下发。
- S3 前端页面（Codex 后续工作单负责）。
