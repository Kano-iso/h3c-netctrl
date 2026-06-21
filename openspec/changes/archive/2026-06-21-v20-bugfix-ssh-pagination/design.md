## Context

V2.0 使用 `paramiko.SSHClient.exec_command()` 执行命令，但 H3C 设备输出有 `---- More ----` 分页提示，exec_command 无法处理，导致 stdout.read() 阻塞超时。

## Goals / Non-Goals

**Goals:**
- SSH 命令执行支持 H3C 分页自动处理
- CMDB 采集有价值字段（型号/SN/固件版本/软件包版本），去掉 CPU/内存
- 日志页面可展开查看具体报错
- 命令执行不阻塞页面

**Non-Goals:**
- 真正的交互式终端
- 实时流式输出

## Decisions

### D1: invoke_shell 替代 exec_command

**选择**：使用 `invoke_shell()` 打开交互式 shell，自动检测 `---- More ----` 并发送空格继续。

**理由**：
- exec_command 无法处理分页，是所有 bug 的根因
- invoke_shell 模拟真实终端，可以发送空格翻页
- 需要额外处理 ANSI 转义序列和命令回显

### D2: CMDB 去掉 CPU/内存，加软件包版本

**选择**：CPU/内存属于监控场景，CMDB 只保留静态资产信息。

**理由**：
- CPU/内存是动态数据，刷新后很快过时
- 软件包版本（boot image）是静态资产信息，更有价值
- 用户明确反馈 CPU/内存不需要

## Risks / Trade-offs

| 风险 | 应对 |
|------|------|
| invoke_shell 输出含 ANSI 转义 | 正则清理 |
| 命令回显需去除 | 去掉第一行匹配命令的文本 |
| 不同设备分页提示格式不同 | 匹配多种格式 |
