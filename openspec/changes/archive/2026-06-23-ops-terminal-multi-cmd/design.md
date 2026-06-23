## Context

发布前接口下发失败（`fix-interface-trunk-deploy` change）落地后，用户确认走 CLI 手工兜底路径。但当前 `OpsTerminal.vue` 单 input + 单命令无法支持多命令场景（如 trunk 配置最少 3 条命令）。

关键现状：
- 后端 `SSHExecutor.execute_commands(commands: list)` **已实现**（ssh_executor.py L120-157），含 H3C 分页处理、错误检测、单 SSH 连接复用
- 后端路由 `POST /api/devices/{id}/execute` **只接受单 command**（execute.py L18-19），未暴露多命令 API
- 前端 `executeApi.run(deviceId, command)` 单字符串签名
- 上一 change `fix-interface-trunk-deploy` proposal.md 第 53-54 行已声明"后续 trunk + allowed_vlans 走 SSH/CLI 路径"，但前端工具链缺位

## Goals / Non-Goals

**Goals:**
- 后端 `/api/devices/{id}/execute` 支持 `commands: list[str] + delay_ms: int`，向前兼容 `command: str`
- 后端 `execute_commands` 返回结构由 `"success/!success 单 output"` 改为 `[{"cmd", "output", "success", "error"}, ...]`
- 前端运维终端用 `<textarea>` 替代 `<input>`，支持 Shift+Enter 换行 / Enter 执行
- 前端按用户配置 `delay_ms`（默认 1000）控制命令间隔
- 终端输出区**逐条插入**每条命令的回显与输出，遇错继续
- 历史命令按多命令模板存，点击恢复整段

**Non-Goals:**
- 不实现并行多设备执行（已有 `/api/batch/execute`）
- 不实现脚本变量替换 / 条件分支（仅纯顺序）
- 不改 H3C 分页处理逻辑（已成熟，沿用）
- 不改 `record_log` 单条记录策略（仍按 batch 记一行）
- 不引入命令预设 / 收藏夹（后续 change）

## Decisions

### 1. API 入参兼容：双模式

- **选择**：`ExecuteRequest` 接受 `command: Optional[str]` + `commands: Optional[list[str]]` + `delay_ms: Optional[int]`，**至少一个非空**
- **理由**：保留向后兼容（已有前端、其他调用方不破坏）；`commands` 优先于 `command`（前端默认走 commands）
- **替代**：拆两个 endpoint（`/execute` + `/execute-multi`）。评估后双模式更简单，前端可控

### 2. 错误处理：遇错继续

- **选择**：每条命令独立 try/except，**不中断**后续命令；返回 `[{cmd, output, success, error}, ...]` 列表
- **理由**：CLI 场景下用户往往输入多条配置（进入 system-view → interface → 配置 → 退出），前一条失败不阻塞后续；用户根据输出判断结果
- **替代**：遇错立即停。用户决策明确拒绝此方案
- **实现**：`execute_commands` 已有 try/finally + error_indicators 字符串匹配，可继续沿用并细化返回值

### 3. 命令间隔 sleep

- **选择**：`executor.execute_commands(commands, delay_ms=1000)` 在每条命令发送后 `time.sleep(delay_ms / 1000)`
- **理由**：H3C 设备命令执行需要时间完成状态切换（如 system-view → interface），且 SSH 通道存在缓冲；1000ms 保守默认可避免丢响应
- **替代**：动态等待"提示符出现"再发下一条。实现复杂，且 H3C 提示符在配置模式下会变（`<H3C>` → `[H3C]`），不通用
- **用户偏好**：明确 1000ms 保守默认 + 暴露 UI 可调

### 4. 前端 textarea + Enter 行为

- **选择**：
  - `<textarea rows="4">` 替代 `<input>`（4-5 行可视）
  - `Shift+Enter` 插入 `\n`
  - `Enter`（无 shift）触发 execute
  - 在 `<textarea>` 的 `@keydown` 事件中根据 `event.shiftKey` 区分
- **理由**：用户明确要求 Enter 不直接换行（避免误发送）
- **替代**：
  - 显式"执行"按钮（已有，保留作 fallback）
  - `<textarea>` + Ctrl+Enter（用户已选 Shift+Enter）

### 5. 输出区呈现：逐条插入

- **选择**：每条命令执行后立即 `output.value.push(...)` 一次，输出区形成"命令 → 输出 → 命令 → 输出"的时序流
- **理由**：用户决策明确，时序可追踪
- **替代**：合并输出（一条 command 行 + 一个大输出块）。用户拒绝
- **前端实现**：在 `await executor.execute_commands` 之后按 `commands.length` 循环插入（前端需重构为循环调用 `executor.execute` 单次或后端改为流式返回）。**当前选择**：后端一次返回全列表，前端循环 push 即可，无需 SSE

### 6. 历史命令：存拼接字符串

- **选择**：历史面板按 `commands.join('\n')` 存为一个 `cmd` 字段，点击恢复填回 textarea
- **理由**：恢复后用户可编辑单条，UX 简单
- **替代**：存结构化 `{commands: []}`。评估后字符串已足够

### 7. 后端日志策略

- **选择**：`record_log` 仍按一次 batch 写一条 `action=execute`，`detail` 字段包含 `N 条命令: cmd1\ncmd2\n...`
- **理由**：与现有日志粒度一致，不污染日志表
- **替代**：每条命令写一行。**非目标**（声明在 Non-Goals）

## Risks / Trade-offs

- **[风险] 1000ms 默认延迟 + N 条命令 → 总耗时 N 秒** → **缓解**：UI 暴露 delay_ms 输入框，用户可临时改小；状态栏显示进度（"执行 3/10..."）
- **[风险] 遇错继续策略下，部分配置可能半成品** → **缓解**：UI 在输出末尾用红色 banner 提示"X 条失败"；用户可按需在 CLI 手工撤销
- **[风险] 文本框换行不严格（用户复制粘贴混入空行）** → **缓解**：前端提交前 `split('\n').map(s => s.trim()).filter(Boolean)`，自动跳过空行
- **[风险] `time.sleep(1)` 在 FastAPI 同步路由中阻塞** → **缓解**：保持当前 `/execute` 路由同步（已有同模式），不引入 async 重构；长命令用户接受 N 秒等待
- **[风险] H3C 错误检测靠字符串匹配（"Error:", "Unrecognized command"）** → **缓解**：沿用现有 `execute_commands` 实现，不在本 change 范围
- **[回归] 现有调用 `/execute` 传 `command: str` 的代码** → **缓解**：双模式入参，`command` 仍按原路径走 `executor.execute`

## Migration Plan

- **部署**：后端容器重启即可（无 DB 迁移、无新依赖）；前端 vite HMR
- **回退**：移除前端 textarea + 后端新参数兼容即可，旧 `command: str` 路径不受影响
- **数据**：无 schema 变更
- **历史命令**：旧 history 数据 `cmd: "display version"` 在前端仍可读（直接赋值给 textarea.value 即可）
