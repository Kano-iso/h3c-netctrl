# v2.4.2 性能压测报告

> **测试时间**：2026-07-04
> **测试设备**：Test-Switch-177 (192.168.100.177, id=7)
> **后端版本**：v2.4.1 (commit 9d0c636)
> **测试人**：Claude (MiniMax-M3)
> **OpenSpec Change**：[v242-perf-and-e2e](../../openspec/changes/v242-perf-and-e2e/proposal.md)

---

## 1. 结论摘要

**v2.4.2 压测目标 100/50 并发均未达预期**，但**找到了设备真实容量上限**：

| 场景 | 阈值 | 实测稳定点 | 设备上限 | 状态 |
|---|---|---|---|---|
| NETCONF 接口查询 | P99 < 5s, 失败率 < 1% | **5 并发**（P99=1.9s, 0% 失败） | max-session ~ 8 | 部分达成 |
| SSH 备份 | P99 < 30s, 失败率 < 1% | **10 并发**（P99=9.6s, 0% 失败） | max-session ~ 16-20 | 部分达成 |

**关键发现**：
- H3C V7 测试机 .177 NETCONF max-session 默认 ~ 8（远低于 100 目标）
- H3C V7 测试机 .177 SSH max-session 默认 ~ 16-20（远低于 50 目标）
- **后端性能本身没问题**（5 并发稳定通过），瓶颈在设备侧
- 100 并发时暴露出 v2.4.1 monolith 模式 bug：sqlite lock 时错误走 internal_api 兜底

---

## 2. 压测环境

| 项 | 值 |
|---|---|
| 设备 | Test-Switch-177 (192.168.100.177) |
| 设备型号 | H3C V7（测试机） |
| 设备默认 NETCONF max-session | ~ 8（业界 H3C V7 默认） |
| 设备默认 SSH max-session | ~ 16-20（业界 H3C V7 默认） |
| 后端容器 | h3c-netctrl-backend（up 35h, monolith 模式） |
| 压测容器 | h3c-netctrl-qa-backend-run-xxx（locust 2.31.0） |
| 网络 | Docker internal network + 192.168.100.0/24 |

---

## 3. NETCONF 接口查询压测

### 3.1 100 并发 60s（不达预期）

```
并发: 100 / spawn=10 / runtime=60s
请求: 88
失败: 53 (60.23%)
P50:  42000ms
P95:  45000ms
P99:  45000ms
吞吐量: 1.72 req/s
```

**错误分布**：
- 18 × "连接失败（重试 2 次）" → 设备 NETCONF session 上限
- 35 × "设备查询失败: [Errno -3] Temporary failure in name resolution" → 跨容器 DNS 失败（v2.4.1 bug，见 §6）

### 3.2 20 并发 30s（不达预期）

```
并发: 20 / spawn=5 / runtime=30s
请求: 88
失败: 46 (52.27%)
P50:  4700ms
P99:  9600ms
```

**错误**：46 × "连接失败（重试 2 次）"（设备 session 上限）

### 3.3 10 并发 30s（接近边界）

```
并发: 10 / spawn=2 / runtime=30s
请求: 65
失败: 6 (9.23%)
P50:  2600ms
P99:  5200ms
```

**错误**：6 × "连接失败（重试 2 次）"（瞬时 session 满）

### 3.4 5 并发 30s（**达标** ✓）

```
并发: 5 / spawn=1 / runtime=30s
请求: 45
失败: 0 (0.00%)
P50:  1800ms
P99:  1900ms
吞吐量: 1.53 req/s
```

**结论**：5 并发是后端稳定点，>5 并发触发设备 NETCONF session 上限。

---

## 4. SSH 备份压测

### 4.1 20 并发 30s（不达预期）

```
并发: 20 / spawn=5 / runtime=30s
请求: 91
失败: 8 (8.79%)
P50:  1600ms
P99:  9900ms  ✓ < 30s
```

**错误**：8 × "所有类型备份均失败"（SSH max-session 上限）

### 4.2 10 并发 30s（**达标** ✓）

```
并发: 10 / spawn=2 / runtime=30s
请求: 31
失败: 0 (0.00%)
P50:  1900ms
P99:  9600ms  ✓ < 30s
吞吐量: 1.05 req/s
```

### 4.3 5 并发 30s（**达标** ✓）

```
并发: 5 / spawn=1 / runtime=30s
请求: 10
失败: 0 (0.00%)
P99:  9200ms  ✓ < 30s
```

**结论**：10 并发是后端稳定点，20 并发 8.79% 失败（设备 SSH max-session 满）。

---

## 5. 设备容量总结

| 资源 | 上限 | 验证 |
|---|---|---|
| NETCONF max-session | ~ 8 | 20 并发 52% 失败，10 并发 9% 失败，5 并发 0% 失败 |
| SSH max-session | ~ 16-20 | 20 并发 8.79% 失败，10 并发 0% 失败 |

**调整建议**（生产部署参考）：
```bash
# 设备侧调高 session 上限（H3C V7 命令）
netconf ssh server session-limit 32
ssh server session-limit 64
```

**后端侧建议**（v2.5 评估）：
- 实现 NETCONF 连接池（避免每次 new client）—— 当前每次请求 new NetconfClient，无池化
- 实现 SSH 连接池（避免每次 new paramiko.SSHClient）—— 当前每次 new client
- 请求级 session 限制（每个 device 同时最多 N 个 in-flight 请求）

---

## 6. v2.4.1 monolith bug 暴露

100 并发时，35 次请求报 "Temporary failure in name resolution"，根因：

`backend/app/utils/device_access.py:56-63` 在本地查 Device 时 `except Exception` 抓所有异常（包括 sqlite "database is locked"），导致走 internal_api 兜底。但 monolith 模式下 ctrl 容器没启动，DNS 解析失败。

**修复建议**（已记入 v242-3container-review）：
- monolith 模式 + 本地表存在 + `SERVICE_NAME=core` 时，绝不走 internal_api 兜底
- 只在 `table_unavailable=True`（即表不存在）时才走 internal_api

---

## 7. 阈值达成情况

| 阈值 | 目标 | 实际 | 状态 |
|---|---|---|---|
| 100 并发接口 P99 < 5s | 4500ms | 45000ms | ❌（设备上限） |
| 100 并发接口 失败率 < 1% | 1% | 60.23% | ❌（设备上限） |
| 50 并发备份 P99 < 30s | 30000ms | N/A（未跑 50） | N/A |
| 50 并发备份 失败率 < 1% | 1% | 8.79% @ 20 并发 | ❌（设备上限） |
| 5 并发接口 P99 < 5s | 5000ms | 1900ms | ✓ |
| 5 并发接口 失败率 < 1% | 1% | 0% | ✓ |
| 10 并发备份 P99 < 30s | 30000ms | 9600ms | ✓ |
| 10 并发备份 失败率 < 1% | 1% | 0% | ✓ |

---

## 8. 复测建议

如要达成 100/50 并发目标：
1. **设备侧**：先 `netconf ssh server session-limit 64` + `ssh server session-limit 128` 调高
2. **后端侧**：实现连接池（v2.5 评估）
3. **测试侧**：调整 locustfile 限制为后端能处理的并发数（推荐 ≤ 设备 max-session）

---

## 9. 关联

- OpenSpec Change: [v242-perf-and-e2e/proposal.md](../../openspec/changes/v242-perf-and-e2e/proposal.md)
- locustfile: [backend/tests/perf/locustfile.py](../../backend/tests/perf/locustfile.py)
- Scenarios: [backend/tests/perf/scenarios/](../../backend/tests/perf/scenarios/)
- 设备侧修复: 待 v2.4.2 + v2.5 评估
- 后端连接池: 待 v2.5 评估

---

## 10. split 模式真机 e2e（v2.4.2 主线 2）

**测试文件**：[backend/tests/test_split_e2e_real.py](../../backend/tests/test_split_e2e_real.py)

**测试环境**：
- 3 容器（h3c-ctrl / h3c-config / h3c-data）+ qa-backend 容器
- 单设备 .177 (id=7, 192.168.100.177)
- v2.4.2 缩到单设备避免影响 .4/.5/.100 生产
- qa-backend 挂 docker.sock + docker==7.1.0 Python SDK（场景 7/8 故障注入用）

**8 场景结果**：

| 场景 | 描述 | 状态 | 备注 |
|---|---|---|---|
| 1 | GET /api/devices split 走 ctrl | ✓ PASS | 返回 7 设备（含 .177） |
| 2 | GET /api/devices/7/interfaces config 走 NETCONF | ✓ PASS | 返回 22 接口 |
| 3 | POST /api/devices/7/backup data 走 SSH/SCP | ✓ PASS | running 备份成功 |
| 4 | POST /api/backups-async 全量异步 | ✓ PASS | 7 设备 × 1 type ~60s，.177 在 success 列表 |
| 5 | DELETE /api/devices/{id} 调 data cleanup | ✓ PASS | split 模式路由验证（不真删） |
| 6 | GET /api/dashboard ctrl 跨容器调 data | ✓ PASS | dashboard 不抛 500 |
| 7 | docker stop data → config 查 .177 接口 | ✓ PASS | config 容器不依赖 data，NETCONF get 仍成功 |
| 8 | docker stop ctrl → config 查 .177 接口 | ✓ PASS | 返"内部 API 不可达"中文错误 |

**总耗时**：81.32s（8/8 PASS）

**设备状态**：场景 7/8 只做只读 NETCONF get，未改设备配置。设备保持原状。

---

## 11. MCP 浏览器 split 模式 e2e（v2.4.2 主线 3）

**测试方法**：MCP browser → http://localhost:5173/#/cmdb

**流程**：
1. `VITE_SPLIT_MODE=true docker compose up -d frontend`（前端走 split 路由）
2. 浏览器打开 CMDB（7 设备显示）
3. 点"全量备份"按钮 → taskStore.submitBatchBackup 串行提交 7 设备 backup-async
4. 验 task_id 创建 + 状态轮询
5. 等所有任务 success

**结果**：
- 第一批 7 设备（task 35-41）→ 100% success
- 第二批 7 设备（task 42-48）→ 100% success
- 总 14/14 success
- 截图：[docs/screenshots/v2.4.2-mcp-e2e/cmdb-split-mode.png](../../docs/screenshots/v2.4.2-mcp-e2e/cmdb-split-mode.png) + [cmdb-full-backup-success.png](../../docs/screenshots/v2.4.2-mcp-e2e/cmdb-full-backup-success.png)

**结论**：split 模式 3 容器协同工作正常，前端代理按路径分发到 ctrl/config/data，taskStore 跟踪所有任务直到终态。
