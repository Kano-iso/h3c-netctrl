## MODIFIED Requirements

### Requirement: ops-toolkit SHALL 包含 9 个预制脚本

ops-toolkit 容器（profile: ops）SHALL 预装 9 个运维脚本，覆盖设备连通性 / NETCONF / SSH / 配置拉取 / 重启 / 审计 / 批命令 / 接口配置 / 任务监控场景。脚本 MUST 通过 PATH 注入（cp 到 /usr/local/bin）可直接执行。

#### 9 脚本清单

| # | 脚本 | 用途 | 引入版本 |
|---|------|------|----------|
| 1 | `check-host.sh` | ICMP + TCP 22 + TCP 830 | v2.3 |
| 2 | `check-netconf.sh` | ncclient + schema-capabilities | v2.3 |
| 3 | `ssh-test.sh` | paramiko SSH + show version | v2.3 |
| 4 | `reboot-wait.sh` | reboot 等待（90s retry） | v2.3 |
| 5 | `capture-config.sh` | 拉 startup + running-config | v2.3 |
| 6 | `audit-switch.sh` | 交换机审计 | v2.4.2 |
| 7 | `paramiko-batch-exec.sh` | 单设备 SSH 批命令（复用 backend SSHExecutor） | v2.4.2.1 |
| 8 | `interface-config.sh` | vlan/access/trunk CLI 一键下发（v2.5 新增） | v2.5 |
| 9 | `task-monitor.sh` | task_id 轮询 status 直至终态（v2.5 新增） | v2.5 |

#### Scenario: 全部 9 脚本可执行

- **WHEN** 执行 `docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit ls /usr/local/bin/*.sh`
- **THEN** 列出 9 个脚本文件，均可执行

#### Scenario: 新脚本默认 .177 设备

- **WHEN** 执行 `interface-config.sh --device test vlan add 100` 或 `task-monitor.sh <task_id>`
- **THEN** `--device test` 别名指向 `192.168.100.177`（Test-Switch-177），不连生产

### Requirement: interface-config.sh SHALL 复用 backend API 下发配置

`interface-config.sh` MUST 通过 HTTP 调用 backend API（`POST /api/devices/{id}/vlans` / `PUT /api/devices/{id}/interfaces/{name}/config`）下发配置，不裸写 SSH/NETCONF。凭据 MUST 从 .env 注入（`DEVICE_USERNAME` / `DEVICE_PASSWORD`），禁止 admin fallback。

#### 子命令

- `vlan add <vlan-id> [--name <name>]`：创建 VLAN
- `vlan del <vlan-id>`：删除 VLAN
- `access set <interface> <vlan-id>`：设置接口 access VLAN
- `trunk allow <interface> <vlan-list>`：设置 trunk allowed VLANs

#### Scenario: 创建 VLAN

- **WHEN** 执行 `interface-config.sh --device test vlan add 100 --name test-vlan`
- **THEN** 调用 `POST /api/devices/{id}/vlans` 创建 VLAN 100，输出 JSON 结果

#### Scenario: 凭据缺失明确报错

- **WHEN** .env 未配置 `DEVICE_USERNAME` / `DEVICE_PASSWORD`
- **THEN** 脚本报错退出，提示"请配置 .env 中的 DEVICE_USERNAME/DEVICE_PASSWORD"，不使用 admin fallback

#### Scenario: API 不可达降级提示

- **WHEN** backend 容器未启动，HTTP 调用失败
- **THEN** 脚本报错退出，提示"backend 不可达，离线场景请用 paramiko-batch-exec.sh"

### Requirement: task-monitor.sh SHALL 轮询 task status 直至终态

`task-monitor.sh` MUST 调用 `GET /api/tasks/{task_id}` 轮询任务状态，默认间隔 2s，超时 300s。终态（`success` / `failed` / `cancelled`）时退出并输出最终结果 JSON。支持 `--follow` 持续输出进度。

#### Scenario: 终态退出

- **WHEN** 执行 `task-monitor.sh <task_id>`，任务最终状态为 `success`
- **THEN** 脚本轮询直到 `success` 状态，输出最终结果 JSON 并退出（exit 0）

#### Scenario: 超时退出

- **WHEN** 任务 300s 内未达到终态
- **THEN** 脚本超时退出（exit 1），输出最后获取到的状态

#### Scenario: follow 模式

- **WHEN** 执行 `task-monitor.sh <task_id> --follow`
- **THEN** 每次轮询输出进度（如 `progress: 50%`），终态时输出最终结果

### Requirement: 新脚本末尾 SHALL 输出文档链接

`interface-config.sh` 和 `task-monitor.sh` 末尾 MUST 输出文档链接（用法 + 凭据来源 + 排错 SOP），格式与 `paramiko-batch-exec.sh` 一致。链接指向的章节 MUST 真实存在（`docs/ops-toolkit.md#interface-config` / `docs/ops-toolkit.md#task-monitor`）。

#### Scenario: 脚本输出文档链接

- **WHEN** 执行 `interface-config.sh --help` 或脚本运行结束
- **THEN** 输出包含 `📖 用法: /opt/docs/ops-toolkit.md#interface-config` 等链接

#### Scenario: 文档章节真实存在

- **WHEN** 访问 `docs/ops-toolkit.md#interface-config`
- **THEN** 该章节存在且内容完整（用途 / 示例 / 参数 / schema / 复用说明 / pytest 覆盖 / 限制）

## 关联 change

- 历史：`openspec/changes/archive/2026-06-29-add-ops-toolkit/`（v2.3，5 脚本）
- v2.4.2 新增：`audit-switch.sh`（6 脚本，spec 漏更）
- v2.4.2.1 新增：`paramiko-batch-exec.sh`（7 脚本，spec 漏更）
- v2.5 新增：`interface-config.sh` + `task-monitor.sh`（9 脚本，本 spec 同步补齐）
