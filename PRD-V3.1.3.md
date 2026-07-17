# H3C NetCtrl V3.1.3 PRD：资产可见

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| V3.1.3 Draft | 2026-07-18 | 用户拍板 + Codex 共创 | V3.1.3 = 资产可见：前端实时刷新 + 新设备上线通知 + 死信队列处理 UI |

---

## 1. 背景与目标

### 1.1 背景

v3.1.2 已实现 controller 主动 SSH 纳管，**新设备能自动入 `sdn_devices` 表 + `assets` 表**。

但**前端展示仍是手动的**：

- Devices.vue / CMDB.vue 默认不刷新
- 用户必须手动 F5 才能看到新设备
- 死信队列只能在 DB 层查（`SELECT * FROM sdn_ztp_dead_letter`）
- 不符合"白屏用户零操作"的目标（用户应该不操作就能看到）

### 1.2 目标

**前端设备列表 / CMDB / Dashboard 自动显示新设备，无需手动刷新**：

1. 设备列表（Devices.vue）自动 poll（5s 间隔）
2. CMDB 资产表（CMDB.vue）自动 poll（10s 间隔）
3. Dashboard 统计（设备总数 / 在线 / 离线）实时更新
4. 新设备上线通知（toast）
5. 死信队列处理 UI（CMDB.vue 加 tab）

### 1.3 关键约束

- ✅ **白屏用户零操作**：设备上线 = 前端自动可见 + 通知
- ✅ **性能可控**：poll 间隔合理（5~10s），不压垮后端
- ✅ **死信可处理**：白屏用户能看 / 重试 / 删除死信
- ❌ **不做 WebSocket / SSE 推送**（v3.1.3 简化：仅 poll）
- ❌ **不做实时监控大屏**（v3.4 前端大屏）

### 1.4 依赖

- **v3.1.2**（已规划）：自动纳管 + 死信队列 + 业务 IP 推送
- **v3.1.1**（已规划）：1:1 静态 IP 池子
- **v3.1.0**（已闭环）：独立 ztp-server 容器
- **v2.6.0**（已闭环）：vue-i18n v9 中英双语（toast 文案国际化）
- **v2.5.0**（已闭环）：Playwright 37 e2e case
- **v2.4.1**（已闭环）：ctrl + config + data 3 容器拆分

---

## 2. V3.1.3 范围

### 2.1 Devices.vue 实时刷新

#### 2.1.1 目标

**新设备 90s 内自动出现在 Devices.vue 表格**，无需手动刷新。

#### 2.1.2 实现

**前端**（`frontend/src/views/Devices.vue`）：

- 表格组件加 `setInterval(() => fetchDevices(), 5000)`（5s poll）
- 表格顶部加"上次刷新时间"显示
- 表格右上角加"手动刷新"按钮（兼容老用户）
- 新设备高亮 3s（淡绿色背景）→ 提示用户"新设备上线"
- 后端无响应时 → 弹 toast 警告（连续 3 次失败才弹）

**后端**（`config` 容器）：

- `GET /api/devices` 已有，无需改
- 新增 `GET /api/devices?since={timestamp}` — 只返回 since 之后变更的设备（减少 payload）
- `Device.updated_at` 字段已有，无需改

**性能优化**：

- poll 时不重新拉全表 → 增量拉（since timestamp）
- 设备表行 < 200 → 拉全表（v3.1.3 简化，避免过度设计）
- 设备表行 > 200 → 增量拉（v3.4+ 评估）

#### 2.1.3 设计决策

| 方案 | 优势 | 劣势 | 决策 |
|---|---|---|---|
| **A：定期轮询** | 简单 + 兼容老接口 | 5-10s 延迟 | ✅ **采用** |
| **B：WebSocket 推送** | 实时 | 需后端 WS 服务 + 心跳 | ❌ 推 v3.4+ |
| **C：SSE 推送** | 实时 + 单向 | 需后端 SSE 服务 | ❌ 推 v3.4+ |

**v3.1.3 决策**：A 方案（定期轮询，5s 间隔）

### 2.2 CMDB.vue 资产表实时刷新

#### 2.2.1 目标

**新设备 10s 内自动出现在 CMDB 资产表**。

#### 2.2.2 实现

- 表格 poll 间隔 10s（比 Devices.vue 慢，因资产表数据量大）
- 新资产高亮 5s
- 死信队列 tab（v3.1.3 新增）

**死信队列 tab**：

- 表格下方加 `<el-tabs>`，第一个 tab 是"正常资产"，第二个 tab 是"死信队列"
- 死信队列表格字段：`{mac, ip, sysname, error_type, error_message, retry_count, last_retry_at, actions}`
- actions：重试 / 删除 / 查看详情
- 死信告警：死信 > 5 条 → 头部红色 chip 提示

### 2.3 Dashboard 实时统计

#### 2.3.1 目标

**Dashboard 设备总数 / 在线 / 离线 实时更新**（10s 间隔）。

#### 2.3.2 实现

**前端**（`frontend/src/views/Dashboard.vue`）：

- 设备统计卡片加 poll
- 卡片显示：总数 / 在线 / 离线 / 未知 + 按 vendor 分布
- 折线图（最近 24h 设备变化）保留静态（每小时刷新）

**后端**：

- `GET /api/dashboard/stats` 已有
- 新增 `GET /api/dashboard/stats?since={timestamp}` — 增量统计

### 2.4 新设备上线通知

#### 2.4.1 目标

**新设备上线时弹 toast 通知**，提示用户"发现新设备"。

#### 2.4.2 实现

**触发条件**：

- 设备表 `INSERT` → 前端 poll 检测到新设备 → 弹 toast
- 死信队列 `INSERT` → toast 红色警告

**toast 文案**（中英双语，v2.6.0 i18n 复用）：

- zh-CN: "发现新设备 {sysname}（{ip}）已上线"
- en-US: "New device {sysname} ({ip}) online"

**防骚扰**：

- 同一台设备只弹 1 次（按 `device.mgmt_ip` 去重）
- 用户可关闭"新设备通知"（设置开关，存 localStorage）

**实现**：

- `frontend/src/utils/deviceWatcher.ts`（新增）：监听设备表变化，弹 toast
- Devices.vue / CMDB.vue / Dashboard.vue 都引入
- 集成现有 toast 系统（v2.6.2 全局 toast）

### 2.5 死信队列处理 UI

#### 2.5.1 目标

**白屏用户能看 / 重试 / 删除死信**，无需查 DB。

#### 2.5.2 死信队列表格

字段：

| 字段 | 说明 |
|---|---|
| MAC | 设备 MAC |
| IP | DHCP 分到的 IP |
| sysname | 设备 sysname（采集失败时为空）|
| error_type | SSH_CONNECT_FAILED / AUTH_FAILED / API_FAILED |
| error_message | 错误详情 |
| retry_count | 已重试次数 |
| last_retry_at | 最后重试时间 |
| actions | 重试 / 删除 / 详情 |

**操作**：

- **重试**：`POST /api/sdn/dead-letter/{id}/retry` → 重新入 sdn_ztp_discovery → controller 调度纳管
- **删除**：`DELETE /api/sdn/dead-letter/{id}` → 永久删除（不可恢复，符合"设备删除不可逆"约束）
- **详情**：弹窗显示完整错误堆栈 + SSH 输出（可读化）

**死信告警**：

- 死信 > 5 条 → Dashboard / CMDB 头部红色 chip "死信队列异常"
- 死信 > 20 条 → 弹红色 toast 告警

---

## 3. 设计决策

### 3.1 实时刷新方案

- **决策**：定期轮询（方案 A）
- **理由**：简单 + 兼容老接口 + 5-10s 延迟可接受
- **备选**：WebSocket / SSE 推 v3.4+（v3.1.3 简化）

### 3.2 通知方式

- **决策**：toast 通知（v2.6.2 全局 toast 复用）
- **去重**：按 `device.mgmt_ip` 去重，同一设备只弹 1 次
- **可关闭**：用户可关闭"新设备通知"（localStorage）

### 3.3 死信队列处理

- **重试**：用户手动重试（不自动重试，避免死循环）
- **删除**：永久删除（不可恢复）
- **告警**：死信 > 5 / > 20 双重阈值

### 3.4 性能优化

- poll 间隔：Devices 5s / CMDB 10s / Dashboard 10s
- 增量拉取：`?since={timestamp}`（v3.1.3 简化版：仅 Dashboard 增量）
- 设备表行 < 200 → 拉全表（v3.1.3 简化）

### 3.5 不做（明确边界）

- ❌ 不做 WebSocket / SSE 推送（v3.4+）
- ❌ 不做实时监控大屏（v3.4）
- ❌ 不做 AI 辅助识别（远期）
- ❌ 不做 per-device 凭据（v3.1.3 接受所有 ZTP 设备凭据一致）

---

## 4. 验收标准

### 4.1 Devices.vue 实时刷新

- [ ] 表格 5s 自动 poll
- [ ] 新设备自动出现在表格
- [ ] 新设备高亮 3s（淡绿色背景）
- [ ] "上次刷新时间"显示
- [ ] "手动刷新"按钮（兼容老用户）
- [ ] 后端无响应 → 连续 3 次失败弹 toast 警告
- [ ] 设备表行 < 200 时不卡顿

### 4.2 CMDB.vue 资产表实时刷新

- [ ] 资产表 10s 自动 poll
- [ ] 新资产自动出现在表格
- [ ] 新资产高亮 5s
- [ ] 死信队列 tab 可切换
- [ ] 死信告警 chip 显示（> 5 条）

### 4.3 Dashboard 实时统计

- [ ] 设备总数 / 在线 / 离线 / 未知 实时更新
- [ ] 折线图每小时刷新
- [ ] 按 vendor / model 分布实时更新

### 4.4 新设备上线通知

- [ ] 新设备上线时弹 toast
- [ ] 中英双语（v2.6.0 i18n）
- [ ] 同一设备只弹 1 次
- [ ] 用户可关闭通知（localStorage 开关）

### 4.5 死信队列处理 UI

- [ ] 死信队列表格（MAC / IP / sysname / error / retry_count / last_retry_at / actions）
- [ ] 重试按钮（POST /api/sdn/dead-letter/{id}/retry）
- [ ] 删除按钮（DELETE /api/sdn/dead-letter/{id}）
- [ ] 详情弹窗（完整错误堆栈 + SSH 输出）
- [ ] 死信告警 chip（> 5 / > 20 双阈值）

### 4.6 测试覆盖

- [ ] 前端 Devices.vue vitest ≥ 5 case（实时刷新逻辑）
- [ ] 前端 CMDB.vue vitest ≥ 5 case（死信队列 tab）
- [ ] 前端 Dashboard.vue vitest ≥ 3 case（实时统计）
- [ ] 前端 deviceWatcher.ts unit ≥ 5 case（toast 触发 / 去重 / 关闭）
- [ ] 集成测试（API）≥ 10 case
- [ ] Playwright e2e ≥ 5 case（Devices 实时刷新 / 死信处理 / 通知）
- [ ] 真机测试（3 平台）≥ 3 case（ZTP → 自动纳管 → 前端可见）

### 4.7 文档同步

- [ ] `frontend/src/views/Devices.vue` 加注释（实时刷新逻辑）
- [ ] `docs/ops-toolkit.md` §ztp-前端集成 章节新增
- [ ] `VERSION-ROADMAP.md` v3.1.3 行状态更新（⏳ → ✅）
- [ ] `RELEASE-NOTES-v3.1.3.md` 新建

---

## 5. 依赖关系

### 5.1 上游依赖

- **v3.1.2**（已规划）：自动纳管 + 死信队列 + 业务 IP 推送（**强依赖**）
- **v3.1.1**（已规划）：1:1 静态 IP 池子
- **v3.1.0**（已闭环）：独立 ztp-server 容器
- **v2.6.2**（已闭环）：全局 toast 系统
- **v2.6.0**（已闭环）：vue-i18n v9 中英双语
- **v2.5.0**（已闭环）：Playwright 37 e2e case
- **v2.4.1**（已闭环）：ctrl + config + data 3 容器拆分

### 5.2 下游被依赖

- 无（v3.1.3 是 v3.1 大版本最后一环）

### 5.3 API 端点

- `GET /api/devices?since={timestamp}` — 增量设备列表（v3.1.3 新增）
- `GET /api/dashboard/stats?since={timestamp}` — 增量 Dashboard 统计（v3.1.3 新增）
- `GET /api/sdn/dead-letter` — 死信队列（v3.1.2 已定义，v3.1.3 复用）
- `POST /api/sdn/dead-letter/{id}/retry` — 重试（v3.1.2 已定义）
- `DELETE /api/sdn/dead-letter/{id}` — 删除（v3.1.2 已定义）

### 5.4 前端组件

- `frontend/src/views/Devices.vue` — 加实时刷新 + 高亮 + toast
- `frontend/src/views/CMDB.vue` — 加实时刷新 + 死信 tab + 告警 chip
- `frontend/src/views/Dashboard.vue` — 加实时统计 + 折线图
- `frontend/src/utils/deviceWatcher.ts`（新增）— 监听设备表变化 + 弹 toast
- `frontend/src/components/DevelLetterQueue.vue`（新增）— 死信队列组件
- `frontend/src/components/DevelLetterDetailModal.vue`（新增）— 死信详情弹窗

---

## 6. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| **风险 1：频繁 poll 压垮后端** | 5s 间隔 × N 用户 = 高 QPS | poll 间隔 5-10s + 增量拉取（`?since=`）+ 设备表行 < 200 拉全表 |
| **风险 2：toast 通知骚扰** | 用户被频繁弹窗 | 按 `device.mgmt_ip` 去重 + 关闭开关 |
| **风险 3：死信队列膨胀** | DB 表越来越大 | 死信 > 30 天自动清理（v3.1.3 简化：用户手动删除） |
| **风险 4：前端内存泄漏** | poll 定时器未清理 | 组件 unmount 时 clear interval |
| **风险 5：i18n 文案翻译遗漏** | 通知文案只显示中文 | v2.6.0 已加 i18n 检查，CI 卡控 |

---

## 7. 走法（5 阶段）

| 阶段 | 主题 | 输出 | 依赖 |
|---|---|---|---|
| **T1** | 后端增量 API | `?since=` 参数支持 | v3.1.2 后端 |
| **T2** | 前端实时刷新 | Devices / CMDB / Dashboard poll | T1 |
| **T3** | 新设备通知 | deviceWatcher.ts + toast 集成 | T1+T2 |
| **T4** | 死信队列 UI | DevelLetterQueue 组件 + 详情弹窗 | v3.1.2 后端 |
| **T5** | 真机验证 + 文档同步 | 3 平台 × 1 场景 = 3 case + RELEASE-NOTES | T1-T4 |

---

## 8. 不做（明确边界）

- ❌ **不做 WebSocket / SSE 推送**（v3.4+）
- ❌ **不做实时监控大屏**（v3.4）
- ❌ **不做死信 30 天自动清理**（v3.1.3 简化：用户手动删除）
- ❌ **不做 per-device 凭据管理**（v3.1.3 接受所有 ZTP 设备凭据一致）
- ❌ **不做 AI 辅助识别**（远期）

---

## 9. 与 PRD-V3.1 关系

- **PRD-V3.1** = V3.1 大版本蓝图（4 子版本拆解）
- **PRD-V3.1.1** = V3.1.1 子版本详细 PRD（ZTP 落地）
- **PRD-V3.1.2** = V3.1.2 子版本详细 PRD（自动纳管）
- **PRD-V3.1.3** = V3.1.3 子版本详细 PRD（**资产可见，本文件**）
- 3 个子版本 PRD 独立 OpenSpec change 跟踪
- 共同构成 V3.1 大版本完整 PRD 体系
- **v3.1 大版本闭环** = v3.1.0（调研）+ v3.1.1（落地）+ v3.1.2（纳管）+ v3.1.3（可见）

---

## 10. 参考文档

- [PRD-V3.1.md](PRD-V3.1.md) — V3.1 大版本蓝图
- [PRD-V3.1.1.md](PRD-V3.1.1.md) — V3.1.1 ZTP 落地
- [PRD-V3.1.2.md](PRD-V3.1.2.md) — V3.1.2 自动纳管
- [VERSION-ROADMAP.md §v3.1.3](VERSION-ROADMAP.md) — 版本路线图
- [docs/ztp-stack.md](docs/ztp-stack.md) — ZTP 容器栈详解
- [RELEASE-NOTES-v3.1.0.md](RELEASE-NOTES-v3.1.0.md) — v3.1.0 调研成果
