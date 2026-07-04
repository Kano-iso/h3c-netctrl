# v2.4.2.1 paramiko 工具 — Design

## 1. 工具定位

**一句话**：单设备 SSH 批命令执行器，用于研发场景的"前置加配置 + 后置验证"。

**典型使用流程**（从 user 确认）：
```
1. 研发新功能（v2.5+ 新增接口 X）→ 用 paramiko 工具在 .177 加测试配置
   paramiko-batch-exec.sh --device test --commands "interface G1/0/1" "port link-mode bridge" "port access vlan 100"
2. 前端 / 后端 API 触发新功能
3. 用 paramiko 工具验证配置 / 路由表 / 接口状态
   paramiko-batch-exec.sh --device test --commands "display vlan 100" "display ip routing-table"
4. 测试完用 paramiko 工具恢复原状
   paramiko-batch-exec.sh --device test --commands "interface G1/0/1" "undo port access vlan" "undo port link-mode"
```

**明确边界**（不做的）：
- ❌ **不**做"5 设备 × 3 命令批量配置"——这是工程工具，v2.5+ 再说
- ❌ **不**做"全网扫"——同上位工具
- ❌ **不**做"config replace"（整段配置替换）——风险高，应该用 git 化配置管理

## 2. 命令行设计

```bash
paramiko-batch-exec.sh \
  --device <name|ip|alias>          # 设备（默认 test = .177）
  --commands "cmd1" "cmd2" ...      # 命令数组
  --commands-file /path/to/cmds.txt # 命令文件（每行 1 条）
  --pass-cipher "gAAAAABm..."       # 密码密文（Fernet）
  --timeout <seconds>                # 单命令 timeout（默认 30s）
  --retries <n>                      # 失败重试次数（默认 0）
  --output-format <text|json>        # 输出格式（默认 json）
  --continue-on-error                # 遇错继续（默认 true）
```

**参数冲突处理**：
- `--commands` 和 `--commands-file` 二选一，同时给报错
- `--device` 必填（避免误连错设备）

## 3. 输出格式

### 3.1 JSON（默认，pytest 可断言）

```json
{
  "device": "test",
  "ip": "192.168.100.177",
  "total": 3,
  "success": 3,
  "failed": 0,
  "elapsed_ms": 8420,
  "results": [
    {
      "command": "display version",
      "returncode": 0,
      "stdout": "H3C Comware Platform Software\n...",
      "stderr": "",
      "elapsed_ms": 1200,
      "success": true
    },
    {
      "command": "display vlan 100",
      "returncode": 0,
      "stdout": "VLAN ID: 100\n...",
      "stderr": "",
      "elapsed_ms": 1500,
      "success": true
    }
  ]
}
```

### 3.2 Text（人类阅读，--output-format text）

```
[1/3] display version  (1200ms, rc=0, ✓)
[2/3] display vlan 100  (1500ms, rc=0, ✓)
[3/3] display ip routing-table  (1800ms, rc=0, ✓)
✅ 3/3 成功 (8420ms total)
```

## 4. 关键技术决策

### 4.1 加解密：Fernet（AES128-CBC + HMAC）

```python
from cryptography.fernet import Fernet
# 生成密钥：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 加密密码：python -c "from cryptography.fernet import Fernet; print(Fernet(b'KEY').encrypt(b'adminpass').decode())"
```

**为什么用 Fernet**：
- 行业标准（cryptography 库自带，pip 装即可）
- AES128-CBC + HMAC-SHA256，足够安全
- API 简单（一行 encrypt / decrypt）

**密钥管理**：
- `ENCRYPTION_KEY` 环境变量（注入 `.env`）
- `.env` 加入 `.gitignore`（已有）
- `.env.example` 加 `ENCRYPTION_KEY=your-fernet-key-here`

### 4.2 凭据来源

**优先级**：
1. `--pass-cipher` 参数（明文密文）
2. `OPS_TOOLKIT_PASS_CIPHER` 环境变量
3. `OPS_TOOLKIT_PASS` 环境变量（明文，不推荐）
4. 从后端 API 查询设备 + 提示用户输入（fallback）

**不**支持 `sshpass` 风格 `-p` 参数（避免明文密码进 history）

### 4.3 实现语言：Python（不是 shell）

**为什么**：
- paramiko + cryptography + JSON 都是 Python 原生支持
- shell 调 Python 反而复杂
- 复用项目已有的 paramiko（device_service.py 用了）

**调用方式**：bash 脚本作为 wrapper，内部 `python3 -c "..."` 或调用独立的 `paramiko_batch_exec.py` 模块

**最终方案**：
- `ops-toolkit/scripts/paramiko-batch-exec.sh`（bash 入口，处理参数解析）
- `ops-toolkit/scripts/_paramiko_batch_exec.py`（Python 模块，核心逻辑）
- 复用 `ops-toolkit/scripts/_lib.sh` 的 `_get_device_arg()` / `_resolve_alias()` / `_print_doc_links()`

### 4.4 timeout / retry

```python
# 单命令 timeout
client.connect(host, port=22, username=user, password=pass, timeout=connect_timeout)
# cmd-level timeout 用 signal / threading 实现
```

**默认**：
- connect timeout = 10s
- cmd timeout = 30s
- retries = 0（v2.4.2 默认不重试，避免设备 session 锁）
- retry backoff = 5s

## 5. 测试策略

### 5.1 单元测试（mock，10 个 case）

- 参数解析：--device / --commands / --commands-file 互斥
- Fernet 加解密：encrypt / decrypt 往返
- JSON 输出：含所有字段
- text 输出：含 ✓/✗
- 错误命令：returncode != 0
- 设备不可达：connect timeout
- 命令文件不存在
- --commands 和 --commands-file 同时给：报错

### 5.2 真机 smoke test（1 个 case）

```python
@pytest.mark.integration
def test_paramiko_real_device_runs_display_version():
    """真机 smoke test：跑 1 条 display version，验有 stdout"""
    r = run(["bash", "paramiko-batch-exec.sh", "--device", "test",
             "--commands", "display version", "--output-format", "json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["success"] >= 1
    assert any("H3C" in res["stdout"] for res in data["results"])
```

**默认指向 .177**（v2.4.2 QA 工具默认 test 设备一致）。

## 6. 文档

新增 `docs/ops-toolkit.md` §4.7 "paramiko-batch-exec — 单设备批命令 + Fernet 加解密"：

- 用法
- Fernet 密钥生成 + 密码加密示例
- 命令文件格式
- JSON 输出 schema
- pytest 覆盖说明

## 7. 风险与回退

| 风险 | 回退 |
|---|---|
| Fernet 密钥泄露 | 旧密钥撤销 + 重生成 + 设备改密码 |
| paramiko 性能问题 | 加连接池（v2.5 backlog） |
| 命令拼错 | --dry-run 选项（v2.5 backlog，本次不做） |
| 与 ssh-test.sh 重复 | 保留 ssh-test.sh 为排错工具，paramiko 工具是"测试"用 |

## 8. 实施 Task 列表

见 `tasks.md`。
