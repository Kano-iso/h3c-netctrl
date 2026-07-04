## 工具使用红线：开箱即用，不裸写命令
### 核心原则
项目已投入精力构建了 2 个专用工具容器（ops-toolkit + QA）+ 1 个 MCP 浏览器工具，所有文档链接已内置在回显中。当你需要排错或测试时，如果能直接复用这些现成能力，就不需要从零开始手工拼命令。用了工具自然看到文档，看到文档自然知道怎么用 ——形成闭环。

---

## 📌 qa 默认设备（v2.4.2 起强制）

**所有 qa 工具 / qa 测试 / 反复跑的脚本，默认指向 Test-Switch-177 (192.168.100.177)**：

- **强制理由**：qa 工具"反复跑"特性，误连生产可能导致配置污染（v2.3 教训：曾误改 Leaf-04 的 vlan 100）
- **ops-toolkit 6 脚本**：`check-host / ssh-test / check-netconf / capture-config / reboot-wait / audit-switch`
  - 不带 `--device` = 默认 `.177`（安全默认）
  - `--device test` / `Test-Switch` / `Test-Switch-177` = 显式 test
  - `--device <生产 IP>` = 显式生产（日志 warn，但不阻止）
  - 设备名别名：`leaf-03` / `leaf-04` / `spine-01` → 对应生产 IP
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
| **ops-toolkit 6 脚本** | `ops-toolkit` 容器 | 设备排错 / 巡检 | 不做批量压测（v2.4.2 加 perf 脚本） | 按需 |
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
