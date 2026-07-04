# v2.4.2.1 paramiko 工具（v242-paramiko-tool）

## Why

ops-toolkit 6 脚本用原生 SSH 排错（sshpass + ssh），结构化能力弱：

1. **无加解密传参**：密码走 `sshpass -p` 明文或环境变量，可被 ps aux / history 看到
2. **无批命令**：每次只跑 1 条命令，多条要分多次调用
3. **无结构化输出**：直接 stdout 文本，pytest 难以断言
4. **无重试 / timeout 保护**：原 sshpass 没内置 timeout / retry，设备慢响应会卡住

`v242-3container-review` §3.3 把"加 `interface-config.sh` + 批命令执行"列为 P1，但归到 v2.5 不对——v2.4.2 标题是 QA 工程化，QA 工具能力补完属于 v2.4.2 范围。

## What

新增 `paramiko-batch-exec.sh`（**单设备** "前置加配置 + 后置验证" 开发辅助工具）：

- **加解密传参**：Fernet（AES128-CBC + HMAC）加密密码，密钥走 `ENCRYPTION_KEY` 环境变量
- **批命令支持**：跟 `--commands "cmd1" "cmd2"` 数组 / `--commands-file /path/to/cmds.txt`
- **JSON 结构化输出**：每条命令返 `{command, returncode, stdout, stderr, elapsed_ms, success}`，pytest 可断言
- **timeout + 重试**：单条命令可配 timeout（默认 30s），设备 NETCONF 锁时可重试（默认 0 次）
- **pytest 覆盖**：mock + 真机两套测试

**明确边界**（不做）：
- ❌ **不**做 5 设备 × 3 命令批量配置（这是工程工具，不是这个脚本的定位）
- ❌ **不**做"全网扫"、"批量改 vlan"、"config replace" 等操作
- ❌ **不**改 ssh-test.sh / capture-config.sh 等现有脚本（保留为排错用）

## Impact

**新增文件**（5 个）：
- `ops-toolkit/scripts/paramiko-batch-exec.sh` — 主脚本（~250 行）
- `ops-toolkit/tests/test_paramiko_batch_exec.py` — pytest 覆盖（~200 行）
- `ops-toolkit/scripts/paramiko-batch-exec.example.txt` — 命令文件示例
- `docs/ops-toolkit.md` §4.7 — 新章节
- `RELEASE-NOTES-v2.4.2.1.md` — patch 发版说明

**修改文件**（3 个）：
- `ops-toolkit/Dockerfile` — 加 `cryptography` pip 包（Fernet 依赖）
- `ops-toolkit/scripts/_lib.sh` — 加 `_fernet_decrypt_password()` 公共函数
- `.env.example` — 加 `ENCRYPTION_KEY` 示例

**不影响**：
- 6 个现有 ops-toolkit 脚本（ssh-test.sh / check-host.sh 等）— 保持原状
- 3 容器架构 / 后端 / 前端 — 纯 ops-toolkit 增量
- pytest 218+ 测试 — ops-toolkit 测试独立

## Risks

- **低风险**：纯 ops-toolkit 增量，不影响 3 容器 / 后端 / 前端
- **Fernet 密钥管理**：`.env` 注入即可，参考现有 `SSH_USER / SSH_PASS` 模式
- **paramiko 连接池**：脚本单次连接跑批命令后 close，不维护长连接（v2.4.2 压测已证明设备 max-session 6/7，不能扛长连接）

## Acceptance Criteria

- [ ] `bash paramiko-batch-exec.sh --device test --commands "display version"` 在 .177 上跑通，输出 JSON
- [ ] `bash paramiko-batch-exec.sh --device test --commands-file cmds.txt` 跑文件里所有命令
- [ ] 密码密文传入：`--pass-cipher "gAAAAABm..."` 解密后登录
- [ ] 错误命令 returncode != 0 时 `success: false`
- [ ] 设备不可达时退出码 != 0，stderr 报"设备 X.X.X.X 不可达"
- [ ] pytest 200 行：mock 测 5 个场景 + 真机 1 个 smoke test（默认指向 .177）
- [ ] qa-backend pytest 全过（与现有 218+ 测试不冲突）
- [ ] docs/ops-toolkit.md §4.7 加完
- [ ] RELEASE-NOTES-v2.4.2.1.md 写完 + tag v2.4.2.1

## Estimated Effort

1-2 天（按 v2.4.1 收尾节奏：每 task 一次 commit，commit 后自测）。
