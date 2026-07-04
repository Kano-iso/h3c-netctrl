# v242-perf-and-e2e Design

> v2.4.2 Change 2 的设计决策与文件清单。

---

## 1. 关键设计决策

### 1.1 压测工具：locust

**方案 A：locust**（推荐）
- 优点：Python 写用户行为，轻量 ~10MB，HTTP 压测一把好手
- 缺点：不支持 SSH 直压（需走 HTTP API 中转）
- 选型理由：现有 backend 是 FastAPI HTTP，locust 天然契合

**方案 B：wrk**（放弃）
- C 写的 HTTP 压测工具，性能强
- 缺点：场景用 lua 脚本写，复杂度高，个人项目过重

**方案 C：vegeta**（放弃）
- Go 写的，CSV 输出
- 缺点：场景不灵活，ab 类工具

**方案 D：自写 asyncio 脚本**（备选）
- 用 `aiohttp` + `asyncio.gather` 写 100 并发
- 优点：零新装包
- 缺点：缺统计（P50/P99/失败率自己算），指标弱于 locust

→ **选 A**（locust）

### 1.2 压测目标设备

**100 并发接口查询**：
- 目标：Test-Switch-177
- 路径：locust → backend (monolith) → 真实 NETCONF 到 .177
- 监控：后端 1 进程 + .177 1 设备，关注 SSH 连接数

**50 并发备份**：
- 目标：Test-Switch-177（同一设备反复备份）
- 路径：locust → backend (data 容器，split 模式) → 真实 SSH/SCP 到 .177
- 监控：备份文件数、轮转是否触发、SSH 连接数

**绝对不压生产设备**：.4 / .5 / .100 / .177 中的生产设备（.5）**不参与压测**。
只压 .177，且压前必须 ping 通（ops-toolkit check-host）。

### 1.3 压测阈值

| 指标 | 目标 | 理由 |
|---|---|---|
| 接口查询 P99 | < 5s | 单设备 NETCONF get ~500ms × 3 模块 filter |
| 备份 P99 | < 30s | SFTP 拉 startup + running + 写本地 + 轮转 |
| 失败率 | < 1% | 容许偶发网络抖动 |
| SSH 并发连接 | < 50 | H3C V7 默认 max-session 偏保守 |
| 设备 CPU | < 80% | 避免压垮测试设备 |
| 内存增长 | < 100MB | 1 小时压测内不能 OOM |

**超阈值怎么办**：
- 记入 `docs/PERF-RESULTS-v2.4.2.md` 报告
- 列为"v2.5 待优化项"（不阻塞 v2.4.2 发版）
- 调小并发数（100→50，50→25）再跑

### 1.4 split 模式真机 e2e 实现

**起容器**：
```bash
docker compose -f docker-compose.dev.yml --profile split up -d ctrl config data
```

**fixture**（`backend/tests/conftest.py` 加）：
- `@pytest.fixture def split_3containers()`：检查 3 容器都 up，否则 skip
- `@pytest.fixture def real_4_devices()`：返回 4 设备 id（.4/.5/.100/.177）

**8 场景**（与 v241-supplement 一致，去掉 monkeypatch）：
- 1-6：同 v241-supplement 但用真 HTTP 跨容器
- 7：`docker stop data` → config 改 .177 接口
- 8：`docker stop ctrl` → config 返中文错误
- 跑完恢复：`docker start data` / `docker start ctrl`

**MCP 浏览器 e2e**（`v242-perf-and-e2e/tests/mcp_browser_e2e.py`）：
- 用 integrated_browser 跑 CMDB 全量备份
- 截图存 `docs/screenshots/v2.4.2-mcp-e2e/`
- 断言：task_id 出现 + status=success

### 1.5 设备状态恢复

每个 case 跑完必须恢复设备原状（n → n+1 → n）：
- 接口配置变更 → 用 NETCONF 改回
- 备份删除 → 直接 DB 删行 + 文件删
- 设备重启 → 90s 等待 + retry

---

## 2. 文件清单

### 2.1 新增

| 文件 | 用途 |
|---|---|
| `backend/tests/perf/locustfile.py` | locust 用户行为（NetconfConfigUser / SshBackupUser） |
| `backend/tests/perf/scenarios/100_concurrent_interfaces.sh` | 100 并发接口压测 |
| `backend/tests/perf/scenarios/50_concurrent_backup.sh` | 50 并发备份压测 |
| `backend/tests/perf/requirements.txt` | locust 依赖 |
| `backend/tests/perf/README.md` | 压测 SOP |
| `backend/tests/test_split_e2e_real.py` | 8 场景真机 e2e（无 mock） |
| `docs/PERF-RESULTS-v2.4.2.md` | 压测结果 + 指标 + 截图 |
| `docs/screenshots/v2.4.2-mcp-e2e/` | MCP 浏览器截图目录 |

### 2.2 修改

| 文件 | 改动 |
|---|---|
| `backend/requirements.txt` | 加 locust |
| `backend/tests/conftest.py` | 加 split_3containers + real_4_devices fixture |
| `docker-compose.dev.yml` | （无变化，profile split 已存在） |

### 2.3 不修改

- 3 容器代码、API、前端
- v2.4.1 214 passed 测试

---

## 3. 升级回退

### 升级

```bash
git pull
docker compose -f docker-compose.dev.yml --profile split up -d ctrl config data
# 跑压测
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend \
  sh -c "cd /app/tests/perf && locust -f locustfile.py --headless -u 100 -r 10 --run-time 60s --host http://backend:8000"
# 跑 split 真机 e2e
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend \
  pytest tests/test_split_e2e_real.py -m integration -v
```

### 回退

```bash
git revert <commit>
# 删 backend/tests/perf/ 目录
```

---

## 4. 风险评估

| 风险 | 等级 | 缓解 |
|---|---|---|
| 100 并发压垮 .177 | 中 | 压前 ops-toolkit check-host 验可达；阈值触发自动降并发；保留 1 个 SSH 长连接逃生 |
| locust 装包失败 | 低 | 备用方案：自写 aiohttp 脚本 |
| split 模式真机 e2e 设备不通 | 中 | fixture 默认 skip；记录"X 设备不可达" |
| docker stop data / ctrl 影响其他测试 | 低 | 跑前后确认 3 容器都 up；stop 前保存状态 |
| MCP 浏览器 split 模式 UI 路径未实现 | 中 | 走 v2.4.1 现状路径；不通时改 monolith 模式回归 |
| 备份压测产生大量文件 | 低 | 测试前清 backup dir；测试后清 |

---

## 5. 验证 checklist

- [ ] locust 装包成功，`locust --version` 输出
- [ ] 100 并发接口压测：P99 < 5s，失败率 < 1%
- [ ] 50 并发备份压测：P99 < 30s，失败率 < 1%
- [ ] SSH 连接数监控 < 50
- [ ] split 模式 3 容器都 up
- [ ] 8 场景真机 e2e 全 PASS（设备不通时 skip）
- [ ] 故障注入场景 7 / 8 真 docker stop 后系统行为符合预期
- [ ] MCP 浏览器 split 模式 CMDB 全量备份流程通
- [ ] 设备状态全部恢复原状
- [ ] 3 容器全部 up
- [ ] qa-backend 214 passed 不破
- [ ] `docs/PERF-RESULTS-v2.4.2.md` 写完
