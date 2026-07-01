# v2.4-roadmap Design

## Context

v2.3.1 (2026-07-01) 发版后，monolith 后端 + 临时手敲 SSH 排错的工程债暴露：
- **运维效率债**：ops-toolkit 容器（v2.3.0 引入）有 5 个脚本，但用户实测发现"进容器手敲 SSH 命令，意义不大"
- **架构债**：monolith 后端承载 SDN / 数据库 / 备份 / 监控，I/O 争抢 + 故障域不隔离
- **环境债**："有一些容器不知道啥时候在跑着还是 stop 了"
- **文档债**："长期记忆丢失"——写过的总结文档 / nav 文档用着用着就忘了

v2.4 把"工程化加固 + 拆容器"集中发版，新功能（VPC 联动 / SDN 大动作）放 v3.0。

**Stakeholders**：
- 用户（owner）：要"用工具 + 不用探索 + 不凭印象"
- 后续 AI session：要"看到工具回显带文档链接就能想起文档在哪"

## Goals / Non-Goals

**Goals:**
- 工具回显**强制带文档链接**（解决"长期记忆丢失"）
- 后端 monolith → 拆 3 容器（sdn-control / data / monitor），故障域隔离
- 冗余容器盘点 + 清理 + 留基线文档
- 前端 0 改动（API 路径不变）
- 沿用 v2.3.1 决策：不引入 Playwright / 不重写测试框架 / 不上 Postgres（v2.4 决策点）

**Non-Goals:**
- VPC 联动（新功能，v3.0）
- SDN 大动作（v3.0）
- 新测试框架
- 前端拆分
- 自动化部署 / CI 流程变更
- API 路径变更
- 引入新依赖（除 ops-toolkit docs 索引文件）

## Decisions

### 决策 1：工具回显带文档链接——放在哪个层？

**选 B：在脚本 / 容器入口层实现**
- ✅ 任何调用方式（手动 / 脚本 / AI）都能看到
- ✅ 与脚本内容紧耦合，文档与代码同步更新
- ❌ 不能拦截 Python import 的工具（如 paramiko 直调）

**示例**（`audit-switch.sh` 末尾）：
```bash
# 文档导航
cat <<EOF
📖 用法: /opt/docs/ops-toolkit.md#audit-switch
📖 设备凭据: /opt/docs/secrets.md
📖 排错 SOP: /opt/docs/troubleshooting.md
EOF
```

**否决 A**：放 README 顶部——用户进容器不会先看 README
**否决 C**：放单独 `--help` flag——不调用就看不到

### 决策 2：拆 3 容器 vs 拆 2 容器

**选 A：拆 3 容器（sdn-control / data / monitor）**
- ✅ 故障域清晰：sdn-control 改端口不受 data I/O 阻塞
- ✅ v3.0 VPC 在 sdn-control 上发力
- ✅ v3.0+ AI troubleshooting 在 monitor 上发力
- ❌ 3 个容器运维成本 > 2 个

**否决 B：拆 2 容器（core / asset，v2.4-container-decoupling 评估方案）**：
- 2 容器 ROI 低（asset 拆出来 data 还是共享一个数据库）
- 故障域仍不清晰
- v3.0 VPC 落地还要再拆一次

**否决 C：不拆，继续 monolith**：
- v2.3.0 / v2.3.1 都已暴露 I/O 争抢问题
- 故障域全平台挂

### 决策 3：SQLite vs Postgres

**选 A：v2.4 暂不迁 Postgres，决策点记录到 v2.4.0 评估**
- ✅ 拆容器 + SQLite 已能解决 80% 问题（I/O 隔离）
- ✅ 迁移风险大（数据导出/导入/兼容性）
- ❌ 多容器**不能共享** SQLite 文件（NFS 是 hack）

**v2.4 实施路径**：
- 3 容器**各自有独立 SQLite**（sdn-control.db / data.db / monitor.db）
- data 容器包含 CMDB + 备份元数据
- sdn-control 容器包含 device + interface + vpn
- monitor 容器包含 metrics + 自愈记录
- v2.4 收尾时**评估**是否迁 Postgres（v2.5 或 v3.0）

**否决 B：v2.4 立即迁 Postgres**：
- 数据迁移风险高，v2.3 已经在跑生产
- 拆容器 + 迁库同步做，rollback 复杂

### 决策 4：容器间通信方式

**选 A：Docker internal network + HTTP REST（轻量）**
- ✅ 简单，无外部依赖
- ✅ 用环境变量 `SDN_API_URL=http://sdn-control:8000` 配置
- ❌ 比 gRPC 慢，但内部调用 QPS 低，可接受

**示例**：
```python
# data 容器 → sdn-control 容器（拿 device 列表用于备份）
import httpx
resp = httpx.get(f"{SDN_API_URL}/api/devices", headers={"X-Internal-Token": TOKEN})
```

**否决 B：gRPC**：
- 复杂度高，个人项目 ROI 低
- 内部调用 QPS 不高
**否决 C：共享 DB**：
- 等于不拆

### 决策 5：冗余容器清单的"基线"形式

**选 A：`docs/CONTAINER-INVENTORY.md`（人工盘点 + 提交）**
- ✅ 文档可追溯，可 diff
- ✅ 人类可读
- ❌ 容器状态变化时文档会 stale

**自动化**：`make container-inventory` 脚本 = `docker ps -a --format` → 输出基线

**否决 B**：纯脚本输出——下次跑就没了

### 决策 6：v2.4 阶段切分

**v2.4.0**：3 大主线一次性发版
- `v24-container-cleanup`（P0，基线）
- `v24-toolkit-ux-and-doc-discovery`（P0，独立）
- `v24-decoupling-inventory-doc`（P0，决策支持）
- `v24-container-decoupling-3tier`（P0，大头）

**v2.4.1**：性能压测 + 故障注入
- 故障注入：docker stop data → sdn-control 仍能改端口
- 性能：3 容器后 NETCONF 100 并发不受 backup I/O 影响

**v2.4.2**：灰度上线
- 单机先跑 1 周
- 多机推广

**否决 B**：v2.4.0 = 工具完善化，v2.4.1 = 拆容器——分两版
- 拆容器是大头，分两版后 v2.4.1 工作量过载
- 一次性发版，问题集中暴露

## Risks / Trade-offs

**[Risk] 拆容器后数据迁移丢数据** → Mitigation
- v2.4 实施前 `make backup` 强制走一遍（沿用 v2.1.x 决策）
- 每个 sub-change 独立 revert，monolith 仍在 git history
- 灰度：先单机后多机

**[Risk] 容器间通信失败导致 sdn-control 改端口挂** → Mitigation
- 内部 API 用 timeout + retry（3 次 + 指数退避）
- 失败时**降级**："CMDB 不可用，已记录本地日志"（中文错误 + 不阻塞）
- 故障注入测试覆盖

**[Risk] 工具回显带文档链接——文档路径 hardcode** → Mitigation
- 文档用相对路径（`/opt/docs/...`）
- 提供 `--docs-prefix` flag（默认 `/opt/docs/`，容器外可覆盖）
- 文档随容器 image 一起打进去

**[Risk] SQLite 不能跨容器共享，导致 data 容器备份时拿不到 device 列表** → Mitigation
- sdn-control 容器暴露 `GET /api/devices` 给 data 容器
- 沿用决策 4 的 HTTP REST 通信
- data 容器**缓存** device 列表（每 5 分钟刷新）

**[Risk] v2.4 工作量过大（拆 3 容器是大头）** → Mitigation
- 分 2 阶段：v2.4.0 拆 + v2.4.1 性能压测
- 拆容器是渐进式：先 sdn-control + data 二分（v2.4.0-rc1），再加 monitor（v2.4.0-rc2）
- 卡壳 3 次立即停手复盘

**[Risk] 工具回显被截断 / 忽略** → Mitigation
- 用 emoji 📖 开头（视觉锚点）
- 文档链接放脚本输出**末尾**（用户看完结果才看）
- 不放中间（避免干扰主输出）

## Migration Plan

### 阶段 0：基线（v2.4.0-rc0，1 天）
1. `v24-container-cleanup`：
   - 跑 `docker ps -a` + `docker images` + `docker volume ls` 盘点
   - 关停 stop 容器、删 dangling image、未用 volume
   - 写 `docs/CONTAINER-INVENTORY.md`（基线）
2. `v24-toolkit-ux-and-doc-discovery`：
   - 重写 ops-toolkit 5 脚本（封装 + 文档链接）
   - qa-backend / qa-frontend 入口加文档链接
   - 写 `docs/ops-toolkit.md`（nav 文档）
3. `v24-decoupling-inventory-doc`：
   - 写 `docs/CONTAINER-DECOUPLING.md` 更新版（3 容器蓝图）

### 阶段 1：拆 2 容器（v2.4.0-rc1，3-5 天）
4. `v24-container-decoupling-3tier` step 1：
   - monolith → sdn-control + data 二分
   - 各自 Dockerfile + docker-compose 调整
   - 内部 API 通信封装
   - 端到端：sdn-control 改端口 → data 备份
   - 故障注入：docker stop data → sdn-control 改端口仍成功

### 阶段 2：拆 3 容器（v2.4.0-rc2，2-3 天）
5. `v24-container-decoupling-3tier` step 2：
   - data → data + monitor 二分
   - monitor 容器包含 metrics + 自愈记录（v2.4 基础监控，v3.0+ AI troubleshooting）
   - 端到端：3 容器协同

### 阶段 3：压测 + 故障注入（v2.4.1，2-3 天）
6. NETCONF 100 并发压测（拆容器后）
7. 故障注入：data 挂 / sdn-control 挂 / monitor 挂
8. 灰度：单机跑 1 周

### Rollback

- 每个 sub-change 独立 revert（沿用 OpenSpec 决策）
- 最坏情况：回退到 monolith `docker-compose.dev.yml`（git history 保留）
- v2.4.2 灰度期间如有问题，单机回退 → 全机回退

## Open Questions

1. **monitor 容器初期包含什么？** v2.4 只做基础 metrics 采集（NETCONF 设备状态 + 接口 up/down），还是顺手做告警？—— v2.4 决定：基础 metrics，告警推 v3.0
2. **data 容器是否承担"备份文件持久化"？** v2.3 备份文件在 `h3c-netctrl-backups` volume，data 容器挂载这个 volume 即可—— v2.4 决定：是
3. **Postgres 评估什么时候做？** v2.4 收尾时评估，决策点 v2.5 / v3.0—— v2.4 决定：v2.4.0 收尾时评估
4. **拆容器后 ops-toolkit 容器还能正常工作吗？**（它连的是 monolith 后端）—— v2.4 决定：ops-toolkit 加 `BACKEND_URL` 环境变量，默认 monolith，拆完后改成 sdn-control URL
5. **qa-backend / qa-frontend 容器跑测试时连哪个后端？**—— v2.4 决定：默认连 sdn-control（主要 API），但 `BACKEND_URL` 可覆盖

---

## 关联

- [proposal.md](proposal.md)
- [docs/CONTAINER-DECOUPLING.md](../../../docs/CONTAINER-DECOUPLING.md)（蓝图更新）
- [docs/QA-GUIDE.md](../../../docs/QA-GUIDE.md)
- 现有评估：[v2.4-container-decoupling/proposal.md](../v2.4-container-decoupling/proposal.md)（拆 2 容器，被 v2.4 升级为 3 容器）
- 上版：[RELEASE-NOTES-v2.3.1.md](../../../RELEASE-NOTES-v2.3.1.md)
