# sdn-device-templates Spec Deltas (sdn-vpc-device-templates)

> 本 change 在 [sdn](../../../../specs/sdn/spec.md) 之上 **ADDED**：
> 新增 sdn-device-templates spec 定义，作为 v3.0 SDN 设备配置模板的稳定规格。

---

## ADDED Requirements

### Requirement: H3C V7 S6850 设备型号白名单

`SdnDeviceAdapter.SUPPORTED_MODELS` MUST 包含：
- `S6850` / `S6850-56HF` / `S6850-54HF`

`H3cV7Adapter.supports_model(model: str)` MUST：
- 当 `model` 包含 `"S6850"` 或 `"Comware V7"` 子串时返 `True`
- 否则返 `False` 并抛 `SDN_DEVICE_MODEL_UNSUPPORTED` 错误（i18n error_key）

#### Scenario: S6850 设备通过

- **WHEN** 设备 asset.model = "S6850-56HF"
- **AND** 调用 `H3cV7Adapter.supports_model("S6850-56HF")`
- **THEN** 返 `True`

#### Scenario: 不支持的型号被拒

- **WHEN** 设备 asset.model = "Cisco Catalyst 9300"
- **AND** 调用 `H3cV7Adapter.supports_model("Cisco Catalyst 9300")`
- **THEN** 抛 `SDN_DEVICE_MODEL_UNSUPPORTED` 错误

### Requirement: VPCConfigPlanner 配置计划生成

`VPCConfigPlanner.plan_vpc_create(vpc, tenant, dry_run=False)` MUST 返 `List[ConfigCommand]`：

| # | 命令 | 模式 |
|---|---|---|
| 1 | `vsi {vsi_name}` | configure |
| 2 | `  gateway vsi-interface {vsi_interface}` | configure |
| 3 | `  vxlan {vni}` | configure |
| 4 | `  evpn encapsulation vxlan` | configure |
| 5 | `    route-distinguisher 1:{vni // 10}` | configure |
| 6 | `ip vpn-instance l3vpn` | configure |
| 7 | `  route-distinguisher 1:{tenant.l3_vni}` | configure |
| 8 | `  address-family evpn` | configure |
| 9 | `interface Vsi-interface{vsi_interface}` | configure |
| 10 | `  ip binding vpn-instance l3vpn` | configure |
| 11 | `  ip address {gateway_ip} {subnet_mask}` | configure |
| 12 | `  mac-address {gateway_mac}` | configure |
| 13 | `  l3-vni {tenant.l3_vni}` | configure |
| 14 | `vxlan tunnel mac-learning disable` | configure（一次性）|

变量替换规则：
- `vsi_name` = `f"vpc{vpc_id:04d}"`（4 位 0-pad）
- `rd` = `f"1:{vni // 10}"`（第 1 轮，跟 .2/.3 现状）
- `subnet_mask` = `ipv4_mask_from_cidr(vpc.cidr)`（如 /24 → 255.255.255.0）

`dry_run=True` MUST NOT 写 `SdnDeployment` 表。

#### Scenario: dry-run 计划生成

- **WHEN** 调用 `plan_vpc_create(vpc_mock, tenant_mock, dry_run=True)`
- **THEN** 返 14 条 ConfigCommand
- **AND** DB 中无新 SdnDeployment 记录

#### Scenario: 计划与 .2/.3 现状比对

- **WHEN** 用 .2 实际 vpc vpna 的属性（VNI=10, RD=1:10）调用 dry-run
- **THEN** 模板生成的 `vxlan 10` + `route-distinguisher 1:1`（与 1:10 一致 — .2 用 VNI/10 = 1）

### Requirement: SdnPreflight 6 项预检

`SdnPreflight.preflight_vpc_deploy(vpc, device_id)` MUST 通过 6 项检查：

| # | 检查项 | 失败时错误码 |
|---|---|---|
| 1 | 设备型号在白名单 | `SDN_DEVICE_MODEL_UNSUPPORTED` |
| 2 | 设备 status == "online" | `SDN_PREFLIGHT_FAILED`（reason: device offline）|
| 3 | VNI 在设备上未存在 | `SDN_VPC_ALREADY_EXISTS` |
| 4 | VLAN 在设备上未占用 | `SDN_VLAN_CONFLICT` |
| 5 | BGP peer 已 Established | `SDN_BGP_PEER_NOT_ESTABLISHED` |
| 6 | l3vpn vpn-instance 已存在 | `SDN_L3VPN_NOT_FOUND` |

全部通过 → 返 `PreflightResult(success=True, commands=[])`
任一失败 → 返 `PreflightResult(success=False, error_key=..., reason="...")` 立即返回

#### Scenario: 全部通过

- **WHEN** 6 项检查全部通过
- **THEN** 返 `PreflightResult(success=True)`
- **AND** VPC 可下发

#### Scenario: 设备 offline

- **WHEN** 设备 status = "offline"
- **THEN** 预检立即返 `success=False, error_key=SDN_PREFLIGHT_FAILED, reason="device offline"`

### Requirement: 端口绑定 2 种模式

`plan_port_bind(binding, vpc, mode="auto")` MUST 支持 2 种绑定模式：

**Mode 1: service-instance（EVPN 标准）**
```python
[
    "interface {interface_name}",
    "  port link-mode bridge",
    "  service-instance {binding.service_instance}",
    "    xconnect vsi {vpc.vsi_name} access",
]
```

**Mode 2: port access vlan（传统 fallback）**
```python
[
    "interface {interface_name}",
    "  port link-mode bridge",
    "  port access vlan {binding.access_vlan}",
]
```

**Mode = "auto"** 时：
- 如 `binding.service_instance` 非空 → Mode 1
- 如 `binding.service_instance` 为空 → Mode 2（用 `access_vlan`）

#### Scenario: 默认用 service-instance

- **WHEN** binding.service_instance = 1001
- **AND** 调用 `plan_port_bind(binding, vpc, mode="auto")`
- **THEN** 返 Mode 1 命令序列（4 条）

#### Scenario: fallback 到 access vlan

- **WHEN** binding.service_instance = None
- **AND** binding.access_vlan = 2
- **THEN** 返 Mode 2 命令序列（3 条）

### Requirement: ops-toolkit 3 工具

`ops-toolkit/scripts/vpc-{apply,reset,show}.sh` MUST 暴露：

| 工具 | 入参 | 功能 |
|---|---|---|
| `vpc-apply.sh` | `--deployment <id>` `--device <name>` | 读 SdnDeployment.planned_config + 下发 |
| `vpc-reset.sh` | `--vpc <id>` `--device <name>` `--force` | 删 vpc 全部配置（保留 l3vpn）|
| `vpc-show.sh` | `--vpc <id>` `--device <name>` | display l2vpn vsi + vxlan tunnel + bgp peer |

凭据 MUST 从 env (`$SSH_USER` / `$SSH_PASS` / `$DEVICE_USERNAME` / `$DEVICE_PASSWORD`) 注入，**禁止**脚本内 hardcode。

#### Scenario: vpc-apply 成功

- **WHEN** SdnDeployment.planned_config 含 14 条命令
- **AND** `vpc-apply.sh --deployment 1 --device .5`
- **THEN** 14 条命令通过 SSH 顺序下发
- **AND** SdnDeployment.status = "success"
- **AND** SdnVpc.status = "active"

#### Scenario: vpc-show 只读

- **WHEN** `vpc-show.sh --vpc 1 --device .5`
- **THEN** 执行 3 条 display 命令
- **AND** 不下发任何配置命令
- **AND** 不写 SdnDeployment

### Requirement: 不修改 .2 / .3 设备

本 change MUST：
- .2 (192.168.100.2) **只读参考**，不调用任何 write/edit 命令
- .3 (192.168.100.3) **只读参考**，不调用任何 write/edit 命令
- .5 (192.168.100.5) 可 write，但**仅在用户在场**时手动执行 `vpc-apply.sh`
- .177 (192.168.100.177) 用于开发期 dry-run 纠错

### Requirement: 凭据与安全

- 任何代码、commit message、测试数据**不**包含 `DEVICE_USERNAME` / `DEVICE_PASSWORD` / SSH 密码
- ops-toolkit 脚本凭据从 env 注入
- `vpc-apply.sh` 输出**不**打印明文命令（仅打印命令 hash / 行数）

### Requirement: 不破坏现有 L0 数据

- 本 change 不修改 `SdnTenant` / `SdnVpc` / `SdnPortBinding` / `SdnDeployment` / `SdnValidationSnapshot` 5 张表的字段
- 仅**新增**服务层 + 工具
- L0 已有 19/19 测试 MUST 继续通过
