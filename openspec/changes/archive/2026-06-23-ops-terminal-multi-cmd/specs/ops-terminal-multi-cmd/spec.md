## ADDED Requirements

### Requirement: 后端 execute 端点支持多命令顺序执行

`POST /api/devices/{id}/execute` MUST 接受 `commands: list[str]` 入参（与现有 `command: str` 二选一，不能同时为空），按顺序在设备 SSH 通道上逐条执行，每条命令之间按 `delay_ms` 等待（默认 1000ms）。任一条命令执行失败 MUST 不中断后续命令执行。返回结果 MUST 为列表结构 `[{cmd, output, success, error}, ...]`，与每条命令一一对应。

#### Scenario: 多命令全部成功
- **WHEN** 调用 `POST /api/devices/{id}/execute`，body 为 `{commands: ["display version", "display device"]}`
- **THEN** 端点按顺序在 SSH 通道执行两条命令，每条 sleep 1000ms；返回 `success=true`，`data.results = [{cmd, output, success=true, error=null}, {cmd, output, success=true, error=null}]`

#### Scenario: 中间命令失败仍继续
- **WHEN** 调用 `POST /api/devices/{id}/execute`，body 为 `{commands: ["display version", "this-is-bad-cmd", "display device"]}`
- **THEN** 端点执行完 3 条命令，**不因第 2 条失败而停止**；返回 `success=true`，`data.results` 中第 2 条 `success=false, error` 含错误描述，第 1/3 条仍 `success=true`

#### Scenario: 向后兼容单命令
- **WHEN** 调用 `POST /api/devices/{id}/execute`，body 为 `{command: "display version"}`
- **THEN** 端点走原有 `executor.execute(command)` 路径，返回结构与变更前一致

#### Scenario: 间隔可配
- **WHEN** 调用 `POST /api/devices/{id}/execute`，body 为 `{commands: ["cmd1", "cmd2"], delay_ms: 500}`
- **THEN** 第 1 条执行后 sleep 500ms 再发第 2 条（验证可通过命令时间戳或 SSH trace）

#### Scenario: 空入参拒绝
- **WHEN** 调用 `POST /api/devices/{id}/execute`，body 为 `{command: "", commands: []}` 或两者均为空
- **THEN** 端点返回 `success=false, error="命令不能为空"`

### Requirement: 前端运维终端支持多命令输入

`frontend/src/views/OpsTerminal.vue` MUST 用 `<textarea>` 替代当前 `<input>` 接收命令，textarea 默认高度 MUST 至少 4 行可见。**Enter 键（无 Shift）MUST 触发 execute；Shift+Enter MUST 插入换行符**。textarea 内容按 `\n` 拆分并 trim 空白后 MUST 过滤空行，得到 `commands` 列表提交给后端。

#### Scenario: 多行命令提交
- **WHEN** 用户在 textarea 输入：
  ```
  system-view
  interface GigabitEthernet 1/0/1
  port link-type trunk
  port trunk permit vlan 10,20,30
  ```
  并按 Enter
- **THEN** 前端按 `\n` 拆为 4 条命令，调 `executeApi.run(deviceId, {commands: [...], delay_ms})`；textarea 清空

#### Scenario: Shift+Enter 换行不提交
- **WHEN** 用户在 textarea 中按 Shift+Enter
- **THEN** textarea 中插入换行符（输入区内容增加），**不**触发 execute

#### Scenario: 单条命令兼容
- **WHEN** 用户在 textarea 中输入单行 `display version` 并按 Enter
- **THEN** 前端拆分为 1 条命令的 `commands: ["display version"]`，提交后端

#### Scenario: 空行自动跳过
- **WHEN** 用户输入含空行的命令（如 `cmd1\n\ncmd2`）
- **THEN** 前端 `split('\n').map(s => s.trim()).filter(Boolean)` 后提交 `["cmd1", "cmd2"]`，空行不发送

### Requirement: 前端可配命令间隔

`OpsTerminal.vue` MUST 提供"延迟 (ms)"数字输入框，默认值 MUST 为 1000。执行时 MUST 把该值作为 `delay_ms` 提交给后端。

#### Scenario: 调整默认延迟
- **WHEN** 用户把延迟输入框改为 `500`
- **THEN** 下次执行时后端按 500ms 间隔顺序执行命令

#### Scenario: 延迟非法值兜底
- **WHEN** 用户输入 `<= 0` 或非数字
- **THEN** 前端兜底为 1000ms 提交（不阻断用户操作）

### Requirement: 多命令结果在终端输出区逐条呈现

执行多命令后，终端输出区 MUST 按"命令 → 输出 → 命令 → 输出"的时序逐条插入。每条命令 MUST 标记索引（`[CMD n/m]`），失败命令 MUST 在对应输出后用红色 `[失败] <错误描述]` 标识。**输出末尾**若存在任意失败命令 MUST 显示汇总 banner（`共 N 条，X 条失败`）。

#### Scenario: 全部成功呈现
- **WHEN** 后端返回 `results = [{success: true}, {success: true}]`
- **THEN** 输出区显示：
  ```
  [CMD 1/2] display version
  <output 1>
  [CMD 2/2] display device
  <output 2>
  ```

#### Scenario: 部分失败呈现
- **WHEN** 后端返回 `results = [{success: true}, {success: false, error: "..."}, {success: true}]`
- **THEN** 输出区依次插入 3 段，第 2 段后追加 `[失败] ...` 红色行；末尾追加 banner `共 3 条，1 条失败`

### Requirement: 历史命令存多命令模板

运维终端历史面板 MUST 存多命令拼接字符串（`commands.join("\n")`），点击历史项 MUST 把整段填回 textarea，用户可编辑。

#### Scenario: 多命令历史保存
- **WHEN** 用户执行 `["system-view", "interface GE 1/0/1"]` 两条命令
- **THEN** 历史面板新增一条 `cmd = "system-view\ninterface GE 1/0/1"`，时间戳与设备名同现

#### Scenario: 点击历史恢复
- **WHEN** 用户点击历史面板中的多命令项
- **THEN** textarea 内容被设为该 `cmd` 字符串（保留 `\n`），用户可继续编辑
