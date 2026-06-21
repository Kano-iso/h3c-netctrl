## Why

V2.0 实施后发现 SSH 命令执行存在根本性问题：H3C 设备输出带 `---- More ----` 分页提示，`exec_command` 的 stdout.read() 会卡住等待用户输入空格，导致运维终端、CMDB 刷新、接口查询全部超时失败。此外 CMDB 采集了不需要的字段（CPU/内存），缺少有价值的字段（软件包版本），日志页面不展示具体报错信息。

## What Changes

- 修复 SSH 执行器：从 `exec_command` 改为 `invoke_shell` + 分页自动处理
- CMDB 硬件信息采集：去掉 CPU/内存，增加软件包版本
- 日志详情展开：操作日志可查看具体报错信息
- 前端命令执行不阻塞页面：后台执行，可切换页面

## Capabilities

### Modified Capabilities
- `ops-terminal`: 修复 SSH 分页问题，命令执行不再超时
- `cmdb`: 修复资产刷新，优化采集字段（去 CPU/内存，加软件包版本）
- `interface-management`: 修复接口列表获取失败
- `log-viewer`: 日志条目可展开查看具体报错信息

## Impact

- 后端：ssh_executor.py 完全重写（invoke_shell 替代 exec_command）
- 前端：运维终端页面增加后台执行能力，日志页面增加展开功能
- 数据库：assets 表增加 software_package 字段（需 Alembic migration）
