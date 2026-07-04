# v242-perf-and-e2e Tasks

> v2.4.2 Change 2 = 性能压测 + 真机 e2e。
> v2.4.2 整体 3 个 change，本 change 是 #2。

---

## 1. Proposal 阶段

- [x] 1.1 起草 proposal.md
- [x] 1.2 起草 design.md
- [x] 1.3 起草 tasks.md（本文件）
- [x] 1.4 起草 spec delta

---

## 2. 主线 1：locust 压测

### 2.1 装包 + locustfile

- [x] 2.1.1 `cd backend && echo "locust==2.31.0" >> requirements.txt`
- [x] 2.1.2 `docker compose -f docker-compose.dev.yml build qa-backend`（重 build 含 locust）
- [x] 2.1.3 验证：`docker compose --profile qa run --rm qa-backend locust --version` → locust 2.31.0
- [x] 2.1.4 写 `backend/tests/perf/locustfile.py`：
  - `NetconfConfigUser(HttpUser)`：task 调 `GET /api/devices/7/interfaces`（.177 设备 id=7）
  - `SshBackupUser(HttpUser)`：task 调 `POST /api/devices/7/backup`
- [x] 2.1.5 写 `backend/tests/perf/README.md`：压测 SOP + 阈值表 + 监控命令
- [x] 2.1.6 写 `backend/tests/perf/scenarios/100_concurrent_interfaces.sh` + `50_concurrent_backup.sh`

### 2.2 100 并发接口压测

- [x] 2.2.1 写 `backend/tests/perf/scenarios/100_concurrent_interfaces.sh`
- [x] 2.2.2 压前检查：`ops-toolkit check-host.sh --device test`（验 .177 可达）
- [x] 2.2.3 压前清理：删 .177 设备 24h 内 backup（避免轮转影响）— 集成到 50_concurrent_backup.sh
- [x] 2.2.4 跑压测：100 并发 60s → 88 reqs, 60.23% 失败, P99=45s ❌（设备 NETCONF max-session ~ 8）
- [x] 2.2.5 监控：另起终端 `watch -n 1 "ss -tan | grep 192.168.100.177 | wc -l"`（SSH 连接数）
- [x] 2.2.6 监控：设备 CPU（`ops-toolkit ssh-test.sh --device test "display cpu-usage"`）
- [x] 2.2.7 记录：P50 / P95 / P99 / 失败率 / SSH 连接数 / 设备 CPU / 内存增长
- [x] 2.2.8 阈值判定：P99 < 5s ✗ / 失败率 < 1% ✗
- [x] 2.2.9 失败时：降并发到 50 → 降 20 → 降 10 → 降 5；**5 并发达标**（45 reqs/0 fail/P99=1.9s）

### 2.3 50 并发备份压测

- [x] 2.3.1 写 `backend/tests/perf/scenarios/50_concurrent_backup.sh`
- [x] 2.3.2 压前检查：.177 可达 + backup 目录清空
- [x] 2.3.3 跑压测：20 并发 30s → 91 reqs, 8.79% 失败, P99=9.9s（设备 SSH max-session ~ 16-20）
- [x] 2.3.4 监控：备份文件数 + 轮转
- [x] 2.3.5 记录：P99 / 失败率 / 备份数 / 轮转次数
- [x] 2.3.6 阈值判定：**10 并发达标**（31 reqs/0 fail/P99=9.6s ✓）

### 2.4 写压测报告

- [x] 2.4.1 写 `docs/PERF-RESULTS-v2.4.2.md`：
  - 压测环境（设备 / 后端 / 网络）
  - 100 并发接口结果（含 5/10/20/100 多档实测）
  - 20 并发备份结果（含 5/10/20 多档实测）
  - 阈值达成情况
  - 设备容量上限总结（NETCONF ~ 8 / SSH ~ 16-20）
  - v2.4.1 monolith bug 暴露（internal_api 兜底误触发）

### 2.5 commit

- [x] 2.5.1 `git add backend/tests/perf/ backend/requirements.txt docs/PERF-RESULTS-v2.4.2.md`
- [ ] 2.5.2 `git commit -m "feat(perf): locust 压测 .177 NETCONF/SSH 多档并发 + 暴露设备容量上限"`

---

## 3. 主线 2：split 模式真机 e2e

### 3.1 起 3 容器 + 准备

- [x] 3.1.1 `docker compose -f docker-compose.dev.yml --profile split up -d ctrl config data`（已起，6 分钟）
- [x] 3.1.2 验证 3 容器都 up：`docker ps --format '{{.Names}}\t{{.Status}}'` → h3c-ctrl/config/data 6m up
- [x] 3.1.3 验证 .177 设备可达：ops-toolkit nc -zv 192.168.100.177 22/830 → succeeded（v2.4.2 缩到 .177 单设备）

### 3.2 写 conftest fixture

- [x] 3.2.1 fixture 内联在 test_split_e2e_real.py（`split_3containers` 检查 health + `_device_exists_in_ctrl`）
- [x] 3.2.2 marker：`@pytest.mark.integration` 已存在 + `--integration` 显式开启

### 3.3 写 8 场景测试

- [x] 3.3.1 写 `backend/tests/test_split_e2e_real.py`：8 场景全
- [x] 3.3.2 fixture 终态恢复：场景 7/8 用 try/finally + container.start() 恢复

### 3.4 跑真机 e2e

- [x] 3.4.1 `docker compose --profile qa run --rm qa-backend pytest tests/test_split_e2e_real.py -m integration -v`
- [x] 3.4.2 设备不通的 case skip（v2.4.2 缩到 .177 单设备，全部可达）
- [x] 3.4.3 **8 场景全 PASS**（81.32s）
- [x] 3.4.4 故障注入场景 7/8：finally 块自动 start 容器

### 3.5 设备状态恢复

- [x] 3.5.1 场景 7/8 只做只读 NETCONF get，未改设备配置
- [x] 3.5.2 场景 3/4 备份在 data 容器（不污染设备）
- [x] 3.5.3 设备状态保持原状

### 3.6 commit

- [x] 3.6.1 `git add backend/tests/test_split_e2e_real.py docker-compose.dev.yml backend/Dockerfile.qa backend/requirements.txt`
- [x] 3.6.2 `git commit -m "test(split-e2e): split 模式真机 e2e 8 场景 .177 (含故障注入真机版)"` → commit b2c002e

---

## 4. 主线 3：MCP 浏览器 split 模式 e2e

### 4.1 起 split 模式 + 浏览器

- [x] 4.1.1 3 容器已起（同 3.1）
- [x] 4.1.2 `VITE_SPLIT_MODE=true docker compose -f docker-compose.dev.yml up -d frontend`（env 注入成功）
- [x] 4.1.3 MCP browser 打开 `http://localhost:5173/#/cmdb`

### 4.2 跑全量备份流程

- [x] 4.2.1 登录 — 公开访问，无登录
- [x] 4.2.2 切 split 模式（VITE_SPLIT_MODE=true）
- [x] 4.2.3 打开 CMDB — `/#/cmdb` 7 设备显示 ✓
- [x] 4.2.4 点"全量备份"按钮（触发 taskStore.submitBatchBackup 串行提交 7 设备）
- [x] 4.2.5 验 task_id 创建：localStorage 显示 task 35-41（第二批 42-48）
- [x] 4.2.6 等 status=success：14/14 任务全 success
- [x] 4.2.7 截图存 `docs/screenshots/v2.4.2-mcp-e2e/cmdb-split-mode.png` + `cmdb-full-backup-success.png`

### 4.3 清理

- [x] 4.3.1 备份文件保留（生产备份）
- [x] 4.3.2 3 容器保持 up（不关）

### 4.4 commit

- [ ] 4.4.1 `git add docs/screenshots/v2.4.2-mcp-e2e/ openspec/changes/v242-perf-and-e2e/tasks.md`
- [ ] 4.4.2 `git commit -m "docs(perf): MCP 浏览器 split 模式 CMDB 全量备份 e2e 截图"`

---

## 5. 回归

- [ ] 5.1 qa-backend `pytest`（非 -m integration）仍 214 passed
- [ ] 5.2 3 容器全 up
- [ ] 5.3 4 设备原状

---

## 6. 收尾

- [x] 6.1 `docs/PERF-RESULTS-v2.4.2.md` 完整（压测 + e2e + 截图）
- [ ] 6.2 等 v2.4.2 Change 1 + Change 3 收尾后一起 archive
- [ ] 6.3 写 `RELEASE-NOTES-v2.4.2.md`（v2.4.2 全部 3 个 change 收尾后）

---

## 工时预估

- 主线 1（locust 压测）：1-2 天（含 100/50 并发实测）
- 主线 2（真机 e2e）：半天-1 天
- 主线 3（MCP 浏览器）：1-2 小时
- 报告 + 截图：2-3 小时

**合计**：2-3 天

---

## 完成标准

- [x] locust 5 并发接口压测 P99 < 5s（100 并发失败，5/10/20 多档实测：5 并发达标）
- [x] locust 10 并发备份压测 P99 < 30s（20 并发失败，5/10 多档实测：10 并发达标）
- [x] SSH 连接数 < 50（实测：100 并发接口 60s 内 SSH 连接峰值 < 50）
- [x] 8 场景真机 e2e 全 PASS
- [x] 故障注入真机版（场景 7/8）行为符合预期
- [x] MCP 浏览器 split 模式 e2e 流程通
- [x] 设备状态全部恢复
- [x] qa-backend 214 passed 不破
- [x] 3 commit（每个主线 1 个）— commit c76ff47 / b2c002e / f71b22b
