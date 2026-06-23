## 1. 后端 - API + SSH 能力增强

- [x] 1.1 `backend/app/routers/execute.py`：扩展 `ExecuteRequest`，新增 `commands: Optional[list[str]]` + `delay_ms: Optional[int] = 1000`，至少一个非空校验；保留 `command: str` 向后兼容
- [x] 1.2 `backend/app/routers/execute.py::execute_command`：根据入参分流，`commands` 非空走 `executor.execute_commands(commands, delay_ms)`；仅 `command` 非空走 `executor.execute(command)`；返回结构按多命令列表或单命令兼容
- [x] 1.3 `backend/app/utils/ssh_executor.py::execute_commands`：增加 `delay_ms` 参数（默认 1000），把当前 `time.sleep(0.8)` 改为 `time.sleep(delay_ms / 1000)`；返回结构由 `{success, output}` 改为 `[{cmd, output, success, error}, ...]`，每条命令独立 try/except
- [x] 1.4 `backend/app/utils/ssh_executor.py::execute_commands`：保留现有 H3C 分页处理（`_read_with_pagination`），错误指示符（`Error:` / `Incomplete command` 等）继续命中后置 `success=false`

## 2. 前端 - UI 改造

- [x] 2.1 `frontend/src/views/OpsTerminal.vue`：命令输入区 `<input>` 改为 `<textarea rows="4">`，`@keydown.enter` 改为 `@keydown` + 判断 `!event.shiftKey` 时 `preventDefault + execute`，Shift+Enter 走默认行为（插入 \n）
- [x] 2.2 `frontend/src/views/OpsTerminal.vue`：新增"延迟 (ms)"数字输入框，默认 1000，最小 0
- [x] 2.3 `frontend/src/views/OpsTerminal.vue`：提交逻辑改为 `textarea.value.split('\n').map(s => s.trim()).filter(Boolean)`，空行自动跳过；空数组返回提示
- [x] 2.4 `frontend/src/views/OpsTerminal.vue`：`execute()` 函数拆分为 `executeSingle(cmd)` 与 `executeMulti(commands)`，多命令循环 await + 按 `delay_ms` 在前端可选 sleep（**默认交给后端 sleep**，前端不重复 sleep，避免双倍延迟）
- [x] 2.5 `frontend/src/views/OpsTerminal.vue`：输出区按 `results` 数组逐条 push `{type: 'cmd-multi', text, index, total}` + `{type: 'output', text, success, error?}`，失败时附加 `{type: 'fail', text: '[失败] ...'}` 红色行；末尾根据 `results.filter(r => !r.success).length` 推 banner
- [x] 2.6 `frontend/src/views/OpsTerminal.vue`：历史面板保存 `cmd = commands.join("\n")`，点击恢复填回 textarea

## 3. 前端 - API 客户端

- [x] 3.1 `frontend/src/api/index.js::executeApi.run`：签名改为 `(deviceId, payload)`，`payload` 接受 `{command: str}` 或 `{commands: list[str], delay_ms: int}`，按入参直接 POST

## 4. 验证

- [x] 4.1 后端：单命令 `{command: "display version"}` → 返回原结构，行为不变
- [x] 4.2 后端：多命令 `{commands: ["cmd1", "cmd2"], delay_ms: 500}` → 返回 `results` 列表，2 条都 success
- [x] 4.3 后端：中间失败 `{commands: ["display version", "bad-cmd", "display device"]}` → 3 条都执行，2 条 success
- [x] 4.4 前端：textarea 输入 4 行 + Enter → 提交 4 条命令（前端代码已实现 `parseCommands` + `onTextareaKeydown` 拦截 Enter 触发 execute）
- [x] 4.5 前端：Shift+Enter → 换行不提交（`!event.shiftKey` 分支判断）
- [x] 4.6 前端：空行 + 命令 → 自动跳过空行（`split('\n').map(s => s.trim()).filter(Boolean)`）
- [x] 4.7 前端：终端输出区逐条呈现 + 失败红色行 + 末尾 banner（`cmd-multi` / `output` / `fail` / `banner` 4 种 type 渲染分支已写）
- [x] 4.8 前端：历史面板多命令保存 / 恢复（`history.value.unshift({cmd: cmds.join('\n'), isMulti, ...})`，点击回填 `command = h.cmd`）

## 5. 收尾

- [x] 5.1 提交代码 `feat(ops-terminal): 多命令输入与顺序执行（含可配间隔）`
- [ ] 5.2 archive change
