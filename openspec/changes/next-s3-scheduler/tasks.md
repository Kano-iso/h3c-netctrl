# Tasks

- [x] 1. 数据模型：SdnAssuranceSlot（每 VPC 至多一条窗口状态机）+ SdnAssuranceRun 加
       slot_key/error、status CHECK 扩展含 failed；SdnVpc 级联关联；Alembic 迁移 015
       （slots 表 + runs 重建，幂等可升降，014 数据保持）
- [x] 2. 调度服务 app/services/sdn_assurance_scheduler.py：tick_once（同步可测）+ 轮询
       线程；CAS 认领/完成/失败/推进（rowcount 校验）；lease 过期接管；重启恢复；
       cadence 改变续跑不补跑；批量上限；SERVICE_NAME 门控
- [x] 3. 公共评估持久化：services/sdn_assurance.persist_assurance_run / persist_failed_run
       （manual 与 scheduled 共用同一投影/白名单路径；失败诚实记录）
- [x] 4. 路由适配：manual run 改用公共路径（行为不变）；GET 策略附加
       schedule_status/next_due/last_scheduled_at（只读）；run 序列化附加 slot_key/error
- [x] 5. 生命周期接线：main.py startup 启动（config/core + enabled）、shutdown 停止；
       config 增 4 项（ENABLED/INTERVAL/LEASE/TICK_MAX）；SQLite 引擎 timeout=5；
       conftest 默认关闭
- [x] 6. 对抗测试 test_s3_002_scheduler.py：并发唯一 winner / 重复 tick 幂等 /
       禁用与 manual 跳过 / cadence 改变 / 重启恢复 / lease 边界 / 失败诚实可重试 /
       旧代际迟到不覆盖 / SERVICE_NAME 门控 / 线程 start-stop / 零设备 I/O 与零业务
       写副作用 / 批量上限 / GET 调度信息 / 手动向后兼容；test_sdn_migration.py 增
       015 三条（升级建表与数据保持、幂等、降级）
- [x] 7. OpenSpec change next-s3-scheduler（proposal/design/spec/tasks/readiness）+
       review-manifest 更新（S3-002 / baseline 845a2fe）+ collaboration.md 索引更新
- [x] 8. 门禁：openspec validate --strict next-s3-scheduler 与 next-s1-backend、
       manifest JSON、git diff --check
- [x] 9. CR61（Codex 复审窄返工）：
       - run 与 slot 终态原子：scheduled run flush 与 owner-aware terminal CAS 同一事务，
         CAS 0 行 / 唯一约束命中 → 整个事务 rollback，不留 orphan/重复历史；manual 保持
         S3-001 事务语义
       - DB 防御唯一索引 uq_sdn_assurance_runs_vpc_slot_key（ORM 与迁移 015 命名一致，
         SQLite NULL 允许多个 manual；重复升级/降级保持）
       - terminal CAS 增加 status='claimed' 匹配并清空 claim_token/claimed_at/lease；
         同 token 重放 / complete→fail / 旧 token / 旧 generation 均 0 行不改 run_id/status
       - claimed 未过期时 cadence/策略版本变化不抢代际：先收尾，后续 tick 按新策略推进
       - 批量上限计入每 tick 全部持久化窗口变更（建窗口/认领评估/terminal 推进/
         policy-change 推进），纯只读跳过不计
       - 对抗测试：takeover 迟到唯一 run、terminal CAS 重放不可改写、claimed 未过期不抢
         代际、20+ slot 下 max_slots=2 恰 2 个被修改、migration/ORM 唯一索引命名一致
- [x] 10. CR62（Codex 终审所有权快照）：认领 token 显式传入评估入口，评估前校验
        generation/status/token；异常 rollback 前脱离 slot owner 快照，防止 SQLAlchemy
        过期刷新后误取接管者 token。覆盖“执行前已接管”与“执行中接管后旧
        owner 异常”两种顺序。

## QA（qa-backend 容器，真实 SQLite）

- `pytest tests/test_s3_002_scheduler.py tests/test_sdn_migration.py -q`：**34 passed**
- `pytest tests/test_s3_001_assurance.py tests/test_i18n.py tests/test_sdn_api.py tests/test_s2_016_attention.py -q`：
  **78 passed**（S3-001 全部 + i18n + 受影响回归，行为保持）
- 前端：本轮无前端源码变更（GET 策略字段为服务端附加，API client 不变）
