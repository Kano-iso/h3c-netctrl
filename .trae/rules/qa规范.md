## 工具使用红线：开箱即用，不裸写命令
### 核心原则
项目已投入精力构建了 2 个专用工具容器（ops-toolkit + QA）+ 1 个 MCP 浏览器工具，所有文档链接已内置在回显中。当你需要排错或测试时，如果能直接复用这些现成能力，就不需要从零开始手工拼命令。用了工具自然看到文档，看到文档自然知道怎么用 ——形成闭环。

---

## 📌 qa 默认设备（v2.4.2 起强制）

**所有 qa 工具 / qa 测试 / 反复跑的脚本，默认指向 Test-Switch-177 (192.168.100.177)**：

- **强制理由**：qa 工具"反复跑"特性，误连生产可能导致配置污染（v2.3 教训：曾误改 Leaf-04 的 vlan 100）
- **ops-toolkit 7 脚本**（v2.4.2.1 加 paramiko-batch-exec）：`check-host / ssh-test / check-netconf / capture-config / reboot-wait / audit-switch / **paramiko-batch-exec**`
  - 不带 `--device` = 默认 `.177`（安全默认）
  - `--device test` / `Test-Switch` / `Test-Switch-177` = 显式 test
  - `--device <生产 IP>` = 显式生产（日志 warn，但不阻止）
  - 设备名别名：`leaf-03` / `leaf-04` / `spine-01` → 对应生产 IP
  - **paramiko-batch-exec**（v2.4.2.1 新增）：单设备 SSH 批命令执行（研发场景"前置加配置 + 后置验证"），复用 backend SSHExecutor，**H3C V7 ssh-rsa 兼容**（其他 6 个 sshpass+ssh 工具不兼容 H3C）
- **qa-backend 真机 e2e fixture**：默认 `.177`
- **qa 容器入口 banner**：标注默认目标

> 详见 [docs/ops-toolkit.md § 默认设备](../../docs/ops-toolkit.md#-默认设备v242-改) + [docs/QA-GUIDE.md § qa 默认设备](../../docs/QA-GUIDE.md#15-qa-默认设备v242-改)

**禁止**：
- ❌ 在 qa 容器 / 反复跑的脚本里默认指向生产设备（leaf-03/04/spine-01）
- ❌ 在没确认 device 的情况下 `ssh admin@192.168.100.5 "display ..."`（裸连生产）

---

## ops-toolkit 容器：设备排错唯一入口

### 什么时候用：

- 你怀疑某台设备网络不通，想知道是 ping 不通还是 SSH 22 端口挂了还是 NETCONF 830 端口挂了
- 你想快速验证 SSH 登录设备是否正常、能不能执行命令
- 你想验证 NETCONF 连接是否正常、设备能力集有哪些
- 你想从设备上抓一份 startup.cfg 到本地，快速对比配置差异
- 你要重启设备，并且需要自动等待 SSH 恢复确认设备真正起来了
- 你要对一台设备做全面审计（端口状态、VLAN 配置、路由表、版本信息等），输出标准化报告

### 禁止的裸写方式：

- ❌ 在宿主机上 sshpass -p xxx ssh admin@192.168.100.5 "display version"
- ❌ 在后端容器内 docker exec backend python3 -c "import paramiko; ..."
- ❌ ping 192.168.100.5 -c 3 然后手动 nc -zv 192.168.100.5 22 再 nc -zv 192.168.100.5 830
- ❌ 临时写个 test_connection.py 脚本放 backend 目录下

### 正确方式：

凭据怎么办： 不用手动敲密码。推荐 `--device <设备名>`，脚本自动从后端 API 查询 IP + 凭据（需 backend 容器在运行）。也支持 `--device <IP> --user admin --pass xxx` 或环境变量 `SSH_USER / SSH_PASS`。

**默认 device 不带参数时 = `.177` test 设备**（v2.4.2 改）。

文档发现： 每个脚本执行完末尾自动输出文档链接。

不需要提前翻文档，用的时候自然看到。想深入了解某个脚本的用法，跟着链接看对应章节。

如果脚本不够用： 容器内预装了 ping / nc / ssh / sshpass / nmap / curl / python3 + paramiko + ncclient + netmiko。如果现有 6 脚本覆盖不了你的需求，在这个容器内临时组合命令，但优先考虑把新需求封装成第 7 个脚本并同步更新 docs/ops-toolkit.md。

---

## QA 容器：测试唯一入口

### 什么时候用：

- commit 前跑后端测试（Apply 阶段必跑）
- archive 前跑前端 **lint + build**（v2.4.2 起，组件测试待 v2.5）
- 发版前跑全量测试
- 需要跑真机集成测试（`--integration` marker，**默认指向 .177**）

### 禁止的裸写方式：

- ❌ 在宿主机 pytest backend/tests/（依赖版本可能不一致）
- ❌ 在宿主机 cd frontend && npm run build（Node 版本可能不一致）
- ❌ 在后端容器内 pytest（qa-backend 有独立环境，不污染开发容器）
- ❌ 跳过 lint 直接 build（v2.4.2 起 lint 不过 build 不跑）

### 正确方式：

文档发现： QA 容器启动时自动输出 banner，跟着 QA-GUIDE 链接看 SOP 流程。

**前端 QA 流程**（v2.4.2 起）：
```bash
docker compose -f docker-compose.dev.yml --profile qa up qa-frontend
# 内部执行: npm run lint && npm run build
# lint 不过 → build 不跑 → exit 1
```

**后端 QA 流程**：
```bash
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
# 期望: 42+ tests PASS in <5s
# 集成测试默认 skip（不阻塞）
```

**真机集成**（按需）：
```bash
docker compose -f docker-compose.dev.yml run --rm --entrypoint "pytest -m integration -v" qa-backend
# 默认指向 .177 test 设备
```

不通过怎么办： 修代码 → 重跑 → 修测试 → 重跑。**不允许 skip 关闭测试，不允许不跑就 commit**。

---

## MCP 浏览器：小测试 / 单功能验证 / 排错

### 定位：**不进 qa 容器**

MCP 浏览器是 IDE 内嵌工具（`browser_navigate` / `browser_click` / `browser_snapshot` 等），用于：

- ✅ 单功能快速验证（点一下 UI 看返回对不对）
- ✅ 排错时直接看 console / network 请求
- ✅ 调试某个具体 API 的 UI 行为
- ✅ 真机 e2e 的 UI 流程验证（v2.4.1 backup-async 教训：必须用 MCP 浏览器跑一遍 UI 流程）

### 禁止的用法：

- ❌ **不进 qa 容器的全量回归**（MCP 浏览器是手动工具，不是 CI 工具）
- ❌ **不进 qa 容器的发布前验证**（必须走 qa-frontend lint + build + qa-backend pytest）
- ❌ 用 MCP 浏览器代替组件测试 / 单元测试（MCP 浏览器是手动点，不是自动断言）

### 正确边界：

| 场景 | 工具 |
|---|---|
| 单元 / 组件测试 | qa-backend pytest / qa-frontend vitest（v2.5 计划） |
| 全量回归 | qa 容器（lint + build + pytest） |
| 排错 / 单功能快速验证 | **MCP 浏览器** |
| 真机 e2e 流程 | MCP 浏览器 + 真机（QA 容器只跑 API 层） |

---

## 📊 工具边界表（v2.4.2 起）

| 工具 | 入口 | 用途 | 不做什么 | 何时跑 |
|---|---|---|---|---|
| **ESLint** | `qa-frontend` 容器内 `npm run lint` | 前端代码风格 / 错误检查 | 不做类型检查（vue-tsc 待 v2.5） | Apply + Archive |
| **Vitest** | `qa-frontend` 容器内 `npm run test`（v2.5 计划） | Vue 组件单元测试 | 不做 e2e | Archive（v2.5 起） |
| **vite build** | `qa-frontend` 容器内 `npm run build` | 编译验证 + 类型检查 | 不做 lint | Archive（lint 之后） |
| **MCP 浏览器** | IDE 内嵌工具 | 单功能验证 / 排错 / UI 流程 e2e | **不做全量回归 / 不进 qa 容器** | 按需 |
| **真机 e2e** | MCP 浏览器 + 真机（pytest --integration） | 端到端验证 | 不替代单元 / 集成测试 | 发版前 + 关键功能完成时 |
| **ops-toolkit 7 脚本** | `ops-toolkit` 容器 | 设备排错 / 巡检（v2.4.2.1 加 paramiko-batch-exec 单设备 SSH 批命令） | 不做批量压测（v2.4.2 加 perf 脚本） | 按需 |
| **qa-backend pytest** | `qa-backend` 容器 | 后端单测 / 集成 / bugfix regression | 不做压测（v2.4.2 perf-and-e2e 加） | Apply + Archive |

---

## 文档发现原则：用的时候自然看到，不提前翻

设计理念： 文档不是用来"提前学"的，是用来"用到时参考"的。所有文档链接都内置在工具的回显输出中——脚本末尾、容器 banner、错误提示。你不需要记住 /opt/docs/ops-toolkit.md 在哪，因为用 check-host 的时候它自己会告诉你。

### 新增工具/脚本的同步义务：

- 新增 ops-toolkit 脚本 → 必须在 docs/ops-toolkit.md 加对应章节（用法 + 示例 + 输出说明）
- 新增 QA 流程/模板 → 必须在 docs/QA-GUIDE.md 更新（SOP + checklist）
- 修改容器入口 → 必须同步更新 entrypoint-qa.sh 的 banner 链接
- 回显链接必须可落地 ——链接指向的文档章节必须真实存在，不允许断链
- 修改工具边界 / 默认设备 / MCP 浏览器定位 → 必须同步更新本文档

---

## 🔐 凭据规范（v2.4.2.1 复盘）

**核心原则：找不到凭据就明确报错，禁止 admin fallback**（v2.4.2.1 复盘教训：贴心的 admin 默认值会掩盖 .env 注入失败）。

### 凭据 4 级优先级（任何工具/脚本通用）

按顺序匹配，**任一来源找不到 → 立即报错**（不静默 fallback 到 admin）：

1. **命令行参数**：`--user` / `--pass` / `--pass-cipher`（Fernet 密文）
2. **环境变量**：`$SSH_USER` / `$SSH_PASS`
3. **`.env` 注入**：`$DEVICE_USERNAME` / `$DEVICE_PASSWORD`（**推荐，开箱即用**）
4. **兼容老 env**：`$DEVICE_USER` / `$DEVICE_PASS`

### 禁止动作

- ❌ **禁止 admin fallback**（v2.4.2.1 复盘）——找不到凭据时**写代码报明确错**并提示 `.env` 配置
- ❌ **禁止 `docker compose run -e USERNAME=xxx -e PASSWORD=xxx`** ——shell history 会泄露密码
- ❌ **禁止代码里硬编码 admin / password** ——commit 进 Git 永久泄露
- ❌ **禁止凭据进 commit message**（如 `Admin123!@#`）——bash `!@#` 还会触发 history expansion
- ❌ **禁止在 ops-toolkit 容器外裸写 `sshpass -p xxx ssh admin@192.168.100.5 "display version"`**

### 正确方式

- ✅ 不知道密码？→ 读 `.env`（`DEVICE_USERNAME` / `DEVICE_PASSWORD`），**不要特加 admin**
- ✅ 需要 Fernet 密文？→ 见 [docs/ops-toolkit.md §4.7 paramiko-batch-exec 凭据来源](../../docs/ops-toolkit.md#paramiko-batch-exec)
- ✅ 测试要传凭据？→ 走 `env_file: - .env`（docker-compose.dev.yml 已配）

### 触发条件

- ✅ 当用户问"密码是什么" → **不要回答具体值**，引导读 `.env`
- ✅ 当用户问"为什么找不到凭据" → 检查 `env_file` 配置（`docker-compose.dev.yml`）和 `.env` 存在性
- ✅ 当用户问"能不能加个默认 admin" → **明确拒绝**，引 v2.4.2.1 复盘

---

## ✅ 发版前测试清单（v2.4.2 强化）

### Apply 阶段（每个 Task 完成后）

- [ ] `qa-backend` 单测全过：`docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend`（`225 passed` baseline）
- [ ] 修改的 Python 文件 lint：`qa-backend` 容器内 `ruff check`（如果有）
- [ ] 修改的 Vue/TS 文件 lint：`qa-frontend` 容器内 `npm run lint`（v2.4.2 起必跑）

### Archive 阶段（change 闭环前）

- [ ] `qa-backend` 全量 pytest：必须 `225+ passed, 0 failed`（与上一发版 baseline 对比）
- [ ] `qa-frontend` lint + build：`docker compose -f docker-compose.dev.yml --profile qa up qa-frontend`（**lint 不过 build 不跑** → exit 1）
- [ ] ops-toolkit 工具回归：跑 1 条命令 `paramiko-batch-exec.sh --device test --command "display version"` 验证 success=1
- [ ] 容器 rebuild：`docker compose -f docker-compose.dev.yml build ops-toolkit qa-backend qa-frontend`（如有 Dockerfile / package.json / requirements.txt 改）

### 发版前（tag + push 前）

- [ ] 真机集成（按需）：`pytest -m integration --integration` 跑 .177 设备
- [ ] MCP 浏览器（按需）：关键 UI 流程（CMDB / 备份 / 删除设备 等）
- [ ] RELEASE-NOTES-vX.Y.Z.md 写完且包含 commit 序列 + 测试统计
- [ ] VERSION-ROADMAP.md 加 §X.Y.Z 章节 + §1 全景表加 1 行
- [ ] README.md 顶部版本表 + 当前架构表同步
- [ ] change archive 闭环（`git mv openspec/changes/<id>/ → archive/<date>-<id>/`）
- [ ] git tag vX.Y.Z + push（**需用户确认**）

### 禁止动作

- ❌ **禁止跳过 lint 直接 build**（v2.4.2 起 lint 不过 → build 不跑 → exit 1）
- ❌ **禁止 skip 关闭测试**（"修测试" 改为"修代码"，不允许修改测试让它通过）
- ❌ **禁止不跑测试就 commit**（每个 commit 前必跑相关 case）

---

## 🧹 容器清理规范（v2.4 起）

### 容器用完是否要删？

| 容器 | 用完处理 | 理由 |
|---|---|---|
| **h3c-netctrl-backend** | **保留**（不删） | 开发环境长跑，下次秒级连 |
| **h3c-netctrl-frontend** | **保留**（不删） | 同上，HMR 需要 |
| **h3c-netctrl-ops-toolkit** | **保留**（不删，但可 `docker compose stop`） | 单设备排错随时要；7 脚本容器化；启动 2-3s |
| **h3c-netctrl-qa-backend** | **保留**（不删） | 测试入口，CI 反复用 |
| **h3c-netctrl-qa-frontend** | **保留**（不删） | 同上 |
| **`docker compose run --rm`** 临时起的容器 | **自动删**（`--rm`） | 一次性任务（locust / 临时调试）|
| **`docker cp` 临时复制的文件** | **rebuild 后会丢** | 不持久化，需要持久化走 `.env` 或 volume mount |

### 清理 SOP（按需）

```bash
# 1. 看哪些容器在跑（不删先看）
docker ps --format 'table {{.Names}}\t{{.Status}}'

# 2. 停止但不删 ops-toolkit（保留 image，下次秒级启动）
docker compose -f docker-compose.dev.yml --profile ops stop ops-toolkit

# 3. 清理孤儿容器（已退出的临时容器）
docker container prune -f

# 4. 清理 24h+ 旧镜像（保留正在用的）
docker image prune -f --filter "until=24h"

# 5. 完整清理（含 volumes，慎用，会删 SQLite 数据库）
make clean   # 或 docker compose down --volumes --remove-orphans
```

### 详细 SOP

> [docs/CONTAINER-CLEANUP-SOP.md](../../docs/CONTAINER-CLEANUP-SOP.md) — v2.4 起强制遵循，列了"必须保留容器清单" + "可清理项" + "回滚路径"。

### 禁止动作

- ❌ **禁止无差别 `docker system prune -a`** ——会把 base image 全删，下次 build 慢 5+ min
- ❌ **禁止在生产数据库容器上 `docker compose down --volumes`** ——会清 SQLite
- ❌ **禁止 `docker rm -f` 已运行容器**（除非已 stop）——会丢未持久化的临时数据

---

## 🚦 使用姿势 + 禁止动作（除非不得已 + 触发条件）

### 通用原则

- ✅ **遇到任何排错 / 测试 / 验证需求 → 先想"有现成工具吗"** —— 工具目录见 [docs/ops-toolkit.md](../../docs/ops-toolkit.md) / [docs/QA-GUIDE.md](../../docs/QA-GUIDE.md)
- ✅ **现成工具覆盖不了** → 临时组合命令，但**优先考虑封装为新工具**并同步更新 docs
- ❌ **禁止绕过工具直接裸写命令**（除非满足下方"不得已"条件）

### "不得已"触发条件（允许裸写命令的 3 个例外）

1. **新工具开发本身**：正在写第 8 个 ops-toolkit 脚本时，可临时裸写 paramiko / ssh 调试
2. **底层 bug 排查**：工具本身坏了（如 sshpass + ssh H3C 兼容性问题），需要手动验证协议层
3. **CI/CD 自动化脚本**：在 GitHub Actions / GitLab CI 里必须裸写（容器化还没集成）

**所有"不得已"裸写后，必须：**
1. 在 commit message 注明"临时裸写：<原因>"
2. 在下个发版里**封装为工具**并删裸写代码
3. 同步更新本文档 + docs/ops-toolkit.md / docs/QA-GUIDE.md

### 典型反模式

| 反模式 | 为什么错 | 正确做法 |
|---|---|---|
| `sshpass -p xxx ssh admin@192.168.100.5 "display version"` | 凭据裸写在命令行 + 误连生产 | `docker compose ... run --rm ops-toolkit paramiko-batch-exec.sh --device test --command "display version"` |
| `docker exec backend python -c "import paramiko; ..."` | 污染后端容器 + 凭据泄露 | `docker compose ... run --rm ops-toolkit bash` → 跑工具 |
| `pytest backend/tests/ --integration`（宿主机） | 依赖版本不一致（paramiko 2.x vs 3.x） | `docker compose ... run --rm --entrypoint "pytest tests/ -m integration -v" qa-backend` |
| `cd frontend && npm run build`（宿主机） | Node 版本不一致 | `docker compose ... --profile qa up qa-frontend` |
| `ping 192.168.100.5 -c 3`（手动端口检查） | 慢 + 缺统一报告 | `docker compose ... run --rm ops-toolkit check-host --device <ip>` |
| `临时写 test_connection.py 放 backend/` | 污染后端源码 | `backend/tests/test_*.py` 走 pytest（qa-backend 跑） |

---

## 🔧 排错指南：不通了怎么办？

### 决策树（按现象查工具）

| 现象 | 第一步 | 第二步 | 兜底 |
|---|---|---|---|
| **设备 ping 不通** | `check-host --device <ip>` | 看 ping 输出 | `audit-switch` 看全状态 |
| **设备 SSH 22 不通** | `check-host --device <ip>`（看 SSH 状态） | `ssh-test` 试登录 | 设备侧 `display ssh server status` |
| **设备 NETCONF 830 不通** | `check-netconf --device <ip>` | 设备侧 `netconf ssh server enable` | backend API `GET /api/devices/<id>/test-netconf` |
| **H3C 设备 sshpass 报 ssh-rsa 错** | **必走 paramiko-batch-exec**（不裸写 sshpass）| `paramiko-batch-exec.sh --device <ip> --command "display version"` | SSHExecutor 内部 kex 配置 |
| **命令想批量下发给单设备** | `paramiko-batch-exec --device <ip> --commands-file <file>` | 看 JSON 输出 | 改 SSHExecutor 重试逻辑 |
| **命令想批量下发给多设备** | ❌ 当前不做（边界）| 用 backend 批量 API（前端 Batch 页面）| 自己写 Python 调多设备（不推荐）|
| **后端测试失败** | `qa-backend` 容器跑 pytest，看 traceback | 改代码或测试 | 跑 `pytest -v --tb=long` 看完整堆栈 |
| **前端 build 失败** | `qa-frontend` 容器跑 `npm run lint && npm run build` | 修 lint / 类型错 | `npm run build --debug` |
| **前端 UI 行为异常** | **MCP 浏览器**（不开 qa 容器）| 查 console / network | backend API 测试 |
| **不知道密码** | 读 `.env`（`DEVICE_USERNAME` / `DEVICE_PASSWORD`）| 不要特加 admin | 找文档不要凭据值 |
| **不知道用什么容器** | 查本文档"工具边界表" | 查 `docs/ops-toolkit.md` / `docs/QA-GUIDE.md` | 问用户 |

### 排错铁律

- ❌ **禁止在不通时改代码试**（先排错，不通 ≠ 错）
- ❌ **禁止在不通时 reset 设备**（先 SSH 验证设备活着）
- ❌ **禁止裸写 `paramiko` 协议代码**（必复用 backend SSHExecutor）
- ❌ **禁止反复跑 1 个工具 10+ 次**（看 stderr 末尾的文档链接，去查文档）

### 兜底文档

- 设备排错：[docs/ops-toolkit.md](../../docs/ops-toolkit.md) — 7 脚本完整用法
- 后端测试：[docs/QA-GUIDE.md](../../docs/QA-GUIDE.md) — qa-backend SOP
- 前端测试：[docs/QA-GUIDE.md § 1 容器清单](../../docs/QA-GUIDE.md#1-容器清单) + [docs/QA-GUIDE.md § 2.4 发版前必跑全量](../../docs/QA-GUIDE.md#24-发版前必跑全量) — lint + build（前端 QA 流程见文档顶部引用）
- 容器清理：[docs/CONTAINER-CLEANUP-SOP.md](../../docs/CONTAINER-CLEANUP-SOP.md) — 必保留清单
- 架构蓝图：[docs/CONTAINER-DECOUPLING.md](../../docs/CONTAINER-DECOUPLING.md) — 3 容器职责
- 版本路线：[VERSION-ROADMAP.md](../../VERSION-ROADMAP.md) — 当前到哪版 / 接下来做啥
- 项目经验：[/home/bytedance/.trae-cn/memory/projects/-root-workpace-h3c-netctrl/project_memory.md](file:///home/bytedance/.trae-cn/memory/projects/-root-workpace-h3c-netctrl/project_memory.md) — 硬约束 / 工程规约 / 教训

---

## � 文档维护义务

qa 规范本身的维护规则：本文档是必然被读到的（每次 AI 启动必读），**本文档之外的"项目级 / OpenSpec 闭环回归 / A/B 文档分类"等维护规范**见 [.trae/rules/project-convention.md](project-convention.md)（v2.4.2.1 拆出）。

qa 规范自身同步义务（与 project-convention 互补）：

- 任何工具 / 脚本 / 测试 / 排错规范变化 → **必须同步更新本文档**
- 任何 ops-toolkit 脚本新增 → 更新 [docs/ops-toolkit.md](../../docs/ops-toolkit.md) + **本文档边界表**
- 任何 QA 流程变化 → 更新 [docs/QA-GUIDE.md](../../docs/QA-GUIDE.md) + **本文档边界表**
- 任何容器入口变化 → 更新 `backend/entrypoint-qa.sh` banner + **本文档相关章节**
- 任何凭据规范变化 → 更新本文档"凭据规范" + [docs/ops-toolkit.md §4.7](../../docs/ops-toolkit.md#paramiko-batch-exec)
- 任何发版前测试变化 → 更新本文档"发版前测试清单"
- 任何容器清理 SOP 变化 → 更新本文档"容器清理规范" + [docs/CONTAINER-CLEANUP-SOP.md](../../docs/CONTAINER-CLEANUP-SOP.md)
- **回显链接必须可落地** ——不允许断链，不允许指向未存在的章节

