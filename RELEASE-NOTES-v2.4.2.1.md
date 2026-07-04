# RELEASE-NOTES-v2.4.2.1

**版本**: v2.4.2.1
**日期**: 2026-07-04
**主题**: ops-toolkit 第 7 脚本 paramiko-batch-exec（单设备排错工具）
**前序**: v2.4.2 (2026-07-04)

---

## 1. 主题

v2.4.2.1 = **ops-toolkit 工具集新增第 7 脚本 paramiko-batch-exec**。**不开 v2.5**，因为这是 v2.4.2 review 报告 P1 项的**前置闭环**（review 报告结论："ops-toolkit 6 脚本稳定，但缺单设备精排错能力"）。

v2.4.2.1 包含 **1 个 change**：

| change | 主题 | 状态 |
|---|---|---|
| v242-paramiko-tool | ops-toolkit 加 paramiko-batch-exec.sh（单设备 SSH 批命令执行） | ✅ archive |

---

## 2. 包含的 Changes（1 个）

### Change：v242-paramiko-tool（单设备 SSH 批命令工具）

#### 2.1 问题

v2.4.2 review 报告 P1 项指出：ops-toolkit 现有 6 脚本（check-host / ssh-test / check-netconf / capture-config / reboot-wait / audit-switch）缺**单设备精排错能力**。

研发场景典型痛点：
- 新功能开发时需要"前置加配置 + 后置验证"——加完配置后用工具看有没有下发下去
- 删功能测试时需要"前置看配置 + 中间触发删除 + 后置看是否真删了"
- ssh-test 用 sshpass + ssh，**H3C V7 设备不兼容**（OpenSSH 8+ 默认禁 ssh-rsa host key）

#### 2.2 解决方案

**复用 backend SSHExecutor（不手搓 paramiko 协议）**：
- `_paramiko_batch_exec.py` 是 **154 行薄壳**，`sys.path.insert(0, "/opt")` + `from ssh_executor import SSHExecutor`
- 所有 H3C 协议处理（ssh-rsa kex / `---- More ----` 分页 / `[Y/N]` 二次确认）由 backend `app/utils/ssh_executor.py` 已实现
- `ops-toolkit/Dockerfile` 只 `COPY backend/app/utils/ssh_executor.py /opt/ssh_executor.py` 一个文件，不挂整个 backend 目录

**核心特性**：
- 单设备（非批量配置，边界明确）
- 批命令：单条 / 数组 / 文件 3 种方式
- 输出：默认 JSON（pytest 友好），`--output-format text` 改可读
- 凭据：4 级优先级 + Fernet 密文支持
- 容错：timeout 30s / retry 0 次（整 batch 重试）/ continue-on-error

#### 2.3 关键设计决策

1. **复用 SSHExecutor 而非新写**——避免重复造 H3C 协议轮子
2. **禁止 admin fallback**——凭据找不到时明确报错（v2.4.2 paramiko 工具复盘教训：admin 是"贴心的默认值"反而掩盖 .env 注入失败）
3. **禁止 `-e USERNAME=xxx -e PASSWORD=xxx`**——必须 `env_file: - .env`（避免 shell history 泄露）
4. **JSON 默认输出**——pytest 可直接 `json.load` 断言
5. **命令文件支持**——长命令列表走文件，注释 / 空行自动跳过

#### 2.4 凭据来源（4 级优先级）

1. `--user` / `--pass` / `--pass-cipher` 命令行
2. `$SSH_USER` / `$SSH_PASS` 环境变量
3. `$DEVICE_USERNAME` / `$DEVICE_PASSWORD`（.env 注入，**推荐**）
4. `$DEVICE_USER` / `$DEVICE_PASS`（兼容老 env）

任一来源找不到 → 立即报错（不静默 fallback）。

---

## 3. 关联

- 前序: v2.4.2 (2026-07-04) — review 报告 P1 项的前置
- 路线图: [VERSION-ROADMAP.md v2.4.2.1](VERSION-ROADMAP.md)
- 工具文档: [docs/ops-toolkit.md §4.7 paramiko-batch-exec](docs/ops-toolkit.md#paramiko-batch-exec)
- Change archive: [openspec/changes/archive/2026-07-04-v242-paramiko-tool/](openspec/changes/archive/2026-07-04-v242-paramiko-tool/)

---

## 4. 测试 / 验证

### qa-backend 单元测试（新增 11 case）

`backend/tests/test_ops_toolkit_paramiko.py`：
- Case 1: 单条命令成功
- Case 2: 批命令混合结果
- Case 3: stop_on_error 行为
- Case 4: SSH 连接失败
- Case 5: retry 第 1 次失败第 2 次成功
- Case 6: retry 用尽仍失败
- Case 7: 空命令列表（被过滤）
- Case 8: main() 缺 host fail-fast
- Case 9: main() 缺命令 fail-fast
- Case 10: main() JSON 输出格式
- Case 11: 反射断言"复用 SSHExecutor 不手搓 invoke_shell"

**回归**：214 + 11 = 225 passed, 19 skipped（**未破坏 v2.4.2 全部测试**）

### 真机集成测试（3 case，`pytest -m integration`）

- 真机跑 `display version` → success=1, stdout 含 "H3C"
- 真机跑批命令 → success=N
- 真机跑多设备别名（test / leaf-04）

### 真机工具验证（.177 设备）

```bash
$ docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit \
    paramiko-batch-exec.sh --device test --command "display version"
{
  "host": "192.168.100.177",
  "total": 1,
  "success": 1,
  "failed": 0,
  "elapsed_ms": 1667,
  "results": [{
    "command": "display version",
    "returncode": 0,
    "stdout": "H3C Comware Software, Version 7.1.070, Alpha 7170\n...",
    "stderr": "",
    "elapsed_ms": 800,
    "success": true
  }]
}
```

```bash
$ docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit \
    paramiko-batch-exec.sh --device test --commands "display version" "display vlan 1"
{
  "host": "192.168.100.177",
  "total": 2,
  "success": 2,
  "failed": 0,
  ...
}
```

---

## 5. 关键 commit 序列（10 个）

| commit | 说明 |
|---|---|
| `eff1558` | feat(ops-toolkit): paramiko-batch-exec 骨架 + .env 凭据注入 (Task 1) |
| `f5de66a` | feat(ops-toolkit): Fernet 加解密支持 --pass-cipher (Task 2) |
| `eed8bd2` | feat(ops-toolkit): JSON 默认输出 + stdout 清理 (Task 4) |
| `4f8f996` | chore(openspec): 标记 v242-paramiko-tool Task 4/5 [x] 实测通过 |
| `ed44d22` | refactor(ops-toolkit): 复用 backend SSHExecutor + 删 admin fallback |
| `fed20d3` | test(ops-toolkit): 单元测试 11 case + 真机集成 3 case（Task 6/7） |
| `936399c` | fix(ops-toolkit): _lib.sh + paramiko-batch-exec 删 admin fallback + 文档去'默认 admin'残留 |
| `e0030ce` | docs(ops-toolkit): paramiko-batch-exec 工具完整文档 (Task 8) |
| 待 commit | chore(v2.4.2.1): archive 闭环 + RELEASE-NOTES + VERSION-ROADMAP |
| 待 tag | `v2.4.2.1` |

---

## 6. 升级 / 回退

### 升级

```bash
git pull
docker compose -f docker-compose.dev.yml build ops-toolkit
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend \
    python -m pytest tests/test_ops_toolkit_paramiko.py -v
# 预期: 11 passed

docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit \
    paramiko-batch-exec.sh --device test --command "display version"
# 预期: JSON 输出 success=1
```

### 回退

```bash
git revert <v2.4.2.1 commits>
docker compose -f docker-compose.dev.yml build ops-toolkit
# 行为恢复 v2.4.2（6 脚本 + 无 paramiko-batch-exec）
```

---

## 7. v2.5 Backlog 入口（review 报告 P1 推进）

v2.4.2.1 完成 review 报告 P1 项"加 paramiko 单设备排错工具"后，剩余 P1/P2：

| 优先级 | 项 | 状态 |
|---|---|---|
| P1 | internal_api 加本地缓存（5s TTL） | 待 v2.5 |
| P1 | container split mode 设为默认 | 待 v2.5 |
| P1 | vitest 组件测试 EACCES 排障 | 待 v2.5 |
| P1 | Playwright 端到端 e2e | 待 v2.5 |
| P1 | 加 `interface-config.sh`（vlan/access/trunk 一键下发） | 待 v2.5 |
| P1 | 加 `task-monitor.sh`（task_id 轮询 status） | 待 v2.5 |
| **（v2.4.2.1 完成）** | **加 `paramiko-batch-exec.sh`（单设备排错）** | **✅** |

详见 [docs/REVIEW-v242-3container-maturity.md §4](docs/REVIEW-v242-3container-maturity.md#4-v25-候选-backlog)。
