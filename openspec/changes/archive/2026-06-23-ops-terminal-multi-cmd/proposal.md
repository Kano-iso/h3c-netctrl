## Why

运维终端当前只支持单命令（`executeApi.run` 接 `command: str`）。用户手工兜底配置 trunk 时，需要多条命令连续下发：

```
interface GigabitEthernet 1/0/1
port link-type trunk
port trunk permit vlan 10,20,30
```

**来源**：上一 change `fix-interface-trunk-deploy`（commit f914a74）实施"NETCONF 走不通时改走 CLI 兜底"，但前端无工具链支持多命令输入，用户只能每条单独发送，配置 trunk 实际不可用。

**关键发现**：后端 `SSHExecutor.execute_commands(commands: list)` **已经存在**（ssh_executor.py L120-157），但 `/api/devices/{id}/execute` 路由**只接受单 command**（execute.py L18-19），API 层未暴露多命令能力。

## What Changes

- **后端 `execute.py`**：扩展 `ExecuteRequest` 接受 `commands: list[str]`（或保留向后兼容的 `command: str`），`execute_command` 路由根据入参选择 `executor.execute(command)` 或 `executor.execute_commands(commands)`；每条命令逐条执行，按用户配置 `delay_ms` 在命令间 sleep；遇错继续，输出按"命令→输出"分块返回
- **后端 `ssh_executor.py`**：增强 `execute_commands` 支持可配 `delay_ms`（默认 1000ms），返回结构改为 `[{cmd, output, success, error}, ...]` 列表
- **前端 `OpsTerminal.vue`**：单行 `<input>` 改为多行 `<textarea>`（4-5 行可视），新增"延迟 (ms)"输入框（默认 1000），Shift+Enter 换行、Enter 提交；提交时按 `\n` 拆分 strip 空行；终端输出区**逐条插入** `[CMD n/m] cmd` + 输出 + 失败标记
- **前端 `api/index.js`**：`executeApi.run` 签名扩展为 `(deviceId, payload)`，`payload` 接受 `{command: str}` 或 `{commands: list[str], delay_ms: int}`
- **历史命令**：保存多命令模板（join 后的字符串），点击恢复
- **日志**：`logs` 表 `action=execute` 单条记录包含命令数 + 拼接内容；每条命令单独记一行（如需可在后续 change 加细粒度日志）

## Capabilities

### New Capabilities
- `ops-terminal-multi-cmd`：运维终端多命令输入与顺序执行能力

### Modified Capabilities
- （无现有 spec 修改）

## Impact

- **代码**：
  - `backend/app/routers/execute.py`：扩展入参与执行逻辑
  - `backend/app/utils/ssh_executor.py`：增强 `execute_commands` 签名
  - `frontend/src/views/OpsTerminal.vue`：UI 改造
  - `frontend/src/api/index.js`：API 客户端扩展
- **API 兼容性**：
  - 保留 `command: str` 入参向后兼容（已有调用方不需改动）
  - 新增 `commands: list[str] + delay_ms: int` 入参
- **数据库**：无迁移
- **依赖**：无新增
- **回归**：单命令路径行为不变（仍走 `executor.execute`）
- **安全**：单设备单 SSH 连接，不引入多设备并发
