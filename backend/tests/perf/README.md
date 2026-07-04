# 性能压测 SOP（v2.4.2）

> **目标**：定位后端 NETCONF / SSH 并发性能瓶颈，验证 v2.4.1 拆 3 容器后连接池无泄漏。
> **范围**：仅 Test-Switch-177 (192.168.100.177, id=7)，**绝对不压生产设备**。

## 1. 压测目标

| 场景 | 并发 | 持续 | 阈值 | 关注指标 |
|---|---|---|---|---|
| 接口查询 (NETCONF) | 100 | 60s | P99 < 5s, 失败率 < 1% | SSH 连接数 < 50 |
| 备份 (SSH) | 50 | 60s | P99 < 30s, 失败率 < 1% | 备份文件数 / 轮转 |

## 2. 前置

1. 后端已起：
   ```bash
   docker compose -f docker-compose.dev.yml up -d backend
   # 或 split 模式：docker compose --profile split up -d ctrl config data
   ```
2. .177 设备可达：
   ```bash
   docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit check-host.sh
   # 默认指向 .177
   ```
3. 备份目录空间充足（>500MB 推荐）

## 3. 跑法

### 3.1 100 并发接口查询

```bash
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend \
  bash tests/perf/scenarios/100_concurrent_interfaces.sh
```

另起终端监控：
```bash
# 容器内（locust 容器或 backend 容器）：
watch -n 1 'ss -tan | grep 192.168.100.177 | wc -l'

# 设备侧 CPU（每 10s）：
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit ssh-test.sh "display cpu-usage"
```

### 3.2 50 并发备份

```bash
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend \
  bash tests/perf/scenarios/50_concurrent_backup.sh
```

监控：
```bash
# backup 文件数：
ls /root/workpace/h3c-netctrl/backend/data/backups/ | wc -l

# 轮转日志：
docker compose -f docker-compose.dev.yml logs backend 2>&1 | grep -i rotation
```

## 4. 调参

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `PERF_HOST` | `http://backend:8000` | 后端地址（split 模式用 `http://config:8000`） |
| `PERF_USERS` | 100/50 | 并发用户数 |
| `PERF_SPAWN` | 10/5 | spawn 速率（用户/秒） |
| `PERF_RUNTIME` | 60s | 持续时间 |

示例：20 并发跑 30s（轻量回归）
```bash
PERF_USERS=20 PERF_RUNTIME=30s docker compose ... run --rm qa-backend \
  bash tests/perf/scenarios/100_concurrent_interfaces.sh
```

## 5. 阈值不达预期

- P99 > 5s（接口）→ 可能是 NETCONF session 串行化，看后端日志是否有 lock wait
- SSH 连接数 > 50 → paramiko 连接池未复用，每个请求新开 TCP（瓶颈）
- 失败率 > 1% → 设备 max-session 上限（默认 32），需 `ssh server session-limit` 调整

## 6. 报告

压测结果记录到 `docs/PERF-RESULTS-v2.4.2.md`：
- 压测环境（设备型号 / 后端版本 / 网络拓扑）
- 100 并发接口结果（P50/P95/P99/失败率/SSH 连接数）
- 50 并发备份结果（P99/失败率/备份数/轮转次数）
- 阈值达成情况
- 待优化项
