# review-report-process Specification

## Purpose
TBD - created by archiving change v242-3container-review. Update Purpose after archive.
## Requirements
### Requirement: 3 容器 + 双 qa + ops-toolkit 成熟度 review 报告

每个发版周期结束（v2.4.2 / v2.5 / v3.0...）MUST 产出 1 份 review 报告，存 `docs/REVIEW-<version>-<topic>.md`：

- **覆盖范围**：
  - 容器边界 review（路由归属 / 数据归属 / 跨容器调用）
  - QA 容器成熟度 review（单测数 / 跑测时间 / 覆盖率 / 用户体验）
  - ops-toolkit 工具容器成熟度 review（脚本使用频率 / 文档发现 / 默认设备）
  - 下一版本候选 backlog（量化理由 + P0/P1/P2/P3 优先级）
- **格式**：每块按 4 维度写（现状 / 痛点 / 建议 / 优先级）
- **总体评分**：每块 1 个字母评分（A/B/C/D/F）+ 1 句话理由
- **重要约束**：review 报告**只产出评估**，不写新代码。发现的 bug / 优化 / 重构 → 写到下版本 backlog，不在本 change 实施
- **不发版约束**：review 报告不阻塞发版（v2.4.2 即使 review 没写完也可发版）

#### Scenario: v2.4.2 review 报告完成

- **WHEN** v2.4.2 全部 3 个 change（qa-and-tooling / perf-and-e2e / 3container-review）收尾
- **THEN** `docs/REVIEW-v242-3container-maturity.md` MUST 存在
- **AND** 4 大块 review 都覆盖
- **AND** v2.5 backlog 候选每条都有量化理由

#### Scenario: review 报告被 user review

- **WHEN** review 报告写完
- **THEN** user MUST 看过报告内容
- **AND** 决定 v2.5 backlog 哪些进 P0

#### Scenario: review 报告不影响其他 change 实施

- **WHEN** v2.4.2 Change 1（qa-and-tooling）和 Change 2（perf-and-e2e）实施中
- **THEN** Change 3（3container-review）可并行 / 串行，但**不修改 Change 1/2 的代码**
- **AND** Change 3 自身的产出物只有 review 报告
