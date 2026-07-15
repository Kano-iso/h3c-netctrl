# sdn-vpc-netconf-schema-xml — Design

## 背景

`2026-07-11-sdn-vpc-deployment-executor` archive 后真机验证发现 H3C V7 NETCONF 不接受 CLI 文本下发。本 change 通过 .5 设备探针（2026-07-11）逐步定位 H3C V7 NETCONF 业务下发的正确路径。

> **当前最终口径（T1.7 修订）**：本文前半部分的 T0 结论曾误把“OpenConfig `network-instances` 空实例可创建”理解为“L2vpn/VXLAN/EVPN/VSI 业务可走 OpenConfig NETCONF”。T1/T1.5/T1.6 已经推翻该业务结论；T1.7 又进一步修正了 T1.6 的过度表述：H3C V7 S6850 确实能通过 `ietf-netconf-monitoring` 拉到 `H3C-l2vpn-config` / `H3C-evpn-config` / `H3C-vxlan-config` YANG，且 YANG 中存在 `L2VPN/VSIs/VSI`、`VXLAN/VXLANs/Vxlan` 等配置节点。当前事实不是“完全没有 YANG/XML 模型”，而是“YANG schema 存在，但当前 `get/get-config/edit-config` 入口仍未找到可用路径，真实 VSI 在完整 `get-config source=running` 中不可见”。后续不能继续基于 T0 的 OpenConfig 空实例误判推进 XML 模板；是否最终走 SSH CLI 或继续投入 NETCONF 路径，需要基于 T1.7 证据重新决策。

## 探针发现（.5 设备实测 2026-07-11）

### 1. 错误格式 ❌

| 格式 | 设备响应 |
|---|---|
| `<config xmlns="h3c-ns"><Configuration>vsi vpc9999</Configuration></config>` | `Element [h3c-ns]config does not meet requirement` |
| `<config><top xmlns="h3c-ns"><Configuration>vsi vpc9999</Configuration></top></config>` | `Configuration can not have a textual child element` |
| `<config xmlns:xc="..."><top xmlns="h3c-ns"><Configuration><Text>...</Text></Configuration></top></config>` | `Unexpected element 'Text' under 'Configuration'` |
| `<config xmlns:xc="..."><top xmlns="h3c-ns"><Configuration><Command>...</Command></Configuration></top></config>` | `Unexpected element 'Command' under 'Configuration'` |
| `<top xmlns="h3c-ns"><L2VPN>...` | `Unexpected element 'L2VPN' under top` |
| `<top xmlns="h3c-ns"><L2vpnVSI xmlns="...L2VPN-ns">` | `Unexpected element 'L2vpnVSI' under top` |
| `<top xmlns="h3c-ns"><MVPN><Name>vpc9999</Name></MVPN>` | `Unexpected element 'Name' under MVPN` |

**结论**：H3C V7 NETCONF **不直接接受 CLI 文本下发**，且 L2VPN/EVPN/MVPN 顶层 wrapper **不在 top 直接子节点中**。

### 2. T0：OpenConfig 空 network-instance 可写（仅证明基础路径可达，已被 T1/T1.6 限定）

| 格式 | 验证结果 |
|---|---|
| `<config xmlns:xc="..."><top xmlns="h3c-ns"><network-instances><network-instance><name>vpc9999</name></network-instance></network-instances></top></config>` | **edit-config 成功 + get-config 验证存在 + undo 验证可删** |

**T0 当时结论（已废弃）**：曾判断 H3C V7 L2VPN/VXLAN/VSI 配置走 **OpenConfig `network-instances` 模型**。

**T1/T1.6 修正**：该探针只证明 H3C NETCONF 可以创建一个空 `network-instance`，不能证明 VSI/VXLAN/EVPN 子业务在 OpenConfig 下可写。后续 17 个 network-instance 子元素探针全失败，且真实设备上存在的 VSI 在完整 `get-config source="running"` 中完全不可见，因此不能以 T0 结果作为业务下发依据。

### 3. 设备脏数据自查

- 探针 1：vpc9999 创建 + undo 完成，get-config 验证只剩 mgt
- 探针 2-7：所有失败（schema 错），H3C 回滚无脏数据
- 探针完成时 .5 状态：`<network-instances><network-instance><name>mgt</name></network-instance></network-instances>`

## 历史架构假设（已被 T1/T1.6 推翻）

本节保留 T0 后形成的历史方案，便于解释为什么后来需要 T1/T1.6 继续验证。它不再作为实现依据。

### 历史假设 1：业务下发走 OpenConfig network-instances 模型（已废弃）

- L3vpn 走原 v2.4 路径：`<top><L3vpn><L3vpnVRF><VRF>...</VRF></VRF></L3vpnVRF></L3vpn></top>`（已验证）
- L2vpn/VXLAN/VSI/EVPN 走新路径：`<top><network-instances><network-instance>...</network-instance></network-instances></top>`（T0 仅验证空实例；T1/T1.6 已证明业务子结构不可达）
- Vsi-interface 走 Ifmgr module 路径（v2.4 已验证）

### 历史假设 2：planned_config 序列化格式（已废弃）

**当前**（v3.0 简化方案，错误）：
```json
[{"mode": "configure", "command": "vsi vpc0001"}, ...]
```

**历史 XML 方案**（OpenConfig + 元素化，已废弃）：
```json
[
  {"namespace": "openconfig-network-instance", "element": "network-instance", "config": "..."},
  {"namespace": "h3c-l2vpn", "element": "vxlan-vni", "config": "..."},
  ...
]
```

或更直接：每条是一个完整的 `<config>` XML 片段（不依赖 H3C <config> 顶层，H3C 自己做）：
```json
[
  "<network-instance xmlns=\"http://www.h3c.com/netconf/config:1.0\"><name>vpc0001</name></network-instance>",
  "<vxlan><vni-id>20000</vni-id></vxlan>",
  ...
]
```

**T0 时的选择（已废弃）**：模板（VPCConfigTemplate）输出**完整 edit-config 顶层 XML**（含 `<config xmlns:xc><top xmlns="h3c-ns">...</top></config>` 包装），planned_config 存 List[完整 edit-config XML 字符串]。

**T1.6 后的新方向**：L2vpn/VXLAN/EVPN/VSI planned_config 应回到 List[CLI 文本] 或按 Unit 封装的 CLI 文本序列，由 backend 内部 SSH executor/paramiko 执行；不是 XML。

### 历史假设 3：每条独立 edit-config（已废弃）

保留 v1 方案——每条命令单独发一次 edit-config，失败立即停。
- 优点：失败定位准
- 缺点：每条 ~0.5s SSH 开销
- vpc_create 共 14 条 → ~7s 总耗时（可接受）

T1.6 后，该策略仅保留“按 Unit 拆分、失败立即停”的思想；底层执行方式不再是 NETCONF `edit-config`，而是 backend 内封装 SSH CLI。

## 历史架构图（已废弃）

> 下图是 T0 后的 XML edit-config 方案，T1.6 后不再作为 L2vpn/VXLAN/EVPN/VSI 业务实现方向。

```
┌──────────┐  POST /api/sdn/deployments/{id}/apply  ┌──────────────┐
│ Frontend │ ─────────────────────────────────────► │ config 容器   │
└──────────┘                                         │  (FastAPI)    │
                                                     │               │
                                                     │  sdn.py router│
                                                     └──────┬────────┘
                                                            │
                                                            ▼
                                                     ┌──────────────┐
                                                     │ SdnDeployment│
                                                     │   Executor   │
                                                     │              │
                                                     │ 1. parse planned_config (List[完整 edit-config XML])
                                                     │ 2. 串行 edit_config
                                                     │ 3. 失败 → 记录 + status=failed
                                                     └──────┬───────┘
                                                            │
                                                            ▼
                                                     ┌──────────────┐
                                                     │ NetconfClient│
                                                     │ (edit_config)│
                                                     └──────┬───────┘
                                                            │ NETCONF edit-config
                                                            ▼
                                                     ┌──────────────┐
                                                     │   设备 .5    │
                                                     │  (Leaf-04)   │
                                                     └──────────────┘
```

## 历史数据流（已废弃）

1. 用户前端触发 `POST /api/sdn/deployments/1/apply`
2. config 容器 SdnDeploymentExecutor.execute(db, 1)
3. 读 SdnDeployment.planned_config（List[XML 字符串]）
4. NetconfClient context manager，每条 XML 单独 edit_config
5. 写回 status = success / failed

## 前端粒度设计：Unit 拆分（v2 应用户 review 增加）

**用户反馈**：VPC 创建的 14 条命令**不能"一个按钮全下"**，要按 unit 拆，前端可按 unit 触发。

### Unit 拆解

| Unit | 包含的 H3C 命令 | 触发场景 | 独立可 undo | 共享性 |
|---|---|---|---|---|
| **VSI-L2** | `vsi vpc0001` / `vxlan 20000` / `evpn encapsulation vxlan` / `route-distinguisher 1:2000` | 用户创建 VPC 后自动 | ✓ | vpc 独享 |
| **PortBind** | `service-instance 1001` / `xconnect vsi vpc0001 access` | 用户每个端口接入 | ✓ | 每端口独立 |
| **L3VPN** | `ip vpn-instance l3vpn` / `route-distinguisher 1:10000` / `address-family evpn` | 等所有用户接入完，启用 L3 路由 | ✓（首 VPC 创建/末 VPC 删除）| 设备级共享 |
| **VSI-L3** | `interface Vsi-interface1` / `ip binding vpn-instance l3vpn` / `ip address 10.0.1.1 24` / `mac-address 00-00-00-00-4e20-01` / `l3-vni 10000` | 启用 L3 网关 | ✓ | vpc 独享 |
| **Global** | `vxlan tunnel mac-learning disable` | 设备首次初始化 | ✓ | 设备级共享 |
| **PortUnbind** | `undo service-instance 1001` / `undo port access vlan 2` | 用户端口解绑 | — | 每端口独立 |

### 前端典型流程（拆 unit 后）

```
1. 用户提交"创建 VPC"表单（name / cidr / gateway）
   → POST /api/sdn/vpcs
   → 后端: SdnVpc (status=pending) + 自动触发 Unit VSI-L2
2. 用户在 VPC 详情页逐个绑定端口
   → POST /api/sdn/ports/bind  (每个端口)
   → 后端: SdnPortBinding + Unit PortBind
3. 所有端口接入完成（前端判断 SdnPortBinding.count == 计划数）
   → 用户点"启用 L3 路由"
   → POST /api/sdn/vpcs/{id}/enable-l3
   → 后端: Unit L3VPN (首 VPC) + Unit VSI-L3
4. 设备首次初始化（系统级，一次性）
   → POST /api/sdn/devices/{id}/init
   → 后端: Unit Global
```

### 数据模型补充

SdnDeployment 现状是"vpc_create" 14 条混在一起。需要扩展为按 unit 拆分：

```python
class SdnDeployment:
    # 老字段
    action: str  # "create" | "delete"
    planned_config: str  # JSON: List[完整 edit-config XML]
    status: str

    # 新增（v2）
    unit: str  # "vsi-l2" | "port-bind" | "l3vpn" | "vsi-l3" | "global" | "port-unbind" | "vpc-create-all"
    parent_deployment_id: Optional[int]  # unit 间依赖（vsi-l2 必须先于 vsi-l3）
```

### 模板输出格式调整

模板从 `List[ConfigCommand]` 改为 `List[Unit]`，每 Unit 自带 metadata：

```python
class TemplateUnit:
    name: str  # "vsi-l2"
    description: str  # "创建 VPC L2 骨架"
    commands: List[str]  # List[完整 edit-config XML]
    preflight: List[str]  # ["device_model", "device_online", "vpc_not_exists"]
    undo_commands: List[str]  # 反向 XML
```

### 失败回滚策略

- Unit VSI-L2 失败 → 删 vpc0001 VSI（1 条 undo）
- Unit PortBind 失败 → 删对应端口 service-instance（1 条 undo）
- Unit L3VPN 失败 → 删 l3vpn vpn-instance（如果首 VPC；否则不动，共享）
- Unit VSI-L3 失败 → 删 Vsi-interface1
- **任一 unit 失败** → 只 undo 当前 unit，**不**回滚前面已成功的 unit（让用户决定）

### 后端 API 拆分（v2）

| Unit | API |
|---|---|
| VSI-L2 | `POST /api/sdn/vpcs/{id}/units/vsi-l2` |
| PortBind | `POST /api/sdn/ports/{id}/bind` |
| L3VPN | `POST /api/sdn/vpcs/{id}/units/l3vpn`（首 VPC）|
| VSI-L3 | `POST /api/sdn/vpcs/{id}/units/vsi-l3` |
| Global | `POST /api/sdn/devices/{id}/init` |
| PortUnbind | `POST /api/sdn/ports/{id}/unbind` |

**注意**：本 change 只完成 schema 化 XML 重写 + 后端 unit 拆分，**不**做前端。前端是后续 change。

## 与之前 change 的关系

| 旧 change | 影响 |
|---|---|
| `sdn-vpc-model-and-foundation` | 数据模型**扩展**：SdnDeployment 加 `unit` / `parent_deployment_id` 字段，需要 alembic 迁移 |
| `sdn-vpc-device-templates` | 模板输出格式变（从 CLI 文本列表 → Unit 列表）|
| `sdn-vpc-deployment-api` | API 拆分（按 unit）|
| `sdn-vpc-deployment-executor` | executor 内部实现变（每 Unit 独立 SdnDeployment，独立 undo）|

## 历史待研究（Task 1，已由 T1/T1.6 关闭）

**network-instance 下 VSI/VXLAN/EVPN 子结构的准确 schema 化 XML** 曾是开放问题：
- network-instance 下哪些子元素被接受（VSI / VXLAN / EVPN 子 wrapper 名）
- 子元素的子结构（vni-id / encapsulation / gateway-interface / etc）

T1/T1.6 已关闭该方向：network-instance 下 17 个候选子元素全失败；真实 VSI 在完整 `get-config source="running"` 中不可见；.2/.3 参考机的真实 L2vpn/VXLAN/EVPN/VSI 业务也只能通过 SSH display 拉到 CLI 文本。后续不再继续反推 XML 子结构。

**结论**：不再估时，不再继续 schema 化 XML 探针；转向方案 A（backend 内 SSH CLI）。

---

## T1 探针结果（2026-07-11）：架构冲突，需用户决策

### 探针过程

T1 在 .5 设备上做以下 4 轮探针：

1. **T1-A 探针 network-instance 下 17 个候选子元素**（vsi/vxlan/evpn/encapsulation/gateway/l2vpn/l2vfi/p2p/interface/endpoint/vxlan-vni/vni/vni-id/l2vpn-vsi/service/xconnect/access-port）—— **全部 FAIL**（`<top><network-instances><network-instance><子元素>` 路径都不被接受）
2. **T1-B 查 mgt network-instance 真实子结构** —— mgt 是空壳（只有 `<name>`），不能提供"允许子元素"线索
3. **T1-C SSH `display l2vpn vsi verbose` 读 .5 真实 VSI** —— 设备上有 `Auto_L3VNI3000_3`（系统自动建，State Down，Gateway Vsi-interface 3，VXLAN ID 3000）
4. **T1-D NETCONF `get-config` 拉真实 VSI schema 化 XML** —— `network-instances` 只返回 mgt；L2VPN/L2vpnVSI/L2vpnVSIs/L2vpn/EVPN/Vxlan/Vsi **顶层 wrapper 全部不存在**

### T1.5 增强验证（2026-07-11，应用户 review）：补查官方文档 + 真实 capability + 系统前提

> **用户反馈**：是否有查过官方文档、核实过网上所有实现方式、确认不是验证缺失？或是否下发顺序问题（如配置依赖未满足）？要求基于事实支撑结论，而不是只有自测结果。

#### A. 官方文档调研

| 文档 | 关键发现 |
|---|---|
| [H3C《使用NETCONF配置设备操作指导书-6W103》](https://www.h3c.com/cn/Service/Document_Software/Document_Center/Home/Switches/00-Public/Configure/Operation_Manual/NETCONF_OM-6W103/) | "YANG files are integrated in the device software... You can identify the supported operations by retrieving and analyzing the content of YANG files." —— **官方未公开 L2VPN XML 样例**，需 client 端自取 YANG 文件 |
| [H3C S6850&S9850&... Config Examples 15-EVPN](https://www.h3c.com/en/d_202002/1273991_294551_0.htm) | **EVPN 业务前强制要求**（§General restrictions and guidelines）：<br>1. `system-working-mode standard` + save + **reboot**<br>2. enable L2VPN (`l2vpn enable`) |
| [H3C S5560X-EI Command Reference §l2vpn enable](https://www.manualslib.com/manual/2369534/H3c-S5560x-Ei-Series.html?page=23) | "**You must enable L2VPN before you can configure L2VPN settings.** Default: L2VPN is disabled." |
| H3C EVPN-DCI over MPLS L3VPN (S6805/S6825/S6850/S9850/S9820) | S6850 Release 6555P01+ 支持 EVPN/VXLAN **CLI** 业务（已验证）；未提 NETCONF edit-config L2VPN 样例 |

#### B. 网上实现案例调研

| 来源 | 关键发现 |
|---|---|
| CSDN「基于NETCONF与Python实现H3C交换机自动化配置实战」 | 用 H3C S6850 7.1.070 实战 NETCONF，**示例仅含 VLAN/接口/BGP 业务，**没** L2VPN/VXLAN/EVPN 案例** |
| CSDN「H3C交换机NETCONF避坑指南」 | 强调 `netconf ssh server enable` + `device_params={'name':'h3c'}` 必备；未提 L2VPN 业务 |
| 博客园「ncclient模块」| ncclient 0.6.9+ 走 `device_params={'name':'h3c'}`，**示例仅含 ARP/Ifmgr/VLAN 业务，无 L2VPN 案例** |
| H3C 知识库「Using NETCONF to issue security policies for firewalls」 | 防火墙场景用 `OMS/SecurityPolicies` wrapper；L2VPN/VXLAN 业务 NETCONF 案例**未找到** |
| **GitHub 搜索结果** | 未找到 H3C V7 S6850 通过 NETCONF edit-config 下发 L2VPN/VXLAN/EVPN 业务的开源实现案例 |

#### C. `.5` 设备系统前提验证（应用户问"下发顺序"）

| 项 | 验证命令 | 结果 | 是否为前提 |
|---|---|---|---|
| **system-working-mode** | `display system-working-mode` | `The current system working mode is standard. The system working mode for next startup is standard.` | ✅ **已就绪**（official EVPN 强制项）|
| **l2vpn enable** | `display current-configuration \| include l2vpn` | `l2vpn enable` + `address-family l2vpn evpn` | ✅ **已就绪**（official 强制项）|
| **BGP EVPN 地址族** | 同上 | `address-family l2vpn evpn` | ✅ **已就绪**（参考 .2/.3）|
| **NETCONF 服务** | ncclient connect | 成功；server hello 返回完整 capability | ✅ 已开 |
| **VSI running config** | `display current-configuration \| include vsi` | **空** | 初始状态 |
| **L3vpn running config** | `display current-configuration \| include vpn-instance` | 仅 `mgt` | 初始状态 |

**结论**：**所有官方文档强调的前置条件都已满足**，但 L2vpn NETCONF 业务仍不可达。**非配置依赖问题**。

#### D. 真实 NETCONF capability 调研

通过 ncclient 连 .5 设备拉 server hello capabilities，L2VPN 业务相关 module 列表（**完整 revision 字符串，H3C 默认 NS 接受 module-specific NS**）：

```
http://www.h3c.com/netconf/config:1.0-L2VPN?module=L2VPN&revision=2022-04-22
http://www.h3c.com/netconf/config:1.0-EVPN?module=EVPN&revision=2022-05-19
http://www.h3c.com/netconf/config:1.0-VXLAN?module=VXLAN&revision=2021-06-09
http://www.h3c.com/netconf/config:1.0-MVPN?module=MVPN&revision=2022-08-26
http://www.h3c.com/netconf/config:1.0-L3vpn?module=L3vpn&revision=2023-01-09
```

> **T1 之前没看到完整 capability 列表**——是 T1.5 才通过 ncclient 拿到的。这是 T1 探针缺失的关键信息。

#### E. 基于完整 capability 的多组合探针

测试组合（T1.5 共 11 组 edit-config 探针，均失败，**未**留脏数据）：

| # | top 默认 NS | L2vpn 容器 NS | L2vpn wrapper | 子结构 | 错误 |
|---|---|---|---|---|---|
| 1 | H3C 默认 | H3C 默认 | `<L2VPN>` | `<VSIs><VSI><ID>` | `Unexpected element '...':'L2VPN' under top[1]` |
| 2 | H3C 默认 | module-spec | `<m:L2VPN>` | `<m:VSIs><m:VSI><m:ID>` | `Unexpected element '...-L2VPN?module=L2VPN&revision=...':'L2VPN' under top[1]` |
| 3 | module-spec | — | `<L2VPN>` | `<VSIs><VSI><ID>` | `The child elements of config[1] are invalid`（module-spec 不能作 top 默认 NS）|
| 4 | H3C 默认 | H3C 默认 | `<L2vpn>` (v2.4 L3vpn 风格) | `<L2vpnVSIs><VSI><Name>` | `Unexpected element '...':'L2vpn' under top[1]` |
| 5 | H3C 默认 | H3C 默认 | `<L2vpn>` (单数) | `<L2vpnVSI><VSI><Name>` | `Unexpected element '...':'L2vpn' under top[1]` |
| 6 | H3C 默认 | H3C 默认 | `<MVPN>` | `<VSIs><VSI><Name>` | MVPN 接受；`Unexpected element '...':'VSIs' under MVPN[1]` |
| 7 | H3C 默认 | H3C 默认 | `<EVPN>` | `<EVPNs>` | `Unexpected element '...':'EVPN' under top[1]` |
| 8 | H3C 默认 | H3C 默认 | `<VXLAN>` | `<VXLANs>` | `Unexpected element '...':'VXLAN' under top[1]` |
| 9 | H3C 默认 | H3C 默认 | `<L3vpn>` | `<L3vpnVRF><VRF><Name>` | L3vpn 接受；`Unexpected element '...':'Name' under VRF[1]`（字段名待查）|
| 10 | H3C 默认 | L3vpn module-spec | `<L3vpn>` | `<L3vpnVRF><VRF><m:Name>` | L3vpn 接受；`Unexpected element '...':'Name' under VRF[1]`（**业务字段**必须 H3C 默认 NS）|
| 11 | H3C 默认 | H3C 默认 | `<L3vpn>` | `<L3vpnVRF><VRF><Description>` | (L3vpn 路径走通，子字段名探索中，**与 L2vpn 路径**非**冲突**)|

**T1.5 探针关键结论**：

1. **`<top>` 下的 L2VPN/EVPN/VXLAN wrapper 全部被拒**（无论 namespace/wrapper 名/operation）
2. **`<top>` 下的 L3vpn wrapper 被接受**，走到 VRF 层（**v2.4 验证 L3vpn 业务 NETCONF 可达**）
3. **`<top>` 下的 MVPN wrapper 被接受**，但子元素路径与 L2vpn 不重合（MVPN 是 multicast VPN）
4. **不是 namespace 问题**：H3C 默认 NS 和 module-specific NS（含完整 revision）都试过
5. **不是 wrapper 名问题**：L2VPN / L2vpn / L2vpnVSI / L2vpnVSIs / EVPN / VXLAN 都试过
6. **不是 operation 问题**：merge / create 都试过
7. **不是系统前提问题**：system-working-mode standard + l2vpn enable + BGP EVPN 地址族都已就绪
8. **不是配置依赖问题**：VSI running config 完全空（无既有 VSI 干扰）

### 关键发现

| 项 | 事实 |
|---|---|
| H3C 官方 EVPN 文档系统前提 | 满足（system-working-mode standard / l2vpn enable / BGP EVPN AF）|
| NETCONF server capability 中 L2VPN module | **存在**（`config:1.0-L2VPN?module=L2VPN&revision=2022-04-22`）|
| `.5` 真实 L2VPN/VSI/EVPN/VXLAN running config | **不存在** |
| `display l2vpn vsi verbose` 看到的 VSI | 系统自动建的 `Auto_L3VNI3000_3`（非用户配，不持久化到 running config）|
| NETCONF edit-config L2vpn/VSI/EVPN/VXLAN 业务 | **不可达**（11 组 namespace/wrapper/operation 组合全 FAIL）|
| NETCONF edit-config L3vpn（vrf）业务 | **可达**（v2.4 已用）|
| NETCONF edit-config `network-instances`（OpenConfig 空实例）| **可达**（T0 验证）|
| 网上 L2vpn NETCONF 实现案例 | **未找到** H3C V7 S6850 通过 NETCONF edit-config 下发 L2VPN 业务的开源实现 |
| H3C 官方 L2VPN NETCONF XML 样例 | **未公开**（官方文档只说"通过 YANG 文件自取"，未提供 L2vpn 样例）|

### 结论

**H3C V7 S6850 设备（.5）的 L2vpn / VXLAN / EVPN / VSI 业务配置，NETCONF edit-config 协议不可达**——经过**多维事实交叉验证**：

1. ✅ 系统前提已就绪（`system-working-mode standard` / `l2vpn enable` / BGP EVPN AF）
2. ✅ 11 种 namespace + wrapper + operation 组合 edit-config 探针全失败
3. ✅ 官方文档 + 网上案例均**无** L2vpn NETCONF 实现样例
4. ✅ L3vpn（vrf）业务 NETCONF **可达**（v2.4 验证）——证明 NETCONF 通道正常
5. ✅ OpenConfig `network-instances` 实例**可达**（T0 验证）——证明 H3C 默认 NS 路径正常

**不是验证缺失、不是配置依赖、不是 namespace 问题、不是 wrapper 名问题**。

**最终结论**：H3C V7 S6850 在该软件版本下，**L2vpn/VXLAN/EVPN/VSI 业务仅支持 SSH CLI 下发，NETCONF edit-config 不可达**。

### 架构冲突

| 项 | 现状 |
|---|---|
| **旧 Hard Rule（需修订）** | "SDN/VPC business logic must use NETCONF protocol via backend services (config container), not SSH/paramiko" |
| **H3C V7 现实** | L2vpn/VXLAN/EVPN/VSI 业务**只**走 SSH CLI，不走 NETCONF |

修订后的原则应为：**业务执行必须走 backend 服务，不绕过到 ops-toolkit；具体协议按设备能力选择。** 能通过 NETCONF/YANG 稳定闭环的业务继续走 NETCONF；当前 H3C V7 S6850 L2vpn/VXLAN/EVPN/VSI 业务未在 NETCONF 配置树暴露，按方案 A 走 backend 内 SSH CLI。

**3 个候选方案**（需用户决策）：

#### 方案 A：架构妥协（推荐务实）
- v3.0 标注 H3C V7 L2vpn/VXLAN/EVPN 业务下发走 **SSH CLI**（paramiko 封装）
- 数据采集（`vpc-show.sh`）继续走 SSH
- planned_config 序列存 List[CLI 文本]（不是 XML），回到原 sdn-vpc-device-templates 的设计
- 架构原则 v3.1+ 修订："NETCONF 优先；不支持 NETCONF 的业务走 SSH CLI（如 H3C V7 L2vpn）"
- **业务执行仍走 backend**（不绕过 ops-toolkit），只是 L2vpn 部分走 SSH 不走 NETCONF
- **影响**：T1-T7 重新拆解（不需要 schema 化 XML），T0.5 仍可保留（unit 拆分），T3-T5 重写为"CLI 文本序列"，T6 重写 executor 走 paramiko

#### 方案 B：换设备
- 等 v3.0.1 拿到支持 NETCONF L2vpn 的 H3C 设备（如 v9 / v10）再继续
- v3.0 暂不实现 L2vpn/VXLAN/VSI 业务下发（只做 L3vpn/port binding）
- **影响**：v3.0 范围大幅缩减

#### 方案 C：维持原则，承认 H3C V7 限制
- v3.0 标注 H3C V7 L2vpn **不在 v3.0 范围**
- 只做 L3vpn（vrf）+ 接口 + port binding（v2.4 接口改造）
- **影响**：v3.0 范围大幅缩减

### 设备脏数据自查

T1.5 探针完成时 .5 状态：`<network-instances>` 空、`<L3vpn>` 空，**无任何残留**（vpc9999 探针历史也已被 mgt-only 探针前的 SSH 清扫过）。

---

## T1.6 终极验证（2026-07-11，应用户 review "拉参考机 XML"）：强证据指向 H3C V7 S6850 L2vpn 未通过 NETCONF 暴露

> **用户反馈**：之前都是手写 XML 探针（11 组全失败）。能不能直接拉**已配 L2vpn 业务**的设备（如 .2 / .3 参考机）**完整 running config XML**，看真实业务在 XML 里怎么序列化，反推 wrapper 写法？

### 验证 1: .5 完整 running config（不传 filter）—— 顶层只有 5 个 wrapper

```python
r = m.get_config(source="running")  # 不传 filter
```

lxml 解析结果（**NETCONF 顶层 wrapper 全集**）：

| Wrapper | Namespace | 模型 |
|---|---|---|
| `<bgp>` | `urn:ietf:params:xml:ns:yang:ietf-bgp` | IETF 标准 |
| `<network-instances>` | `urn:ietf:params:xml:ns:yang:ietf-network-instance` | IETF 标准 |
| `<routing>` | `urn:ietf:params:xml:ns:yang:ietf-routing` | IETF 标准 |
| `<bgp>` | `http://openconfig.net/yang/bgp` | OpenConfig |
| `<network-instances>` | `http://openconfig.net/yang/network-instance` | OpenConfig |

**结论**：H3C V7 S6850 NETCONF running config **顶层只有 5 个 wrapper**，**完全没有** `L2vpn` / `L2VPN` / `EVPN` / `VXLAN` / `VsiInterface` / `VSIs`。

### 验证 2: `.5` 上有真实用户配的 VSI `vpc_test_probe`（vxlan 20000, evpn encapsulation vxlan）—— NETCONF get-config 拉不到

```bash
# SSH display 看到（CLI 文本）
vsi vpc_test_probe
 vxlan 20000
 evpn encapsulation vxlan
```

但 NETCONF 拉全部 21996 字符的 running config 中**完全找不到** `vpc_test_probe`：

```
vpc_test_probe NOT in NETCONF running config (但 SSH display 看到有)
```

### 验证 3: .2 / .3 参考机 SSH display 看真实业务 + NETCONF filter 拉不到

`.2` 上有完整用户配 VSI（`display l2vpn vsi verbose`）：

```
VSI Name: vpna
  VSI Index               : 0
  VSI State               : Up
  VXLAN ID                : 10
  Gateway Interface       : Vsi-interface 1
  ACs:
    GE1/0/2 srv1000        Up          Manual
VSI Name: vpnb
  VSI Index               : 2
  VSI State               : Up
  VXLAN ID                : 20
  Gateway Interface       : Vsi-interface 2
  ACs:
    GE1/0/3 srv2000        Up          Manual
```

`.2` `display current-configuration | begin vsi` 拉到的 L2vpn 业务 CLI 文本（**真实配置模板**）：

```h3c
vsi vpna
 gateway vsi-interface 1
 vxlan 10
 evpn encapsulation vxlan
  route-distinguisher 1:10
  vpn-target 1:10 export-extcommunity
  vpn-target 1:10 1:20 import-extcommunity
#
vsi vpnb
 gateway vsi-interface 2
 vxlan 20
 evpn encapsulation vxlan
  route-distinguisher 1:20
  vpn-target 1:20 export-extcommunity
  vpn-target 1:10 1:20 import-extcommunity
#
interface GigabitEthernet1/0/2
 port link-mode bridge
 port link-type trunk
 undo port trunk permit vlan 1
 port trunk permit vlan 100
 port trunk pvid vlan 100
 combo enable fiber
 #
 service-instance 1000
  encapsulation s-vid 100
  xconnect vsi vpna
```

`.2` NETCONF `get-config` filter 试 L2vpn/EVPN/VXLAN/VsiInterface 顶层 wrapper（`<filter><top xmlns="http://www.h3c.com/netconf/data:1.0"><X/></top></filter>`）—— **全部** `Unexpected element 'http://www.h3c.com/netconf/data:1.0':'X' under element '/rpc/get-config[1]/filter[1]/top[1]`。

### 终极结论

**当前 H3C V7 S6850 软件版本与 NETCONF datastore 视角下，L2vpn/VXLAN/EVPN/VSI 业务不存在可用的 NETCONF XML 配置闭环**：

1. ✅ NETCONF running config **顶层只有 5 个 wrapper**（BGP / network-instances / routing，IETF + OpenConfig），**无** L2vpn
2. ✅ 已有 L2vpn 业务（.2/.3/.5 上的 vpna/vpnb/vpc_test_probe）在 NETCONF get-config 中**完全找不到**（SSH display 能看到）
3. ✅ 之前 T1.5 探针 11 组 edit-config 组合全失败
4. ✅ 系统前提已就绪（system-working-mode standard + l2vpn enable + BGP EVPN AF）
5. ✅ 真实业务配置**只能**通过 SSH `display current-configuration` 拉，**是 CLI 文本**（不是 XML）

**没有继续盲目"反推 XML 模板"这条工程路径**——至少在当前设备与当前 NETCONF 能力下，真实 L2vpn 业务没有出现在 `get-config source="running"` 返回的配置树里，已知 wrapper/filter/edit-config 探针也无法到达该业务。

**业务下发**只能走 **SSH CLI（paramiko 封装在 backend 服务内）**。架构原则修订：
- v3.0: H3C V7 L2vpn/VXLAN/EVPN/VSI 业务走 **SSH CLI**（planned_config 存 List[CLI 文本]）
- v3.1+: 若升级到支持 NETCONF L2vpn 的 H3C 设备型号，可平滑切回 NETCONF 路径（planned_config 序列化格式可重写）

**业务执行仍走 backend**（不绕过 ops-toolkit），只是 L2vpn 部分走 SSH 不走 NETCONF。

---

## T1.12 RESTful/gRPC/Ansible 路径排除（2026-07-11，应用户 "RESTful/Ansible/gRPC" 建议）

> **用户反馈**：除了 SSH CLI，还应该评估 RESTful / Ansible+RESTful / gRPC / 继续 NETCONF 等路径。提出"H3C 设备端官方支持 RESTful（白皮书 2.1 节）和 gRPC（白皮书 2.8 节）"。

> **重要前提**：本节评估在 **T1.11 已验证 CLI-over-NETCONF 可写 L2vpn/VSI/VXLAN** 之后——CLI-over-NETCONF（走 830 端口 + H3C `<CLI><Configuration>` 扩展）是 v3.0 业务下发的**主选通道**（不是 SSH 22 CLI）。

### A. .5 设备端口实地点对点验证

| 端口 | 状态 | 服务 |
|---|---|---|
| 22 | **OPEN** | SSH |
| 830 | **OPEN** | NETCONF（含 CLI-over-NETCONF 扩展） |
| 80, 443, 8080, 8443 | **CLOSED** | 标准 HTTP/HTTPS — RESTful 默认关 |
| 30000 | **CLOSED** | H3C SeerEngine-DC RESTful — 默认关 |
| 50051, 50052, 9339 | **CLOSED** | gRPC — 默认关 |

**事实**：H3C V7 S6850 **默认配置下**只开 SSH (22) + NETCONF (830)。RESTful/gRPC **需要 device 端手动 enable**（`restful enable` / `grpc enable` + 配认证 + 配证书）。

### B. 5 条路径的评估（T1.11 后）

| 路径 | 设备端能力 | .5 现状 | 实现成本 | 项目适配性 | 价值 |
|---|---|---|---|---|---|
| **NETCONF schema 化 XML**（L3vpn 用） | H3C 支持 | ✅ 已开 | 0 | ✅ 已闭环 | L3vpn OK / L2vpn schema 存在但 RPC 不可达（T1.7-T1.9）|
| **CLI-over-NETCONF**（L2vpn 用，**T1.11 已验证可写**） | H3C `<CLI><Configuration>` 扩展 | ✅ 已开 830 | 0（ncclient 已封装）| ✅ ncclient 已封装 | **L2vpn/VSI/VXLAN 业务主选通道** |
| **SSH CLI 22**（fallback） | H3C 支持 | ✅ 已开 | 0 | ✅ paramiko 已封装 | CLI-over-NETCONF 不可用时的 fallback |
| **RESTful** | H3C 支持（需 enable）| ❌ 默认关 | 设备 enable + 自研 H3C 私有 RESTful 客户端 | H3C 私有 API，**不跨厂商** | 对 v3.0 价值有限（CLI-over-NETCONF 已能写）|
| **Ansible + RESTful** | H3C 官方 Plug-In 2024-03 | ❌ 默认关 | **重型引擎**（Ansible + inventory + playbook + 整套 modules）+ H3C 官方 module 与 .5 软件版本兼容性未验证 | 对**个人自研项目过重** | 业界主流是事实但与项目规模不匹配 |
| **gRPC** | H3C 支持（需 enable）| ❌ 默认关 | 设备 enable + 自研 Protobuf stub（H3C 无现成 stub） | 类型安全但 stub 自研工作量大 | 性能优势对 SDN 业务非关键（CLI-over-NETCONF 已能写）|

### C. 关键澄清

1. **h3c-netctrl 是个人自研项目，不是紫光云**——"紫光云 Ansible 虚机"、"紫光云 02 文档"、"SeerEngine-DC" 等不适用本项目
2. **RESTful/gRPC/Ansible 都被 T1.11 验证过的 CLI-over-NETCONF 替代**——CLI-over-NETCONF **走 NETCONF 端口 830**（统一通道），**用 H3C 私有 CLI 文本**（受 H3C datastore 支持），**已经在 .177 真机验证可写 L2vpn/VSI/VXLAN 并可回滚**
3. **RESTful/gRPC 启用也未必能下发 L2vpn**——H3C 设备内部 datastore 本身就不暴露 L2vpn 业务，RESTful/gRPC **也**会面对类似限制（待验证）
4. **后端项目已有依赖**：paramiko (SSH 22 fallback) + ncclient (NETCONF 830) + httpx (内部 container REST)。**没有** RESTful 设备客户端、gRPC stub、Ansible module
5. **T1.11 关键优势**：
   - 走统一 NETCONF 端口 830（业务一致性）
   - 用 ncclient（已封装 NETCONF）
   - 不需要 paramiko SSH 22 直连
   - 已在 .177 真机最小可回滚闭环

### D. 项目级最终推荐（T1.11 修订）

**业务下发通道：NETCONF (830) 优先；schema 化不可达走 CLI-over-NETCONF；都不可达才走 SSH 22 fallback**：

- **L3vpn/VRF 业务**：NETCONF schema 化 XML（v2.4 已闭环，业界标准，跨厂商）
- **L2vpn/VSI/VXLAN/EPN 业务**：**CLI-over-NETCONF**（H3C `<CLI><Configuration>` 扩展，**T1.11 在 .177 真机验证可写**）
- **SSH 22 CLI**：**fallback**（CLI-over-NETCONF 不可用时）
- **RESTful/gRPC/Ansible**：**不投入**——成本高、风险高、价值低（CLI-over-NETCONF 已能写）

**架构原则 v3.0 修订**（T1.11 后）：
- 业务下发**走 NETCONF 端口 830**（统一通道）
- 业务 payload 优先 schema 化 XML（跨厂商）
- H3C 私有业务（schema 不可达）走 **CLI-over-NETCONF**（H3C 扩展）
- SSH 22 仅作 fallback
- 业务执行**必须**走 backend 服务（不绕过 ops-toolkit 容器）
- v3.1+ 若升级到支持 NETCONF L2vpn schema 化 edit-config 的 H3C 设备型号，可平滑切回纯 schema 化路径

### E. T1.12b display running-config 二次确认（2026-07-11）

> **强证据补强**：T1.12 端口扫描仅证明"端口未开"，但服务是否需要 enable 才能开端口（vs 端口被防火墙 block）需要从设备 running config 二次确认。本节通过 ops-toolkit `paramiko-batch-exec.sh` 走 SSH 22（默认 .env 凭据自动注入）拉 .5 设备当前 running config 中 restful/grpc/telemetry/gNMI/openflow 启用状态。

**探针命令**（统一在一个 SSH 会话）：

```bash
docker exec h3c-netctrl-ops-toolkit paramiko-batch-exec.sh \
  --device leaf-04 \
  --commands \
    "display current-configuration | include restful" \
    "display current-configuration | include grpc" \
    "display current-configuration | include telemetry" \
    "display current-configuration | include gNMI" \
    "display current-configuration | include openflow" \
  --output-format text
```

**结果**（5/5 成功，总耗时 3373ms）：

| 命令 | 设备响应 | 结论 |
|---|---|---|
| `display ... \| include restful` | 空（无匹配行） | **RESTful 未启用** |
| `display ... \| include grpc` | 空 | **gRPC 未启用** |
| `display ... \| include telemetry` | 空 | **telemetry 未启用** |
| `display ... \| include gNMI` | 空 | **gNMI 未启用** |
| `display ... \| include openflow` | 空 | **OpenFlow 未启用** |

**对比 T1.12 端口扫描结论**：

| 证据维度 | T1.12 端口扫描 | T1.12b display running-config | 交叉验证 |
|---|---|---|---|
| RESTful | 端口 80/443/30000/8080/8443 全部 CLOSED | `display ... \| include restful` 无匹配 | ✅ 双向证实**未启用** |
| gRPC | 端口 50051/50052/9339 全部 CLOSED | `display ... \| include grpc` 无匹配 | ✅ 双向证实**未启用** |
| telemetry | 端口 9339 CLOSED | `display ... \| include telemetry` 无匹配 | ✅ 双向证实**未启用** |
| gNMI | 端口 57400 CLOSED | `display ... \| include gNMI` 无匹配 | ✅ 双向证实**未启用** |
| OpenFlow | — | `display ... \| include openflow` 无匹配 | ✅ 证实**未启用** |

**最终结论**（T1.12b 后，证据链完整）：

1. **RESTful 路径出局**：.5 设备**服务未启用** + 端口未开 → 任何 RESTful 方案都需要先 `restful enable` + 配证书 + 配认证 → 增加 v3.0 业务复杂度，且 `.5/.6` 是测试设备不应被破坏性改配置
2. **Ansible + RESTful 出局**：RESTful 不可用 + Ansible 引擎对个人项目过重
3. **gRPC 路径出局**：.5 设备**服务未启用** + 端口未开 → 同 RESTful，需 `grpc enable`
4. **H3C schema 化 NETCONF**：L3vpn 可达（v2.4 已闭环），L2vpn/VXLAN/EVPN/VSI 不可达（T1-T1.11 实证）
5. **唯一可行的下发通道**：**CLI-over-NETCONF**（走 NETCONF 830 端口已开 + H3C `<CLI><Configuration>` 扩展 + ncclient 已封装 + T1.11 在 .177 真机验证可写 + 串行单跑 + display 校验 + 显式 undo 清理）

**`requirements.txt` 现状**（T1.12b 时点）：
- 已有：paramiko / ncclient / httpx
- 没有：RESTful 客户端（requests/grpcio/ansible）— 后端无任何 4 条候选路径的客户端依赖

**业务下发通道最终方案**（T1.12b 落地）：

| 业务类型 | 下发通道 | 实现依赖 |
|---|---|---|
| L3vpn / VRF / RD / RT | **NETCONF schema 化 XML**（`<top><L3vpn>...`） | ncclient（已封装）|
| L2vpn / VSI / VXLAN / EVPN | **CLI-over-NETCONF**（`<CLI><Configuration>` 扩展） | ncclient（**新增 `send_cli()` 方法**）|
| SSH 22 CLI | **fallback** | paramiko（已封装）|
| RESTful / gRPC / Ansible | **不投入** | — |

---

## T1.13 enable 命令探针（2026-07-11，应用户授权"先试试 enable 再决定"）

> **重要前提**：T1.12 端口扫描 + T1.12b display running-config 双向证实 .5 设备 RESTful/gRPC/telemetry/gNMI/OpenFlow **未启用**。但用户认为"也许只是默认没开，enable 一下就能开"——本节应用户授权在 .5 设备上做 enable 命令实测。
>
> **预期**：如果 enable 命令被接受 → RESTful/gRPC 路径"启用"出局（端口立即 OPEN），可走 R2-R5 探针 API；如果 enable 命令被设备拒绝（`% Unrecognized command`）→ **设备平台/版本根本不支持**，T1.12b 结论强化为"终态"。

### A. SSH session 准备

```bash
docker exec h3c-netctrl-ops-toolkit paramiko-batch-exec.sh \
  --device leaf-04 \
  --commands "system-view" "display this" \
  --output-format text
```

**结果**：
- `system-view` → `System View: return to User View with Ctrl+Z.`（进入 system-view 成功）
- `display this` → 完整 running-config 视图：
  - `system-working-mode standard` ✅
  - `l2vpn enable` ✅
  - `ssh server enable` ✅
  - `netconf ssh server enable` ✅
  - **无 `restful enable` / `http enable` / `https enable` / `grpc enable`**（T1.12b 结论二次证实）

### B. RESTful enable 命令综合探针

```bash
docker exec h3c-netctrl-ops-toolkit paramiko-batch-exec.sh \
  --device leaf-04 \
  --commands \
    "http ?" \
    "ip http ?" \
    "web-management ?" \
    "restful http enable" \
    "ip http enable" \
    "http enable" \
  --output-format text
```

**结果**（6/6 全部失败）：

| 命令 | 设备响应 | 结论 |
|---|---|---|
| `http ?` | `% Unrecognized command found at '^' position.` | **平台不支持** |
| `ip http ?` | `% Unrecognized command` | **平台不支持** |
| `web-management ?` | `% Unrecognized command` | **平台不支持** |
| `restful http enable` | `% Unrecognized command` | **平台不支持**（help 列出但执行不识别）|
| `ip http enable` | `% Unrecognized command` | **平台不支持** |
| `http enable` | `% Unrecognized command` | **平台不支持** |

**关键观察**：`restful ?` 在 system-view 下 help 列出 `http`/`https` 子命令，但 `restful http enable` 实际执行报 Unrecognized——这是 H3C 设备的常见行为：help 列出所有**已注册**的命令（即使平台 license 禁用），实际执行时平台/license 验证失败。

### C. gRPC / telemetry / gNMI / OpenFlow enable 命令综合探针

```bash
docker exec h3c-netctrl-ops-toolkit paramiko-batch-exec.sh \
  --device leaf-04 \
  --commands \
    "grpc ?" \
    "grpc enable" \
    "telemetry ?" \
    "gnmi ?" \
    "gnxi ?" \
    "openflow ?" \
  --output-format text
```

**结果**（6/6 全部失败）：

| 命令 | 设备响应 | 结论 |
|---|---|---|
| `grpc ?` | `% Unrecognized command` | **平台不支持** |
| `grpc enable` | `% Unrecognized command` | **平台不支持** |
| `telemetry ?` | `% Unrecognized command` | **平台不支持** |
| `gnmi ?` | `% Unrecognized command` | **平台不支持** |
| `gnxi ?` | `% Unrecognized command` | **平台不支持** |
| `openflow ?` | `% Unrecognized command` | **平台不支持** |

### D. 设备无残留（enable 全部失败，无需 undo 清理）

> **关键保障**：因为 12 个候选 enable 命令**全部** Unrecognized，**没有任何 enable 命令实际生效**——不需要 undo 清理。
>
> 验证：第二次 `display current-configuration | include restful` 仍返回空（与 T1.12b 一致）。

### E. T1.13 错误结论（已被 T1.13b 推翻）

> **T1.13 错误根因**：B 节探针失败是因为 SSH batch 在 user-view 下跑 `restful http enable` —— `restful` 是 **system-view 命令**，user-view 下不可用。我探针时**未先 system-view**，导致所有 `restful *` 命令被设备当 Unrecognized。`http ?` / `ip http ?` / `web-management ?` 三个非 `restful` 顶层命令也失败，是因为这台设备**确实**没有这 3 个顶层命令（用 `restful http` / `restful https` 才对）。
>
> **T1.13 错误传播**：错误结论写进了 project_memory.md（"RESTful/gRPC 平台/license 根本不支持 enable"）——**这条结论是错的**，T1.13b 探针推翻。

### F. T1.13b 真实能力验证（2026-07-13，应用户手测后）

> **触发**：用户亲上 .5 设备 console，手动在 system-view 下 `restful https enable` → **成功**。证明 T1.13 探针错误，需重新评估。

#### 1. enable 命令真实可达

```
[SWC]restful ?
   http   Use HTTP as the transport protocol
   https  Use HTTPS as the transport protocol

[SWC]restful https ?
   enable             Enable RESTful
   port               Specify the RESTful service port
   ssl-server-policy  Specify an SSL server policy for HTTPS access control

[SWC]restful https enable
[SWC]dis this | in res
  irf mac-address persistent timer
  restful https enable
[SWC]
```

> **enable 命令是 system-view 下的合法命令，T1.13 探针时未进入 system-view 导致全失败**。T1.13 结论 "12 个候选 enable 命令全 Unrecognized" 是探针方法错误，不是平台能力问题。

#### 2. RESTful 服务端口实测（80 / 443）

```bash
# 端口扫描（17 端口）
for port in 80 443 50051 50052 830 57400 9339 8080 8443 6030 6031 3015 3016 30000 40465 4789 4790; do
  echo > /dev/tcp/192.168.100.5/$port 2>/dev/null && echo "$port: OPEN" || echo "$port: closed"
done
```

**结果**：
- `80 OPEN` ✅ HTTP RESTful
- `443 OPEN` ✅ HTTPS RESTful
- `830 OPEN` ✅ NETCONF SSH
- 50051/50052/30000/40465/4789/4790 等其他端口全 closed

#### 3. token 认证实测

```bash
# HTTP 端点
curl -k -u "python:Admin123!@#" -X POST -H "Content-Type: application/json" \
  http://192.168.100.5/api/v1/tokens
# → HTTP/1.1 201 Created
#   {"token-id":"4000031782244c35b5a18e2e8fde0b859ffa",
#    "link":"http://192.168.100.5/api/v1/tokens/...",
#    "expiry-time":"01:18:50"}

# HTTPS 端点（不工作，401）
curl -k -u "python:Admin123!@#" -X POST -H "Content-Type: application/json" \
  https://192.168.100.5/api/v1/tokens
# → HTTP/1.1 401 Unauthorized
```

**token 头部认证方式**：

| 方式 | 结果 |
|---|---|
| `Authorization: Bearer <token>` | 401 |
| `X-Auth-Token: <token>` | **认证通过**（200/404，无 401）|

> **H3C V7 S6850 RESTful 用 `X-Auth-Token` 头，不是 `Authorization: Bearer` 标准**。这是厂商私有扩展。

#### 4. 业务 API 端点实测（关键）

> 用 `X-Auth-Token` 头认证后，探针 14 个业务路径：

| 路径 | HTTP code | 说明 |
|---|---|---|
| `GET /` | 404 | 根路径无 |
| `GET /api` | 404 | 旧 API 路径无 |
| `GET /api/v1` | 301 → `/api/v1/` | 重定向 |
| `GET /api/v1/` | 404 `Path not found` | 根 API 不存在 |
| `GET /api/v1/network-instances` | 404 | OpenConfig 模型无 |
| `GET /api/v1/l2vpn` / `/vsi` / `/evpn` | 404 | L2vpn 业务 API 不存在 |
| `GET /api/v1/vxlan` / `/vxlans` | 404 | VXLAN 业务 API 不存在 |
| `GET /api/v1/interfaces` / `/system` / `/config` | 404 | 基础 API 不存在 |

> **关键发现**：H3C V7 S6850（软件版本 R6555）RESTful 服务**只提供 `/api/v1/tokens` 认证端点，**没有提供任何业务 API 端点**（VSI/VXLAN/EVPN/network-instances/interfaces/config 全 404）。

#### 5. gRPC / telemetry / gNMI / openflow 验证（仍无效）

`display current-configuration | include grpc` / `telemetry` / `gNMI` / `openflow` —— **全空**。

SSH 探针 `grpc ?` / `grpc enable` / `telemetry ?` / `gnmi ?` / `openflow ?` —— 仍全 Unrecognized（这部分 T1.13 结论正确：这些协议在这台设备上**确实**无 enable 命令）。

#### 6. 设备残留

用户手测后 .5 设备有 2 条 enable 命令生效：
- `restful http enable`（用户之前 enable 的）
- `restful https enable`（T1.13b 新 enable 的）

> **下一步**：T1.13b 探针完成 → undo 清理（`undo restful http enable` + `undo restful https enable`），设备回到 T1.13 之前的初始态。

### G. T1.13b 终态结论（4 维证据链）

| 证据维度 | 数量 | 结论 |
|---|---|---|
| enable 命令实测（T1.13b） | 2 个命令成功（`restful http/https enable`）| **RESTful enable 实际可达**——T1.13 探针错误 |
| 端口扫描（T1.13b） | 80/443/830 OPEN，其他 14 端口 CLOSED | RESTful HTTP/HTTPS 服务**在跑** |
| 业务 API 端点实测（T1.13b） | 14 个路径全 404（含 OpenConfig/L2vpn/VXLAN/EVPN/interfaces）| **H3C V7 S6850 RESTful 只提供 token 端点，无业务 API** |
| gRPC/telemetry/gNMI/openflow enable | 6 个命令全 Unrecognized + running-config 全空 | 这些协议在 .5 设备上**确实无 enable 命令** |

### H. 4 条业务路径最终评估（修正 T1.13 错误）

| 路径 | 评估 | 否决原因 |
|---|---|---|
| **RESTful API** | ❌ **否** | H3C V7 S6850 RESTful 服务**能 enable + token 认证 OK**，但**完全没有业务 API 端点**（VSI/VXLAN/EPN 全 404）。不可能走通。 |
| **Ansible + RESTful** | ❌ **否** | H3C 官方 Plug-In 2024-03 依赖 RESTful 业务 API——H3C V7 S6850 不提供，业务 API 404，Ansible 模块无可调。 |
| **gRPC** | ❌ **否** | 50051/50052 端口 closed + enable 命令 Unrecognized + running-config 空。H3C V7 S6850 不支持 gRPC。 |
| **H3C schema 化 NETCONF** | △ **部分** | L3vpn/VRF/RD/RT 业务**可达**（v2.4 验证）；L2vpn/VSI/VXLAN/EVPN 业务**不可达**（T1 全部 11 组探针失败）。 |

### I. v3.0 业务下发通道最终方案（T1.13b 强化版）

> **业务下发通道最终方案**：

| 业务类型 | 下发通道 | 实现依赖 | 状态 |
|---|---|---|---|
| **L3vpn / VRF / RD / RT** | **NETCONF schema 化 XML** | ncclient（已封装）| ✅ 验证通过（v2.4 复用）|
| **L2vpn / VSI / VXLAN / EVPN** | **CLI-over-NETCONF** | ncclient 新增 `send_cli()` 方法 | ✅ T1.11 在 .177 验证可写 |
| **SSH 22 CLI** | **fallback** | paramiko（已封装）| ✅ fallback |
| RESTful / gRPC / Ansible | **不投入**（T1.13b 业务 API 不存在 + gRPC 平台不支持）| — | ❌ 终态否决 |

**架构原则 v3.0 终态**（T1.13b 修订）：
- 业务下发**走 NETCONF 端口 830**（统一通道）
- 业务 payload 优先 schema 化 XML（跨厂商）
- H3C 私有业务（schema 不可达）走 **CLI-over-NETCONF**（H3C 扩展）
- SSH 22 仅作 fallback
- 业务执行**必须**走 backend 服务（不绕过 ops-toolkit 容器）
- **RESTful / gRPC / Ansible 路径在 .5 设备上不可能走通**：
  - RESTful：H3C V7 S6850 R6555 RESTful 服务只提供 token 端点，无业务 API（不是 enable 问题）
  - gRPC：平台无 enable 命令（enable 确实不可达）
  - Ansible+RESTful：依赖 RESTful 业务 API，404 不可用
- v3.1+ 若升级到支持 RESTful/gRPC 的 H3C 设备型号，可重评估

### J. project_memory.md 同步修正

> **T1.13 错误结论需从 project_memory.md 移除/修订**：
> - 移除"RESTful/gRPC 平台/license 根本不支持 enable"——错。RESTful enable 实际可达。
> - 改为"H3C V7 S6850 RESTful 服务能 enable + token 认证 OK，但**没有业务 API 端点**；gRPC 平台确实不支持 enable"。
> - 这条 lessons learned 也需要新增："探针 enable 类命令时必须 system-view，否则结果不可信"。

---

# T1 详查汇总（2026-07-11 累计）

> 本节汇总 T1.7-T1.11 的累计结论（system 自动累计的 session 历史）。这些章节按时间顺序覆盖了 4 轮扩展复核，最终落地在 T1.11 的 CLI-over-NETCONF 验证。

---

## T1.8 无写验证（2026-07-11）：NETCONF validate 也拒绝 L2VPN/VXLAN 入口

> 目的：在不写设备配置的前提下，用设备声明支持的 `:validate:1.0` / `:validate:1.1` 能力验证 XML 结构是否被配置校验器接受。

`.5` server capabilities 包含：

```text
urn:ietf:params:netconf:capability:validate:1.0
urn:ietf:params:netconf:capability:validate:1.1
urn:ietf:params:netconf:capability:writable-running:1.0
urn:ietf:params:netconf:capability:rollback-on-error:1.0
```

无 `candidate` capability。

### validate 测试 1：H3C-l2vpn-config 真实路径

```xml
<validate xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <source>
    <config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
      <top xmlns="http://www.h3c.com/netconf/config:1.0">
        <L2VPN>
          <VSIs>
            <VSI>
              <VsiName>vpc_xml_probe</VsiName>
            </VSI>
          </VSIs>
        </L2VPN>
      </top>
    </config>
  </source>
</validate>
```

结果：

```text
Unexpected element 'http://www.h3c.com/netconf/config:1.0':'L2VPN'
under element '/rpc/validate[1]/source[1]/config[1]/top[1]
```

`<VsiInterfaceID>` 补充字段、去掉 `<top>`、改用 `data:1.0` namespace、改用 capability URI namespace（`config:1.0-L2VPN?module=...`）均失败。

### validate 测试 2：H3C-vxlan-config 真实路径

```xml
<top xmlns="http://www.h3c.com/netconf/config:1.0">
  <VXLAN>
    <VXLANs>
      <Vxlan>
        <VxlanID>20999</VxlanID>
        <VsiName>vpc_xml_probe</VsiName>
      </Vxlan>
    </VXLANs>
  </VXLAN>
</top>
```

结果同样失败：

```text
Unexpected element 'http://www.h3c.com/netconf/config:1.0':'VXLAN'
under element '/rpc/validate[1]/source[1]/config[1]/top[1]
```

### T1.8 结论

1. 这不是 `get-config` filter 的单点问题；`validate` 校验器也拒绝当前 `L2VPN` / `VXLAN` 配置入口。
2. YANG schema 存在，但 schema identifier 与当前 `<top>` 配置树入口之间缺少仍未确认的 H3C XML API 映射。
3. 在没有 H3C XML API 入口说明前，直接做 `edit-config` 写探针大概率仍会报同类 `Unexpected element`，但只有受控写探针能最终确认。
4. 工程实现建议维持：v3.0 如需按现有设备推进，L2vpn/VXLAN/EVPN/VSI 走 backend SSH CLI；NETCONF 路径作为研究项，除非拿到 H3C XML API 映射或 validate 先通过。

---

## T1.9 扩展复核（2026-07-11）：OpenConfig、get-bulk、H3C client capability 与 CLI-over-NETCONF

> 目的：回应“OpenConfig 里有模型，S6850 又是数据中心型号，所以不应轻易判定不可做”的质疑；继续寻找可能漏掉的 H3C NETCONF 入口。

### 1. H3C schema 结构对照

拉取并对比 `H3C-l3vpn-config`、`H3C-l2vpn-config`、`H3C-vxlan-config`、`H3C-network-instances-config`：

- `H3C-l3vpn-config`：顶层 `container L3vpn`，与项目 v2.4 已验证的 `<top><L3vpn>...</L3vpn></top>` 一致。
- `H3C-l2vpn-config`：顶层 `container L2VPN`，包含 `Base/Enable`、`VSIs/VSI`、`ACs/AC`、`VSIInterfaces/Interface`、`VSIIpv4Subnets` 等，schema 不是空壳。
- `H3C-vxlan-config`：顶层 `container VXLAN`，包含 `VXLANs/Vxlan`、`EvpnVxlanEncaps/VxlanEncap`、`EvpnVxlanRTs/VxlanRT`、`VRFs/VRF` 等。
- `H3C-network-instances-config`：顶层 `network-instances/network-instance` 主要是 VRF/OSPFv3/routing 配置结构，不承载 VSI/VXLAN/EVPN 业务模型。

因此，`network-instances` 方向不能替代 `L2VPN` / `VXLAN` 模型。

### 2. validate 对照：L3vpn 与 network-instances 可达，L2VPN/VXLAN/EVPN 不可达

同一台 `.5` 设备、同一 `validate` RPC 下：

| XML | 结果 |
|---|---|
| `<top><L3vpn><L3vpnVRF><VRF><VRF>vpc_probe_l3</VRF>...` | OK |
| `<top><L3vpn/></top>` | OK |
| `<top><network-instances><network-instance><name>vpc_probe_ni</name>...` | OK |
| `<top><L2VPN><Base><Enable>true</Enable></Base></L2VPN></top>` | `Unexpected element L2VPN under top` |
| `<top><L2VPN/></top>` | `Unexpected element L2VPN under top` |
| `<top><VXLAN/></top>` | `Unexpected element VXLAN under top` |
| `<top><EVPN/></top>` | `Unexpected element EVPN under top` |

这说明 `validate` 本身可用，`<top>` 基本写法也可用；失败集中在 L2VPN/VXLAN/EVPN 模块未被当前 RPC 配置树接受。

### 3. 真实设备前提复核

通过 ops-toolkit 只读 SSH 工具确认 `.5`：

```text
display current-configuration | include l2vpn
 l2vpn enable
 address-family l2vpn evpn

display current-configuration configuration vsi
vsi vpc_test_probe
 vxlan 20000
 evpn encapsulation vxlan

display l2vpn vsi verbose
VSI Name: Auto_L3VNI3000_3
VSI Name: vpc_test_probe
```

因此不是“设备未启用 L2VPN/EVPN/VXLAN”导致 NETCONF 不可见。

### 4. OpenConfig 原生命名空间验证

`openconfig-network-instance@2020-06-20` schema 中确实包含 `L2VSI`、`L2P2P`、`endpoints`、`route-distinguisher` 等结构。

但在 `.5` 上：

- `get-config <network-instances xmlns="http://openconfig.net/yang/network-instance"/>` 只能返回 `DEFAULT-INSTANCE` 和 `mgt`，不返回真实 `vpc_test_probe` / `Auto_L3VNI3000_3`。
- `validate` 原生 OpenConfig 空实例与 `L2VSI` 实例均被拒：`Unexpected element 'http://openconfig.net/yang/network-instance':'network-instances' under ... config[1]`。
- IETF `network-instances` 也类似：只读 `get-config` 可见 `mgt`，但 `validate` 不接受写入。

结论：OpenConfig/IETF network-instance 在该设备上更像只读/部分映射视角，不能作为 v3.0 L2VNI/VSI 下发入口。

### 5. H3C `get-bulk` / `get-bulk-config` 验证

官方文档建议表类数据可用 `get-bulk` / `get-bulk-config`。实际验证：

| RPC | L3vpn | L2VPN/VXLAN/EVPN |
|---|---|---|
| `get-bulk-config` | OK | `Unexpected element ... under top` |
| `get-bulk` | 未作为关键路径 | `Unexpected element ... under top` |

因此 `get-bulk` 不是缺失入口。

### 6. H3C client capability 验证

设备 server capabilities 包含：

```text
urn:h3c:params:netconf:capability:h3c-netconf-ext:1.0
urn:h3c:params:netconf:capability:h3c-xml2cli:1.0
urn:h3c:params:netconf:capability:module-specified-namespace:1.0
urn:h3c:params:netconf:capability:not-need-top:1.0
```

临时 patch ncclient H3C handler，分别在 client hello 中加入这些扩展后复测：

- `h3c-netconf-ext`、`h3c-xml2cli`、`h3c-name2index`：L3vpn 仍 OK，但 L2VPN 仍 `Unexpected element`。
- `module-specified-namespace`：common namespace 下 L3vpn 也被拒；改用 module-specific namespace 仍不接受 L2VPN。
- `not-need-top`：common `<top>` L3vpn 被拒，no-top L2VPN 仍不接受。

结论：缺失点不是 ncclient 默认 hello 少了 H3C 扩展 capability。

### 7. CLI-over-NETCONF 可用，但它不是 schema 化 XML 入口

H3C 官方文档提供 `<CLI><Execution>...</Execution></CLI>` 扩展 RPC。`.5` 实测同一 NETCONF 会话可读到 CLI 结果：

```xml
<CLI xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <Execution>
    display current-configuration | include l2vpn
    display current-configuration configuration vsi
  </Execution>
</CLI>
```

返回：

```text
<SWC>display current-configuration | include l2vpn
 l2vpn enable
 address-family l2vpn evpn

<SWC>display current-configuration configuration vsi
vsi vpc_test_probe
 vxlan 20000
 evpn encapsulation vxlan
```

这给工程方案一个折中选项：

- 若目标是“统一走 NETCONF 连接/端口/会话”，可以研究 **CLI-over-NETCONF** 承载 CLI 命令。
- 若目标是“schema 化 YANG/XML edit-config”，目前仍未找到 L2VPN/VXLAN/EVPN 可用入口。

### T1.9 后修订结论

1. 用户质疑成立：不能说“没有 OpenConfig/YANG/XML”。H3C 与 OpenConfig schema 都确实存在。
2. 但基于 `.5` 实测，schema 存在不等于 datastore 可达；L2VPN/VXLAN/EVPN 在 `get`、`get-config`、`get-bulk`、`get-bulk-config`、`validate` 中仍不可达。
3. OpenConfig 原生命名空间目前只读可见 `DEFAULT-INSTANCE/mgt`，不能映射真实 VSI，也不能 validate L2VSI 写入。
4. 当前可确认的 NETCONF 方案只有两类：
   - **可用**：L3vpn、VLAN、Ifmgr、IPV4ADDRESS 等既有 schema 化 XML 路径。
   - **可用但非 schema 化**：H3C `<CLI><Execution>` CLI-over-NETCONF。
5. v3.0 若要快速落地 L2vpn/VXLAN/EVPN/VSI，建议把“backend SSH CLI”修订为更中性的“backend 管理的 CLI 执行器”，优先评估 **CLI-over-NETCONF** 是否可替代 SSH 22；但 PRD/架构上仍不能把它描述成 YANG/XML edit-config。

---

## T1.10 写入可行性焦点修订（2026-07-11）：能不能通过 NETCONF 扩展“写进去”

> 用户澄清：当前重点不是追问“为什么 schema 能看到”，而是判断是否可能通过这类 NETCONF/扩展通道完成配置写入。

### 1. 两种写入必须分开

| 路径 | 当前状态 | 说明 |
|---|---|---|
| YANG/XML `edit-config` | 未打通 | `L2VPN` / `VXLAN` / `EVPN` 在 validate 与 get 系列中均不可达；没有证据说明 schema 化 `edit-config` 能写入 |
| H3C CLI-over-NETCONF | 有明确可行性 | 官方提供 `<CLI><Configuration>` 配置通道；`.5` 只读验证证明可进入 system view 并执行配置视图命令 |

因此，“通过 NETCONF 写进去”是可能的，但当前可信路径不是 `edit-config <L2VPN>...</L2VPN>`，而是 H3C 扩展的 **CLI-over-NETCONF**。

### 2. `h3c-xml2cli` 的真实含义

官方命令参考说明 `netconf log xml2cli enable` 是 **NETCONF 日志的 XML-to-CLI 功能**：

- 它会把成功执行的 `<action>` / `<edit-config>` 操作转换成 CLI 命令并记录。
- 设备与客户端都支持相关 capability 时，成功的 `edit-config` 回复里可携带 `<xml2cli>`，展示 XML 对应的 CLI。
- 它不是“把 CLI 作为 XML 下发”的配置入口，也不能让不可达的 `L2VPN` schema 路径突然可写。

所以 `h3c-xml2cli` 是审计/解释能力，不是本次 L2VPN/VXLAN 写入的突破口。

### 3. CLI-over-NETCONF 配置视图只读验证

官方开发指南给出的 CLI 扩展包括：

```xml
<CLI>
  <Execution>命令行</Execution>
</CLI>
```

以及配置视图：

```xml
<CLI>
  <Configuration exec-use-channel="false|true|persist">
    命令行
  </Configuration>
</CLI>
```

`.5` 无写验证结果：

```xml
<CLI xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <Configuration exec-use-channel="false">display this</Configuration>
</CLI>
```

返回中设备自动进入 system view：

```text
<SWC>system
System View: return to User View with Ctrl+Z.
[SWC]display this
...
l2vpn enable
netconf ssh server enable
```

`exec-use-channel="true"` 与 `persist` 也可执行 `display this`；`Open-channel` / `Close-channel` 返回 `<ok/>`。

### 4. 错误处理注意点

无害错误命令验证：

```xml
<CLI>
  <Configuration exec-use-channel="false">display __codex_invalid_probe__</Configuration>
</CLI>
```

RPC 仍返回成功，但错误在 CDATA 中：

```text
[SWC]display __codex_invalid_probe__
             ^
 % Unrecognized command found at '^' position.
```

因此如果后端走 CLI-over-NETCONF，不能只看 RPC `<ok/>` 或 ncclient 是否抛异常；必须解析命令回显中的 `% ...`、`^`、`Error:` 等失败模式，并在每个配置单元后做 display 校验。

### 5. 与 gRPC 的关系

H3C gRPC 文档主要围绕 telemetry / 采样 / 订阅路径：

- 设备通过 gRPC 向采集器推送数据。
- 采样路径会引用对应模块的 NETCONF XML API 手册。
- gNMI 模式更多用于传感器组和数据采样路径。

当前未找到证据说明 S6850 的 gRPC 能直接替代 NETCONF/CLI 完成 L2VPN/VXLAN 配置下发。对 v3.0 来说，gRPC 更适合作为后续状态采集/遥测候选，不应作为 P0 配置写入路径。

### 6. 建议的最小写入探针（需用户确认后执行）

若要最终确认 CLI-over-NETCONF 写配置是否可作为 v3.0 执行通道，建议在 `.5` 或 `.6` 做一个最小、可回滚探针：

1. `display current-configuration configuration vsi | include codex_cli_probe` 确认不存在。
2. 通过 `<CLI><Configuration exec-use-channel="false">` 下发：
   ```text
   vsi codex_cli_probe
    description codex cli-over-netconf probe
    vxlan 20998
    evpn encapsulation vxlan
   quit
   ```
3. 立即用 CLI-over-NETCONF 或 ops-toolkit display 验证配置出现。
4. 立即清理：
   ```text
   undo vsi codex_cli_probe
   ```
5. 再次 display 验证不存在。

该探针不依赖 schema 化 `edit-config`；它只证明 H3C CLI-over-NETCONF 配置通道可用于 v3.0 的 backend-managed CLI executor。

### 7. `.5` 设备侧辅助能力现状

继续做无写确认：

```text
display current-configuration | include netconf
 netconf ssh server enable

display netconf service
NETCONF over SOAP over HTTP: Disabled (port 80)
NETCONF over SOAP over HTTPS: Disabled (port 832)
NETCONF over SSH: Enabled (port 830)
NETCONF over Telnet: Enabled
NETCONF over Console: Enabled
Active Sessions: 0

display current-configuration | include grpc
<empty>
display current-configuration | include gnmi
<empty>
display current-configuration | include telemetry
<empty>
```

这说明当前 `.5` 的可用远程自动化承载面主要是 NETCONF over SSH；未看到 gRPC/gNMI/telemetry 已启用。`netconf log xml2cli enable` 也未出现在 running config 中。

`save-point` 扩展只读验证：

```xml
<save-point>
  <get-commits/>
</save-point>
```

返回空 `save-point` 数据；在没有活动 save-point 时执行 `<end/>` 返回 `Current session doesn't have a save-point.`。这说明 save-point 是可用但具有会话状态的辅助能力；最小写入探针不应依赖它作为唯一回滚机制，仍应使用显式 `undo vsi codex_cli_probe` 清理并 display 验证。

---

## T1.11 授权写探针（2026-07-11）：`.177` CLI-over-NETCONF 可写 L2VPN/VSI/VXLAN

> 用户授权边界：写测试只能在 `.177` 执行。本节不触碰 `.5/.6`。

### 1. 初始状态

`.177` 是 H3C S6850 测试设备，NETCONF over SSH 开启：

```text
display netconf service
NETCONF over SSH: Enabled (port 830)
NETCONF over SOAP over HTTP: Disabled
NETCONF over SOAP over HTTPS: Disabled
```

写入前检查：

```text
display current-configuration | include l2vpn
<empty>

display current-configuration configuration vsi | include codex_cli_probe|20998
<empty>
```

说明 `.177` 初始未启用 L2VPN，且没有探针残留。

### 2. 第一次探针：未启用 L2VPN 时，VSI 配置被设备拒绝

直接通过 CLI-over-NETCONF 下发：

```text
vsi codex_cli_probe
description codex cli-over-netconf probe
vxlan 20998
evpn encapsulation vxlan
```

返回：

```text
[netops_test]vsi codex_cli_probe
The feature L2VPN has not been enabled.
[netops_test]description codex cli-over-netconf probe
             ^
 % Unrecognized command found at '^' position.
```

这证明命令确实进入了设备配置解析器；失败原因是业务前提未满足，而不是 CLI-over-NETCONF 通道不可写。

### 3. 第二次探针：临时启用 L2VPN 后写入成功

在 `.177` 上通过：

```xml
<CLI xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <Configuration exec-use-channel="false">
    l2vpn enable
    vsi codex_cli_probe
     description codex cli-over-netconf probe
     vxlan 20998
     evpn encapsulation vxlan
    quit
  </Configuration>
</CLI>
```

设备回显：

```text
[netops_test]l2vpn enable
[netops_test]vsi codex_cli_probe
[netops_test-vsi-codex_cli_probe]description codex cli-over-netconf probe
[netops_test-vsi-codex_cli_probe]vxlan 20998
[netops_test-vsi-codex_cli_probe-vxlan-20998]evpn encapsulation vxlan
[netops_test-vsi-codex_cli_probe-evpn-vxlan]quit
```

写后验证：

```text
display current-configuration | include l2vpn
 l2vpn enable

display current-configuration configuration vsi
#
vsi codex_cli_probe
 description codex cli-over-netconf probe
 vxlan 20998
 evpn encapsulation vxlan
#
return
```

### 4. 清理与恢复验证

清理命令：

```text
undo vsi codex_cli_probe
undo l2vpn enable
```

设备回显：

```text
[netops_test]undo vsi codex_cli_probe
[netops_test]undo l2vpn enable
This command will delete L2VPN globally. Continue? [Y/N]:
Stopping L2VPN process, please wait...................................Finished.
```

清理后验证：

```text
display current-configuration configuration vsi | include codex_cli_probe|20998|codex cli-over-netconf probe
<empty>

display current-configuration | include l2vpn
<empty>
```

`.177` 已恢复到探针前状态。

### T1.11 结论

1. **CLI-over-NETCONF 可写入 L2VPN/VSI/VXLAN/EVPN CLI 配置**：已经在 `.177` 完成最小可回滚闭环。
2. 这仍然不是 schema 化 `edit-config`：它使用的是 H3C `<CLI><Configuration>` 扩展，配置内容是 CLI 文本。
3. v3.0 执行器建议修订为：优先使用 backend 内 **CLI-over-NETCONF executor** 下发 L2VPN/VXLAN/EVPN/VSI；SSH 22 CLI 作为 fallback。
4. 后端必须具备：
   - 命令回显错误解析：RPC 成功不等于配置成功。
   - 每个配置单元后的 display 校验。
   - 显式 undo 清理/回滚路径。
   - 对交互提示的风险处理：本次 `undo l2vpn enable` 出现确认提示但最终完成；生产逻辑应避免高风险交互命令，或实现提示检测与白名单处理。
