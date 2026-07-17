# H3C NetCtrl V3.2 PRD：加固切换 + 大迁移

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| V3.2 Draft | 2026-07-18 | 用户拍板 + Codex 共创 | V3.2 = 加固切换 + 大迁移：架构切 EVENG + 全 QA + VPC 全能力验证 |

---

## 1. 背景与目标

### 1.1 背景

v3.0 骨架（sdn-vpc-netconf-schema-xml）已在真机 .5 / .26 验证**配置面** 100% 一致，但：
- **数据面**验证受 .26 设备限制无法做（用户原话："数据面在 26 上做不到的，就我们现在只管配置面就行"）
- **真机环境**模拟 L2/L3 不完整（underlay / OSPF / BGP 邻居由人工提前打通）
- **SDN 后端 QA** 体系不全（v2.4.2 / v2.5.0 的 QA 主要覆盖 ctrl + config + data，SDN 后端专项 QA 缺失）

### 1.2 目标

v3.2 = **加固切换 + 大迁移** 三件大事：

1. **架构切到 EVENG 平台**：用 EVENG 提供完整 L2/L3 模拟环境，绕开真机限制
2. **全 QA 覆盖 SDN 后端已有能力**：把 QA 体系扩张到 SDN 后端全部能力
3. **VPC 全能力验证**：在 EVENG 环境做一次完整 VPC 验证（v3.0 PRD 子能力 4 个：prd-and-model / foundation / port-binding / l3vni-validation）

### 1.3 用户原话

> "v3.2 我们会做一个是加固切换，3.2 叫加固切换，配合 ztp 的能力，做架构切换，切换到 eveng 平台。3.2 的时候呢，把所有的 qa 做了，就是包括 sdn 的后端现在已有能力，就是有一些没实现的能力先不管啊，已有能力先都做一遍。"

> "v3.2 要做一个什么点迁移完了之后我们去把现有的 3.0 实现的能力去... 看看能不能做到啊，vpc 全全能力好吧"

## 2. V3.2 范围

### 2.1 架构切到 EVENG 平台

#### 2.1.1 目标

利用 EVENG（开源网络仿真平台）提供完整 L2/L3 模拟环境，**替代部分真机测试场景**。

#### 2.1.2 范围

- **EVENG 平台搭建**：
  - 部署 EVENG server（独立容器 / 虚拟机）
  - 集成 2-3 个 H3C V7 镜像（v3.0 已用 .5 / .26 / .177 仿真）
  - 提供 L2/L3 拓扑（VPC 业务所需 underlay / OSPF / BGP）
- **业务下发通道 EVENG 验证**：
  - 在 EVENG 设备上跑 v3.0 双套 payload 模板
  - 验证 vpc_create / port_bind 全流程
  - **数据面验证**（真机做不到的部分在 EVENG 验证）
- **真机 + EVENG 双轨**：
  - 真机优先（v3.0 已验证）
  - EVENG 作为补全（v3.2 新增能力）

#### 2.1.3 设计决策

- **EVENG 部署方式**：独立容器（与 ops-toolkit / ztp-server 一致，host network 模式按需）
- **H3C V7 镜像**：用 qemu 仿真（EVENG 原生支持）
- **凭据**：与 .env 集成，eveng 专用账号

#### 2.1.4 验收标准

- [ ] EVENG 容器能启动
- [ ] 2-3 个 H3C V7 设备在 EVENG 运行
- [ ] vpc_create / port_bind 在 EVENG 设备上跑通
- [ ] VPC 数据面验证通过（v3.0 真机做不到的）

### 2.2 全 QA 覆盖 SDN 后端已有能力

#### 2.2.1 目标

把 v2.4.2 / v2.5.0 的 QA 体系扩张到 **SDN 后端全部能力**，确保 v3.0 骨架 + v3.1 ZTP 都有完整测试覆盖。

#### 2.2.2 范围

- **SDN 后端单元测试**：
  - vpc_create / port_bind / sdn_deployment 全部 unit
  - 目标：≥ 200 个 unit（v3.0 已有 73 + v3.1 新增 + v3.2 扩张）
- **集成测试**：
  - 业务下发链路（API → service → SSH/NETCONF → 设备）
  - 跨平台集成（.5 LSTN / .26 RSTN / EVENG）
- **端到端 e2e**：
  - VPC 创建 → 端口绑定 → 状态采集 → 前端展示
  - ZTP 自动配置 → 自动纳管 → 资产可见（v3.1 全链路）
- **性能压测**：
  - VPC 批量创建（10+ VPC 并发）
  - ZTP 批量上线（5+ 设备并发）
  - 资源占用 baseline（CPU / 内存 / DB 连接）

#### 2.2.3 验收标准

- [ ] SDN 后端 unit ≥ 200
- [ ] 集成测试覆盖 100% 业务下发链路
- [ ] e2e 覆盖 5 个核心场景（vpc_create / port_bind / vpc_delete / port_unbind / ztp_landing）
- [ ] 性能压测报告（v3.0 已有，v3.2 更新）

### 2.3 VPC 全能力验证

#### 2.3.1 目标

v3.0 PRD 4 个子能力在 v3.2 集中验证：
- `sdn-vpc-prd-and-model`（数据模型）
- `sdn-vpc-foundation`（VPC CRUD）
- `sdn-port-binding`（端口随接随入）
- `sdn-l3vni-validation`（L3VNI 状态）

#### 2.3.2 范围

- **数据模型定稿**：
  - VPC / VSI / EVPN / L3VPN / Vsi-interface / service-instance 表结构
  - 关联关系（VPC ↔ 设备 / VPC ↔ 端口）
  - Alembic 010 迁移
- **VPC CRUD 后端**：
  - 租户 / VPC / 端口 / 路由 4 类资源 CRUD
  - 配置计划生成（dry-run / planned_config）
  - 业务下发（复用 v3.0 骨架）
- **端口随接随入**：
  - 端口绑定 service-instance 状态机
  - 自动检测端口 UP → 触发 VPC 接入
  - 前端展示端口归属
- **L3VNI 状态采集**：
  - RD/RT/EVPN route 采集
  - ARP/MAC 表采集
  - 校验闭环（VPC 配置 vs 实际状态）

#### 2.3.3 验收标准

- [ ] VPC / VSI / EVPN / L3VPN / Vsi-interface 数据模型定稿 + Alembic 010
- [ ] 4 类资源 CRUD API
- [ ] 配置计划 dry-run 准确率 100%
- [ ] 端口随接随入真机（.5 / .26）或 EVENG 验证
- [ ] L3VNI 状态采集 5min 内完成
- [ ] VPC 创建 → 端口绑定 → 状态采集 → 校验 闭环 100% 通过

## 3. 走法（4 阶段）

| 阶段 | 主题 | 输出 | 依赖 |
|---|---|---|---|
| **阶段 1** | EVENG 平台搭建 | EVENG 容器 + 2-3 H3C 镜像 | 无 |
| **阶段 2** | SDN 后端 QA 扩张 | ≥ 200 unit + 集成 + e2e + 压测 | 阶段 1（部分）|
| **阶段 3** | VPC 全能力 EVENG 验证 | 4 子能力变更 + 数据面验证 | 阶段 1 + 2 |
| **阶段 4** | v3.2.0 整体发版 | tag v3.2.0 + RELEASE-NOTES + push | 阶段 1+2+3 |

## 4. 不做（明确边界）

- ❌ **不做集中式网关降级**（sdn-gateway-fallback 推 v3.3）
- ❌ **不做前端大屏**（sdn-visual-overview 推 v3.4）
- ❌ **不做 etcd 协调**（sdn-etcd-coordination 推 v3.5 远期）
- ❌ **不做商用 R6607+ 设备 ZTP**（v3.1.1 不在 v3.2 范围）

## 5. 依赖关系

- 阶段 1 不依赖 v3.0 之外的能力
- 阶段 2 部分依赖 v3.1（ZTP 后端 QA）
- 阶段 3 依赖阶段 1 + 2

## 6. 风险

- **风险 1：EVENG H3C V7 镜像不可用**：商用镜像可能需授权
  - 缓解：先评估镜像可用性，备选用 HCL 内部测试版
- **风险 2：SDN 后端 QA 体系扩张工作量大**：≥ 200 unit 写起来耗时
  - 缓解：分批写，每个 v3.2.x 子版本承担一部分
- **风险 3：VPC 全能力验证发现 v3.0 骨架 bug**：v3.0 骨架可能在 EVENG 暴露问题
  - 缓解：分阶段验证，发现 bug 立即修
