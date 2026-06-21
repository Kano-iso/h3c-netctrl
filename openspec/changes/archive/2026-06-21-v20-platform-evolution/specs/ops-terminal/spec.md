## Capability: ops-terminal

网络运维终端，命令派发式执行。

## Goal

提供命令执行页面，用户输入命令 → 后端通过 paramiko SSH 执行 → 返回文本输出展示。非交互式终端。

## Scope

### In Scope
- 命令输入框 + 执行按钮
- paramiko SSH exec_command 执行命令
- 输出以等宽字体展示，保留原始格式
- 命令历史记录（最近 20 条，存 localStorage）
- 设备选择（下拉列表）
- 执行超时控制（30 秒）
- 操作日志自动记录

### Out of Scope
- 交互式终端（xterm.js + WebSocket）
- Tab 补全、方向键翻历史
- 多命令批处理（由 batch-operations 覆盖）
- 命令白名单/黑名单

## API Changes

### 新增端点
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/devices/{id}/execute | 执行命令 |

**请求体：**
```json
{ "command": "display interface brief" }
```

**响应体：**
```json
{
  "success": true,
  "data": {
    "output": "...",
    "device_name": "SW-Core-1",
    "execution_time": 2.3
  }
}
```

## Data Model Changes

无新表。命令执行结果不持久化，仅记录操作日志（action="execute"）。

## Acceptance Criteria

- [ ] 命令输入框可输入命令，点击执行后展示输出
- [ ] 输出以等宽字体展示，保留原始格式
- [ ] 执行超时（30秒）返回友好错误提示
- [ ] 设备不存在时返回错误
- [ ] 命令历史记录可快速重发
- [ ] 操作日志自动记录（action=execute）
