# v2.4.2.1 paramiko 工具 — Tasks

## 任务列表

按 v2.4.1 收尾节奏：每 task 一次 commit，commit 后自测。

- [x] **Task 1**: paramiko-batch-exec.sh 骨架 + _paramiko_batch_exec.py 核心（连接 + 跑 1 条命令 + 文本输出）
- [x] **Task 2**: Fernet 加解密（_fernet_decrypt_password 公共函数 + .env.example 加 ENCRYPTION_KEY）
- [x] **Task 3**: 批命令支持（--commands 数组 + --commands-file 文件）
- [ ] **Task 4**: JSON 输出（pytest 可断言）
- [ ] **Task 5**: timeout + retry 逻辑（默认 30s/0 次）
- [ ] **Task 6**: 真机 smoke test（pytest --integration，默认 .177）
- [ ] **Task 7**: 单元测试覆盖（mock，10 个 case）
- [ ] **Task 8**: docs/ops-toolkit.md §4.7 文档
- [ ] **Task 9**: archive v242-paramiko-tool change + commit + tag v2.4.2.1 + RELEASE-NOTES

## Task 1: paramiko-batch-exec.sh 骨架

**目标**：能跑通 `paramiko-batch-exec.sh --device test --commands "display version"`，输出文本。

**步骤**：
1. 创建 `ops-toolkit/scripts/paramiko-batch-exec.sh`（bash 入口，参数解析）
2. 创建 `ops-toolkit/scripts/_paramiko_batch_exec.py`（Python 核心）
3. 复用 `_lib.sh` 的 `_get_device_arg()` / `_resolve_alias()` / `_print_doc_links()`
4. 单元测试：参数解析（--device 必填、--commands 和 --commands-file 互斥）

**验收**：
- [ ] 在 .177 跑通 `display version` 命令
- [ ] 文本输出格式正确
- [ ] qa-backend pytest 跑通

## Task 2: Fernet 加解密

**目标**：支持 `--pass-cipher "gAAAAABm..."` 参数，Fernet 解密后登录。

**步骤**：
1. 在 `_lib.sh` 加 `_fernet_decrypt_password()` 函数
2. ops-toolkit/Dockerfile 加 `pip install cryptography`（如果未装）
3. .env.example 加 `ENCRYPTION_KEY=your-fernet-key-here`
4. 文档：生成密钥 + 加密密码的命令示例

**验收**：
- [ ] `--pass-cipher` 解密后能登录设备
- [ ] 错误密钥时退出码 != 0 + stderr 报"密钥无效"
- [ ] .env.example 完整

## Task 3: 批命令支持

**目标**：支持 `--commands "cmd1" "cmd2"` 数组 + `--commands-file cmds.txt` 文件。

**步骤**：
1. paramiko_batch_exec.py 接收 `commands: list[str]`
2. bash 入口解析 `--commands` 数组
3. bash 入口解析 `--commands-file` 文件（每行 1 条，跳过 # 注释 + 空行）
4. 互斥检查：两个都给则报错

**验收**：
- [ ] 3 条命令全部跑通
- [ ] 文件不存在报错
- [ ] 注释行跳过

## Task 4: JSON 输出

**目标**：默认 JSON 输出，含 `total/success/failed/results` 字段。

**步骤**：
1. paramiko_batch_exec.py 输出 dict
2. bash 入口加 `--output-format <text|json>`（默认 json）
3. pytest 断言 JSON schema

**验收**：
- [ ] JSON 含所有字段
- [ ] pytest 能 load + 断言
- [ ] text 格式人类可读

## Task 5: timeout + retry

**目标**：单命令 timeout 30s + 失败重试 0 次（默认）。

**步骤**：
1. paramiko 连接加 `timeout=connect_timeout`
2. 单命令执行加 timeout（threading / signal）
3. `--retries N` 参数
4. 重试 backoff 5s

**验收**：
- [ ] timeout 生效（设备不响应时 30s 退出）
- [ ] retry 生效（--retries 2 时 2 次重试）
- [ ] pytest 测 timeout case

## Task 6: 真机 smoke test

**目标**：pytest -m integration 跑通真机测试。

**步骤**：
1. `ops-toolkit/tests/test_paramiko_batch_exec_integration.py`
2. `pytest -m integration -v` 跑通
3. 默认指向 .177

**验收**：
- [ ] 真机跑通 `display version`
- [ ] 输出有 "H3C" 字符串
- [ ] pytest exit 0

## Task 7: 单元测试覆盖

**目标**：mock 测 10 个 case。

**步骤**：
1. `ops-toolkit/tests/test_paramiko_batch_exec.py`
2. 用 `unittest.mock` mock paramiko.SSHClient
3. 覆盖：参数解析、Fernet 加密往返、JSON 输出、错误命令、设备不可达、命令文件不存在、互斥

**验收**：
- [ ] 10 个 case 全过
- [ ] qa-backend pytest 218+ 全过（不冲突）

## Task 8: 文档

**目标**：`docs/ops-toolkit.md` §4.7 完整。

**步骤**：
1. §4.7 标题
2. 用法（命令示例）
3. Fernet 密钥生成 + 密码加密示例
4. 命令文件格式
5. JSON 输出 schema
6. pytest 覆盖说明

**验收**：
- [ ] 文档章节完整
- [ ] 命令示例可复制运行

## Task 9: archive + commit + tag

**目标**：归档 + commit + tag v2.4.2.1。

**步骤**：
1. `openspec archive v242-paramiko-tool` （或手动 git mv）
2. 写 `RELEASE-NOTES-v2.4.2.1.md`
3. 9 个 task commit（每个 task 一次 commit）
4. 追加 chore commit：archive + RELEASE-NOTES + VERSION-ROADMAP
5. tag v2.4.2.1

**验收**：
- [ ] openspec/changes/archive/2026-07-04-v242-paramiko-tool/ 完整
- [ ] RELEASE-NOTES-v2.4.2.1.md 写完
- [ ] VERSION-ROADMAP.md 加 v2.4.2.1 条目
- [ ] tag v2.4.2.1

## 验证 checklist（最终）

- [ ] `bash paramiko-batch-exec.sh --device test --commands "display version"` 在 .177 跑通
- [ ] `bash paramiko-batch-exec.sh --device test --commands-file cmds.txt` 跑通
- [ ] `--pass-cipher "gAAAAABm..."` 解密登录
- [ ] 错误命令 returncode != 0 + success: false
- [ ] 设备不可达时退出码 != 0
- [ ] pytest mock 10 个 case + 真机 1 个 case 全过
- [ ] qa-backend pytest 218+ 不破坏
- [ ] docs/ops-toolkit.md §4.7 完整
- [ ] RELEASE-NOTES-v2.4.2.1.md 完整
- [ ] tag v2.4.2.1
