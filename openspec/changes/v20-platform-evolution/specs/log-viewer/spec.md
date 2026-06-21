## Capability: log-viewer (Modified)

V2.0 变更：新增命令执行和批量操作日志类型。

## What Changes

- 日志操作类型新增 `execute`（命令执行）和 `batch_execute`（批量执行）
- 命令执行日志记录具体命令内容
- 批量执行日志记录目标设备数量和成功/失败数
- 前端日志筛选增加新操作类型选项

## API Changes

无新增端点。现有 `GET /api/logs` 的 `action` 筛选参数新增可选值：
- `execute` — 命令执行
- `batch_execute` — 批量执行

## Data Model Changes

logs 表无结构变更，`action` 字段新增两个合法值。

## Acceptance Criteria

- [ ] 命令执行自动记录日志（action=execute）
- [ ] 批量执行自动记录日志（action=batch_execute）
- [ ] 前端日志筛选包含"命令执行"和"批量执行"选项
