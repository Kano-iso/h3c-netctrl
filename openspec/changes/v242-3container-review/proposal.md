# v242-3container-review

> **版本定位**：v2.4.2 Change 3 = **3 容器 + 双 qa + ops-toolkit 成熟度 review**。
> **特殊**：本 change **只产出 review 报告**，**不写新代码**（除了 review 报告本身）。

---

## Why

v2.4.1 实施 3 容器（ctrl / config / data）+ v2.4.0 双 qa（qa-backend / qa-frontend）+ ops-toolkit 工具容器已 1 个月（2026-07-03 → 2026-07-04 起 review）：

1. **3 容器需要 review**：
   - ctrl / config / data 边界是否真的合理
   - 跨容器调用是否合理（HTTP REST + X-Internal-Token）
   - 数据库归属（devices / assets / backups / tasks）是否合理
   - 故障注入（docker stop data / ctrl）行为是否符合预期
2. **双 qa + ops-toolkit 需要 review**：
   - qa-backend 跑 214 passed 是否够
   - qa-frontend 只跑 build 是否足够（v2.4.2 Change 1 加 ESLint 后状态）
   - ops-toolkit 6 脚本被使用频率
   - ops-toolkit 入口 banner / 文档发现是否真的帮用户找到了用法
3. **3 容器优化空间**：
   - 用户原话："我们再去看一看我们的上一个版本做的那三个容器的无优化"
   - 重点找：能否进一步拆 / 能否合并 / 能否简化通信

**目的**：发版前最后 review 一遍，给 v2.5 留出 backlog。

---

## What Changes

v2.4.2 Change 3 = **1 个产出物 + 3 块 review**：

### 产出物

**`docs/REVIEW-v242-3container-maturity.md`**：完整 review 报告，包含：
- 3 容器边界 review
- 双 qa 成熟度 review
- ops-toolkit 成熟度 review
- v2.5 候选优化项 backlog
- 总体评分

### Review 1：3 容器边界（ctrl / config / data）

- 拆容器后跑了哪些 case？
  - 7 设备 CRUD / 4 设备 NETCONF / 4 设备 backup / 8 场景 split 集成测试
- 容器边界是否清晰？
  - 路由归属：device/vlan/interface/vpn/execute/log/auth/health/dashboard/batch → 哪个容器
  - 数据归属：devices / assets / backups / tasks → 哪个容器
  - 跨容器调用：internal_api 的 11 个函数使用频率统计
- 是否有不合理之处？
  - 跨容器调用次数过多（性能瓶颈）
  - 路由被错误归类
  - 数据库 schema 重复
- 3 容器 vs 4 容器（v2.4.0 PRD 原案 +monitor）：
  - 当前 3 容器是否够用
  - monitor 容器是否应该现在立（v2.4.1 决定暂不立）

### Review 2：双 qa 成熟度

- **qa-backend**：
  - 214 passed 是否够（基线 127 in v2.3.0）
  - 是否有重要模块未测
  - 跑测试时间（30s）是否合理
  - 与 dev backend 容器共用 image 还是独立？
- **qa-frontend**（v2.4.2 Change 1 加 ESLint 后）：
  - lint + build 是否覆盖
  - vitest 是否要补（v2.3.0 BLOCKED by EACCES，v2.4.2 Change 1 没做）
  - MCP 浏览器 e2e 流程是否顺畅
- **qa 容器使用频率**：
  - 用户实际多久跑一次
  - 跑测试时遇到的问题

### Review 3：ops-toolkit 工具容器成熟度

- **6 脚本使用频率**：
  - check-host / ssh-test / check-netconf / capture-config / reboot-wait / audit-switch
  - 哪个用得多 / 哪个用得少 / 哪个从来没跑
- **入口 banner / 文档发现**：
  - banner 是不是真的引导用户去翻 docs
  - 文档回显带链接是否还有用
- **默认 test 设备**（v2.4.2 Change 1 改）：
  - 改了后用起来是否顺畅
  - 是否还是有人误连生产
- **新增需求**：
  - 是否还有"第 7 个脚本"需求（按 v24-toolkit-ux 的预留）

### Review 4：v2.5 候选优化项

根据上面 3 块 review，列出 v2.5 backlog 候选：
- 哪些必须做（影响核心功能 / 性能）
- 哪些应该做（影响开发体验）
- 哪些想做（nice-to-have）
- 哪些不做（明确拒绝）

---

## Capabilities

### New Capabilities

无（review 报告不创建新能力）。

### Modified Capabilities

无（review 报告不修改现有能力）。

---

## Impact

- **新增后端代码**：0
- **新增前端代码**：0
- **新增 API**：0
- **修改后端代码**：0
- **修改 ops-toolkit**：0
- **新增文档**：`docs/REVIEW-v242-3container-maturity.md`
- **可回退**：删除 review 报告即可
- **不破坏**：任何东西（review 报告是只读产出物）

---

## 真机验证

不需要真机验证（review 是回顾性报告）。

但 review 过程需要看：
- 实际 git log（看哪些代码被 merge）
- 实际 docker stats（看 3 容器运行时资源）
- 实际 pytest 输出（看 214 passed 覆盖）
- 实际 ops-toolkit 使用记录（如果有日志）

---

## 收尾 / 发版

- 1 个 archive：`openspec/changes/archive/2026-07-XX-v242-3container-review/`
- **关键产出**：`docs/REVIEW-v242-3container-maturity.md`
- 不打 tag（等 v2.4.2 全部 3 个 change 收尾后打 v2.4.2 tag）

---

## Out of Scope

- 不写新代码（review 报告不创建实现）
- 不修 bug（review 报告是 backlog，发现的 bug 走 v2.5）
- 不重构（review 报告是评估，重构走 v2.5）
- 不做 monitor 容器（v2.4.1 决定暂不立，review 报告可提议，但本 change 不实施）

---

## 关联

- 上版：[RELEASE-NOTES-v2.4.1.md](../../../RELEASE-NOTES-v2.4.1.md)
- 路线图：[VERSION-ROADMAP.md § v2.4.2](../../../VERSION-ROADMAP.md)
- Change 1：[openspec/changes/v242-qa-and-tooling/](../v242-qa-and-tooling/proposal.md)
- Change 2：[openspec/changes/v242-perf-and-e2e/](../v242-perf-and-e2e/proposal.md)
- 蓝图：[docs/CONTAINER-DECOUPLING.md](../../../docs/CONTAINER-DECOUPLING.md)
- 容器基线：[docs/CONTAINER-INVENTORY.md](../../../docs/CONTAINER-INVENTORY.md)
- 3 容器 PRD：[v24-roadmap](../archive/2026-07-02-v24-roadmap/proposal.md)
- v2.4.1 实施记录：[v241-container-split](../archive/2026-07-03-v241-container-split/proposal.md)
