# PRD QA 模板（强制规范）

> **每个 OpenSpec change 的 `proposal.md` 必含 "QA 验证计划" 段**，按本模板填写。否则视为不完整 PRD，必须补齐才能进入 Apply。

## 模板（复制到 proposal.md 末尾）

```markdown
## QA 验证计划

### 1. 涉及端点 / UI / 设备

| 类别 | 名称 | 涉及文件 |
|---|---|---|
| 后端 API | POST /api/devices/{id}/backup | backend/app/routers/backup.py |
| 前端 UI | BackupListModal.vue "立即备份" 按钮 | frontend/src/components/BackupListModal.vue |
| 真实设备 | 192.168.100.4 (Leaf-03) | - |

### 2. QA 验证项

#### 2.1 后端 API 单元 / 集成（qa-backend 容器跑）

- [ ] 端点 existence smoke（test_smoke.py 加 1 个 case）
- [ ] 成功路径（mock SSH / paramiko / NETCONF，验证返回数据结构）
- [ ] 错误码：设备不存在 404 / 锁定 403 / body 非法 422 / 文件丢失 410
- [ ] 中文错误信息（"备份失败: 设备不可达"而非裸抛技术异常）
- [ ] 业务约束：force / 二次校验 / 锁定禁删

#### 2.2 前端 UI 验证（qa-frontend 容器跑 vite build + 人工浏览器验证）

- [ ] `npm run build` 编译过（55 modules 编译过 = 语法 / import 错误捕获）
- [ ] 浏览器 6.x 验证（按 change tasks.md 列的 6.1-6.11 或同类）
- [ ] 可选 vitest 组件测试（v2.3+ 启用）

#### 2.3 真机集成（pytest --integration 跑 192.168.100.4 / .5）

- [ ] 设备 192.168.100.4 / .5 端到端（按 change 能力列）
- [ ] **最后必须 restore_original_state**（n → n+1 → n，不允许只测 happy path）
- [ ] reboot 类验证必须 sleep + retry 至少 90s（不是 1 次 timeout 失败就推断）
- [ ] 凭理论推断打 [x] 是禁止的——实测 vs 推断必须在 tasks.md 严格区分

#### 2.4 回归

- [ ] vX.Y 已 archive 的所有 changes 不能破坏（qa-backend 跑 42+ tests 全 PASS）
- [ ] 不破坏既有功能（grep "test_" tests/ 看覆盖）

### 3. 跑法

```bash
# unit + smoke（CI 必跑，秒级）
docker compose -f docker-compose.dev.yml --profile qa up qa-backend

# 集成（按需跑，分钟级，需 SSH 通设备）
docker compose -f docker-compose.dev.yml run --rm --entrypoint "pytest -m integration -v" qa-backend

# 前端编译（CI 必跑，秒级）
docker compose -f docker-compose.dev.yml --profile qa up qa-frontend
```

### 4. 验收标准

- [ ] 单元 / smoke 全 PASS（qa-backend 跑通）
- [ ] 真机集成全 PASS 或设备不通时 skip（不阻塞 CI）
- [ ] 前端编译过（qa-frontend 跑通）
- [ ] vX.Y 既有 tests 全 PASS（不破坏）
- [ ] 文档：proposal.md / design.md / tasks.md / RELEASE-NOTES 都引用本 QA 段
```

## 强制规则

1. **每个 change 的 proposal.md 必含 "QA 验证计划" 段**
2. **Apply 阶段必跑 `docker compose --profile qa up qa-backend`** —— 不允许跳过
3. **Archive 阶段必跑 `docker compose --profile qa up qa-frontend`** —— 验编译
4. **真机集成可推迟**（设备不通时 skip），但单元 / smoke 不能少
5. **每次发版必跑全量 QA** —— v2.2.0 没跑是漏洞，已立 `v2.2.1-followup-v22-qa-repair` 补漏

## 反面教材

- ❌ v2.2.0 发版：commit 19 个，**没跑过 1 次 qa-backend / qa-frontend**——4 收尾 bug 全是用户实测发现
- ❌ qa-frontend 现状：只跑 `npm run build` 验编译，**0 组件测试**——v2.3 引入 vitest 解决
- ❌ v2.2.0 14 个新 API：**0 测试覆盖**——v2.2.1 follow-up 补

## 关联

- v2.2.0 补漏：[v2.2.1-followup-v22-qa-repair](../v2.2.1-followup-v22-qa-repair/proposal.md)
- v2.3 计划：[v2.3-roadmap § QA 规范化](../v2.3-roadmap/design.md)
- qa 容器：[docker-compose.dev.yml `qa-backend` / `qa-frontend`](../../docker-compose.dev.yml)
