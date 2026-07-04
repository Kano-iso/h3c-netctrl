# v242-perf-and-e2e

> **版本定位**：v2.4.2 = **工程化加固 + QA 规范化 + 性能验证**小版本。
> **v2.4.1 后续**：v2.4.1 (tag, 2026-07-03) = 3 容器拆分实施
> **v2.4.2 vs v3.0**：
> - v2.4.2 = 优化（压测 + 真机 e2e + 3 容器 review）
> - v3.0 = 新功能（VPC 联动）

---

## Why

v2.4.1 拆 3 容器上线后，性能 + 稳定性问题暴露：

1. **SSH 连接池风险**（用户明确点）：多设备并发调 NETCONF / SSH 时，连接数可能爆
   - 现状：单设备连接复用，100 并发时未压测
   - 风险：连接耗尽 → 后续请求 timeout → 用户感知"卡"
2. **拆容器后端到端未真机验证**：v2.4.1 写的是"split 模式集成测试"用 monkeypatch mock 跨容器调用
   - 真 docker stop data / 真 SSH 到设备的 fault tolerance 没真机验过
3. **PRD § 5 性能压测 + 故障注入**（v24-roadmap 已写）一直未做
4. **release 前真机大测试未标准化**：之前都是用户口头"用 .5 测一下"，没有规范的 e2e 流程

---

## What Changes

v2.4.2 Change 2（性能压测 + 真机 e2e）= **3 大主线**：

### 主线 1：locust 压测 .177 NETCONF / SSH

- 装包：`pip install locust`（轻量 ~10MB，python 性能压测工具）
- 写 `backend/tests/perf/locustfile.py`：
  - `NetconfConfigUser`：模拟 100 并发用户，每个用户调 `GET /api/devices/{id}/interfaces` 拿接口列表（NETCONF 真链路）
  - `SshBackupUser`：模拟 50 并发用户，每个用户调 `POST /api/devices/{id}/backup`（SSH 拉配置）
  - 目标设备：Test-Switch-177 (192.168.100.177) —— 绝对不能用生产
- 写 `backend/tests/perf/scenarios/`：
  - `100_concurrent_interfaces.sh`：locust -u 100 -r 10 --run-time 60s
  - `50_concurrent_backup.sh`：locust -u 50 -r 5 --run-time 60s
- 关注指标：
  - P50 / P95 / P99 响应时间
  - 失败率
  - 并发 SSH 连接数（用 `ss -tan | grep 192.168.100.177` 监控）
  - 设备侧 CPU / 内存（用 ops-toolkit 拉）
- 目标阈值：
  - P99 < 5s（接口查询）
  - P99 < 30s（备份）
  - 失败率 < 1%
  - 并发 SSH 连接数 < 50（设备侧默认 max-session）

### 主线 2：split 模式真机 e2e（4 设备真链路，PRD § 5.2 故障注入真机版）

- 起 split 3 容器（ctrl / config / data）
- 真机 e2e 8 场景（与 v241-supplement 场景一致，但**无 monkeypatch**，真 docker stop / 真 SSH）：
  1. 设备列表（split 走 ctrl 真 HTTP）
  2. 接口列表（config 真 NETCONF 到 .4/.5/.100/.177）
  3. running 备份（data 真 SCP 到设备）
  4. 全量异步备份（split 端到端真链路）
  5. 设备删除清理（ctrl 真 HTTP 调 data cleanup）
  6. Dashboard 聚合（ctrl 跨容器真调 data）
  7. **故障注入：docker stop data → config 改 .177 接口仍成功**（真停容器）
  8. **故障注入：docker stop ctrl → config 返明确中文错误**（真停容器）
- 状态恢复：每个 case 跑完恢复设备原状（n → n+1 → n）
- 跑完后：恢复所有 3 容器为 up

### 主线 3：MCP 浏览器 split 模式 e2e 验证（补 v241-supplement 留的 TODO）

- 起 split 3 容器
- 用 integrated_browser / Chrome DevTools MCP 跑：
  - 登录（admin / admin123）
  - 切 split 模式（默认 monolith，URL 加 `?mode=split` 或后端 env）
  - 打开 CMDB
  - 点"全量备份"按钮
  - 验 BackgroundTaskPanel 出现 + task_id + status=running → success
  - 截图保存
- 清理 e2e 期间产生的备份文件
- 验证：split 模式 + 浏览器端到端可用

### 顺序

```
locust 装包 + locustfile 写
        ↓
100 并发接口压测 + 50 并发备份压测
        ↓
split 模式真机 e2e 8 场景
        ↓
MCP 浏览器 split 模式验证
```

---

## Capabilities

### New Capabilities

| 子能力 | 主题 | 关键能力 | 装包 |
|---|---|---|---|
| `locust-perf-test` | 性能压测框架 | locust + 100 并发接口 + 50 并发备份 + 阈值监控 | +10MB |
| `split-e2e-real-device` | split 模式真机 e2e | 8 场景真链路 + 故障注入真机版 | 0 |
| `mcp-browser-split-e2e` | MCP 浏览器 split 验证 | CMDB 全量备份浏览器端到端 | 0 |

### Modified Capabilities

- `add-integration-test-framework` (existing capability) — 升级：从 mock 版 split 集成测试，升级为真机版 e2e

---

## Impact

- **新增包**：`locust` (~10MB)
- **新增后端代码**：`backend/tests/perf/locustfile.py` + scenarios 2 个 shell
- **真机影响**：4 设备（.4/.5/.100/.177）在 split 模式被反复 SSH / NETCONF，必须每次恢复原状
- **设备压力**：100 并发接口 / 50 并发备份，**只对 .177**（生产 .4/.5 不参与压测）
- **可回退**：删除 `backend/tests/perf/` 目录
- **不破坏**：v2.4.1 3 容器、v2.4.1.1 214 passed 测试

---

## 真机验证

- **设备**：
  - 压测：192.168.100.177 (Test-Switch-177) 唯一
  - split 真机 e2e：.4 / .5 / .100 / .177 全跑（按 case）
- **压测指标**：
  - 100 并发接口：P99 < 5s，失败率 < 1%
  - 50 并发备份：P99 < 30s，失败率 < 1%
  - SSH 连接数：< 50
- **split 真机 e2e**：8 场景全 PASS
- **MCP 浏览器**：split 模式全量备份流程通

---

## 收尾 / 发版

- 1 个 archive：`openspec/changes/archive/2026-07-XX-v242-perf-and-e2e/`
- 写 `docs/PERF-RESULTS-v2.4.2.md`（压测结果 + 指标阈值 + 真机 e2e 截图）
- 更新 `RELEASE-NOTES-v2.4.2.md`（v2.4.2 全部 3 个 change 收尾后）
- `git tag v2.4.2` 在所有 3 个 change 收尾后打

---

## Out of Scope

- 不做全链路压测（含 4 设备并发）—— 个人项目设备不够
- 不做 monitor 容器（v2.4.1 决定 monitor 暂不立）
- 不做长期稳定性测试（≥ 24h 那种）
- 不做 Postgres 性能对比（决策点 v2.5 评估）
- 不做 Kubernetes 部署压测（Docker Compose 阶段）

---

## 关联

- 上版：[RELEASE-NOTES-v2.4.1.md](../../../RELEASE-NOTES-v2.4.1.md)
- 路线图：[VERSION-ROADMAP.md § v2.4.2](../../../VERSION-ROADMAP.md)
- Change 1：[openspec/changes/v242-qa-and-tooling/](../v242-qa-and-tooling/proposal.md)
- PRD 原文：[v24-roadmap § 5 v2.4.1 性能压测 + 故障注入](../archive/2026-07-02-v24-roadmap/tasks.md#5-v241-性能压测--故障注入)
- 真机设备表：192.168.100.4/.5/.100/.177（详见 [docs/CONTAINER-DECOUPLING.md](../../../docs/CONTAINER-DECOUPLING.md)）
