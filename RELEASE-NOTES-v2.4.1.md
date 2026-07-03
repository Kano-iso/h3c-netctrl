# RELEASE-NOTES-v2.4.1

**版本**: v2.4.1
**日期**: 2026-07-03
**主题**: v241-container-split 补全（删设备清理 + 全量异步 + split 集成测试）
**前序**: v2.4.0 (2026-07-02)

---

## 1. 主题

v2.4.1 = **v241-container-split 留的 3 个 P0 pending 补全**，**不开 v2.4.2**（用户原话："就这么点小功能，又开一个版本，没意义"）。

`v241-container-split` 已 archive（2026-07-03），但留 3 个 pending：
- Task 4.2 删设备清理（split 模式孤儿数据风险）
- Task 8.4 全量备份异步（业务缺失）
- Task 8.5 split 模式集成测试（测试覆盖缺失）

v241-supplement change 全部补完，**重做 v2.4.1 tag**（覆盖 archive 状态）。

---

## 2. 包含的 Changes（1 个 + 3 task）

### v241-supplement（1 个 change，3 task）

#### Task 4.2: 设备删除时 data 容器 cleanup 端点

**问题**：split 模式下 ctrl 容器 `db.delete(device)` 不会自动级联清理 data 容器的 assets / backups 表（SQLAlchemy cascade 跨容器失效），产生孤儿数据 + 孤儿备份文件。

**实现**：
- `backend/app/routers/data_internal.py`: 新增 `DELETE /internal/devices/{id}/cleanup` 端点（删 asset 行 + 删 backup 行 + os.remove 本地文件，文件丢失不抛异常）
- `backend/app/internal_api.py`: 新增 `cleanup_device()` 客户端 + `_internal_delete()` 工具
- `backend/app/routers/device.py`: `delete_device` 在 `SERVICE_NAME='ctrl'` 模式下调 cleanup_device，**内部 API 失败不阻塞主流程**（设备已删事实优先）

#### Task 8.4: 全量备份异步模式

**问题**：v2.4.0 单设备 backup-async 已实现，但全量 `POST /api/backups` 仍是同步阻塞（7 设备 × 2 type = 2-4 分钟）。

**实现**：
- `backend/app/routers/backup.py`: 新增 `_async_backup_all_fn`（多设备串行复用 _async_backup_fn 核心逻辑，进度 5%~95% 按设备均分）
- `backend/app/routers/backup.py`: 新增 `POST /api/backups-async` 端点（立即返回 task_id + status_url）
- `frontend/src/api/index.js`: 新增 `backupApi.createAllAsync`（同步 createAll 保留向后兼容，CMDB/Backup.vue 已走 taskStore 不需改）

**MCP 浏览器 e2e**：split 模式起 3 容器后跑（流程：登录 → CMDB → 点全量备份 → 验 task 出现 → 验完成）。**真机 e2e 留到发版前用户测试**。

#### Task 8.5: split 模式集成测试 4 设备 8 场景

**问题**：13 个现有 integration test 跑 monolith 模式，split 模式 0 覆盖。

**实现**：
- `backend/tests/test_split_integration.py`: 9 case 覆盖 4 设备（192.168.100.4/.5/.100/.177）8 场景：
  1. 设备列表（ctrl 容器）
  2. 接口列表 + status 编码（config 容器 NETCONF）
  3. running 备份成功（data 容器）
  4. 全量异步备份（split 端到端）
  5. 设备删除清理（split 模式调 data 容器 cleanup）
  6. Dashboard 聚合（ctrl 跨容器调 data 降级容错）
  7. 故障注入 data down → config 改接口配置仍成功
  8. 故障注入 ctrl down → config 返明确中文错误
- **技术决策**：所有 case 在 monolith FastAPI TestClient 跑（fast，秒级），跨容器调用用 monkeypatch mock。真机 4 设备 e2e 留到发版前 + MCP 浏览器跑（slow，分钟级）。

---

## 3. 关联

- 前序 change: [v241-container-split](openspec/changes/archive/2026-07-03-v241-container-split/)（已 archive）
- 补全 change: [v241-supplement](openspec/changes/archive/2026-07-03-v241-supplement/)（本次 archive）
- 路线图: [VERSION-ROADMAP.md v2.4.1](VERSION-ROADMAP.md#9-v241-拆-3-容器实施-实施中)
- 蓝图: [docs/CONTAINER-DECOUPLING.md](docs/CONTAINER-DECOUPLING.md)

---

## 4. 测试 / 验证

### qa-backend（单测 + smoke）

```
================= 214 passed, 11 skipped, 10 warnings in 39.48s =================
```

**变化**：v2.4.0 (194 passed) → v2.4.1 (214 passed)，新增 20 case：
- 7 case (Task 4.2 cleanup): 4 endpoint + 3 device integration
- 4 case (Task 8.4 全量异步): 立即返回/类型非法/2 设备成功/无设备
- 9 case (Task 8.5 split 集成): 4 设备 × 8 场景（mock 跨容器）

### qa-frontend（build 验证）

```
dist/index.html                   0.42 kB │ gzip:  0.32 kB
dist/assets/index-BWSC7_Bx.css   47.68 kB │ gzip:  7.88 kB
dist/assets/index-CL8Iry65.js   261.36 kB │ gzip: 84.71 kB
✓ built in 4.72s
```

### split 模式真机 e2e（v2.4.1.1 留到发版前 + MCP 浏览器）

- [ ] 起 3 容器 `docker compose --profile split up -d ctrl config data frontend`
- [ ] 4 设备真机：192.168.100.4/.5/.100/.177 全可达
- [ ] 跑 `pytest tests/test_split_integration.py -m integration -v`（设备不通时 skip）
- [ ] MCP 浏览器跑全量备份异步 e2e（split 模式）

### 回归

- [x] v2.4.0 既有 194 测试全 PASS（不破坏）
- [x] split 模式 API smoke 全过
- [x] monolith 模式向后兼容（device.py cascade 自动级联，split 模式才走内部 API）

---

## 5. 升级步骤

```bash
# 1. 强制备份
make backup

# 2. 拉取新代码 + 新 v2.4.1 tag
git pull
git checkout v2.4.1

# 3. 数据库无 schema 变更

# 4. 启动 split 模式（3 容器）
docker compose -f docker-compose.dev.yml --profile split up -d ctrl config data frontend

# 5. 端到端验证
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
docker compose -f docker-compose.dev.yml --profile qa up qa-frontend

# 6. 真机 e2e（v2.4.1.1 留到发版前用户测试）
```

## 6. 回退步骤

```bash
# 1. 停 split 容器
docker compose -f docker-compose.dev.yml --profile split down

# 2. 切回 v2.4.0 monolith
git checkout v2.4.0
docker compose -f docker-compose.dev.yml up -d backend frontend

# 3. 验证
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
# 预期：194 passed（v2.4.0 monolith 行为不变）
```
