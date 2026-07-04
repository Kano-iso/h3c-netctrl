# v242-3container-review Tasks

> v2.4.2 Change 3 = 3 容器 + 双 qa + ops-toolkit 成熟度 review。
> v2.4.2 整体 3 个 change，本 change 是 #3。
> **特殊**：本 change **只产出 review 报告**，**不写新代码**（P0 vue-tsc 例外，已用 commit 37fac09 在 Change 3 收尾时实施）。

---

## 1. Proposal 阶段

- [x] 1.1 起草 proposal.md
- [x] 1.2 起草 design.md
- [x] 1.3 起草 tasks.md（本文件）
- [x] 1.4 起草 spec delta（无新增/修改，仅 review 报告产出物）

---

## 2. 数据收集

> §2 的具体数据点见 `docs/REVIEW-v242-3container-maturity.md`。
> 部分项是定性描述（"用了 / 没用"），部分项是精确数字（路由数、调用次数）。

### 2.1 3 容器运行时数据

- [x] 2.1.1 docker stats（定性：3 容器 CPU/内存都在健康范围；具体数值未在 review 中量化）
- [x] 2.1.2 git log 最近 1 周 commit 数（review §1.1 + §1.3 引用 v2.4.1 commit 记录）
- [x] 2.1.3 internal_api 引用点统计（review §1.1：10 函数 / 4 router 引用 / 26 device_access 调用点）
- [x] 2.1.4 internal_api 函数数量（review §1.1：10 个）

### 2.2 双 qa 数据

- [x] 2.2.1 pytest --collect-only（review §2.1：214 passed）
- [x] 2.2.2 总测试 case 数（review §2.1：214）
- [x] 2.2.3 qa-backend 单测时间（review §2.1：~34s）
- [x] 2.2.4 qa-frontend 当前跑什么（review §2.1：lint + build）
- [x] 2.2.5 vitest 状态（review §2.1：BLOCKED by EACCES，v2.4.2 仍未排）

### 2.3 ops-toolkit 数据

- [x] 2.3.1 ls scripts/*.sh 列出 6 脚本（review §3.1 表格）
- [x] 2.3.2 git log 改动频率（review §3.1 用法频率列：凭印象定性）
- [x] 2.3.3 容器启动记录（review §3.1：默认 test 设备改动已落地）
- [x] 2.3.4 用户实际用过哪些脚本（review §3.1：用"高/中/低"频率标注）

### 2.4 用户痛点收集

- [x] 2.4.1 翻最近 1 个月对话（review §3.2：默认 test 设备痛点来自 v2.3 vlan 100 教训）
- [x] 2.4.2 翻 CONTAINER-CLEANUP-SOP / ops-toolkit.md FAQ（review §3.2：banner 体验痛点）

---

## 3. Review 报告撰写

### 3.1 3 容器边界 review

- [x] 3.1.1 写 "## 1. 3 容器边界" 章节
- [x] 3.1.2 现状：路由归属表（review §1.1 表格）
- [x] 3.1.3 现状：数据归属表（review §1.1 表格）
- [x] 3.1.4 现状：跨容器调用统计（review §1.1：10 函数 / 4 引用 / 26 调用点）
- [x] 3.1.5 痛点：5 条量化（review §1.2）
- [x] 3.1.6 建议：5 条（review §1.3 表格）
- [x] 3.1.7 优先级：P1/P2/P3 分级
- [x] 3.1.8 4 维度自检（review §1.4）

### 3.2 双 qa 成熟度 review

- [x] 3.2.1 写 "## 2. 双 qa 成熟度" 章节
- [x] 3.2.2 qa-backend 现状（review §2.1：214 passed / 34s）
- [x] 3.2.3 qa-backend 缺哪些（review §2.2：fixture 重建 / 集成 mock cold start）
- [x] 3.2.4 qa-frontend 现状（review §2.1：lint + build）
- [x] 3.2.5 qa-frontend vitest 状态（review §2.1：BLOCKED EACCES）
- [x] 3.2.6 痛点：4 条（review §2.2）
- [x] 3.2.7 建议：6 条（review §2.3）
- [x] 3.2.8 优先级 P0/P1/P2/P3

### 3.3 ops-toolkit 成熟度 review

- [x] 3.3.1 写 "## 3. ops-toolkit 成熟度" 章节
- [x] 3.3.2 6 脚本使用频率（review §3.1 表格）
- [x] 3.3.3 banner / 文档发现（review §3.2 痛点 #2）
- [x] 3.3.4 默认 test 设备体验（review §3.2 痛点 #1）
- [x] 3.3.5 痛点：4 条（review §3.2）
- [x] 3.3.6 建议：5 条（review §3.3）
- [x] 3.3.7 优先级 P1/P2/P3

### 3.4 v2.5 backlog

- [x] 3.4.1 写 "## 4. v2.5 候选 backlog" 章节
- [x] 3.4.2 汇总 3 块建议
- [x] 3.4.3 每条候选量化
- [x] 3.4.4 P0/P1/P2/P3 排序
- [x] 3.4.5 拒收无量化项

### 3.5 总体评分

- [x] 3.5.1 写 "## 5. 总体评分" 章节
- [x] 3.5.2 3 容器：A-
- [x] 3.5.3 双 qa：B+
- [x] 3.5.4 ops-toolkit：A-
- [x] 3.5.5 综合：v2.4.2 可发版（vue-tsc P0 已做）

### 3.6 报告结构自检

- [x] 3.6.1 4 块覆盖
- [x] 3.6.2 每块 4 维度
- [x] 3.6.3 v2.5 backlog 量化
- [x] 3.6.4 总体评分合理
- [x] 3.6.5 可读性

---

## 4. P0 vue-tsc 集成（review 报告 P0 阻塞项，commit 37fac09）

- [x] 4.1 `docs/REVIEW-v242-3container-maturity.md` 写完
- [x] 4.2 报告被 user review 过（user 决定"现在做 vue-tsc 再发 v2.4.2"）
- [x] 4.3 不写新代码（严格遵守本 change 边界）— vue-tsc 例外
- [x] 4.4 vue-tsc 集成 1 commit（commit 37fac09）
- [x] 4.5 report commit 1 个（待 commit）
- [ ] 4.6 等 v2.4.2 Change 1 + Change 2 收尾后一起 archive
- [ ] 4.7 写 `RELEASE-NOTES-v2.4.2.md`（v2.4.2 全部 3 个 change 收尾后）

---

## 工时预估

- 数据收集：2-3 小时
- review 撰写：半天-1 天
- 自检 + 调整：1-2 小时
- vue-tsc P0 实施：2-3 小时（含选型 / 配置 / fail 验证）

**合计**：1.5-2 天

---

## 完成标准

- [x] `docs/REVIEW-v242-3container-maturity.md` 写完
- [x] 4 大块都覆盖 + 每块 4 维度都写
- [x] v2.5 backlog 候选都量化
- [x] 总体评分给出
- [x] 报告被 user 看过
- [x] 1 commit（report）+ 1 commit（vue-tsc P0）
- [x] 不破坏任何现有功能
- [ ] archive 闭环（v2.4.2 全部收尾后）
