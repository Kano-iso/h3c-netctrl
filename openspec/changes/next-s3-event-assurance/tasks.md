# Tasks

- [x] 1. 数据模型：SdnAssuranceRun.event_key（String 128 nullable）+ 具名唯一索引
       uq_sdn_assurance_runs_event_key（manual/scheduled NULL 不受影响）；迁移 016
       （加列 + 唯一索引，幂等可升降，降级重建回 015 schema 并保留 CR61 索引）
- [x] 2. 事件服务 services/sdn_assurance_events.py：record_event_check——未配/禁用零 run、
       manual cadence 不挡事件；复用 S3-001 投影/白名单；先占 event_key（唯一防御）再评估；
       成功 completed / 失败 failed（诚实 overall=None）；绝不向调用方抛异常
- [x] 3. 路由钩子（sdn.py）：sync 成功（含 cached 命中同一快照，去重兜底）→
       snapshot:{id}；scope-exception 新增/修改 → scope-exc:{id}:v{version}；清除 →
       scope-exc:{id}:cleared；业务事务 commit 后触发，双保险 try/except
- [x] 4. run 序列化附加只读 event_key（manual/scheduled 为 None）；既有字段不变
- [x] 5. 对抗测试 test_s3_003_event_assurance.py：快照事件+重试去重 / scope 增改清除三条 /
       禁用与无策略零 run、manual cadence 仍检查 / 评估失败不破坏业务且留 failed run /
       零设备 I/O 零业务副作用 / hook 层去重 / event_key 只读审计且无凭据；迁移 016 三条
       （升级建列+索引+去重拒绝+重复升级、降级移除、ORM 一致）
- [x] 6. OpenSpec change next-s3-event-assurance（proposal/design/spec/tasks/readiness）+
       review-manifest 更新（S3-003 / baseline 9ea4a2b）+ collaboration.md 索引更新
- [x] 7. 门禁：openspec validate --strict next-s3-event-assurance、
       manifest JSON、git diff --check

## QA（qa-backend 容器，真实 SQLite）

- `pytest tests/test_s3_003_event_assurance.py tests/test_sdn_migration.py -q`：**25 passed**
- 直接受影响回归 `test_s3_001_assurance / test_s3_002_scheduler / test_s2_014_scope_exception /
  test_s1_006|007|008_adversarial / test_sdn_api / test_i18n / test_s2_016_attention`：
  **169 passed**
- 隔离真实应用栈：**6 passed + BOUNDARY_OK + STACK_QA_OK**（GUARD 展示 scope-exception
  新增/清除产生的两条 event 历史，设备 I/O 计数不增长）
- 前端：无生产源码变更；复用既有 GUARD trigger 标签与历史列表（API client 不变）
