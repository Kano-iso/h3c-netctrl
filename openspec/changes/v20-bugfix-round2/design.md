## Decisions

### D1: 接口配置路由改为 POST + 请求体

**选择**：将 `PUT /devices/{id}/interfaces/{name}/config` 改为 `POST /devices/{id}/interfaces/config`，接口名放在请求体中。

**理由**：H3C 接口名含 `/`（如 `GigabitEthernet1/0/1`），FastAPI 路径参数无法正确解析。

### D2: 多行命令逐条发送

**选择**：新增 `execute_commands` 方法，逐条发送命令并等待响应。

**理由**：`invoke_shell` 模式下，`\n` 拼接的多行命令可能导致命令丢失或顺序错乱。

### D3: 日志增加 error_message 字段

**选择**：Log 模型增加 `error_message` 列，操作失败时记录具体错误。

**理由**：用户反馈"操作失败"无法排错，需要看到具体原因。
