# Ops Toolkit 使用手册

> v2.5 运维排错工具包，容器化、开箱即用。
> 启动: `docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit <脚本>`
> 容器内脚本目录: `/scripts/`，已软链到 `/usr/local/bin/`

## 📌 默认设备（v2.4.2 改）

**所有 9 个脚本默认指向 Test-Switch-177 (192.168.100.177)**：
- 不带 `--device` = 默认 `.177`（安全默认）
- `--device test` = 显式 test
- `--device <生产 IP>` = 显式生产（日志 warn，但不阻止）
- 显式生产 IP 时，**脚本会输出 ⚠️ 提示**，提醒你注意操作

### 设备名→IP 别名映射（v2.4.2 新增）

`--device` 支持 4 类设备的别名（小写不敏感）：

| 别名 | IP | 说明 |
|---|---|---|
| `test` / `Test-Switch` / `Test-Switch-177` | 192.168.100.177 | **默认**（QA test 设备） |
| `leaf-03` | 192.168.100.4 | 生产 Leaf-03 |
| `leaf-04` | 192.168.100.5 | 生产 Leaf-04 |
| `spine-01` | 192.168.100.100 | 生产 Spine-01 |
| 其他设备名 | （查后端 API） | 透传给 `_resolve_device` |

> 加新别名 → 改 `ops-toolkit/scripts/_lib.sh` 的 `_resolve_alias()` 函数

## 快速开始

启动容器后，9 个预制脚本可直接调用（脚本名就是命令名）。

### 凭据来源（重要）

3 种方式（按优先级）：
1. `--device <设备名/别名>`：从别名表查 IP（已知设备）或后端 API 查 IP+凭据（推荐，需 backend 容器在运行）
2. `--device <IP> --user <user> --pass <pass>`：显式传参
3. 位置参数 `<ip> <user> <pass>`：兼容 v2.3 旧用法
4. IP 模式 + 环境变量：`SSH_USER=admin SSH_PASS=xxx <脚本> <ip>`

环境变量：
- `BACKEND_URL`: 后端 API 地址（默认 `http://backend:8000`）
- `SSH_USER` / `SSH_PASS`: IP 模式的默认凭据
- `OPS_DOCS_PREFIX`: 文档前缀（默认 `/opt/docs`）

## 脚本清单

### check-host
- 用途：主机连通性检查（ping + SSH 22 + NETCONF 830）
- 用法：`check-host --device <name|ip> [count]`
- 示例：`check-host --device Leaf-04` 或 `check-host 192.168.100.5 3`
- 输出：ping 结果 + SSH 22 端口 + NETCONF 830 端口状态

### ssh-test
- 用途：SSH 交互测试（登录 + 执行命令）
- 用法：`ssh-test --device <name|ip> [command]`
- 默认命令：`display version`
- 示例：`ssh-test --device Spine-01 "display interface brief"`

### check-netconf
- 用途：NETCONF 连接测试（ncclient hello + 能力集）
- 用法：`check-netconf --device <name|ip>`
- 示例：`check-netconf --device Leaf-04`

### capture-config
- 用途：SCP 拉取 startup.cfg 到 /captures/
- 用法：`capture-config --device <name|ip>`
- 输出：`/captures/<ip>_<timestamp>_startup.cfg`
- 示例：`capture-config --device Leaf-04`

### reboot-wait
- 用途：触发 reboot + 等待 SSH 恢复（最多 120s）
- 用法：`reboot-wait --device <name|ip>`
- 注意：会触发设备重启，谨慎使用
- 示例：`reboot-wait --device Test-Switch-177`

### audit-switch
- 用途：一键巡检交换机（display version + display device + display interface brief）
- 用法：`audit-switch --device <name|ip>`
- 示例：`audit-switch --device Leaf-04`

### paramiko-batch-exec
- 用途：单设备 SSH 批命令执行（研发场景的"前置加配置 + 后置验证"开发辅助工具）
- 用法：`paramiko-batch-exec.sh --device <name|ip> --command "display version"`
- 定位：单设备排错工具（非批量配置；批量配置是工程工具的活）
- 复用：backend 的 `app/utils/ssh_executor.py`（不重复造 paramiko 协议）
- 关键能力：H3C V7 设备兼容（ssh-rsa kex + `---- More ----` 分页 + `[Y/N]` 二次确认由 SSHExecutor 处理）
- 输出：默认 JSON（pytest 友好），`--output-format text` 改可读模式

#### 用法示例

```bash
# 1. 单条命令（凭据自动读 .env 注入的 DEVICE_USERNAME/DEVICE_PASSWORD）
paramiko-batch-exec.sh --device test --command "display version"

# 2. 批命令（数组）
paramiko-batch-exec.sh --device test --commands "display version" "display vlan 1" "display interface brief"

# 3. 命令文件（每行 1 条，# 开头为注释）
cat > /tmp/cmds.txt <<'EOF'
display version
display vlan 100
display interface GigabitEthernet1/0/1
EOF
paramiko-batch-exec.sh --device test --commands-file /tmp/cmds.txt

# 4. Fernet 密文（避免明文密码进 shell history）
#   密钥生成: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   加密密码: python3 -c "from cryptography.fernet import Fernet; print(Fernet(b'KEY').encrypt(b'PASS').decode())"
#   .env 加: ENCRYPTION_KEY=...
paramiko-batch-exec.sh --device test --command "display version" --user python --pass-cipher "gAAAAA..."

# 5. 显式生产设备（脚本会输出 ⚠️ 提示）
paramiko-batch-exec.sh --device leaf-04 --command "display version"

# 6. JSON 输出（pytest 断言用）
paramiko-batch-exec.sh --device test --command "display version" --output-format json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['success'], d['failed'])"
```

#### 凭据来源（禁止 admin fallback）

按优先级匹配，**任一来源找不到时立即报错**（不静默 fallback 到 admin，避免 .env 注入失败被掩盖）：

1. `--user` / `--pass` / `--pass-cipher` 命令行参数
2. `$SSH_USER` / `$SSH_PASS` 环境变量
3. `$DEVICE_USERNAME` / `$DEVICE_PASSWORD`（.env 注入，**推荐**）
4. `$DEVICE_USER` / `$DEVICE_PASS`（兼容老 env）

**严禁**：在 `docker compose run` 时用 `-e USERNAME=xxx -e PASSWORD=xxx` 传凭据——必须走 `env_file: - .env`（开箱即用，避免 shell history 泄露）。

#### 参数清单

| 参数 | 说明 | 默认 |
|---|---|---|
| `--device <name\|ip\|alias>` | 设备（默认 test = .177） | test |
| `--command <cmd>` | 单条命令 | — |
| `--commands <c1> <c2> ...` | 批命令（与 --commands-file 互斥） | — |
| `--commands-file <path>` | 命令文件（每行 1 条，# 注释，空行跳过） | — |
| `--user <user>` | SSH 用户 | 读 $SSH_USER / $DEVICE_USERNAME |
| `--pass <pass>` | SSH 明文密码（不推荐，进 shell history） | 读 $SSH_PASS / $DEVICE_PASSWORD |
| `--pass-cipher <gAAAAA...>` | Fernet 密文密码（推荐） | 读 $ENCRYPTION_KEY |
| `--timeout <seconds>` | 单命令 timeout | 30 |
| `--retries <n>` | 失败重试次数（整 batch 重跑） | 0 |
| `--output-format <text\|json>` | 输出格式 | json |
| `--continue-on-error` | 遇错继续（默认） | true |
| `--stop-on-error` | 遇错停止 | — |

#### JSON 输出 schema

```json
{
  "host": "192.168.100.177",
  "total": 3,
  "success": 3,
  "failed": 0,
  "elapsed_ms": 2400,
  "results": [
    {
      "command": "display version",
      "returncode": 0,
      "stdout": "...",
      "stderr": "",
      "elapsed_ms": 800,
      "success": true
    }
  ]
}
```

字段含义：
- `host` / `total` / `success` / `failed` / `elapsed_ms` 顶层汇总
- `results[].command` 原始命令（trim 后的）
- `results[].returncode` 0=成功 / 1=失败 / 设备不可达
- `results[].stdout` 命令输出（可能含 H3C `---- More ----` 已被 SSHExecutor 翻页）
- `results[].stderr` 错误信息（连接失败时为 `SSH 连接/执行失败: <exc>`）

#### 复用 backend SSHExecutor（不手搓协议）

`_paramiko_batch_exec.py` 是 **154 行薄壳**：

```python
sys.path.insert(0, "/opt")
from ssh_executor import SSHExecutor  # 复用 backend/app/utils/ssh_executor.py
```

所有 H3C 协议处理都在 `backend/app/utils/ssh_executor.py`：
- `Transport._preferred_kex` 加 `diffie-hellman-group14-sha1`（H3C V7 兼容）
- `Transport._preferred_server_host_key_algorithms` 加 `ssh-rsa`
- `_read_with_pagination` 处理 `---- More ----`（自动发空格翻页）
- `execute_commands` 处理 `[Y/N]` 二次确认

`ops-toolkit/Dockerfile` 只 `COPY backend/app/utils/ssh_executor.py /opt/ssh_executor.py` 一个文件，不挂整个 backend 目录（避免依赖污染）。

#### pytest 覆盖

- 单元测试：`backend/tests/test_ops_toolkit_paramiko.py`（11 case，mock SSHExecutor）
  - 成功/失败/部分失败的 summary 统计
  - retry 行为（retries=N 时整体重试 N+1 次）
  - continue_on_error vs stop_on_error
  - 连接失败的容错
  - 凭据缺失的 fail-fast
  - 验证"复用 SSHExecutor 不手搓 invoke_shell"（反射断言）
- 真机集成：`backend/tests/test_ops_toolkit_paramiko.py`（3 case，`pytest -m integration`）
  - 真机跑 `display version` 含 "H3C"
  - 真机跑批命令
  - 真机跑多设备别名
- 跑：`docker compose -f docker-compose.dev.yml run --rm --entrypoint "python -m pytest tests/test_ops_toolkit_paramiko.py -v" qa-backend`

#### 限制

- **单设备**（明确不做 5 设备批量配置）
- **不做配置变更验证**（只读命令为主；如需下发配置应走 backend API）
- **不分页截图**（H3C 设备的 `display this` 等长输出由 SSHExecutor 内部翻页，工具层无感）

### interface-config（v2.5 新增）

- 用途：通过 backend API 下发接口配置（VLAN 创建/删除、access vlan、trunk 允许 vlan）
- 定位：CLI 入口封装，**不直接走 NETCONF**，复用后端已实现的接口配置 API（避免重复实现 NETCONF 协议）
- 用法：
  - `interface-config vlan add <device> <vlan_id> <name>` — 创建 VLAN
  - `interface-config vlan del <device> <vlan_id>` — 删除 VLAN
  - `interface-config access set <device> <if_index> <vlan>` — 设置 access vlan
  - `interface-config trunk allow <device> <if_index> <vlans>` — 设置 trunk 允许 vlan（`<vlans>` 逗号分隔）
- 输出：✅ / ❌ + backend 返回的 message / error
- 退出码：0 成功，1 失败，2 缺参数，3 API 不可达
- 默认设备：与所有脚本一致（test = .177）
- 凭据：脚本本身不需要设备凭据（已由 backend 持有），只需 backend 容器可达

#### 用法示例

```bash
# 创建 VLAN
interface-config vlan add test 100 "业务 A"
# → ✅ 成功: 100

# 删除 VLAN
interface-config vlan del test 100
# → ✅ 成功: VLAN 100已删除

# 设置 access vlan
interface-config access set test 2 100
# → ✅ 成功: 接口配置已下发

# 设置 trunk 允许 vlan 100,200,300
interface-config trunk allow test 3 100,200,300
# → ✅ 成功: 接口配置已下发
```

#### 参数清单

| 子命令 | 参数 | 说明 |
|---|---|---|
| `vlan add` | `<device> <vlan_id> <name>` | 设备 + VLAN ID (1-4094) + 名称 |
| `vlan del` | `<device> <vlan_id>` | 设备 + VLAN ID |
| `access set` | `<device> <if_index> <vlan>` | 设备 + 接口索引 + VLAN ID |
| `trunk allow` | `<device> <if_index> <vlans>` | 设备 + 接口索引 + 逗号分隔 vlan 列表 |

#### pytest 覆盖

- 单元测试：`backend/tests/test_ops_toolkit_interface_config.py`（待 Task 7.3 补充）
  - 4 个子命令参数解析
  - 设备名 / IP 别名解析（调 backend API 查 device_id）
  - VLAN ID 范围校验（< 1 / > 4094 → 失败）
  - API 不可达降级（config → backend fallback）
- 真机集成：`pytest -m integration` 在 .177 上跑创建/删除 VLAN
- 跑：`docker compose -f docker-compose.dev.yml run --rm --entrypoint "python -m pytest tests/test_ops_toolkit_interface_config.py -v" qa-backend`

#### 限制

- **依赖后端 API**：必须 backend/config 容器在运行
- **不绕过 backend**：不直接走 NETCONF（即使有 SSH 凭据也走 API，保证审计 / 记录 / 凭据管理一致）
- **单设备**：每次操作 1 台设备（批量是后端 batch API 的活）
- **不保存操作记录**：操作日志由 backend record_log 统一记录，ops-toolkit 不重复

### task-monitor（v2.5 新增）

- 用途：轮询异步任务状态（v2.4 引入的 async backup/restore 任务）
- 定位：异步任务的 CLI 监控入口，**轮询 GET /api/tasks/{id}**，不订阅 WebSocket
- 用法：
  - `task-monitor <task_id>` — 默认 300s 超时 / 2s 间隔
  - `task-monitor <task_id> --timeout 600` — 自定义超时
  - `task-monitor <task_id> --interval 5` — 自定义轮询间隔
  - `task-monitor <task_id> --follow` — 完成后继续轮询
  - `task-monitor <task_id> --json` — JSON 输出（CI 友好）
- 退出码：0 成功 / 1 失败或取消 / 2 超时 / 3 API 不可达
- 输出：进度条 + 状态（pending / running / success / failed / cancelled）

#### 用法示例

```bash
# 1. 监控异步备份任务
task-monitor task-restore-001
# → 🔄 [████░░░░░░░░░░░░░░░░░] 30% 执行中 | 正在备份 startup...
# → 🔄 [██████████░░░░░░░░░░] 50% 执行中 | 正在备份 running...
# → ✅ [████████████████████] 100% 成功 | 备份完成
# → 🎉 任务 task-restore-001 执行成功

# 2. 自定义超时 + 间隔
task-monitor task-restore-001 --timeout 600 --interval 5

# 3. JSON 输出（CI 集成）
task-monitor task-restore-001 --json
# → {"task_id": "task-restore-001", "status": "running", "progress": 30, ...}
# → {"task_id": "task-restore-001", "status": "success", "progress": 100, ...}
```

#### pytest 覆盖

- 单元测试：`backend/tests/test_ops_toolkit_task_monitor.py`（待 Task 8.2 补充）
  - 参数解析（--timeout / --interval / --json / --follow）
  - 终态退出码（success=0 / failed=1 / cancelled=1）
  - 超时退出（exit 2）
  - API 不可达退出（exit 3）
  - JSON 输出格式校验
- 真机集成：`pytest -m integration` 跑异步备份，验证 task_id 可被 task-monitor 监控

#### 限制

- **轮询模式**：默认 2s 一次，高频场景（>1 任务/秒）应改用 WebSocket
- **单任务**：每次监控 1 个 task_id（多任务监控是 CI/编排平台的活）
- **无取消功能**：本脚本只能监控，不能取消（如需取消走 `taskApi.cancel`）

## 设备命名约定

设备名对应后端 CMDB 中的 name 字段：
- Spine-01: 192.168.100.100
- Leaf-01: 192.168.100.2
- Leaf-02: 192.168.100.3
- Leaf-03: 192.168.100.4
- Leaf-04: 192.168.100.5
- Leaf-05: 192.168.100.6
- Test-Switch-177: 192.168.100.177

## 常见错误

| 错误 | 原因 | 解决 |
|---|---|---|
| `后端 API 查询失败` | backend 容器未运行 | `docker compose up -d backend` |
| `设备 'XXX' 未找到` | 设备名拼写错误 | 查后端 CMDB 确认名称 |
| `SSH 22 不通` | 设备未开机 / 防火墙 | `check-host` 先 ping |
| `NETCONF 连接失败` | netconf-agent 未启用 | 设备上 `netconf ssh server enable` |
| `permission denied` | 凭据错误 | 用 `--user --pass` 显式传 |

## 关联文档

- [QA-GUIDE.md](QA-GUIDE.md)：QA 测试指南

---

## S6850 / S6860 / S9850 系列 SCP 限制（v2.6.2 新增）

> 适用：H3C V7 S6850 (CMW 7.1.070) / S6860 / S9850 等系列
> **默认禁用 SFTP/SCP subsystem**（v2.6.1 复盘"回滚无反应"问题根因）

### 现象对照

| 操作 | SSH exec channel | SCP/SFTP subsystem |
|---|---|---|
| `display version` | ✅ 正常 | — |
| `display current-configuration` | ✅ 正常 | — |
| **拉取文件**（scp.get / sftp.get） | — | ⚠️ 部分支持 |
| **推送文件**（scp.put / sftp.put） | — | ❌ `Channel closed` |

### 影响

- **备份拉取**（startup.cfg / running.cfg 文本抓取）✅ 不受影响
- **备份回滚**（需真上传文件）❌ **不支持**——NetCtrl UI 点回滚会立即 toast 提示

### 验证方法

```bash
# .5 设备（不支持）：scp.push 立即 Channel closed
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit paramiko-batch-exec \
  --device leaf-04 --command "display version"
# 预期：可正常执行 SSH CLI 命令

# 真机验证 SCP 推回（仅在支持设备上做）
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit paramiko-batch-exec \
  --device test --command "scp /a/b localhost:/dev/null"
# .5 设备：失败（Channel closed）
# .177 设备：成功
```

### NetCtrl UI 行为

- **支持设备**（.177）：点"回滚" → 正常提交回滚任务
- **不支持设备**（.5）：点"回滚" → 立即 toast 弹"设备 S6850 不支持 SCP 推回，无法回滚"
- **预检机制**：v2.6.2 起，restore_async 端点启动前先 probe → 不支持直接 422 + error_key=backup.restore_not_supported
- **设备状态字段**：`device.status.restore_unsupported`（5s TTL 缓存）→ 前端可禁用"回滚"按钮

### 兜底 / 应急

如必须给 S6850 系列设备回滚配置：

1. **推荐方案**：用设备 console / SSH CLI 手工 `startup saved-configuration` + reboot
2. **不推荐**：用 `sftp server enable` 强行开启 SFTP（H3C V7 默认无此命令，部分固件支持）
3. **生产建议**：用支持 SCP 的设备做临时中转（如 .177），中转后手工同步

### 关联

- T1 probe 函数：[`backend/app/utils/backup_manager.py`](../../backend/app/utils/backup_manager.py) `check_restore_support()`
- T2 端点预检：[`backend/app/routers/backup.py`](../../backend/app/routers/backup.py) `restore_backup_async`
- T6 设备状态字段：[`backend/app/routers/device.py`](../../backend/app/routers/device.py) `_get_restore_support_cached`
- 真机验证记录：[`docs/REVIEW-v262-bugfix-round-real-device-validation.md`](REVIEW-v262-bugfix-round-real-device-validation.md)
- v2.6.1 复盘："回滚无反应"问题根因
