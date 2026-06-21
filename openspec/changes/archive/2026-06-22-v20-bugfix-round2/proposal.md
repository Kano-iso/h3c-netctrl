## Why

V2.0 bugfix 第一轮修复了 SSH 分页问题后，用户测试发现：
1. 接口配置路由 404（路径参数含 `/`，FastAPI 不支持）
2. 接口配置命令执行方式错误（多行命令用 `\n` 拼接，invoke_shell 需逐条发送）
3. 日志记录缺少具体错误信息（只有"操作失败"，看不到原因）
4. 前端日志页面展开功能未生效

## What Changes

- 接口配置路由改为 POST + 请求体传接口名（避免路径 `/` 问题）
- SSH 执行器新增 `execute_commands` 方法（逐条发送配置命令）
- 日志模型增加 `error_message` 字段，记录具体报错
- 后端所有操作失败时记录 error_message
- 前端日志展开功能修复

## Capabilities

### Modified Capabilities
- `interface-management`: 修复路由 404 + 多行命令执行
- `log-viewer`: 增加错误详情展示

## Impact

- 后端：interface.py 路由变更（PUT→POST），models.py Log 增加 error_message 字段
- 数据库：logs 表增加 error_message 列（Alembic migration）
- 前端：日志页面修复展开功能
