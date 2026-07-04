# v242-qa-and-tooling Tasks

> v2.4.2 Change 1 = qa 规范与工具完善（ESLint + 默认 test 设备）。
> v2.4.2 整体 3 个 change，本 change 是 #1（qa 完善），#2 是压测，#3 是 review。

---

## 1. Proposal 阶段

- [x] 1.1 起草 proposal.md（Why / What / Acceptance / Impact / 真机验证 / Out of Scope）
- [x] 1.2 起草 design.md（ESLint 选型 / 容器流程 / test 设备 / qa 规范改写 / 文件清单 / 升级回退 / 风险）
- [x] 1.3 起草 tasks.md（本文件）
- [x] 1.4 起草 spec delta（MODIFIED requirements：qa-spec / ops-toolkit-ux）

---

## 2. 主线 1：前端 ESLint 进 qa 容器

### 2.1 装包 + 配置

- [x] 2.1.1 `cd frontend && npm i -D eslint@^8.57.0 eslint-plugin-vue@^9 --registry https://registry.npmmirror.com/`（实测：`@vue/eslint-config-vue` 404 + `eslint-config-vue@2.0.2` 版本冲突，最终只用 `eslint-plugin-vue`）
- [x] 2.1.2 写 `frontend/.eslintrc.cjs`（extends: ['plugin:vue/vue3-essential'] + 个人规则：v-for key、PascalCase、no-unused-vars）
- [x] 2.1.3 写 `frontend/.eslintignore`（dist / node_modules / public / *.config.js / .vscode/ / .idea/）
- [x] 2.1.4 `frontend/package.json` 加 `scripts.lint: "eslint --ext .js,.vue src --max-warnings 0"`

### 2.2 验证 lint 跑通

- [x] 2.2.1 `npm run lint` 跑一遍，记录 issue 数（实测：0 error / 0 warning）
- [x] 2.2.2 issue 数 > 50 → 评估是否放宽规则（保留 essential 即可，去掉 recommended）— 不需要，初始 0 issue
- [x] 2.2.3 修存量代码 lint issue 或调整规则到 0 error
- [x] 2.2.4 再跑 `npm run lint` 确认 0 error

### 2.3 qa-frontend 容器集成

- [x] 2.3.1 改 `frontend/Dockerfile.qa`：
  ```dockerfile
  CMD ["sh", "-c", "npm run lint && npm run build"]
  ```
- [x] 2.3.2 `docker compose -f docker-compose.dev.yml build qa-frontend`
- [x] 2.3.3 `docker compose -f docker-compose.dev.yml --profile qa run --rm qa-frontend`
- [x] 2.3.4 验证：输出含 lint + build 两段；都过 → exit 0

### 2.4 故意制造 fail 验证

- [x] 2.4.1 在 `frontend/src/api/index.js` 故意加 `import { unused } from 'vue'`（未使用 import）
- [x] 2.4.2 重跑 `docker compose --profile qa run --rm qa-frontend` → 验 fail（lint 报错，build 不跑）
- [x] 2.4.3 还原代码

### 2.5 commit

- [x] 2.5.1 `git add frontend/.eslintrc.cjs frontend/.eslintignore frontend/package.json frontend/Dockerfile.qa`
- [x] 2.5.2 `git commit -m "feat(frontend-lint): qa-frontend 容器跑 lint + build (ESLint 8 + vue plugin)"` → commit 2ad6678

---

## 3. 主线 2：默认 test 设备进 qa 工具

### 3.1 _lib.sh 增强

- [x] 3.1.1 改 `ops-toolkit/scripts/_lib.sh` 加 `_resolve_alias()` 函数（test→.177 / leaf-03→.4 / leaf-04→.5 / spine-01→.100，其他透传）
- [x] 3.1.2 加 `DEFAULT_DEVICE="test"` 常量
- [x] 3.1.3 加 `_get_device_arg()` 工具函数：解析 `--device` 参数，缺省用 `DEFAULT_DEVICE`
- [x] 3.1.4 加 `_print_device_banner()` 工具函数：默认 / 显式生产时输出提示

### 3.2 6 脚本接入

- [x] 3.2.1 改 `check-host.sh`：脚本入口加 `_get_device_arg "$@"`
- [x] 3.2.2 改 `ssh-test.sh`：同上
- [x] 3.2.3 改 `check-netconf.sh`：同上
- [x] 3.2.4 改 `capture-config.sh`：同上
- [x] 3.2.5 改 `reboot-wait.sh`：同上
- [x] 3.2.6 改 `audit-switch.sh`：同上

### 3.3 验证默认行为

- [x] 3.3.1 `docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit check-host.sh`（不带参数）→ 验指向 .177
- [x] 3.3.2 同上 `--device test` → 验指向 .177
- [x] 3.3.3 同上 `--device 192.168.100.5` → 验显式指 .5 + warn 日志
- [x] 3.3.4 同上 `--device leaf-04` → 验解析为 .5

### 3.4 容器 banner 增强

- [x] 3.4.1 改 `ops-toolkit/entrypoint.sh`（或入口脚本）加 "📌 默认目标：Test-Switch-177 (192.168.100.177)"（实测：_print_device_banner 在每个脚本入口都打印，重复但确保可见）

### 3.5 文档同步

- [x] 3.5.1 改 `docs/ops-toolkit.md`：新增"设备名→IP 映射表"章节 + `--device test` 用法
- [x] 3.5.2 改 `docs/QA-GUIDE.md`：新增"qa 默认设备"小节

### 3.6 commit

- [x] 3.6.1 `git add ops-toolkit/ docs/ops-toolkit.md docs/QA-GUIDE.md`
- [x] 3.6.2 `git commit -m "feat(qa-tooling): 默认 test 设备 .177 + 设备名→IP 别名映射"` → commit ff3c986

---

## 4. 主线 3：qa 规范.md 重写

### 4.1 改写规则

- [x] 4.1.1 第 34 行 "build + 组件测试" → "lint + build（组件测试待 v2.5）"
- [x] 4.1.2 新增 "qa 默认设备" 章节（强制 .177 / 禁用生产）
- [x] 4.1.3 新增 "MCP 浏览器定位" 章节（小测试/不进 qa 容器）
- [x] 4.1.4 新增 "工具边界表" 章节（ESLint / Vitest / build / MCP 浏览器 / 真机 e2e 各 1 行）

### 4.2 commit

- [x] 4.2.1 `git add .trae/rules/qa规范.md`
- [x] 4.2.2 `git commit -m "docs(qa-spec): qa 规范重写 (lint+build / 默认 test 设备 / MCP 边界)"`

---

## 5. 回归

- [ ] 5.1 qa-backend `pytest` 跑一遍，确认仍 214 passed
- [ ] 5.2 qa-frontend 跑一遍，确认 lint + build 都过
- [ ] 5.3 ops-toolkit 6 脚本各跑一遍，确认默认行为正确
- [ ] 5.4 3 容器（ctrl / config / data）仍在跑，没破坏

---

## 6. 收尾

- [ ] 6.1 `openspec archive v242-qa-and-tooling`（在 v2.4.2 全部 3 个 change 收尾后做，本 change 不单 archive）
- [ ] 6.2 等 v2.4.2 Change 2（v242-perf-and-e2e）和 Change 3（v242-3container-review）都完成后再一起打 tag v2.4.2
- [ ] 6.3 写 `RELEASE-NOTES-v2.4.2.md`（v2.4.2 全部 3 个 change 收尾后）
- [ ] 6.4 更新 `VERSION-ROADMAP.md` v2.4.2 条目

---

## 工时预估

- 主线 1（ESLint）：2-3 小时（含存量代码修复）
- 主线 2（test 设备）：1-2 小时
- 主线 3（qa 规范改写）：30 分钟
- 回归：30 分钟

**合计**：4-6 小时（半天到 1 天）

---

## 完成标准

- [x] qa-frontend 容器跑 lint + type-check + build 都过
- [x] ops-toolkit 6 脚本默认指向 .177
- [x] 故意改 unused import → lint 失败 → build 不跑
- [x] 故意写错类型（.ts 文件）→ type-check 失败 → build 不跑
- [x] qa-backend 214 passed 不破
- [x] `.trae/rules/qa规范.md` 重写完成
- [x] `docs/ops-toolkit.md` + `docs/QA-GUIDE.md` 同步
- [x] 3 commit（每个主线 1 个）— commit 2ad6678 / ff3c986 / be8d485
