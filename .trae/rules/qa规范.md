## 工具使用红线：开箱即用，不裸写命令

项目已投入精力构建了 2 个专用工具容器（ops-toolkit + QA）+ 1 个 MCP 浏览器工具，**所有文档链接已内置在回显中**——脚本末尾、容器 banner、错误提示。看到链接再去查文档，用到时自然看到。

---

## 📌 立场速览（规则只讲立场，不讲细节）

| 场景 | 立场 |
|---|---|
| 设备排错 | 走 `ops-toolkit` 容器（7 脚本）—— 唯一入口 |
| 后端 / 前端测试 | 走 `qa-backend` / `qa-frontend` 容器 —— 唯一入口 |
| 单功能 UI 验证 / 排错 | 用 **MCP 浏览器**（不进 qa 容器、不做全量回归） |
| 默认测试设备 | `.177`（Test-Switch-177）—— 反复跑工具默认指向，不连生产 |
| 凭据 | QA 阶段已注入工具，用户不传、不查、不怀疑 |
| 容器 | 测完没需求就 `docker container prune -f`；5 个常驻容器保留，别无差别 `docker system prune -a` |

详细 SOP / 脚本用法 / 工具命令 → 见 [docs/ops-toolkit.md](../../docs/ops-toolkit.md) / [docs/QA-GUIDE.md](../../docs/QA-GUIDE.md)。

---

## 🚫 禁止动作（全文件唯一一份）

> 任何场景下都生效的硬红线。

- ❌ **宿主机 / 容器内裸写 SSH/paramiko 命令**（sshpass / docker exec / 手写 paramiko）—— 走 ops-toolkit
- ❌ **宿主机跑 pytest / npm run build** —— 走 qa-backend / qa-frontend（环境不一致）
- ❌ **qa 容器 / 反复跑脚本默认指向生产设备**（leaf-03/04/spine-01）—— 默认 .177
- ❌ **跳过 lint 直接 build**（lint 不过 → build 不跑 → exit 1）
- ❌ **skip 关闭测试**（"修测试" 改为"修代码"）
- ❌ **不跑测试就 commit**
- ❌ **不通时改代码试 / reset 设备** —— 先 SSH 验证设备活着
- ❌ **反复跑同一工具 10+ 次** —— 看 stderr 末尾的文档链接
- ❌ **admin fallback**（凭据找不到时）—— 写代码报明确错，提示 `.env` 配置（v2.4.2.1 复盘）

---

## 🧰 工具容器职责

### ops-toolkit — 设备排错唯一入口

- **关键核心定位**：仅作为验证/排错工具，**不要放任何业务逻辑**
- 5 脚本：`check-host / check-netconf / capture-config / reboot-wait / paramiko-batch-exec`
- 凭据 / 命令 / 默认 device 由工具自己处理，用户不传参
- 每个脚本末尾自动输出文档链接（用法 + 凭据来源）
- 脚本不够用 → 容器内临时组合，但**优先封装为新工具**并同步更新 docs/ops-toolkit.md

### QA 容器 — 测试唯一入口

- 入口：`docker compose -f docker-compose.dev.yml --profile qa up <qa-backend|qa-frontend>`
- 后端：pytest（225+ passed baseline）
- 前端：lint → build（lint 不过 build 不跑）
- 集成测试：默认 skip（不阻塞），真机 e2e 按需 `--integration`
- 不通过怎么办：修代码 → 重跑 → 修测试 → 重跑。**不允许 skip**

### MCP 浏览器 — 单功能 / 排错（不进 qa 容器）

- ✅ 单功能快速验证 / 排错 / UI 流程 e2e
- ❌ 不做全量回归 / 不替代组件测试 / 不替代单元测试
- 工具边界：单元/组件测试 → qa 容器；全量回归 → qa 容器；排错/单功能 → MCP 浏览器

---

## 🔧 排错铁律

不通了先看现象 → 选工具：

- 设备 ping/SSH/NETCONF 不通 → `check-host` / `check-netconf`（详见 docs/ops-toolkit.md）
- H3C sshpass 报 ssh-rsa 错 → 走 `paramiko-batch-exec`（SSHExecutor 内部 kex 兼容）
- 后端测试失败 → `qa-backend` 容器看 traceback
- 前端 build 失败 → `qa-frontend` 容器看 lint 错
- 前端 UI 异常 → **MCP 浏览器**（不开 qa 容器）

兜底文档：[docs/ops-toolkit.md](../../docs/ops-toolkit.md) / [docs/QA-GUIDE.md](../../docs/QA-GUIDE.md) / [VERSION-ROADMAP.md](../../VERSION-ROADMAP.md)。

---

## ✅ 发版前测试 checklist

### Apply 阶段（每 Task 后）

- [ ] `qa-backend` 单测全过

### Archive 阶段（change 闭环前）

- [ ] `qa-backend` 全量 pytest（与 baseline 对比）
- [ ] `qa-frontend` lint + build（lint 不过 build 不跑）

### 发版前（tag + push 前）

- [ ] 真机集成（按需）：`pytest -m integration --integration` 跑 .177
- [ ] MCP 浏览器（按需）：关键 UI 流程
- [ ] git tag + push（**需用户确认**）
- [ ] 文档同步（RELEASE-NOTES / VERSION-ROADMAP / README / change archive）→ 见 [.trae/rules/project-convention.md](project-convention.md) §Checkpoint 2

---

## 📌 文档维护原则（规则层，不指定具体文件）

本文档是规则类（C 类），**只规定"什么时候必须更新文档"**，不规定"具体更新哪个文件"——具体由各容器 / 工具 / entrypoint 自己决定。

- ✅ **新增 / 修改任何工具、脚本、测试、排错规范、容器入口、凭据规则、发版流程** → 对应文档必须被回写（哪个文件由当事方自己决定）
- ✅ **回显链接必须可落地** —— 不允许断链；任何回显的文档链接指向的章节必须真实存在
- ✅ **本文档自身的维护义务** → 见 [.trae/rules/project-convention.md](project-convention.md)（A/B/C 分类 + 同步 checkpoint）

> **规则只管"该不该更新"，不管"更新到哪里"** —— 后者是容器 / 工具 / entrypoint 自己的事。
