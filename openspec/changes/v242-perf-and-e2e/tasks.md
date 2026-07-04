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

- [ ] 3.1.1 `docker compose -f docker-compose.dev.yml --profile split up -d ctrl config data`
- [ ] 3.1.2 验证 3 容器都 up：`docker ps --format '{{.Names}}\t{{.Status}}'`
- [ ] 3.1.3 验证 4 设备可达：ops-toolkit check-host.sh 跑 4 次（.4/.5/.100/.177）

### 3.2 写 conftest fixture

- [ ] 3.2.1 改 `backend/tests/conftest.py`：
  - 加 `@pytest.fixture def split_3containers()`：检查 3 容器 up，否则 skip
  - 加 `@pytest.fixture def real_4_devices()`：返回 [4, 5, 100, 177] 设备 id
- [ ] 3.2.2 加 marker：`@pytest.mark.integration` 已存在

### 3.3 写 8 场景测试

- [ ] 3.3.1 写 `backend/tests/test_split_e2e_real.py`：
  - `test_scenario1_devices_list`：GET /api/devices 真链路
  - `test_scenario2_interfaces_list`：GET /api/devices/{id}/interfaces 真 NETCONF
  - `test_scenario3_running_backup`：POST /api/devices/{id}/backup 真 SSH/SCP
  - `test_scenario4_async_full_backup`：POST /api/backups-async 真端到端
  - `test_scenario5_device_delete_cleanup`：DELETE /api/devices/{id} 真调 data cleanup
  - `test_scenario6_dashboard_aggregation`：GET /api/dashboard 真跨容器
  - `test_scenario7_data_container_down_config_works`：docker stop data → config 改接口
  - `test_scenario8_ctrl_container_down_clear_error`：docker stop ctrl → config 返中文错误
- [ ] 3.3.2 每个 case 加 `restore_original_state` fixture

### 3.4 跑真机 e2e

- [ ] 3.4.1 `docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend pytest tests/test_split_e2e_real.py -m integration -v`
- [ ] 3.4.2 设备不通的 case skip
- [ ] 3.4.3 8 场景全 PASS（skip 不算失败）
- [ ] 3.4.4 故障注入场景 7/8：跑完 `docker start data` / `docker start ctrl` 恢复

### 3.5 设备状态恢复

- [ ] 3.5.1 4 设备接口配置检查（vs 备份）
- [ ] 3.5.2 不一致 → NETCONF 改回
- [ ] 3.5.3 清理 e2e 期间 backup 文件

### 3.6 commit

- [ ] 3.6.1 `git add backend/tests/test_split_e2e_real.py backend/tests/conftest.py`
- [ ] 3.6.2 `git commit -m "test(split-e2e): split 模式真机 e2e 4 设备 8 场景 (含故障注入真机版)"`

---

## 4. 主线 3：MCP 浏览器 split 模式 e2e

### 4.1 起 split 模式 + 浏览器

- [ ] 4.1.1 3 容器已起（同 3.1）
- [ ] 4.1.2 `docker compose -f docker-compose.dev.yml up -d frontend`
- [ ] 4.1.3 打开 `http://localhost:5173`（MCP browser）

### 4.2 跑全量备份流程

- [ ] 4.2.1 登录（admin / admin123）
- [ ] 4.2.2 切 split 模式（URL 参数或后端 env 切换）
- [ ] 4.2.3 打开 CMDB
- [ ] 4.2.4 点"全量备份"按钮
- [ ] 4.2.5 验 BackgroundTaskPanel 出现 + task_id + status=running
- [ ] 4.2.6 等 status=success
- [ ] 4.2.7 截图存 `docs/screenshots/v2.4.2-mcp-e2e/cmdb-full-backup-*.png`

### 4.3 清理

- [ ] 4.3.1 删 e2e 期间产生的 backup 文件
- [ ] 4.3.2 3 容器保持 up（不关）

### 4.4 commit

- [ ] 4.4.1 `git add docs/screenshots/v2.4.2-mcp-e2e/ docs/PERF-RESULTS-v2.4.2.md`（追加 MCP 截图引用）
- [ ] 4.4.2 `git commit -m "docs(perf): MCP 浏览器 split 模式 CMDB 全量备份 e2e 截图"`

---

## 5. 回归

- [ ] 5.1 qa-backend `pytest`（非 -m integration）仍 214 passed
- [ ] 5.2 3 容器全 up
- [ ] 5.3 4 设备原状

---

## 6. 收尾

- [ ] 6.1 `docs/PERF-RESULTS-v2.4.2.md` 完整（压测 + e2e + 截图）
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

- [ ] locust 100 并发接口压测 P99 < 5s
- [ ] locust 50 并发备份压测 P99 < 30s
- [ ] SSH 连接数 < 50
- [ ] 8 场景真机 e2e 全 PASS
- [ ] 故障注入真机版（场景 7/8）行为符合预期
- [ ] MCP 浏览器 split 模式 e2e 流程通
- [ ] 设备状态全部恢复
- [ ] qa-backend 214 passed 不破
- [ ] 3 commit（每个主线 1 个）
