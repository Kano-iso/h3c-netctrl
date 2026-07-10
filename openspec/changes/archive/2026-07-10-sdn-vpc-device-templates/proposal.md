# sdn-vpc-device-templates

> **版本定位**：v3.0 第二个 change — **H3C V7 EVPN/VXLAN 设备配置模板**
> **范围**：H3C V7 CLI 模板生成、配置计划、模板渲染；**不**实际下发到设备（sdn-deploy change 负责）
> **依赖**：[sdn-vpc-model-and-foundation](../archive/2026-07-10-sdn-vpc-model-and-foundation/proposal.md)（数据骨架）

---

## Why

sdn-vpc-model-and-foundation 闭环后，v3.0 SDN 有了：
- ✅ 5 张表（tenant / vpc / port_binding / deployment / snapshot）
- ✅ 8 个 CRUD API
- ✅ 19 个单测

但**还差一个核心**：

> **当用户在前端创建一个 VPC，系统怎么知道要在 .5 设备上跑哪些 H3C V7 CLI 命令？**

v3.0 SDN 的核心价值是**让用户能像创建 VM 一样创建 VPC**，而 VPC 创建最终**必须落到设备上跑命令**。当前缺口：

1. **没有 H3C V7 命令模板** → 不知道 VPC 创建时要发哪些命令
2. **没有配置计划生成器** → 没法从 `SdnVpc` model 推导"vsi vpca / vxlan 10 / evpn ..."这种命令序列
3. **没有设备抽象层** → v3.0 唯一支持的设备型号是 H3C V7 S6850，但代码里**没有**型号检查 / 适配层
4. **没有干跑（dry-run）能力** → 不知道"如果下发会跑什么命令"，开发 / 排错困难
5. **没有 .2/.3 的参考模板** → 跨设备一致性靠人脑记忆，不可持续

**实测参考**（2026-07-09 已勘察 .2 / .3 两台参考设备）：
- .2 / .3 现状：vsi vpna / vpnb 已 Up（RD 1:10/1:20，vxlan 10/20，gateway vsi-interface 1/2）
- .2 / .3 缺：import-rt / export-rt（VSI 仍能 Up，因为 BGP 自动默认）
- .2 缺：`vxlan tunnel mac-learning disable`（.3 配了）
- .2 / .3 BGP peer → 1.1.1.1 (spine-01) Established

**结论**：模板生成器必须支持**已验证**的 H3C V7 命令序列，**不能**凭空设计。

## What Changes

### 主线 1：H3C V7 S6850 设备适配层（`SdnDeviceAdapter`）

新增 `backend/app/services/sdn_device_adapter.py`：

- 类 `SdnDeviceAdapter` 封装"型号 → 模板集"映射
- 唯一支持型号：H3C Comware V7（型号前缀 S6850 / S6850-56HF 等）
- 型号识别：`device.asset.model` 包含 "S6850" / "Comware" 关键字
- 型号不支持时返 `SDN_DEVICE_MODEL_UNSUPPORTED` 错误
- **不**直接连设备（仅做模板生成；实际下发由 sdn-deploy change）

### 主线 2：配置计划生成器（`VPCConfigPlanner`）

新增 `backend/app/services/vpc_config_planner.py`：

- `VPCConfigPlanner.plan_vpc_create(vpc: SdnVpc, tenant: SdnTenant) -> List[ConfigCommand]`
- 返回有序命令列表（vsi → vxlan → evpn → vpn-instance → vsi-interface → service-instance）
- 每条命令含 `mode: "configure"` + `command: "vsi vpca"` 字符串
- 计划可序列化（`to_json()` / `from_json()`），存入 `SdnDeployment.planned_config`
- **dry-run 模式**：`planner.plan_vpc_create(..., dry_run=True)` 仅生成不持久化

### 主线 3：H3C V7 CLI 模板集（`vpc_create_template`）

新增 `backend/app/services/templates/h3c_v7_vpc_create.py`：

- 模板常量定义（每行命令的拼装逻辑）
- 支持变量替换：`{vsi_name}` / `{vni}` / `{rd}` / `{gateway_ip}` 等
- **第 1 轮（测试）参数**（与 .2/.3 现状一致）：
  - VSI name = `f"vpc{vpc_id:04d}"`
  - RD = `f"1:{vni // 10}"`（.2/.3 现状用 1:10, 1:20）
  - 共享 l3vpn vpn-instance（不创建新 vpn-instance，**仅**绑定到 l3vpn）
  - Vsi-interface = 系统分配（vpc.vsi_interface 字段）
  - gateway_ip = vpc.gateway_ip（CIDR 末位）
  - gateway_mac = `f"00-00-00-00-{vni:04x}-01"`
- **未来（多租户）参数**（device templates change 末尾留 ADR）：
  - RD = `f"{ASN}:{vni // 10}"`（env SDN_ASN 控制）
  - 每租户一个 vpn-instance
  - import-rt/export-rt 完整配置

### 主线 4：设备配置预检

新增 `backend/app/services/sdn_preflight.py`：

- `preflight_vpc_deploy(vpc: SdnVpc, device_id: int) -> PreflightResult`
- 检查项：
  1. 设备 `asset.model` 是否在 H3C V7 支持列表
  2. 设备 `asset.status` == "online"（不能 offline 设备）
  3. 设备 vpc 是否已存在（按 vni 查重）
  4. 设备 Vlan 是否冲突（vpc.vlan_id 与设备现有 vlan 不撞）
  5. BGP peer 是否已建立（spine-01 → leaf）
  6. l3vpn vpn-instance 是否存在（如果共享模式）
- 失败 → 返 `SDN_PREFLIGHT_FAILED` + 详细 reason

### 主线 5：单测 + 集成测试

- 单元：`backend/tests/test_sdn_device_adapter.py` / `test_vpc_config_planner.py` / `test_sdn_preflight.py`
- 集成：`backend/tests/integration/test_sdn_vpc_deploy.py`（**默认 skip**，需 `--integration`）
- 集成测试目标设备：`.177` 纠错用 + `.5` 真实部署（仅手动 / 用户在场）

### 主线 6：ops-toolkit 工具

新增 `ops-toolkit/scripts/`：

- `vpc-apply.sh`：读 `SdnDeployment.planned_config` + 调 NETCONF/SSH 下发到指定设备
- `vpc-reset.sh`：删指定 VPC 的全部配置（vsi / vxlan / evpn / vpn-instance / service-instance / vsi-interface）
- `vpc-show.sh`：device 侧 display 命令 dry-run 看 vpc 状态
- 全部走 `_lib.sh` 设备别名解析、凭据 env 注入
- 文档同步更新 `docs/ops-toolkit.md`

## 不在本 change 范围（后续 change 处理）

- ❌ 实际下发到设备（NETCONF/SSH）→ `sdn-deploy` change
- ❌ 状态采集（display 命令拉回 + 解析）→ `sdn-collect` change
- ❌ 校验 / 告警 → `sdn-validate` change
- ❌ 前端 VPC 管理 UI → `sdn-frontend` change
- ❌ 多租户 vpn-instance（架构上预留，device templates change 不实现）

## 影响范围

| 类型 | 文件 |
|---|---|
| 新增 | `backend/app/services/__init__.py` |
| 新增 | `backend/app/services/sdn_device_adapter.py` |
| 新增 | `backend/app/services/vpc_config_planner.py` |
| 新增 | `backend/app/services/sdn_preflight.py` |
| 新增 | `backend/app/services/templates/__init__.py` |
| 新增 | `backend/app/services/templates/h3c_v7_vpc_create.py` |
| 新增 | `backend/tests/test_sdn_device_adapter.py` |
| 新增 | `backend/tests/test_vpc_config_planner.py` |
| 新增 | `backend/tests/test_sdn_preflight.py` |
| 修改 | `backend/app/i18n_keys.py`（追加 6 个 SDN 错误码：DEVICE_MODEL_UNSUPPORTED / PREFLIGHT_FAILED / VPC_ALREADY_EXISTS / VLAN_CONFLICT / BGP_PEER_NOT_ESTABLISHED / L3VPN_NOT_FOUND）|
| 新增 | `ops-toolkit/scripts/vpc-apply.sh` |
| 新增 | `ops-toolkit/scripts/vpc-reset.sh` |
| 新增 | `ops-toolkit/scripts/vpc-show.sh` |
| 修改 | `ops-toolkit/Dockerfile`（3 脚本 cp）|
| 修改 | `docs/ops-toolkit.md`（3 工具说明）|

## 验收标准

- [ ] `pytest backend/tests/test_sdn_device_adapter.py` 全过
- [ ] `pytest backend/tests/test_vpc_config_planner.py` 全过（dry-run 命令序列匹配 .2/.3 现状）
- [ ] `pytest backend/tests/test_sdn_preflight.py` 全过
- [ ] `pytest backend/tests/ -q` 全量通过
- [ ] dry-run 模式不产生任何 SdnDeployment 记录
- [ ] 设备型号不支持时返明确错误（不静默走默认）
- [ ] ops-toolkit 3 脚本在 .177 上 dry-run 通过
- [ ] 用户在 .5 上**手动**执行 `vpc-apply.sh` 能成功创建 vpc 模板配置
- [ ] 用户在 .5 上**手动**执行 `vpc-reset.sh` 能干净清除 vpc 全部配置
- [ ] 不修改 .2 / .3 设备（只读参考）
