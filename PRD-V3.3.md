# H3C NetCtrl V3.3 PRD：剩余 VPC 能力

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| V3.3 Draft | 2026-07-18 | 用户拍板 + Codex 共创 | V3.3 = v3.0 PRD 中未在 v3.2 验证的剩余 VPC 能力 |

---

## 1. 背景与目标

### 1.1 背景

v3.0 PRD 列了 7 个子能力 change，其中：
- 4 个已在 v3.2 验证（prd-and-model / foundation / port-binding / l3vni-validation）
- 1 个推到 v3.4（visual-overview）
- 1 个推到 v3.4（ops-toolkit-probes）
- 1 个推到 v3.5 远期（etcd-coordination）
- **1 个推到 v3.3**：**sdn-gateway-fallback**（集中式网关降级/恢复）

### 1.2 目标

完成 v3.0 PRD 剩余的 1 个子能力：**集中式网关降级/恢复**，使 v3.0 PRD 7 个子能力全部落地（除 v3.4 / v3.5 部分）。

## 2. V3.3 范围

### 2.1 集中式网关降级/恢复

#### 2.1.1 目标

为单设备单 VPC 集中式网关场景提供**降级/恢复**能力，便于真实设备定位问题。

#### 2.1.2 业务背景

v3.0 / v3.2 设计的 VPC 默认是**分布式网关**（每个 VPC 在每台 leaf 上都有 Vsi-interface，流量就近转发）。但某些场景需要**集中式网关**（VPC 只在 1 台 leaf 上配 Vsi-interface，其他 leaf 用 EVPN type-5 路由转发），例如：
- 跨 VPC 互访需要统一出口
- 特定 VPC 临时集中管控
- 单设备故障时降级到其他设备

#### 2.1.3 范围

- **网关角色定义**：
  - 分布式网关（默认）：每台 leaf 都是网关
  - 集中式网关：1 台 leaf 是 active 网关，其他 leaf 是 transit
- **网关切换**：
  - 主动切换（admin 操作）：VPC 的 active 网关 leaf-A → leaf-B
  - 被动切换（故障触发）：leaf-A down → 自动选 leaf-B 作为新 active
- **配置生成**：
  - active 网关：保留 Vsi-interface + IP
  - transit 网关：删除 Vsi-interface + IP（仅保留 EVPN type-5 路由）
- **状态采集**：
  - 实时检测 active 网关状态
  - 切换时记录 audit log
- **排障工具**：
  - ops-toolkit 加 `sdn-gateway-status` 脚本
  - 显示当前 active / transit 网关 + EVPN 路由状态

#### 2.1.4 验收标准

- [ ] 集中式网关创建 API（VPC + active leaf）
- [ ] 网关主动切换 API（active leaf-A → leaf-B）
- [ ] 网关被动切换（leaf-A down 触发）
- [ ] 配置生成（active 保留 Vsi-interface，transit 删除 Vsi-interface）
- [ ] 状态采集 5min 内完成
- [ ] ops-toolkit `sdn-gateway-status` 脚本
- [ ] 20 unit + 5 集成 + 3 e2e

#### 2.1.5 不做

- ❌ 跨 VPC 集中式网关（v3.3 仅单 VPC 集中式）
- ❌ 多 active 网关（v3.3 仅 1 active + N transit）
- ❌ 自动重选 active 时的权重策略（v3.3 用 round-robin）

## 3. 走法（3 阶段）

| 阶段 | 主题 | 输出 | 依赖 |
|---|---|---|---|
| **阶段 1** | 数据模型 + CRUD | VPC 网关角色字段 + API | v3.2 数据模型 |
| **阶段 2** | 网关切换逻辑 | 主动/被动切换实现 | 阶段 1 |
| **阶段 3** | ops-toolkit 工具 + 验证 | sdn-gateway-status 脚本 + 真机/EVENG 验证 | 阶段 2 |

## 4. 不做（明确边界）

- ❌ **不做前端大屏**（v3.4）
- ❌ **不做 etcd 协调**（v3.5 远期）
- ❌ **不做多 VPC 集中式网关**（v3.3 仅单 VPC）

## 5. 依赖关系

- 依赖 v3.2 数据模型（VPC / VSI / EVPN / L3VPN）
- 依赖 v3.2 业务下发通道
- 依赖 v3.2 状态采集

## 6. 风险

- **风险 1：网关切换时流量中断**：active 切换时短暂丢包
  - 缓解：用 BFD + 预切换（先同步新 active，再切流量）
- **风险 2：被动切换误判**：BFD 抖动导致频繁切换
  - 缓解：增加 hold-down 时间（3 次失败才切）
- **风险 3：配置生成跨平台差异**：LSTN / RSTN 网关配置命令不同
  - 缓解：复用 v3.0 模板架构，加 gateway-fallback unit
