# QA 容器使用指南

> **目标**：让所有 OpenSpec change 在 Apply / Archive 阶段都跑 QA 容器，避免 v2.2.0 漏 QA 环节的教训（commit 19 个没跑过 1 次 qa-backend，全靠用户实测抓 bug）。

---

## 1. 容器清单

项目已有 2 个 QA 容器（profile: qa）：

| 容器 | 用途 | 装包消耗 | 何时跑 |
|---|---|---|---|
| `qa-backend` | 跑 `pytest backend/tests/` | 0（paramiko + pytest 已装） | Apply 必跑 |
| `qa-frontend` | 跑 `npm run build` + `npm run test`（v2.3+ 加 vitest） | v2.3 引入 vitest ~10MB | Archive 必跑 |

**日常不起**（profile: qa），需要时手动起：
```bash
docker compose -f docker-compose.dev.yml --profile qa up <qa-backend|qa-frontend>
```

---

## 2. 跑法 SOP

### 2.1 Apply 阶段必跑（commit 前）

```bash
# 后端 QA（unit + smoke + bugfix regression + xml builder）
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
# 期望：42+ tests PASS in <5s
# 集成测试默认 skip（不阻塞）
```

**不通过怎么办**：
- 修代码 → 重跑
- 修测试 → 重跑
- **不允许 skip 关闭测试**

### 2.2 Archive 阶段必跑

```bash
# 前端 QA（编译 + 组件测试 v2.3+）
docker compose -f docker-compose.dev.yml --profile qa up qa-frontend
# 期望：vite build 55+ modules 编译过 + (v2.3+) vitest 组件测试全 PASS
```

### 2.3 真机集成（按需，设备通时跑）

```bash
# 集成测试（默认 skip）
docker compose -f docker-compose.dev.yml run --rm --entrypoint "pytest -m integration -v" qa-backend
# 期望：所有 @pytest.mark.integration 跑通
```

**约束**（来自 project_memory lessons learned）：
- ✅ 集成测试必须有 `restore_original_state` 步骤（n → n+1 → n）
- ✅ reboot 验证必须 sleep + retry 至少 90s
- ✅ 凭理论推断打 [x] 是禁止的

### 2.4 发版前必跑全量

```bash
# 全量 QA（后端 + 前端）
docker compose -f docker-compose.dev.yml --profile qa up --abort-on-container-exit
```

---

## 3. 增量规范（新模块 / 新 API 必加 test）

**每次新增功能**：

| 步骤 | 动作 | 何时 |
|---|---|---|
| 1 | 实现 API / UI | Apply 阶段 |
| 2 | **加 test**（smoke + 错误码 + 中文错误） | Apply 阶段（紧跟实现） |
| 3 | 跑 `docker compose --profile qa up qa-backend` 验证 | Apply 阶段（commit 前） |
| 4 | 写 6.x 浏览器验证项（如有 UI） | tasks.md |
| 5 | 跑 `docker compose --profile qa up qa-frontend` 验证编译 | Archive 阶段 |
| 6 | 在 change proposal.md 写 "QA 验证计划" 段 | Propose 阶段 |
| 7 | 在 RELEASE-NOTES.md 写 "QA 覆盖" 小节 | Archive 阶段 |

**反面教材**（v2.2.0）：14 个新 API 0 测试覆盖，全靠用户实测抓 4 个 bug。

---

## 4. 模板位置

| 文档 | 位置 | 何时用 |
|---|---|---|
| PRD QA 模板 | [openspec/changes/QA-TEMPLATE.md](../openspec/changes/QA-TEMPLATE.md) | 每个 change 的 proposal.md 必含 |
| 本文档 | [docs/QA-GUIDE.md](QA-GUIDE.md) | 跑 QA 容器时看 |
| v2.2.0 漏项清单 | [v2.2.1-followup-v22-qa-repair](../openspec/changes/v2.2.1-followup-v22-qa-repair/proposal.md) | 补 v2.2.0 漏的 14 API |
| v2.3 QA 规划 | [v2.3-roadmap](../openspec/changes/v2.3-roadmap/proposal.md) § QA 规范化 | v2.3 引入 vitest + 模板强制 |

---

## 5. 常见问题

### Q1: 集成测试连不上设备，CI 怎么不阻塞？

A: conftest.py 已配 `@pytest.mark.integration` 默认 skip。设备通时手动跑 `pytest --integration`。**不阻塞 CI**。

### Q2: v2.2.0 14 个新 API 啥时候补？

A: 走 [v2.2.1-followup-v22-qa-repair](../openspec/changes/v2.2.1-followup-v22-qa-repair/proposal.md)，P0。建议 Apply 步骤：
1. test_smoke.py 加 14 个 existence smoke
2. test_backup_api.py / test_vpn_api.py / test_interface_edit_api.py 加错误码
3. test_backup_integration.py + test_vpn_integration.py 跑真机（含 reboot verify）

### Q3: 为什么不去 Playwright？

A: 个人项目 ROI 低，模拟点击 = 300MB 浏览器 + 高维护。**真·有价值的回归 = API 层 + 设备协议层**。

### Q4: 怎么知道现在覆盖了多少 API？

A: 看 `backend/tests/` 列表 + grep `client.{get,post,put,delete,patch}` 数端点引用。

### Q5: v2.2.0 为什么漏了？

A: 流程没强制。v2.3 起强制：每个 PRD 必含 "QA 验证计划" 段 + Apply 必跑 qa-backend + Archive 必跑 qa-frontend。

---

## 6. CI 集成

`.github/workflows/qa.yml`（v2.3 计划加）：

```yaml
name: QA
on: [push, pull_request]
jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build qa-backend
        run: docker compose -f docker-compose.dev.yml --profile qa build qa-backend
      - name: Run qa-backend
        run: docker compose -f docker-compose.dev.yml --profile qa up qa-backend --abort-on-container-exit
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build qa-frontend
        run: docker compose -f docker-compose.dev.yml --profile qa build qa-frontend
      - name: Run qa-frontend
        run: docker compose -f docker-compose.dev.yml --profile qa up qa-frontend --abort-on-container-exit
```

---

## 7. 检查清单（每个 change Apply 前自查）

- [ ] proposal.md 含 "QA 验证计划" 段（按 QA-TEMPLATE.md 模板）
- [ ] 涉及的新 API 都有 test_smoke.py existence smoke
- [ ] 涉及的新 API 都有错误码 test（404 / 422 / 403 / 410）
- [ ] 中文错误信息测试（不是裸抛技术异常）
- [ ] `docker compose --profile qa up qa-backend` 全 PASS
- [ ] 真机集成（涉及设备时）：`pytest --integration` 全 PASS
- [ ] 集成测试有 `restore_original_state`（n → n+1 → n）

---

## 8. 关联

- PRD QA 模板：[openspec/changes/QA-TEMPLATE.md](../openspec/changes/QA-TEMPLATE.md)
- v2.2.0 漏项补齐：[openspec/changes/v2.2.1-followup-v22-qa-repair](../openspec/changes/v2.2.1-followup-v22-qa-repair/proposal.md)
- v2.3 QA 规范化：[openspec/changes/v2.3-roadmap](../openspec/changes/v2.3-roadmap/proposal.md)
- 容器定义：[docker-compose.dev.yml](../docker-compose.dev.yml)（`qa-backend` / `qa-frontend`）
- QA backend Dockerfile：[backend/Dockerfile.qa](../backend/Dockerfile.qa)
- QA frontend Dockerfile：[frontend/Dockerfile.qa](../frontend/Dockerfile.qa)
