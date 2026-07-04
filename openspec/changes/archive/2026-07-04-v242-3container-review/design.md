# v242-3container-review Design

> v2.4.2 Change 3 的设计决策与文件清单。

---

## 1. 关键设计决策

### 1.1 Review 报告结构

**方案 A：单文件 review 报告**（推荐）
- `docs/REVIEW-v242-3container-maturity.md`
- 包含 4 大块（3 容器 / 双 qa / ops-toolkit / v2.5 backlog）
- 优点：单文件可一次性 review
- 缺点：长（可能 500+ 行）

**方案 B：拆 4 个 review 报告**（放弃）
- 每块一个 .md
- 优点：粒度细
- 缺点：v2.4.2 收尾时跨文件引用麻烦

→ **选 A**（单文件）

### 1.2 Review 维度

每个 review 块必须包含 4 个维度：

| 维度 | 含义 |
|---|---|
| **现状** | 当前怎么做的（数据 / 配置 / 代码） |
| **痛点** | 不合理 / 难用 / 低效的地方 |
| **建议** | v2.5 可考虑的优化方向（不实施） |
| **优先级** | P0 必须 / P1 应该 / P2 nice / P3 不做 |

### 1.3 v2.5 backlog 量化标准

v2.5 backlog 候选**必须有量化理由**：
- ✅ "3 容器跨容器调用 11 次/分钟，建议合并 ctrl + config"（有数据）
- ❌ "感觉可以再优化一下"（无数据，拒收）

按用户工程规则"Postpone tasks only with specific quantified reasons"。

### 1.4 review 完成度自检

review 报告完成后，问自己 5 个问题：
1. 3 容器边界 review 完后，我清楚"路由归属有 X 处不合理"了吗？
2. 双 qa 成熟度 review 完后，我清楚"qa-backend 缺 Y 类测试"了吗？
3. ops-toolkit 成熟度 review 完后，我清楚"Z 脚本从没被用过"了吗？
4. v2.5 backlog 候选每条都有量化理由吗？
5. 总体评分（A/B/C/D/F）合理吗？

任一答案为否，**继续深挖**。

### 1.5 不写新代码

明确约束：本 change **只产出 review 报告**。
发现的 bug / 优化 / 重构 → **不写**到本 change，写到 v2.5 backlog。

理由：
- 保持 change 边界清晰（review ≠ 实施）
- 避免 review 时一边评估一边改（评估不客观）
- 给 v2.5 留下完整 backlog 数据

---

## 2. 文件清单

### 2.1 新增

| 文件 | 用途 |
|---|---|
| `docs/REVIEW-v242-3container-maturity.md` | 完整 review 报告（4 大块） |

### 2.2 修改

无（review 报告是只读产出物）。

### 2.3 不修改

- 后端代码、前端代码、ops-toolkit、3 容器、QA 容器
- 任何其他文档（review 报告是新增，不改旧文档）

---

## 3. 升级回退

### 升级

```bash
git pull
cat docs/REVIEW-v242-3container-maturity.md
# 4 大块 review 看一遍
# 决定哪些进 v2.5
```

### 回退

```bash
git revert <commit>
rm docs/REVIEW-v242-3container-maturity.md
```

---

## 4. 风险评估

| 风险 | 等级 | 缓解 |
|---|---|---|
| review 报告变成"流水账" | 中 | 严格按 4 维度（现状/痛点/建议/优先级）写 |
| v2.5 backlog 候选无量化 | 中 | 拒收"感觉可优化"，要求数据支撑 |
| review 结论带偏见（"我喜欢的方案"） | 中 | 引用 git log / docker stats / pytest 输出等客观数据 |
| review 时间过长（> 1 天） | 低 | 限制 review 时间 1 天；超时就收尾 |
| review 报告未读 | 中 | review 完单独 commit + 单独 message，方便 git log 搜 |

---

## 5. 验证 checklist

- [ ] `docs/REVIEW-v242-3container-maturity.md` 写完
- [ ] 4 大块都覆盖（3 容器 / 双 qa / ops-toolkit / v2.5 backlog）
- [ ] 每块都按 4 维度写（现状/痛点/建议/优先级）
- [ ] v2.5 backlog 候选每条都有量化理由
- [ ] 总体评分给出（A/B/C/D/F）
- [ ] review 报告被 user review 过
- [ ] 1 commit
- [ ] 不破坏任何现有功能
