# H3C NetCtrl V3.0 PRD：VPC / SDN、端口随接随入与状态闭环

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| V3.0 Draft | 2026-07-08 | Codex + 用户共创 | V3.0 PRD 初稿，定义 VPC/SDN 起步能力、端口随接随入、分布式网关配置自动化、状态校验闭环与前端可视化方向 |

---

## 1. 背景与目标

当前项目已经具备设备管理、接口管理、VPN instance 绑定、命令执行、备份/回滚、split 三容器、QA 容器与 ops-toolkit 排障能力。V3.0 的目标是在这些基础上向轻量 SDN/VPC 编排演进。

用户目标可以概括为：

- 预先把交换机端口配置好，终端或物理设备接入指定端口后，只要配置对应 VPC 网段 IP 与网关，即可接入网络。
- 系统能展示端口归属、VPC、网段、接入状态，形成“随接随入”的体验。
- 支持创建 VPC，并自动下发 IP VPN、VSI、Vsi-interface、service-instance 等配置。
- 底层 underlay、OSPF、BGP 邻居由人工提前打通，V3.0 不接管。
- 系统不止下发配置，还要采集设备状态、判断路由/ARP/MAC/VSI 是否正常，并在前端用直观状态表达。
- ACL 暂不做。

V3.0 是能力进阶版本，不是单点功能补丁。其核心是：

```text
资源建模 -> 配置计划 -> 设备下发 -> 状态采集 -> 闭环校验 -> 可视化呈现
```

---

## 2. 架构边界

### 2.1 当前基础

| 容器 | 当前职责 | V3.0 扩展方向 |
|---|---|---|
| ctrl | 设备身份中心、Dashboard、日志 | 租户/VPC 展示入口、设备选择、项目级概览 |
| config | 接口/VLAN/VPN/命令执行 | VPC 配置编排、模板生成、设备下发、状态采集 |
| data | 资产、备份、任务、采集存储 | VPC 状态快照、校验记录、历史变更、可视化数据源 |
| sdn | 规划中 | 可评估新增，承载独立 VPC 编排与协调 |

V3.0 初期默认不强制新增独立 `sdn` 容器。实现上优先沿用既有“配置下发类能力归属 config 容器”的拆分方式，在 `config` 容器内落地 VPC 编排能力，同时保留后续拆出 `sdn` 容器的模块边界。

是否拆出独立 `sdn` 容器以实际复杂度评估为准：

- VPC 部署任务量、并发下发与状态采集频率是否明显超过 config 容器承载范围。
- SDN 编排是否需要独立任务调度、状态协调、锁和控制面缓存。
- 与接口/VPN/命令执行等既有模块是否高度耦合，拆出后是否会增加不必要的跨容器调用。
- 后续 monitor 能力按既有容器拆分思路独立演进，SDN 是否独立不影响 monitor 边界。

### 2.2 流程约束

- 所有实现变更必须走 OpenSpec：Propose -> Apply -> Archive。
- 设备排错必须走 ops-toolkit，不裸写 SSH/paramiko。
- 测试必须走 qa-backend / qa-frontend 容器。
- 前端单功能验证可用 MCP 浏览器，但不能替代 QA 回归。
- 发版闭环必须同步 README、VERSION-ROADMAP、RELEASE-NOTES、OpenSpec archive。

---

## 3. 核心概念

### 3.1 租户

租户是隔离域，对应设备上的 `ip vpn-instance` 与 RD/RT 语义。

| 字段 | 说明 |
|---|---|
| tenant_name | 用户自定义租户名 |
| rd | Route Distinguisher，用于 BGP EVPN 中区分租户路由身份 |
| import_rt / export_rt | Route Target，用于导入/导出租户路由 |
| l3_vni | 分布式网关场景下的三层 VNI |

关键约束：

- RD/RT 不是传统 IPv4 VPN 的“无关配置”，在 EVPN/VXLAN 分布式网关中是 L3VNI 的控制面身份。
- `Vsi-interface l3-vni` 绑定 `ip vpn-instance` 后，设备需要从 VPN 实例取得 RD/RT 上下文，否则可能出现 `Vsi-interface up/up` 但自动 L3VNI VSI 不可用。
- RD/RT/L3VNI 默认由系统自动分配，预留前 1000 号段给人工、实验或历史配置，避免自动化资源与既有规划冲突。

### 3.2 VPC

项目内 VPC 等同于交换机侧一个可接入业务子网，不设计云厂商式多层嵌套。

| 字段 | 说明 |
|---|---|
| vpc_name | 用户自定义 VPC 名称 |
| tenant_id | 所属租户 |
| cidr | VPC 网段，如 `192.168.10.0/24` |
| gateway_ip | 网关 IP，如 `192.168.10.254` |
| gateway_mac | 分布式网关 MAC，可自动分配或用户指定 |
| logical_vni / device_vni | 产品逻辑 VNI 与设备侧 VXLAN ID；若无需区分则保持一致 |
| vsi_name | 设备侧 VSI 名称 |
| vsi_interface | Vsi-interface 编号 |
| status | pending / deploying / active / degraded / failed |

产品语义：

- 同一租户下可以有多个 VPC，每个 VPC 对应独立 L2VNI / VSI / Vsi-interface。
- 不同租户之间互相隔离，即使业务名称重复也不冲突。
- VNI 是否允许跨租户重复需以 H3C 设备实际能力为准。验证完成前，V3.0 采用更保守策略：设备侧物理 VNI 按 fabric 全局唯一分配。

### 3.3 端口绑定

端口绑定描述“哪个交换机端口属于哪个 VPC”。

| 字段 | 说明 |
|---|---|
| device_id | 交换机设备 |
| interface_name / if_index | 物理接口 |
| tenant_id | 所属租户 |
| vpc_id | 所属 VPC |
| access_vlan / service_instance | 接入侧封装 |
| status | planned / deployed / drift / failed |

---

## 4. V3.0 功能范围

### 4.1 P0 必做

| 模块 | 功能 | 说明 |
|---|---|---|
| 租户管理 | 创建 / 查看租户 | 管理 RD/RT/L3VNI，作为 VPC 隔离域 |
| VPC 创建 | 一键创建 VPC | 录入名称、网段、网关，系统自动分配 RD/RT/VNI/接口编号并生成配置 |
| 端口绑定 | 绑定端口到 VPC | 指定交换机端口归属哪个 VPC，自动下发 service-instance / xconnect |
| 配置下发 | 模板化下发 | 下发 IP VPN、VSI、Vsi-interface、service-instance、必要的 EVPN/VXLAN 保护项 |
| 状态采集 | 采集设备状态 | 获取 VSI、VNI、ARP、MAC、BGP EVPN、端口 AC 状态 |
| 闭环校验 | 生成验收结论 | 判断 VPC 是否 active，端口是否 deployed，终端是否可达 |
| 排障降级 | 单设备单 VPC 集中式网关模式 | 支持针对某设备某 VPC 临时关闭分布式网关相关配置，验证本地 AC/VSI/主机侧是否正常 |
| 操作日志 | 记录配置与校验过程 | 每次创建、绑定、下发、校验必须可追溯 |
| 数据库 | 新增 SDN 资源模型 | tenants / vpcs / port_bindings / deployment_tasks / validation_snapshots |

### 4.2 P1 建议

| 模块 | 功能 | 说明 |
|---|---|---|
| 前端大屏 | 端口 / VPC 可视化 | 展示交换机端口矩阵、VPC 归属、网段、接入状态 |
| 资源详情页 | VPC 详情 | 展示网段、网关、绑定端口、已学习终端、校验结果 |
| Drift 检测 | 配置漂移检测 | 数据库期望态与设备实际态对比 |
| 任务化执行 | 异步部署任务 | 长耗时下发与校验通过 task 追踪 |

### 4.3 P2 评估

| 模块 | 功能 | 说明 |
|---|---|---|
| etcd 协调 | 控制面锁与期望态 | V3.0 P0 不要求集群；先评估单节点 etcd 或轻量 DB 锁是否作为可选协调能力 |
| 外网路由接入 | 默认路由 / NAT / 出口能力 | 本版可预留，不强制实现 |
| 多设备批量模板 | 批量 VPC 下发 | 适合后续 fabric 扩展 |
| 拓扑视图 | VTEP / Spine / Leaf 逻辑拓扑 | 先不作为 P0 |

### 4.4 明确不做

| 不做项 | 原因 |
|---|---|
| ACL | 用户明确暂不规划 |
| underlay OSPF/BGP 邻居自动搭建 | 用户提前打通，V3.0 不接管 |
| 复杂云 VPC 嵌套模型 | 项目设备粒度是子网，不做大 VPC/子网层级 |
| 多租户权限系统 | 当前个人项目无登录权限模型 |
| 自动创建虚拟机 | 当前目标是接入虚拟/物理设备，不管理虚拟化平台 |
| 生产级 HA 控制器 | V3.0 是 SDN 起步，不做大规模控制器集群 |

---

## 5. 配置与校验设计

### 5.1 VPC 创建默认策略

- VPC 名称用户自定义。
- RD/RT 从租户继承或由租户创建时自动分配。
- RD/RT/L3VNI/L2VNI/VLAN/Vsi-interface/service-instance 默认由系统分配；自动分配避开前 1000 号段，并按设备/fabric 范围做冲突检测。
- 网关 IP 默认取 CIDR 最后一个可用地址，如 `/24` 默认 `.254`。
- 网关 MAC 可按 VPC 自动生成，分布式网关场景同一 VPC 在不同 VTEP 保持一致。
- VNI 在设备能力验证前按 fabric 全局唯一分配。

### 5.2 下发配置范围

V3.0 P0 需要生成并下发以下配置族：

```text
ip vpn-instance <tenant>
 route-distinguisher <rd>
 vpn-target <rt> import-extcommunity
 vpn-target <rt> export-extcommunity

vsi <vpc-vsi>
 gateway vsi-interface <n>
 vxlan <l2-vni>
 evpn encapsulation vxlan
  route-distinguisher <l2-rd>
  vpn-target <l2-rt> import-extcommunity
  vpn-target <l2-rt> export-extcommunity

interface Vsi-interface<n>
 ip binding vpn-instance <tenant>
 ip address <gateway-ip> <mask>
 mac-address <gateway-mac>
 local-proxy-arp enable
 distributed-gateway local

interface Vsi-interface<l3-n>
 ip binding vpn-instance <tenant>
 l3-vni <l3-vni>
```

注意：

- 具体命令模板必须以 H3C V7 实测为准。
- 分布式网关场景必须校验 L3VNI 自动 VSI 是否 Up。
- `vxlan tunnel mac-learning disable` / `vxlan tunnel arp-learning disable` 作为推荐保护项纳入模板，但定位是降低数据面学习污染风险，不应误判为 L3VNI 不起的主根因。

### 5.3 集中式网关降级与恢复

该能力定位为排障工具，不是默认部署模式。它用于在分布式网关状态异常时，快速证明本地 AC、VSI、Vsi-interface 与下联主机是否正常。

操作粒度：

- 指定设备。
- 指定租户与 VPC。
- 系统定位该 VPC 在目标设备上的 VSI、Vsi-interface、网关 IP/MAC 与端口绑定。

降级计划：

```text
interface Vsi-interface<n>
 undo distributed-gateway local
 undo local-proxy-arp enable
```

恢复计划：

```text
interface Vsi-interface<n>
 local-proxy-arp enable
 distributed-gateway local
```

系统要求：

- 执行前必须展示目标设备、VPC、Vsi-interface 与预计变更命令。
- 降级后资源状态标记为 `degraded` 或 `troubleshooting`，避免被误认为正常分布式网关状态。
- 降级与恢复都必须写入 deployment 记录，并触发本地 ping / ARP / MAC 校验。
- 该能力不应批量作用于整个租户，避免排障动作扩大影响面。

### 5.4 状态采集命令

P0 采集命令包括但不限于：

```text
display l2vpn vsi verbose
display vxlan tunnel
display vxlan tunnel-interface
display evpn route arp
display evpn route mac
display bgp l2vpn evpn
display bgp peer l2vpn evpn
display arp vpn-instance <tenant>
display ip routing-table vpn-instance <tenant>
display l2vpn mac-address
display l2vpn service-instance interface <interface>
display interface brief
```

### 5.5 校验规则

| 规则 | 通过条件 |
|---|---|
| 租户配置存在 | 目标设备存在对应 `ip vpn-instance`、RD、RT |
| L2VNI 正常 | VPC 对应 VSI Up，VNI tunnel Up |
| L3VNI 正常 | L3VNI 自动 VSI Up，远端主机 `/32` 路由可通过 L3VNI 承载 |
| 端口绑定正常 | service-instance Up，AC 归属正确 |
| 主机学习正常 | 本地主机 ARP/MAC 为 Dynamic，远端主机为 EVPN/BGP |
| 网关正常 | Vsi-interface up/up，网关 GL 表项存在 |
| 无危险漂移 | 数据库期望态与设备实际态一致 |

前端不展示 “Type-2 / Type-5 / RD/RT” 这类专业术语，统一映射为正常、待同步、网关承载异常、端口未接入、路由未学习、设备不可达等状态。

---

## 6. 数据库候选设计（Draft）

本节是 PRD 阶段的候选模型，用于表达资源关系和后续 OpenSpec 拆分方向，不等同于最终 migration。最终字段、索引、约束与命名必须在 `sdn-vpc-prd-and-model` 中结合现有数据库 schema、Alembic 约定和后端模块边界复核后冻结。

设计原则：

- 系统默认自动分配 RD/RT/VNI/VLAN/Vsi-interface/service-instance 等编号，并记录分配来源。
- 在 H3C 设备能力验证完成前，设备侧 VNI 按 fabric 全局唯一处理。
- 若产品逻辑 VNI 与设备物理 VNI 后续需要分离，数据库应能表达映射关系。
- 降级/排障状态必须落库，避免集中式网关临时状态被误判为正常期望态。

候选表：

| 表 | 用途 |
|---|---|
| sdn_tenants | 租户、RD/RT、L3VNI、分配策略 |
| sdn_vpcs | VPC、CIDR、网关、VNI、VSI、Vsi-interface、网关模式 |
| sdn_port_bindings | 端口到 VPC 的绑定关系 |
| sdn_deployments | 配置计划、下发结果、错误信息 |
| sdn_validation_snapshots | 设备状态采集与校验快照 |

---

## 7. API 设计草案（Draft）

本节 API 只定义 V3.0 需要的交互面，最终路径、请求体和响应结构由 OpenSpec 设计稿与现有后端路由风格共同决定。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/sdn/tenants` | 租户列表 |
| POST | `/api/sdn/tenants` | 创建租户 |
| POST | `/api/sdn/tenants/{id}/deploy` | 下发租户基础配置 |
| POST | `/api/sdn/tenants/{id}/validate` | 校验租户状态 |
| GET | `/api/sdn/vpcs` | VPC 列表 |
| POST | `/api/sdn/vpcs` | 创建 VPC |
| POST | `/api/sdn/vpcs/{id}/deploy` | 下发 VPC 配置 |
| POST | `/api/sdn/vpcs/{id}/validate` | 校验 VPC 状态 |
| POST | `/api/sdn/vpcs/{id}/devices/{device_id}/gateway-mode` | 单设备单 VPC 分布式/集中式排障模式切换 |
| GET | `/api/sdn/port-bindings` | 端口绑定列表 |
| POST | `/api/sdn/port-bindings` | 创建端口绑定 |
| POST | `/api/sdn/port-bindings/{id}/deploy` | 下发端口绑定配置 |
| POST | `/api/sdn/port-bindings/{id}/validate` | 校验端口状态 |
| GET | `/api/sdn/overview` | 大屏总览数据 |
| GET | `/api/sdn/devices/{id}/ports-map` | 单设备端口矩阵 |

---

## 8. OpenSpec 拆分建议

V3.0 不建议一个巨型 change 完成，建议拆为：

| change-id | 目标 |
|---|---|
| `sdn-vpc-prd-and-model` | 数据模型、术语、PRD/Spec 定稿 |
| `sdn-vpc-foundation` | 租户/VPC CRUD、Alembic、配置计划生成 |
| `sdn-vpc-device-templates` | H3C IP VPN / VSI / Vsi-interface / service-instance 模板 |
| `sdn-l3vni-validation` | L3VNI、RD/RT、EVPN route、ARP/MAC 状态采集与校验 |
| `sdn-gateway-fallback` | 单设备单 VPC 集中式网关降级/恢复与排障校验 |
| `sdn-port-binding` | 端口绑定、随接随入、端口状态 |
| `sdn-visual-overview` | 前端大屏、端口矩阵、VPC 详情 |
| `sdn-ops-toolkit-probes` | ops-toolkit 增加 VPC/EVPN 专用探测与 ping statistics 读取修复 |
| `sdn-etcd-coordination` | 可选单节点 etcd / 轻量协调方案评估；不作为 V3.0 P0 前置依赖 |

---

## 9. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| H3C EVPN/VXLAN 命令模板差异 | 下发失败或设备状态异常 | 先 fixture + 真机样本固化，模板按设备版本标记 |
| L3VNI/RD/RT 理解错误 | 分布式网关不通 | 将 RD/RT 作为 L3VNI 必需前置校验 |
| VNI 重复能力不确定 | 多租户模型与设备能力冲突 | 设备能力探测，必要时物理 VNI 全局唯一 |
| 状态采集输出不稳定 | 校验误判 | display parser 加单元测试和真实样本 |
| SSH ping 输出读取不完整 | 连通性验收不可靠 | 修 ops-toolkit SSHExecutor，等待 Ping statistics |
| 配置下发不可事务化 | 失败后状态不一致 | deployment 记录每步状态，提供人工回退建议 |
| 前端大屏范围膨胀 | 拖慢后端核心 | 前端分 P1，P0 先保证 API 和状态闭环 |
| 过早冻结库表/API | 后续实现被不成熟模型绑死 | PRD 只给候选模型，最终由 OpenSpec 设计稿和现有 schema 复核后冻结 |
| etcd 引入过重 | 拉高部署和维护复杂度 | V3.0 P0 不依赖 etcd 集群，先评估单节点或 DB 锁是否足够 |

---

## 10. 关键技术结论沉淀

本 PRD 吸收 2026-07-07 至 2026-07-08 EVPN/VXLAN 实验结论：

1. 集中式网关可作为排障降级模型，用于证明 AC/VSI/Vsi-interface/主机侧是否正常。
2. 分布式网关启用后，同网段远端主机可能通过 EVPN host `/32` 路由进入 L3VNI 路径。
3. `Vsi-interface l3-vni` 不是孤立配置；它依赖 `ip vpn-instance` 的 RD/RT 语义。
4. L3VNI 自动 VSI Down 时，即使 L2VNI、Type-2、ARP/MAC 表看似正常，分布式网关仍可能不可用。
5. `vxlan tunnel mac-learning disable` 与 `vxlan tunnel arp-learning disable` 是推荐保护项，能降低 tunnel 数据面学习污染风险，但本次主根因为 L3VNI 所需 RD/RT 上下文缺失或不一致。
6. 后续自动化模板必须同时下发和校验：IP VPN RD/RT、L2VNI VSI、Vsi-interface 网关、L3VNI、端口 AC、EVPN 状态。

---

## 11. 已收敛决策与待验证问题

### 11.1 已收敛决策

1. 容器边界：V3.0 初期默认在 `config` 容器落地 SDN/VPC 下发能力；若任务规模、并发采集、状态协调或代码体量明显超出承载，再提出新增独立 `sdn` 容器。
2. 编号策略：RD/RT/VNI/VLAN/Vsi-interface/service-instance 默认系统自动分配，避开前 1000 号段，并保留后续高级手工覆盖空间。
3. 降级能力：支持“单设备 + 单 VPC”的集中式网关降级/恢复，作为排障能力，不作为默认部署模式。
4. 前端优先级：前端大屏和详情页进入 P1；P0 先完成后端资源模型、下发、采集、校验闭环。
5. etcd 优先级：V3.0 P0 不要求 etcd 集群。是否引入单节点 etcd 或轻量协调能力，由 OpenSpec 阶段评估 VPC 编排是否强依赖锁与期望态协调。

### 11.2 待验证问题

1. H3C 设备在多租户 RD 场景下是否允许 VNI 跨租户重复。验证完成前，自动分配采用设备侧全局唯一 VNI。
2. 集中式网关降级在不同设备版本上的最小命令集是否稳定，目前按 `undo distributed-gateway local` 与 `undo local-proxy-arp enable` 作为候选模板。
3. `sdn` 独立容器是否有必要，需在 `sdn-vpc-foundation` 设计和代码量评估后决定。
4. etcd 是否比数据库锁/任务表更适合当前规模，需要在 P0 基础能力设计完成后再单独判断。
