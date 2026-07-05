# Ops Toolkit 使用手册

> v2.4 运维排错工具包，容器化、开箱即用。
> 启动: `docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit <脚本>`
> 容器内脚本目录: `/scripts/`，已软链到 `/usr/local/bin/`

## 📌 默认设备（v2.4.2 改）

**所有 6 个脚本默认指向 Test-Switch-177 (192.168.100.177)**：
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

启动容器后，6 个预制脚本可直接调用（脚本名就是命令名）。

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
