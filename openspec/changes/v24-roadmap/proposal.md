# v2.4-roadmap

> **版本定位**：v2.4 = **优化 + 工程化加固**小版本（不是新功能大版本）。
> **v2.3.1 后续**：v2.3.1 (`f8b63cb`, 2026-07-01) = 真机回归修复 patch
> **v2.4 vs v3.0**：
> - v2.4 = 优化（拆容器、工具完善化、清理冗余、QA 加固）
> - v3.0 = 新功能（VPC 联动、SDN 大动作、新协议适配）
>
> 用户原话（2026-07-01 v2.3.1 收尾时）：
> - "3.0 版本才是上功能的时候，现在我们还是在做一些优化呀，拆容器这些都是优化"
> - "你像我们说 vpc 功能的都是 3.0 的事情，但是拆容器都是 2.2.4 的事情"

---

## Why

v2.3.1 发版后，monolith 后端 + 临时手敲 SSH 排错 的工程债暴露出来：
1. **运维效率债**：用户提"ops-toolkit 容器做了，但每次还是要进容器手敲 SSH 命令，意义不大"——脚本化、文档化都没做
2. **架构债**：v2.3.0 monolith 承载 SDN / 数据库 / 备份 / 监控，I/O 争抢 + 故障域不隔离
3. **环境债**："有一些容器不知道啥时候在跑着还是 stop 了，给它关掉"

v2.4 把"工程化加固 + 拆容器"集中发版，新功能（VPC 联动、SDN 大动作）放 v3.0。

---

## What Changes

v2.4 = **3 大主线** 集中发版：

### 主线 1：ops-toolkit + qa 容器 UX 完善化（v2.4.0）

- ops-toolkit 5 预制脚本**封装为子命令**（`audit-switch.sh spine-01` 一键替代 `ssh admin@spine-01 display ...`）
- 工具执行回显**强制带文档链接**（"📖 用法：/opt/docs/ops-toolkit.md#audit-switch"）
- qa-backend / qa-frontend 同样思路：跑测试时回显"📖 QA-GUIDE 链接"
- 解决"长期记忆丢失——我们写了文档但忘了在哪里" 的工程债
- 关键设计：把"哪里有文档"的提示**嵌进工具回显**，让使用过程自然想起

### 主线 2：后端拆 3 容器（v2.4.0 大头）

- 拆 `sdn-control` 容器：改端口 / VPN / SDN 联动（v3.0 VPC 在此容器上发力）
- 拆 `data` 容器：数据库 + CMDB + 备份（资产持久化，I/O 隔离）
- 拆 `monitor` 容器：监控 + 自愈（v3.0+ AI 抓包、troubleshooting 在此容器上发力）
- 前端**不变**（API 路径不变，前端无感）
- 容器间通信走内部 Docker network
- 数据迁移：SQLite → 评估是否直接上 Postgres（v2.4 决策点）
- 故障注入：data 挂 → sdn-control 仍能改端口（但 CMDB 失败返回中文错误）

### 主线 3：清理冗余容器（v2.4.0 小事）

- `docker ps -a` 全量盘点
- 区分"在跑但未声明" / "stop 残留" / "stale image"
- 关停 + 删除无用容器 + 清理 dangling image / volume
- 记录基线清单（`docs/CONTAINER-INVENTORY.md`），避免下次又"忘了哪些有用"

### 阶段

- **v2.4.0**：3 大主线一次性发版
- **v2.4.1**：性能压测 + 故障注入测试（拆容器后的稳定性验证）
- **v2.4.2**：灰度上线（先单机后多机）

---

## Capabilities

### New Capabilities

| sub-change | 主题 | 关键能力 | 装包 |
|---|---|---|---|
| `v24-toolkit-ux-and-doc-discovery` | ops-toolkit + qa 容器 UX 完善化 | 脚本封装为子命令 + 工具回显强制带文档链接 + docs 索引文件 | 0 |
| `v24-container-decoupling-3tier` | 后端拆 3 容器（sdn-control / data / monitor） | docker-compose 拆 3 service + 内部 API 通信 + 故障注入测试 | 0 |
| `v24-container-cleanup` | 清理冗余容器 | 盘点 + 关停 + 删除 + docs/CONTAINER-INVENTORY.md 基线 | 0 |
| `v24-decoupling-inventory-doc` | 容器清单文档（决策支持） | docs/CONTAINER-INVENTORY.md 基线 + 拆分蓝图更新 | 0 |

### Modified Capabilities

- `add-ops-toolkit` (existing capability) — 升级：从"5 预制脚本可手敲"升级到"脚本封装子命令 + 回显带文档链接"
- `add-integration-test-framework` (existing capability) — 升级：加故障注入测试（拆容器后验证 SDN/MONITOR 在 DATA 挂时仍可用）
- `container-decoupling-preparedness` (existing capability) — 升级：从 v2.4 "评估"升级为 v2.4 "实施 3 容器拆"

---

## Impact

- **新增容器**：2 个（`sdn-control`, `data`, `monitor`）—— 实际新增 3 个
- **删除容器**：0（前端 + qa + ops-toolkit 保留）
- **修改容器**：1 个（monolith `backend` 拆分为 3 个独立 service）
- **新增 API**：0（前后端 API 路径不变）
- **修改 API**：0
- **新增后端代码**：3 个 Dockerfile + docker-compose 调整 + 内部 API 通信封装
- **修改后端代码**：路由归属标注 service_name（v2.3 已有 `SERVICE_NAME` env 占位）
- **数据库**：SQLite → 评估 Postgres（v2.4 决策点），数据迁移需 backup → restore 流程
- **前端**：0 改动（API 路径不变）
- **CI**：0 改动
- **可回退**：每个 sub-change 独立 revert，最坏情况回退到 monolith docker-compose
- **不破坏**：v2.3.1 archive 的 8 个 change + qa 容器 + ops-toolkit 容器

---

## 顺序与依赖

```
v24-container-cleanup                  (P0, 最小风险, 先做基线)
        ↓
v24-toolkit-ux-and-doc-discovery       (P0, 独立)
        ↓
v24-decoupling-inventory-doc           (P0, 决策支持文档)
        ↓
v24-container-decoupling-3tier         (P0, 大头, 依赖清单文档)
        ↓ (v2.4.1)
性能压测 + 故障注入测试
        ↓ (v2.4.2)
灰度上线
```

**关键依赖说明**：
- `v24-container-cleanup` P0 优先：先盘点基线，避免拆容器时混入 stale 容器
- `v24-toolkit-ux-and-doc-discovery` 独立：可在任何阶段做
- `v24-decoupling-inventory-doc` 是 `v24-container-decoupling-3tier` 的前置：拆之前先有清单决策
- 3 容器拆 = 大头，依赖清单文档 + cleanup 基线

---

## 真机验证

- **设备**：192.168.100.4 / 192.168.100.5（生产 Leaf-03 / Leaf-04）
- **ops-toolkit UX**：`docker compose --profile ops run --rm ops-toolkit audit-switch.sh 192.168.100.4` → 验证回显有"📖 文档链接"段
- **qa 容器发现性**：`docker compose --profile qa run --rm qa-backend` → 验证日志有"📖 QA-GUIDE 链接"
- **拆容器后端到端**：
  - sdn-control 改端口 → data 备份 → monitor 监控（3 容器协同）
  - 故障注入：docker stop data → sdn-control 改端口仍成功 + 中文错误（"CMDB 不可用，已记录本地日志"）
- **冗余容器清理**：`docker ps -a` 输出 = docs/CONTAINER-INVENTORY.md 100% 一致
- **回归**：v2.3.1 archive 的 8 个 change 不能破坏（qa-backend 跑 127 passed）

---

## 收尾 / 发版

- 每个 sub-change 独立 archive（`v24-toolkit-ux-and-doc-discovery` / `v24-container-decoupling-3tier` / `v24-container-cleanup` / `v24-decoupling-inventory-doc`）
- `RELEASE-NOTES-v2.4.0.md` 合并所有 sub-change
- `VERSION-ROADMAP.md` v2.4 状态：进行中 → 已发版
- `README.md` 版本路线图 / 容器拓扑图 / 工程债清单 更新
- push 全部 commits + `git tag v2.4.0`（**待用户确认**）

---

## Out of Scope

- 不引入 v3.0 VPC 联动 + SDN 大动作（v3.0 单独）
- 不重写 monolith 整体架构（拆 3 容器是 v2.4 核心）
- 不做"备份版本对比 UI"（v2.4 评估覆盖范围）
- 不引入新测试框架（沿用 v2.3.1 的 pytest + paramiko + ncclient）
- 不引入 Playwright（个人项目 ROI 低，沿用 v2.3.1 决策）
- 不做 ops-toolkit 之外的运维工具（避免范围蔓延）

---

## 关联

- 蓝图：[docs/CONTAINER-DECOUPLING.md](../../../docs/CONTAINER-DECOUPLING.md)
- 决策支持：现有 `v2.4-container-decoupling` proposal（拆 2 容器 core/asset，2026-06-30 评估）
- 上版：[RELEASE-NOTES-v2.3.1.md](../../../RELEASE-NOTES-v2.3.1.md)
- 上版：[RELEASE-NOTES-v2.3.0.md](../../../RELEASE-NOTES-v2.3.0.md)
- 路线图：[VERSION-ROADMAP.md § v2.4 backlog](../../../VERSION-ROADMAP.md)
- QA 模板：[openspec/changes/QA-TEMPLATE.md](../QA-TEMPLATE.md)
- QA 容器使用：[docs/QA-GUIDE.md](../../../docs/QA-GUIDE.md)
- 现有 spec：[openspec/specs/container-decoupling-preparedness/spec.md](../../specs/container-decoupling-preparedness/spec.md)
