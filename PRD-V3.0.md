# PRD - H3C NetCtrl V3.0

## 版本记录

| 版本 | 日期 | 作者 | 变更说明 |
|---|---|---|---|
| V3.0 Draft | 2026-07-08 | Codex + 用户共创 | V3.0 PRD 初稿，定义 VPC/SDN 起步能力、端口随接随入、分布式网关配置自动化、状态校验闭环与前端可视化方向 |

---

## 1. 版本概述

### 1.1 一句话目标

V3.0 将 H3C NetCtrl 从“交换机配置与运维平台”推进到“轻量 SDN/VPC 编排平台”：用户可在系统中创建 VPC，将交换机端口绑定到指定 VPC/网段，终端或物理设备接入对应端口并配置 IP/网关后，即可随接随入，并由系统持续校验 EVPN/VXLAN、VSI、Vsi-interface、IP VPN 路由与端口状态，形成可视化闭环。

### 1.2 现状问题

当前平台已经具备设备管理、接口管理、VLAN/VPN 配置、备份回滚、3 容器拆分、ops-toolkit 排障与 QA 工程化能力，但在接入编排层仍有短板：

| 问题 | 影响 |
|---|---|
| 虚拟机 / 物理终端接入依赖手工配置 | 新设备入网慢，配置一致性差 |
| 交换机端口与业务 VPC/网段关系不可视 | 接线、排障和变更缺少清晰视图 |
| VPC 创建需要手动理解 IP VPN、VSI、VNI、RD/RT、Vsi-interface | 操作门槛高，容易漏关键前置条件 |
| 配置下发后缺少状态校验闭环 | “命令下了”不等于“网络真的可用” |
| 3 容器架构已有基础，但 SDN 资源模型尚未建立 | ctrl/config/data 之间缺少 VPC、端口绑定、状态采集的协作语义 |

### 1.3 V3.0 定位

V3.0 是关键能力进阶版本，不是简单新增页面。它要把“设备配置命令”抽象成“可管理的网络资源”：

- 租户：隔离域，承载 RD/RT 等三层租户语义。
- VPC：项目里的最小业务网络单元，等同于交换机侧一个可接入子网，不做云厂商式“大 VPC 套小子网”结构。
- 端口绑定：提前把交换机端口纳入某个 VPC，使终端接入后自动进入对应网段。
- 状态闭环：创建、绑定、下发、采集、校验、展示必须形成闭环。

### 1.4 版本原则

| 原则 | 说明 |
|---|---|
| 后端核心优先 | 先落地资源模型、配置模板、下发与校验闭环；前端大屏可分阶段推进 |
| 只管理 VPC/接入层，不接管 underlay | OSPF、BGP EVPN 邻居、VTEP underlay 连通由用户提前打通 |
| 可视化表达隐藏专业细节 | 前端展示对勾、异常、端口/VPC/网段关系，不强迫用户理解 Type-2/Type-5 路由 |
| 配置必须可验证 | 下发成功只是开始，必须采集设备状态并给出可读结论 |
| OpenSpec 拆小步实施 | PRD 定方向，后续按 OpenSpec 拆成可验证 change |

---

## 2. 项目背景与已有基础

### 2.1 已有产品能力

| 版本 | 与 V3.0 相关的基础 |
|---|---|
| V2.0 | 平台化 UI、设备管理、接口管理、命令执行、批量操作、Alembic |
| V2.2 | 接口 VPN instance、L2/L3、link type、L3 接口 IP 编辑能力 |
| V2.4.1 | ctrl/config/data 三容器拆分，config 容器成为配置中心 |
| V2.4.2.1 | ops-toolkit `paramiko-batch-exec`，可通过 SSH 观察 H3C 真实状态 |
| V2.5.0 | split 默认、internal-api 缓存、interface-config/task-monitor 脚本 |
| V2.6.1 | 资产/备份状态修复、数据完整性与 review 流程收口 |

### 2.2 架构边界

当前默认 split 模式：

| 容器 | 当前职责 | V3.0 扩展方向 |
|---|---|---|
| ctrl | 设备身份中心、Dashboard、日志 | 租户/VPC 的展示入口、设备选择、项目级概览 |
| config | 接口/VLAN/VPN/命令执行 | VPC 配置编排、模板生成、设备下发、状态采集 |
| data | 资产、备份、任务、采集存储 | VPC 状态快照、校验记录、历史变更、可视化数据源 |
| sdn | 规划中 | V3.0 可评估新增，承载 VPC 编排与 etcd 协调 |

V3.0 初期默认不强制新增独立 `sdn` 容器。实现上优先沿用既有“配置下发类能力归属 config 容器”的拆分方式，在 `config` 容器内落地 VPC 编排能力，同时保留后续拆出 `sdn` 容器的模块边界。

是否拆出独立 `sdn` 容器以实际复杂度评估为准，评估维度包括：

- VPC 部署任务量、并发下发与状态采集频率是否明显超过现有 config 容器承载范围。
- SDN 编排是否需要独立的任务调度、状态协调、锁和控制面缓存。
- 与接口/VPN/命令执行等既有模块是否高度耦合，拆出后是否会增加不必要的跨容器调用。
- 后续 monitor 能力按既有容器拆分思路独立演进，SDN 是否独立不影响 monitor 边界。

### 2.3 流程约束

- 所有实现变更必须走 OpenSpec：Propose -> Apply -> Archive。
- 设备排错必须走 ops-toolkit，不裸写 SSH/paramiko。
- 测试必须走 qa-backend / qa-frontend 容器。
- 前端单功能验证可用 MCP 浏览器，不能替代 QA 回归。
- 发版闭环必须同步 README、VERSION-ROADMAP、RELEASE-NOTES、OpenSpec archive。

---

## 3. 核心概念与产品模型

### 3.1 租户

租户是隔离域，对应设备上的 `ip vpn-instance` 与 RD/RT 语义。

| 字段 | 说明 |
|---|---|
| tenant_name | 用户自定义租户名 |
| rd | Route Distinguisher，用于 BGP EVPN 中区分租户路由身份 |
| import_rt / export_rt | Route Target，用于导入/导出租户路由 |
| l3_vni | 分布式网关场景下的三层 VNI |

关键设计约束：

- RD/RT 不是传统 IPv4 VPN 的“无关配置”，在 EVPN/VXLAN 分布式网关中是 L3VNI 的控制面身份。
- `Vsi-interface l3-vni` 绑定了 `ip vpn-instance` 后，设备需要从该 VPN 实例取得 RD/RT 上下文，否则可能出现 `Vsi-interface up/up` 但自动 L3VNI VSI 不可用的状态。
- V3.0 必须把 RD/RT 作为创建租户 / L3VNI 的必填或自动分配项，不允许只下发 `l3-vni`。
- RD/RT/L3VNI 默认由系统自动分配，预留前 1000 号段给人工、实验或历史配置，避免自动化资源与既有网络规划冲突。

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
- VNI 是否允许跨租户重复需以 H3C 设备实际能力为准。在验证完成前，V3.0 采用更保守的策略：设备侧物理 VNI 按 fabric 全局唯一分配，避免不同 RD 下的 VNI 冲突导致不可预期行为。
- 产品层仍保留租户作用域建模。若后续实测确认设备支持租户内逻辑 VNI 重复映射，可在数据库中区分“逻辑 VNI / 设备 VNI”；若不支持，则两者保持一致且全局唯一。

### 3.3 端口绑定

端口绑定描述“哪个交换机端口属于哪个 VPC”。

| 字段 | 说明 |
|---|---|
| device_id | 交换机设备 |
| interface_name / if_index | 物理接口 |
| tenant_id | 所属租户 |
| vpc_id | 所属 VPC |
| access_mode | access / trunk / service-instance |
| service_instance_id | H3C service-instance 编号 |
| vlan_id | 接入 VLAN / s-vid |
| status | planned / deployed / drift / failed |

目标效果：

- 端口提前预配置。
- 物理设备或虚拟机接入端口后，只需配置对应 VPC 网段 IP 与网关即可入网。
- 前端可清晰看到交换机每个端口归属的 VPC、网段、状态。

### 3.4 状态校验

状态校验是 V3.0 的一等能力，不是附属日志。

| 校验对象 | 设备侧观测 | 前端表达 |
|---|---|---|
| VPC 配置 | ip vpn-instance / vsi / Vsi-interface / l3-vni | VPC 配置完成 |
| L2VNI | `display l2vpn vsi verbose`, `display vxlan tunnel` | 二层通道正常 |
| L3VNI | `Auto_L3VNI*` 状态、Vsi3、BGP EVPN L3 路由 | 分布式网关正常 |
| 主机学习 | ARP、EVPN route arp、L2VPN MAC | 已发现终端 |
| 端口绑定 | AC Up、service-instance Up、接口 up/down | 端口接入正常 |
| 连通性 | 网关 ping、主机路由、必要时业务探测 | 连通 / 异常 |

前端不展示“Type-2 / Type-5 / RD/RT”这类专业术语，统一映射为图标和状态文案。

---

## 4. V3.0 功能范围

### 4.1 P0 必做功能

| 模块 | 功能 | 说明 |
|---|---|---|
| 租户管理 | 创建 / 查看租户 | 管理 RD/RT/L3VNI，作为 VPC 隔离域 |
| VPC 创建 | 一键创建 VPC | 录入名称、网段、网关，系统自动分配 RD/RT/VNI/接口编号并生成 IP VPN / VSI / Vsi-interface 配置 |
| 端口绑定 | 绑定端口到 VPC | 指定交换机端口归属哪个 VPC，自动下发 service-instance / xconnect |
| 配置下发 | 模板化下发 | 下发 IP VPN、VSI、Vsi-interface、service-instance、必要的全局 EVPN/VXLAN 保护项 |
| 状态采集 | 采集设备状态 | 获取 VSI、VNI、ARP、MAC、BGP EVPN、端口 AC 状态 |
| 闭环校验 | 生成验收结论 | 判断 VPC 是否 active，端口是否 deployed，终端是否可达 |
| 排障降级 | 单设备单 VPC 集中式网关模式 | 支持针对某设备某 VPC 临时关闭分布式网关相关配置，验证本地 AC/VSI/主机侧是否正常 |
| 操作日志 | 记录配置与校验过程 | 每次创建、绑定、下发、校验必须可追溯 |
| 数据库 | 新增 SDN 资源模型 | tenants / vpcs / port_bindings / deployment_tasks / validation_snapshots |

### 4.2 P1 建议功能

| 模块 | 功能 | 说明 |
|---|---|---|
| 前端大屏 | 端口 / VPC 可视化 | 展示交换机端口矩阵、VPC 归属、网段、接入状态 |
| 资源详情页 | VPC 详情 | 展示网段、网关、绑定端口、已学习终端、校验结果 |
| Drift 检测 | 配置漂移检测 | 数据库期望态与设备实际态对比 |
| 任务化执行 | 异步部署任务 | 长耗时下发与校验通过 task 追踪 |

### 4.3 P2 评估功能

| 模块 | 功能 | 说明 |
|---|---|---|
| etcd 协调 | 控制面锁与期望态 | V3.0 P0 不要求集群；先评估单节点 etcd 或轻量 DB 锁是否作为可选协调能力，防止多任务同时改同一设备 / VPC |
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

## 5. 详细功能需求

### 5.1 租户管理

#### 5.1.1 创建租户

用户输入：

- 租户名称
- RD（可手动或自动生成）
- IPv4 RT import/export
- EVPN RT import/export
- L3VNI

系统行为：

1. 校验 RD/RT/L3VNI 是否冲突。
2. 写入数据库，状态为 `planned`。
3. 生成设备侧 IP VPN 配置模板。
4. 支持一键下发到指定 VTEP 设备。
5. 采集 `display current-configuration` / `display bgp l2vpn evpn` / `display ip routing-table vpn-instance` 验证。

#### 5.1.2 租户状态

| 状态 | 含义 |
|---|---|
| planned | 仅数据库存在，尚未下发 |
| deploying | 正在下发 |
| active | 所有关联设备校验通过 |
| degraded | 部分设备配置或路由状态异常 |
| failed | 下发失败或关键状态缺失 |

### 5.2 VPC 创建

#### 5.2.1 创建表单

字段：

- VPC 名称
- 所属租户
- CIDR
- 网关 IP
- L2VNI（默认系统自动分配，支持高级模式确认）
- VLAN / s-vid（默认系统自动分配，支持高级模式确认）
- VSI 名称（默认系统生成）
- Vsi-interface 编号（默认系统自动分配）
- 网关 MAC
- 目标设备范围

默认策略：

- VPC 名称用户自定义。
- RD/RT 从租户继承。
- RD/RT/L3VNI/L2VNI/VLAN/Vsi-interface/service-instance 默认由系统分配；自动分配避开前 1000 号段，并按设备/fabric 范围做冲突检测。
- 网关 IP 默认取 CIDR 最后一个可用地址，如 `/24` 默认 `.254`。
- 网关 MAC 可按 VPC 自动生成，分布式网关场景同一 VPC 在不同 VTEP 保持一致。
- VNI 在设备能力验证前按 fabric 全局唯一分配；若后续确认 H3C 支持跨租户重复，可再放宽为逻辑 VNI 与设备 VNI 分离模型。

#### 5.2.2 下发配置范围

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
- `vxlan tunnel mac-learning disable` / `vxlan tunnel arp-learning disable` 作为推荐保护项纳入模板，但不可再把它误判为本次 L3VNI 不起的主根因；其定位是降低数据面学习污染风险。

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

### 5.4 端口绑定与随接随入

#### 5.4.1 绑定端口

用户选择：

- 设备
- 接口
- VPC
- 接入模式

系统下发：

```text
interface GigabitEthernet x/x/x
 port link-mode bridge
 port link-type trunk
 port trunk permit vlan <vlan>
 port trunk pvid vlan <vlan>
 service-instance <id>
  encapsulation s-vid <vlan>
  xconnect vsi <vsi>
```

或根据设备能力与接入形态选择 access/hybrid/service-instance 模板。

#### 5.4.2 端口状态展示

端口状态至少包含：

- 物理 up/down
- 绑定 VPC
- 绑定 VLAN/VNI
- AC/service-instance up/down
- 学到的终端 IP/MAC
- 最近一次校验结果

### 5.5 状态采集与闭环校验

#### 5.5.1 采集命令

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

#### 5.5.2 校验规则

| 规则 | 通过条件 |
|---|---|
| 租户配置存在 | 目标设备存在对应 `ip vpn-instance`、RD、RT |
| L2VNI 正常 | VPC 对应 VSI Up，VNI tunnel Up |
| L3VNI 正常 | L3VNI 自动 VSI Up，远端主机 `/32` 路由可通过 Vsi3/L3VNI 承载 |
| 端口绑定正常 | service-instance Up，AC 归属正确 |
| 主机学习正常 | 本地主机 ARP/MAC 为 Dynamic，远端主机为 EVPN/BGP |
| 网关正常 | Vsi-interface up/up，网关 GL 表项存在 |
| 无危险漂移 | 数据库期望态与设备实际态一致 |

#### 5.5.3 前端状态映射

| 技术状态 | 前端表达 |
|---|---|
| 全部通过 | 绿色对勾，状态：正常 |
| 部分设备未下发 | 黄色提示，状态：待同步 |
| VSI Down / L3VNI Down | 红色告警，状态：网关承载异常 |
| AC Down / 接口 down | 红色端口，状态：端口未接入 |
| 路由缺失 | 黄色或红色，状态：路由未学习 |
| 采集失败 | 灰色，状态：设备不可达 |

### 5.6 前端可视化

#### 5.6.1 VPC 总览大屏

目标：第一屏直接看懂网络接入状态。

核心区域：

- 交换机列表 / VTEP 列表
- 端口矩阵
- VPC 颜色标识
- 每个端口显示 VPC 名称、网段、状态图标
- 异常端口高亮

#### 5.6.2 VPC 详情页

展示：

- VPC 基本信息：名称、租户、CIDR、网关、VNI
- 绑定端口
- 已学习终端 IP/MAC
- 设备下发状态
- 校验状态
- 最近操作日志

#### 5.6.3 创建 VPC 向导

步骤：

1. 选择租户或创建租户。
2. 输入 VPC 名称、网段、网关。
3. 选择目标设备。
4. 选择端口绑定。
5. 预览配置计划。
6. 执行下发。
7. 展示校验结果。

前端不在 V3.0 初期追求复杂拓扑动画，优先做稳定、清楚、可操作的大屏和详情视图。

---

## 6. 数据库候选设计（Draft）

本节是 PRD 阶段的候选模型，用于表达资源关系和后续 OpenSpec 拆分方向，不等同于最终 migration。最终字段、索引、约束与命名必须在 `sdn-vpc-prd-and-model` 中结合现有数据库 schema、Alembic 约定和后端模块边界复核后冻结。

设计原则：

- 系统默认自动分配 RD/RT/VNI/VLAN/Vsi-interface/service-instance 等编号，并记录分配来源。
- 在 H3C 设备能力验证完成前，设备侧 VNI 按 fabric 全局唯一处理。
- 若产品逻辑 VNI 与设备物理 VNI 后续需要分离，数据库应能表达映射关系。
- 降级/排障状态必须落库，避免集中式网关临时状态被误判为正常期望态。

### 6.1 候选表：sdn_tenants

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER | 主键 |
| name | VARCHAR | 租户名 |
| rd | VARCHAR | RD |
| import_rt | VARCHAR | IPv4/EVPN import RT |
| export_rt | VARCHAR | IPv4/EVPN export RT |
| l3_vni | INTEGER | L3VNI |
| allocation_policy | VARCHAR | auto/manual/mixed |
| status | VARCHAR | planned/deploying/active/degraded/failed |
| created_at / updated_at | DATETIME | 时间戳 |

### 6.2 候选表：sdn_vpcs

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER | 主键 |
| tenant_id | INTEGER | 关联 sdn_tenants |
| name | VARCHAR | VPC 名 |
| cidr | VARCHAR | 网段 |
| gateway_ip | VARCHAR | 网关 IP |
| gateway_mac | VARCHAR | 网关 MAC |
| vlan_id | INTEGER | 接入 VLAN |
| logical_vni | INTEGER | 产品层逻辑 VNI，若无需区分可与 device_vni 一致 |
| device_vni | INTEGER | 实际下发到设备的 L2VNI/VXLAN ID |
| vsi_name | VARCHAR | VSI 名称 |
| vsi_interface | INTEGER | Vsi-interface 编号 |
| gateway_mode | VARCHAR | distributed/centralized/troubleshooting |
| status | VARCHAR | planned/deploying/active/degraded/failed |
| created_at / updated_at | DATETIME | 时间戳 |

### 6.3 候选表：sdn_port_bindings

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER | 主键 |
| vpc_id | INTEGER | 关联 VPC |
| device_id | INTEGER | 关联设备 |
| if_index | INTEGER | 接口索引 |
| interface_name | VARCHAR | 接口名 |
| service_instance_id | INTEGER | service-instance |
| access_mode | VARCHAR | access/trunk/service-instance |
| status | VARCHAR | planned/deployed/drift/failed |
| last_validated_at | DATETIME | 最近校验时间 |

### 6.4 候选表：sdn_deployments

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER | 主键 |
| resource_type | VARCHAR | tenant/vpc/port_binding |
| resource_id | INTEGER | 资源 ID |
| device_id | INTEGER | 目标设备 |
| status | VARCHAR | pending/running/success/failed |
| planned_config | TEXT | 计划配置 |
| result | TEXT | 下发结果 |
| error_message | TEXT | 错误信息 |
| created_at / updated_at | DATETIME | 时间戳 |

### 6.5 候选表：sdn_validation_snapshots

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER | 主键 |
| resource_type | VARCHAR | tenant/vpc/port/device |
| resource_id | INTEGER | 资源 ID |
| device_id | INTEGER | 设备 |
| status | VARCHAR | pass/warn/fail/unknown |
| summary | TEXT | 面向用户的摘要 |
| raw_facts | JSON/TEXT | 原始采集事实 |
| created_at | DATETIME | 时间戳 |

---

## 7. API 设计草案（Draft）

本节 API 只定义 V3.0 需要的交互面，最终路径、请求体和响应结构由 OpenSpec 设计稿与现有后端路由风格共同决定。原则上先保证后端核心能力可通过 API 调用，再推进 P1 前端大屏。

### 7.1 租户 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/sdn/tenants` | 租户列表 |
| POST | `/api/sdn/tenants` | 创建租户 |
| GET | `/api/sdn/tenants/{id}` | 租户详情 |
| POST | `/api/sdn/tenants/{id}/deploy` | 下发租户基础配置 |
| POST | `/api/sdn/tenants/{id}/validate` | 校验租户状态 |

### 7.2 VPC API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/sdn/vpcs` | VPC 列表 |
| POST | `/api/sdn/vpcs` | 创建 VPC |
| GET | `/api/sdn/vpcs/{id}` | VPC 详情 |
| POST | `/api/sdn/vpcs/{id}/deploy` | 下发 VPC 配置 |
| POST | `/api/sdn/vpcs/{id}/validate` | 校验 VPC 状态 |
| POST | `/api/sdn/vpcs/{id}/devices/{device_id}/gateway-mode` | 单设备单 VPC 分布式/集中式排障模式切换 |

### 7.3 端口绑定 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/sdn/port-bindings` | 端口绑定列表 |
| POST | `/api/sdn/port-bindings` | 创建端口绑定 |
| POST | `/api/sdn/port-bindings/{id}/deploy` | 下发端口绑定配置 |
| POST | `/api/sdn/port-bindings/{id}/validate` | 校验端口状态 |

### 7.4 可视化 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/sdn/overview` | 大屏总览数据 |
| GET | `/api/sdn/devices/{id}/ports-map` | 单设备端口矩阵 |
| GET | `/api/sdn/vpcs/{id}/topology` | VPC 逻辑视图 |

---

## 8. 配置下发策略

### 8.1 下发方式

| 配置类型 | 优先方式 | 说明 |
|---|---|---|
| VPN instance / RD / RT | SSH CLI | H3C EVPN/VXLAN CLI 能力为主，NETCONF 兼容性待验证 |
| VSI / VNI / EVPN | SSH CLI | 需要完整模板与回显校验 |
| Vsi-interface / IP / L3VNI | SSH CLI 或 NETCONF | 以实测稳定路径为准 |
| 端口 service-instance | SSH CLI | 现有 trunk/VLAN 经验表明 CLI 更可靠 |
| 状态采集 | SSH display | 走 ops-toolkit / backend SSHExecutor |

V3.0 不追求“所有配置都 NETCONF”。项目既有约束是 NETCONF 优先，但 H3C V7 上 trunk allowed VLAN 等能力已证明必须 CLI；EVPN/VXLAN 模板允许以 SSH CLI 为主，只要日志、校验和回滚边界清楚。

### 8.2 原子性与失败处理

配置下发不是天然事务，系统必须保存计划与结果：

1. 生成 planned_config。
2. 执行前写 deployment pending。
3. 逐设备执行，记录每步输出。
4. 任一步失败时停止后续高风险步骤。
5. 自动执行状态采集。
6. 给出成功 / 部分成功 / 失败结论。

V3.0 P0 不要求自动回滚复杂 EVPN/VXLAN 配置，但必须给出“已下发到哪一步、下一步建议、可人工回退命令”。

---

## 9. 验收标准

### 9.1 后端验收

1. 可创建租户，RD/RT/L3VNI 写入数据库并校验冲突。
2. 可创建 VPC，生成 VSI/VNI/Vsi-interface/IP VPN 配置计划。
3. 可绑定设备端口到 VPC，生成 service-instance/xconnect 配置计划。
4. 可对指定设备下发 VPC 与端口绑定配置。
5. 可采集并解析 VSI、VXLAN tunnel、EVPN route arp/mac、BGP EVPN、ARP、IP routing-table 状态。
6. 可生成 VPC active/degraded/failed 状态。
7. 可记录每次下发与校验日志。
8. Alembic migration 可 upgrade/downgrade。

### 9.2 网络验收

1. 集中式网关模式下，本地 Vsi-interface 到下联主机可 ping 通。
2. 分布式网关模式下，L3VNI 自动 VSI 必须 Up。
3. 分布式网关模式下，远端主机 `/32` 路由进入对应 VPN 实例并能通过 L3VNI 承载。
4. VPC 内本地与远端终端互通。
5. 不同租户之间默认隔离。
6. 端口绑定后，终端接入并配置对应 IP/网关即可入网。

### 9.3 前端验收

1. 可创建租户与 VPC。
2. 可将端口绑定到 VPC。
3. 可看到交换机端口矩阵及 VPC 归属。
4. 可看到 VPC 状态、端口状态、终端学习状态。
5. 异常状态以图标 / 对勾 / 告警表达，不要求用户理解底层路由类型。

### 9.4 QA 验收

1. 后端单元测试覆盖数据模型、配置生成、状态解析、校验规则。
2. 设备命令解析必须有 fixture，不依赖实时设备。
3. 真机集成按需通过 ops-toolkit / integration marker 执行，不默认压生产设备。
4. 前端 lint/build/vitest/playwright 按现有 QA 容器规则执行。
5. MCP 浏览器用于关键 UI 流程点测。

---

## 10. OpenSpec 拆分建议

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

## 11. 风险与应对

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

## 12. 关键技术结论沉淀

本 PRD 吸收 2026-07-07 至 2026-07-08 EVPN/VXLAN 实验结论：

1. 集中式网关可作为排障降级模型，用于证明 AC/VSI/Vsi-interface/主机侧是否正常。
2. 分布式网关启用后，同网段远端主机可能通过 EVPN host `/32` 路由进入 L3VNI 路径。
3. `Vsi-interface l3-vni` 不是孤立配置；它依赖 `ip vpn-instance` 的 RD/RT 语义。
4. L3VNI 自动 VSI Down 时，即使 L2VNI、Type-2、ARP/MAC 表看似正常，分布式网关仍可能不可用。
5. `vxlan tunnel mac-learning disable` 与 `vxlan tunnel arp-learning disable` 是推荐保护项，能降低 tunnel 数据面学习污染风险，但本次主根因为 L3VNI 所需 RD/RT 上下文缺失或不一致。
6. 后续自动化模板必须同时下发和校验：IP VPN RD/RT、L2VNI VSI、Vsi-interface 网关、L3VNI、端口 AC、EVPN 状态。

---

## 13. 已收敛决策与待验证问题

### 13.1 已收敛决策

1. 容器边界：V3.0 初期默认在 `config` 容器落地 SDN/VPC 下发能力；若任务规模、并发采集、状态协调或代码体量明显超出承载，再提出新增独立 `sdn` 容器。
2. 编号策略：RD/RT/VNI/VLAN/Vsi-interface/service-instance 默认系统自动分配，避开前 1000 号段，并保留后续高级手工覆盖空间。
3. 降级能力：支持“单设备 + 单 VPC”的集中式网关降级/恢复，作为排障能力，不作为默认部署模式。
4. 前端优先级：前端大屏和详情页进入 P1；P0 先完成后端资源模型、下发、采集、校验闭环。
5. etcd 优先级：V3.0 P0 不要求 etcd 集群。是否引入单节点 etcd 或轻量协调能力，由 OpenSpec 阶段评估 VPC 编排是否强依赖锁与期望态协调。

### 13.2 待验证问题

1. H3C 设备在多租户 RD 场景下是否允许 VNI 跨租户重复。验证完成前，自动分配采用设备侧全局唯一 VNI。
2. 集中式网关降级在不同设备版本上的最小命令集是否稳定，目前按 `undo distributed-gateway local` 与 `undo local-proxy-arp enable` 作为候选模板。
3. `sdn` 独立容器是否有必要，需在 `sdn-vpc-foundation` 设计和代码量评估后决定。
4. etcd 是否比数据库锁/任务表更适合当前规模，需要在 P0 基础能力设计完成后再单独判断。
