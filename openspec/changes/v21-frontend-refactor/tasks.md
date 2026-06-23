# v21-frontend-v2 Tasks

实施顺序：新 frontend 搭建 + 后端对接 → Dockerfile 适配 → 本地端到端 + 子页面适配 → QA 容器修整迭代 → 旧 frontend backup → 归档 + 删 PoC

每个 Phase 一次 commit，commit 粒度保持"一次可提交、可自测、可运行"。

---

## Phase 1: 新 frontend 搭建 + 后端对接

> 目标：基于 PoC 脚手架搭建新 frontend，删除 mock.js，对接后端 7 个 API

- [ ] 1.1 复制 `frontend-poc/` 内容到 `frontend/`（脚手架起步）
- [ ] 1.2 删除 `frontend/src/mock.js`（PoC 临时数据）
- [ ] 1.3 新增 `frontend/src/api/index.js` —— API 客户端封装（参考旧 `frontend/src/api/index.js`）
- [ ] 1.4 扩展 API 客户端覆盖 7 个后端 API（dashboardApi / deviceApi / executeApi / interfaceApi / batchApi / assetApi / logApi）
- [ ] 1.5 Dashboard.vue —— 改用 dashboardApi 拉数据
- [ ] 1.6 Devices.vue —— 改用 deviceApi 拉数据
- [ ] 1.7 OpsTerminal.vue —— 改用 executeApi
- [ ] 1.8 Interfaces.vue —— 改用 interfaceApi
- [ ] 1.9 Batch.vue —— 改用 batchApi
- [ ] 1.10 CMDB.vue —— 改用 assetApi
- [ ] 1.11 Logs.vue —— 改用 logApi
- [ ] 1.12 验证 7 个 view 都能正确拉取/发送数据
- [ ] 1.13 保留 3 个未来 view（Topology / Backup / AIAssistant）作为占位
- [ ] 1.14 commit: `feat(frontend): v2.1 scaffold + backend integration`

## Phase 2: Dockerfile 适配

> 目标：Dockerfile.dev / Dockerfile.qa 适配 Vite + Tailwind 构建

- [ ] 2.1 适配 `frontend/Dockerfile.dev` —— Node 20 + `npm install` + `npm run dev`
- [ ] 2.2 适配 `frontend/Dockerfile.qa` —— Node 20 + `npm install` + `npm run build`
- [ ] 2.3 验证本地 `make dev` 启动正常
- [ ] 2.4 commit: `chore(docker): adapt Dockerfile to Vite + Tailwind`

## Phase 3: 本地端到端测试 + 子页面适配升级

> 目标：本地 `make dev` 端到端跑通，并对 PoC 未真验证的子页面做适配升级

- [ ] 3.1 启动 `make dev`，本地浏览器端到端走查 10 个 view
- [ ] 3.2 走查首页（Dashboard）—— 确认 KPI / 设备总览 / 快速入口正常
- [ ] 3.3 走查 Devices —— 列表 / 新增 / 编辑 / 删除 / 测试连接
- [ ] 3.4 走查 OpsTerminal —— 命令执行 + 输出展示
- [ ] 3.5 走查 Interfaces —— 接口列表 / 配置下发
- [ ] 3.6 走查 Batch —— 批量操作
- [ ] 3.7 走查 CMDB —— 资产信息 / 刷新
- [ ] 3.8 走查 Logs —— 日志筛选 / 搜索
- [ ] 3.9 走查 3 个未来 view（Topology / Backup / AIAssistant）—— 确认占位正常
- [ ] 3.10 子页面适配升级：PoC 中未真验证的 view，按视觉系统规范（米白/圆角/阴影/字体/背景光晕）做适配
- [ ] 3.11 修复走查中发现的 UI / 交互 / 数据问题
- [ ] 3.12 记录走查结果，commit: `feat(frontend): e2e walkthrough + subpage polish`

## Phase 4: QA 容器修整迭代

> 目标：用 QA 容器测后端 → 本地补前端/适配 → 修整容器 → QA 再测，迭代至稳定

- [ ] 4.1 用已有 QA 容器跑 `make qa-backend` 验证后端测试通过
- [ ] 4.2 对比 QA 容器覆盖范围 vs 本地新增，识别 QA 中缺失的部分（前端构建 / 端到端等）
- [ ] 4.3 修整 QA 容器：删除原 QA 中废弃的步骤，加入前端构建 / 端到端验证
- [ ] 4.4 重新构建 QA 镜像：`make qa-frontend` 验证前端 build 通过
- [ ] 4.5 `make qa-backend` 验证后端测试仍通过
- [ ] 4.6 修复 QA 验证过程中发现的所有 build / lint / 测试错误
- [ ] 4.7 commit: `chore(qa): align QA container with v2.1 frontend`

## Phase 5: 旧 frontend backup

> 目标：新 frontend 稳定后，旧 frontend 保留为 backup，不被任何 compose/CI 引用

- [ ] 5.1 验证 `frontend/` 完全独立运行，旧 `frontend/` 未被引用
- [ ] 5.2 `git mv frontend frontend.bak` —— 旧版本 backup 化
- [ ] 5.3 验证 docker-compose / Makefile / CI 不引用 frontend.bak（只引用 frontend/）
- [ ] 5.4 commit: `chore: backup legacy frontend to frontend.bak`

## Phase 6: 归档 + 删 PoC

> 目标：归档 v21 change，确认 PoC 不被调用后删除

- [ ] 6.1 验证 frontend-poc/ 不被任何代码引用
- [ ] 6.2 归档 `openspec/changes/v21-frontend-refactor` → `openspec/changes/archive/`
- [ ] 6.3 删除 `frontend-poc/` 目录（PoC 工作完成使命）
- [ ] 6.4 commit: `chore: archive v21 + remove frontend-poc`
