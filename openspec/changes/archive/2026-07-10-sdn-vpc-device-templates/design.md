# sdn-vpc-device-templates — Design

> 配套 proposal.md，本文件回答**怎么实现**（架构 / 数据流 / 命令序列模板 / ADR）

---

## 1. 架构定位

```
v3.0 SDN 分层
├── L0 数据骨架      ✅ 已闭环 (sdn-vpc-model-and-foundation, 8 commits)
├── L1 端口绑定      → sdn-port-binding
├── L2 设备配置模板  ← 本 change (sdn-vpc-device-templates)
├── L3 配置下发      → snd-deploy
├── L4 状态采集      → sdn-collect
└── L5 可视化校验    → sdn-validate
```

L2 不下发到设备，只生成命令序列。下发由 L3 负责。

## 2. 类图（精简）

```
SdnDeviceAdapter (抽象基类)
  └── H3cV7Adapter (实现，型号 S6850 / Comware V7)
        ├── supports_model(model: str) -> bool
        └── get_template(vpc_action: str) -> VPCConfigTemplate

VPCConfigPlanner (入口)
  ├── __init__(adapter: SdnDeviceAdapter)
  ├── plan_vpc_create(vpc, tenant) -> List[ConfigCommand]
  ├── plan_vpc_delete(vpc) -> List[ConfigCommand]
  ├── plan_port_bind(binding) -> List[ConfigCommand]
  └── plan_port_unbind(binding) -> List[ConfigCommand]

SdnPreflight
  ├── check_device_model(device) -> Result
  ├── check_device_online(device) -> Result
  ├── check_vpc_not_exists(device, vpc) -> Result
  ├── check_vlan_not_conflict(device, vpc) -> Result
  ├── check_bgp_peer_established(device) -> Result
  └── check_l3vpn_exists(device) -> Result
```

## 3. H3C V7 CLI 模板（第 1 轮，与 .2/.3 现状一致）

### 3.1 VPC 创建（vpc_create_template）

输入：`SdnVpc` (id=1, vni=20000, vlan_id=2, vsi_interface=1, gateway_ip=10.0.1.1/24, gateway_mac=00-00-00-00-4e20-01, cidr=10.0.1.0/24) + `SdnTenant` (rd=100:1, l3_vni=10000)

输出（命令序列，每条 `mode: configure`）：

```python
[
    # 1. 创建 VSI
    "vsi vpc0001",
    "  gateway vsi-interface 1",
    "  vxlan 20000",
    "  evpn encapsulation vxlan",
    "    route-distinguisher 1:2000",   # 1:VNI/10
    
    # 2. 共享 l3vpn vpn-instance (第 1 轮)
    "ip vpn-instance l3vpn",
    "  route-distinguisher 1:10000",
    "  address-family evpn",
    # import-rt / export-rt 第 1 轮省略 (BGP 自动默认)
    
    # 3. 创建 Vsi-interface
    "interface Vsi-interface1",
    "  ip binding vpn-instance l3vpn",
    "  ip address 10.0.1.1 255.255.255.0",
    "  mac-address 00-00-00-00-4e20-01",
    # l3-vni 10000 绑定 (VSI l3vpn 关联)
    "  l3-vni 10000",
    
    # 4. 全局配置 (一次性, 设备级)
    "vxlan tunnel mac-learning disable",
]
```

### 3.2 VPC 删除（vpc_delete_template，反向）

```python
[
    "undo vsi vpc0001",
    "undo interface Vsi-interface1",
    # l3vpn vpn-instance 共享, 不删
    # vxlan tunnel mac-learning disable 设备级, 不删
]
```

### 3.3 端口绑定（port_bind_template）

输入：SdnPortBinding (if_index=14, access_vlan=2, service_instance=1001) + Vpc(vsi_name=vpc0001)

输出：

```python
[
    # 进入接口视图
    "interface GigabitEthernet1/0/14",
    "  port link-mode bridge",   # 确保 L2 模式
    "  service-instance 1001",
    "    xconnect vsi vpc0001 access",
]
```

注意：第 1 轮**优先 service-instance**（EVPN 标准）；如 service-instance 已被占用，fallback `port access vlan 2`（传统）。

### 3.4 端口解绑（port_unbind_template）

```python
[
    "interface GigabitEthernet1/0/14",
    "  undo service-instance 1001",
    "  undo port access vlan 2",
]
```

## 4. 关键设计决策（ADR）

### ADR-101：型号白名单硬编码

**决策**：`SdnDeviceAdapter.SUPPORTED_MODELS = ["S6850", "S6850-56HF", "S6850-54HF"]`

- **理由**：v3.0 P0 唯一支持的型号（基于现有设备清单）
- **未来**：Cisco / Huawei 适配器作为独立 adapter 类（v3.0.1+）

### ADR-102：第 1 轮省略 import-rt / export-rt

**决策**：第 1 轮不配置 import-rt / export-rt

- **理由**：.2/.3 现状就是没配，VSI 仍能 Up，BGP 默认行为可用
- **未来**：v3.0.1 多租户阶段补全

### ADR-103：VPC 名称格式 vpc{vpc_id:04d}

**决策**：4 位 0-pad（vpc0001 ~ vpc9999）

- **理由**：
  - H3C VSI name 限长 32 字符
  - vpc_id 主键唯一，不依赖 tenant/vpc name
  - 排序好（vpc0001 < vpc0002 < vpc0010）
- **替代**：`vpc_{tenant_id}_{vpc_id}` 弃用（太长）

### ADR-104：service-instance 优先，access vlan fallback

**决策**：默认 service-instance + xconnect；fallback 传统 access vlan

- **理由**：service-instance 是 EVPN 标准；access vlan 是 .5 现状（缺 service-instance 时 fallback）
- **决策表**：
  - VSI 存在 service-instance 配置 → 用 service-instance
  - VSI 不存在 service-instance → 用 access vlan

### ADR-105：dry-run 不写 SdnDeployment

**决策**：`VPCConfigPlanner.plan_vpc_create(..., dry_run=True)` **不**写数据库

- **理由**：dry-run 是开发 / 排错工具，不污染业务数据
- **未来**：可选 `dry_run=False, persist=True` 模式（L3 deploy change 用）

## 5. 边界与不做的事

| 边界 | 不做 | 留给 |
|---|---|---|
| 实际下发 | 不连 NETCONF/SSH | sdn-deploy |
| 状态采集 | 不调 display | sdn-collect |
| 校验 | 不比对预期 vs 实际 | sdn-validate |
| 端口绑定 CRUD API | 不暴露 REST 端点 | sdn-port-binding |
| 多租户 vpn-instance | 第 1 轮用共享 l3vpn | v3.0.1+ |
| 设备型号扩展 | 只支持 H3C V7 S6850 | v3.0.1+ |

## 6. 数据流

```
用户 POST /api/sdn/vpcs
  ↓
  router/sdn.py create_vpc()
  ↓
  SdnVpc created (status="pending")
  ↓ (异步 / 用户手动)
  VPCConfigPlanner.plan_vpc_create(vpc, tenant)
  ↓
  SdnAdapter.get_template("vpc_create")
  ↓
  List[ConfigCommand]
  ↓
  SdnDeployment(planned_config=json.dumps(cmds), action="create")
  ↓ (用户手动)
  ops-toolkit/vpc-apply.sh --deployment <id>
  ↓
  SSH/NETCONF 到 .5 设备下发
  ↓ (成功)
  SdnDeployment.status = "success"
  ↓
  SdnVpc.status = "active"
```

## 7. split 容器兼容

- 设备模板生成是**纯计算**，无 I/O，可在 `core` / `config` 容器内运行
- 实际下发（vpc-apply.sh）在 `ops-toolkit` 容器内执行（**不**走 sdn router）
- 数据库访问（写 SdnDeployment）在 `config` 容器

## 8. 风险与回退

| 风险 | 缓解 | 回退 |
|---|---|---|
| H3C V7 命令拼错 | dry-run + .177 纠错 | 退回旧 .5 状态（vpc-reset.sh）|
| 多 vpc 编号撞 | 靠 SdnAllocator max+1 | 手动改 vpc.vni |
| service-instance 已被占用 | fallback access vlan | 用户手动调 service_instance 字段 |
| 型号不支持 | 明确报错 | 退回当前 SD6850 测试设备 |

## 9. 测试策略

- **单测**：100% 覆盖模板拼装逻辑（mock DB / 不连设备）
- **dry-run 测试**：用 .2/.3 现状的 VSI / vxlan / evpn 配，反推模板，验证模板生成跟现状一致
- **集成测试**：默认 skip，仅用户在场手动跑
- **回退测试**：vpc-reset.sh 在 .5 跑过后，display 验证无残留
