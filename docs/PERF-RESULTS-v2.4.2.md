# v2.4.2 性能压测报告

> **测试时间**：2026-07-04
> **测试设备**：Test-Switch-177 (192.168.100.177, id=7)
> **后端版本**：v2.4.1 (commit 9d0c636)
> **测试人**：Claude (MiniMax-M3)
> **OpenSpec Change**：[v242-perf-and-e2e](../../openspec/changes/v242-perf-and-e2e/proposal.md)

---

## 1. 结论摘要

**v2.4.2 压测目标 100/50 并发均未达预期**，但**找到了设备真实容量上限**：

| 场景 | 阈值 | 实测稳定点 | 设备上限（精确定位） | 状态 |
|---|---|---|---|---|
| NETCONF 接口查询 | P99 < 5s, 失败率 < 1% | **7 并发**（P99=5.9s, 0% 失败） | **max-session = 7**（8 首次失败） | 部分达成 |
| SSH 备份 | P99 < 30s, 失败率 < 1% | **6 并发**（P99=9.6s, 0% 失败） | **max-session = 6**（7 首次失败） | 部分达成 |

**关键发现**：
- H3C V7 测试机 .177 NETCONF max-session = **7**（8 首次失败，10 失败率 28%）
- H3C V7 测试机 .177 SSH max-session = **6**（7 首次失败，8 失败率 8.3%）
- 粗档位"max-session ~ 8 / ~ 16-20"是插值猜的，细档位实测**显著低于此**——v2.4.2 补
- **后端性能本身没问题**（6-7 并发稳定通过），瓶颈在设备侧
- 100 并发时暴露出 v2.4.1 monolith 模式 bug：sqlite lock 时错误走 internal_api 兜底
- mixed 模式（weight 3:1）测不出单类瓶颈，**ssh-only 模式**才能定位 SSH 临界点——v2.4.2 补方法学

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

## 5. 设备容量总结（v2.4.2 补：粗档位 vs 细档位）

| 资源 | 粗档位结论（v2.4.2 首发） | **细档位精确定位**（v2.4.2 补） | 验证 |
|---|---|---|---|
| NETCONF max-session | ~ 8 | **7** | 5/6/7 并发 0% 失败；**8 并发首次失败**（1/32 = 3%）；9 并发 7.9%；10 并发 28%；12 并发 15% |
| SSH max-session | ~ 16-20 | **6** | 3/4/5/6 并发 0% 失败；**7 并发首次失败**（1/19 = 5%）；8 并发 8.3% |

**修正结论**：原报告"NETCONF ~ 8 / SSH ~ 16-20"是 5/10/20/100 粗档位插值，**显著高估了 SSH 上限**（实际 6 不是 16-20）。细档位精确定位后，v2.5 调参建议需要按新数据校准。

**调整建议**（生产部署参考，按精确定位）：
```bash
# 设备侧调高 session 上限（H3C V7 命令）—— 实际需要从 7/6 提到 16-20 才能扛 10+ 并发
netconf ssh server session-limit 16
ssh server session-limit 16

# 后端侧建议（v2.5 评估）：
# - 实现 NETCONF / SSH 连接池（避免每次 new client）—— 当前每次请求 new，无池化
# - 请求级 session 限制（每个 device 同时最多 N 个 in-flight 请求）
# - 6-7 并发是后端稳定点，超出会触发设备 session 拒绝
```

---

## 6. 细档位压测数据（v2.4.2 补）

> **背景**：原报告 §3 §4 的粗档位（5/10/20/100）结论"max-session ~ 8 / ~ 16-20"是插值猜的，user 质疑"是不是没测出真实上限就下结论"。补细档位压测。

### 6.1 NETCONF 接口查询细档位（mixed 模式，weight 3:1）

跑法：`bash backend/tests/perf/scenarios/finetune_interfaces.sh`（qa-backend 容器内），每档 30s，每档间不 sleep（依赖 30s 压测自然冷却）。

| 档位 | 30s reqs | GET reqs | GET 失败 | GET 失败率 | GET P99 | 状态 |
|---|---|---|---|---|---|---|
| 5  | 34 | 30 | 0 | 0%   | 2.3s | ✓ |
| 6  | 35 | 27 | 0 | 0%   | 5.4s | ✓ |
| 7  | 43 | 33 | 0 | 0%   | 5.9s | ✓ **稳定点** |
| **8**  | 43 | 32 | 1 | 3.1% | 5.6s | ⚠️ **临界点** |
| 9  | 51 | 38 | 3 | 7.9% | 5.2s | ❌ |
| 10 | 49 | 35 | 10 | 28%  | 5.3s | ❌ |
| 12 | 59 | ? | 9  | 15%  | 9.7s | ❌ |

**精确定位**：NETCONF max-session = **7**（7 全过，8 首次失败）

### 6.2 SSH 备份细档位（ssh-only 模式）

**重要方法学**：原 locustfile mixed 模式 weight 3:1，10 并发时只有 1.6 个 SshBackupUser，**测不出 SSH 真实瓶颈**。细档位改用 `--class-picker SshBackupUser` 单独跑。

跑法：`bash backend/tests/perf/scenarios/finetune_backup.sh`，每档 30s + 20s sleep（防 H3C V7 session 锁）。

| 档位 | 30s reqs | 失败 | 失败率 | P99 | 状态 |
|---|---|---|---|---|---|
| 3  | 6  | 0 | 0%   | 9.5s | ✓ |
| 4  | 8  | 0 | 0%   | 9.5s | ✓ |
| 5  | 10 | 0 | 0%   | 9.5s | ✓ |
| **6**  | 15 | 0 | 0%   | 9.6s | ✓ **稳定点** |
| **7**  | 19 | 1 | 5.3% | 9.8s | ⚠️ **临界点** |
| 8  | 24 | 2 | 8.3% | 9.6s | ❌ |

**精确定位**：SSH max-session = **6**（6 全过，7 首次失败）

### 6.3 修正后的 v2.5 调参建议

| 项 | 粗档位建议 | 细档位修正后建议 |
|---|---|---|
| 设备 `netconf ssh server session-limit` | 32 | **16**（7×2 = 14 → 留 buffer 取 16） |
| 设备 `ssh server session-limit` | 64 | **16**（6×2 = 12 → 留 buffer 取 16） |
| 后端 per-device 限流 | 10 | **6**（与设备 SSH 上限对齐） |
| batch 全量备份串行度 | 4-6 | **2-3**（避免 7 设备同时 backup 触发 SSH 满） |

---

## 7. 测试方法学说明（v2.4.2 补）

### 7.1 mixed 模式 vs ssh-only 模式

原 locustfile.py（[locustfile.py:23-44](../../backend/tests/perf/locustfile.py)）有 2 个 User 类：

```python
class NetconfConfigUser(HttpUser):
    @task(3)  # weight 3
    def list_interfaces(self): ...

class SshBackupUser(HttpUser):
    @task(1)  # weight 1
    def create_backup(self): ...
```

**问题**：locust 按 weight 比例分配用户。10 并发时只有 ~1.6 个 SshBackupUser，**SSH 真实并发永远上不去**。

**修正**：细档位用 `--class-picker SshBackupUser` 单独跑 SSH 备份，**才能定位 SSH 临界点**。

### 7.2 mixed 模式的适用场景

mixed 模式（weight 3:1）**适合模拟真实用户行为**（90% 查询 + 10% 备份）但**不适合定位单类瓶颈**。两者目标不同：

- 真实用户行为模拟 → mixed 模式
- 定位某类资源上限 → ssh-only / netconf-only 模式

### 7.3 细档位压测脚本

新增 2 个细档位脚本（v2.4.2 补 commit）：
- `backend/tests/perf/scenarios/finetune_interfaces.sh`：NETCONF 5/6/7/8/9/10/12 档（mixed 模式）
- `backend/tests/perf/scenarios/finetune_backup.sh`：SSH 3/4/5/6/7/8 档（ssh-only 模式 + sleep 20）

**v2.5 改进**：
- 加 `--class-picker NetconfConfigUser` 跑 netconf-only 模式
- 加档位自动化扫描（5→20 二分法找临界点）

---

## 8. 原始粗档位数据（保留，对比用）

> §3 §4 的粗档位数据保留作为"插值猜的"基线参考。**业务决策以 §6 细档位数据为准**。

---

## 9. v2.4.1 monolith bug 暴露（粗档位原始发现）

100 并发时，35 次请求报 "Temporary failure in name resolution"，根因：

`backend/app/utils/device_access.py:56-63` 在本地查 Device 时 `except Exception` 抓所有异常（包括 sqlite "database is locked"），导致走 internal_api 兜底。但 monolith 模式下 ctrl 容器没启动，DNS 解析失败。

**修复建议**（已记入 v242-3container-review）：
- monolith 模式 + 本地表存在 + `SERVICE_NAME=core` 时，绝不走 internal_api 兜底
- 只在 `table_unavailable=True`（即表不存在）时才走 internal_api

---

## 10. 阈值达成情况

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

## 11. 复测建议

如要达成 100/50 并发目标：
1. **设备侧**：先 `netconf ssh server session-limit 64` + `ssh server session-limit 128` 调高
2. **后端侧**：实现连接池（v2.5 评估）
3. **测试侧**：调整 locustfile 限制为后端能处理的并发数（推荐 ≤ 设备 max-session）

---

## 12. 关联

- OpenSpec Change: [v242-perf-and-e2e/proposal.md](../../openspec/changes/v242-perf-and-e2e/proposal.md)
- locustfile: [backend/tests/perf/locustfile.py](../../backend/tests/perf/locustfile.py)
- Scenarios: [backend/tests/perf/scenarios/](../../backend/tests/perf/scenarios/)
- 设备侧修复: 待 v2.4.2 + v2.5 评估
- 后端连接池: 待 v2.5 评估

---

## 13. split 模式真机 e2e（v2.4.2 主线 2）

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

## 14. MCP 浏览器 split 模式 e2e（v2.4.2 主线 3）

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
