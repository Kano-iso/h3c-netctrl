# RELEASE NOTES — v3.0.0

**版本**: v3.0.0
**日期**: 2026-07-18
**主题**: **v3.0 骨架** — SDN 业务下发通道 + 双套 payload 模板 + 跨平台真机验证
**前序**: v2.6.2 (2026-07-08)

> v3.0.0 = **大版本骨架**。v3.0 PRD 的"完整 VPC 能力 / 端口随接随入 / 分布式网关 / 状态校验闭环"等愿景**不在本次发版**——本版本只交付"骨架"（业务下发通道 + 双套 payload 模板 + 跨平台验证），子能力按新规划拆到 v3.1.1 / v3.2 / v3.3 / v3.4 大版本（详见 [PRD-V3.0.md](PRD-V3.0.md) 补充说明 + [VERSION-ROADMAP.md](VERSION-ROADMAP.md)）。
>
> **无 BREAKING SCHEMA 业务破坏** — 仅增加 `device.platform` / `sdn_deployment.unit` / `sdn_deployment.parent_deployment_id` 字段（Alembic 008/009 迁移幂等）。

---

## 1. 主题

v3.0.0 = **SDN 业务下发通道骨架**。本版本解决"SDN 业务在 H3C V7 设备（跨平台 LSTN 老芯片 / RSTN 新芯片）怎么下发"的核心问题：

1. **业务下发通道选型**：L3vpn/VRF/RD/RT 用 schema 化 NETCONF XML；L2vpn/VSI/VXLAN/EVPN 按 `device.platform` 路由（LSTN → SSH 22 + paramiko CLI / RSTN → schema 化 NETCONF）
2. **双套 payload 模板架构**：每条业务命令同时生成 CLI 命令（SSH 通道）和 XML payload（NETCONF 通道），运行时按平台动态选择
3. **跨平台真机验证**：.5 S6850 R6555（LSTN / SSH 通道） + .26 V9850 R7643P02（RSTN / NETCONF 通道），配置面 100% 一致

## 2. 关联 OpenSpec change

| change | 主题 | commit | 状态 |
|---|---|---|---|
| `sdn-vpc-netconf-schema-xml` | 业务下发通道选型 + 双套 payload 模板 + .5/.26 跨平台真机验证 | 42 | ✅ archive |
| `openspec/specs/sdn-vpc-netconf-schema-xml/spec.md` | main spec 沉淀 | 1 | ✅ |

[archive/2026-07-16-sdn-vpc-netconf-schema-xml](openspec/changes/archive/2026-07-16-sdn-vpc-netconf-schema-xml/)

## 3. 关键产出

### 3.1 业务下发通道最终定稿（T1.13a-g 多轮探针，3 维证据链证实）

| 业务类型 | 下发通道 | 适用范围 |
|---|---|---|
| **L3vpn / VRF / RD / RT** | schema 化 NETCONF XML | 所有 H3C V7 设备 |
| **L2vpn / VSI / VXLAN / EVPN** | **按 device.platform 路由** | 见下 |
| ├─ LSTN 老芯片（.5 / .177 S6850）| **SSH 22 + paramiko 跑 system-view CLI** | T1.13g 推翻 CLI-over-NETCONF（ncclient 同步 reply 不可靠）|
| └─ RSTN 新芯片（.26 V9850）| schema 化 NETCONF XML | 同 L3vpn |
| SSH 22 CLI | fallback | 同时是 LSTN 主通道 |
| RESTful / gRPC / Ansible | **不投入** | .5 业务 API 缺失 / gRPC 平台无 enable |

### 3.2 双套 payload 模板架构（5 unit × 4 字段）

`backend/app/services/templates/h3c_v7_vpc_create.py` + `h3c_v7_port_bind.py`：

```python
@dataclass
class DeploymentUnit:
    name: str                              # e.g. "vsi-l2" / "port-bind-1"
    cli_commands: List[str]                # LSTN 通道（system-view CLI）
    xml_payloads: List[ET.Element]         # RSTN 通道（schema 化 NETCONF XML）
    undo_cli: List[str]                    # 撤销 CLI
    undo_xml: List[ET.Element]             # 撤销 XML
```

**5 unit**（vpc_create）：VSI-L2 / EVPN / L3VPN / VSI-L3 / Global
**1 unit**（port_bind）：service-instance + xconnect vsi（含 `encapsulation default` 跨平台兼容）

### 3.3 跨平台真机验证（.5 LSTN/SSH + .26 RSTN/NETCONF, 2026-07-16）

- **vpc0001 业务命令 union 一致**：vsi / vxlan 20000 / evpn encapsulation vxlan / RD 1:20000
- **port_bind service-instance 1001 业务命令 union 一致**：GE1/0/4 + HGE1/0/8
- **配置面 100% 一致**（数据面 .26 受限暂不验证，符合 user 指示"只管配置面"）

## 4. 关键修复（A 方案，T8 2026-07-16）

| 修复项 | 根因 | 修复方式 |
|---|---|---|
| RD 唯一性 | 不同 VPC 间 RD 冲突 | 1:{vni} 格式 |
| `vsi-l3` unit 命令终止符 | 误用 `return` 退出 system-view，后续命令 Unrecognized | 改用 `quit` |
| MAC 地址格式 | 设备内部归一化差异 | H-H-H 格式 |
| SSH error_indicators | 漏识别业务级错误（无 `%` 前缀）| 增强识别 "The RD is used by another EVPN instance." |
| 内部 API platform 字段 | 透传丢失 | 显式传递 |
| Asset PUT / i18n error code | schema 兼容 | 修复 |
| `encapsulation default` 缺失 | .5 设备 `xconnect vsi` 报 "Incomplete command" | 模板统一加 `encapsulation default` |

## 5. 数据模型扩展

| 表 | 字段 | 类型 | 迁移 |
|---|---|---|---|
| `Device` | `platform` | `Optional[str]` | alembic 009 幂等 |
| `SdnDeployment` | `unit` | `str` | alembic 008 幂等 |
| `SdnDeployment` | `parent_deployment_id` | `Optional[int]` | alembic 008 幂等 |

## 6. 测试统计

- ✅ **73 SDN 单测全过**
- ✅ **全量 432 PASS / 3 pre-existing FAIL**（async_backup + split_integration，与本 change 无关）
- ✅ **42 commits push to origin/main**（e5b2e61..5690d60）

## 7. PRD 补充说明（重要）

按用户 2026-07-18 拍板的新规划，**v3.0 PRD-V3.0.md 写的 7 个子能力 change 不在 v3.0.0 范围**，归属如下：

| 原 sdn-* change | 归属大版本 |
|---|---|
| sdn-vpc-prd-and-model（数据模型 + PRD/Spec 定稿）| **v3.2**（VPC 验证时一起做）|
| sdn-vpc-foundation（VPC CRUD + 业务配置）| **v3.2**（VPC 全能力验证时做）|
| sdn-port-binding（端口随接随入）| **v3.2**（VPC 全能力验证时做）|
| sdn-l3vni-validation（L3VNI 状态采集）| **v3.2**（VPC 全能力验证时做）|
| sdn-gateway-fallback（集中式网关降级/恢复）| **v3.3**（剩余 VPC 能力）|
| sdn-visual-overview（前端大屏、端口矩阵）| **v3.4**（前端集中做）|
| sdn-ops-toolkit-probes（VPC/EVPN 专用探测）| **v3.4**（工具随前端）|
| sdn-etcd-coordination（轻量协调方案）| **v3.5 远期** |

详见 [PRD-V3.0.md](PRD-V3.0.md) 补充说明 + [VERSION-ROADMAP.md](VERSION-ROADMAP.md) §1 全景表。

## 8. 后续 change 计划

| Change | 范围 | 状态 |
|---|---|---|
| v3.1.0 ztp-research | ZTP 调研发版 | ✅ 已发版 |
| v3.1.1 ztp-landing | autocfg.cfg 多平台适配（.5 R6555 / .26 R7643P02 / .177 T7064P15）+ 1:1 静态 IP 池子 | ⏳ 待启动 |
| v3.1.2 ztp-auto-onboard | controller 主动 SSH 纳管 + 推业务 IP | ⏳ |
| v3.1.3 ztp-asset-sync | 资产自动可见 | ⏳ |
| v3.2 architecture-switch | 架构切 EVENG + 全 QA + VPC 全能力验证 | ⏳ |
| v3.3 vpc-remaining | 剩余 VPC 能力（端口随接随入 / L3VNI / 集中式网关）| ⏳ |
| v3.4 frontend-overview | 前端大屏 + UX | ⏳ |
| v3.5 etcd-coordination | 远期 | ⏳ 远期 |
