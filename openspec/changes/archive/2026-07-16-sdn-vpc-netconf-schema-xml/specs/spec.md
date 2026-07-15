# sdn-vpc-netconf-schema-xml — Spec

## 目标

为 v3.0 SDN/VPC 业务的 H3C V7 设备配置下发建立**按 device platform 路由的双套 payload 架构**。

**业务问题**：
- H3C V7 L2VPN/VSI/VXLAN/EVPN 业务下发在不同 platform 上行为不同
  - LSTN 老芯片平台（.5/.177 S6850）：schema 化 NETCONF **不可达**（T1.13a/d/e 3 维证据）
  - RSTN 新芯片平台（.26 V9850）：schema 化 NETCONF **完整可写**（T1.13d 探针）
- 同一份业务逻辑（创建 VPC vpc0001）需要为两套平台分别生成配置指令
- 现行 v3.0 模板只输出单一 CLI 文本，无法满足多平台需求
- LSTN 设备 CLI-over-NETCONF 真实可用（T1.13f 推翻 T1.13a 错误结论）

## 范围

### In-Scope（本 change 实现）

1. **device.platform 识别**：根据 device.model 映射到 LSTN / RSTN / UNKNOWN
2. **H3cV7VpcCreateTemplate 双套 payload**：6 unit × 4 字段（cli + xml + undo_cli + undo_xml）
3. **H3cV7VpcDeleteTemplate / H3cV7PortBindTemplate / H3cV7PortUnbindTemplate**：同模式改双套 payload
4. **VPCConfigPlanner 适配**：从 List[{mode, command}] 改为 List[TemplateUnit]
5. **SdnDeploymentExecutor 按 device.platform 路由**：LSTN 走 CLI / RSTN 走 schema XML
6. **数据模型扩展**：Device 模型加 platform 字段（alembic 009）
7. **schema + i18n 同步**：DeviceResponse + SDN_DEVICE_PLATFORM_UNKNOWN
8. **单测覆盖**：6 unit × 4 字段 + XML 合法性 + executor 路由

### Out-of-Scope（不在本 change 范围）

1. **RESTful / gRPC / Ansible 业务路径**——5 路径评估后否决，不投入
2. **前端实现**——v3.0 边界外；unit 拆分为前端预留接口
3. **ZTP / EVE-NG 迁移工程**——v3.0 后置
4. **3 容器 split 部署业务下发**——v3.0 P0 单容器 monolith 模式跑通后扩展
5. **设备 .6 (Leaf-05) 业务下发验证**——v3.0 P0 仅 .5 验证；.6 待 RSTN 设备到位后补

## 设计决策

### ADR-109: 按 device.platform 路由通道（LSTN 走 CLI / RSTN 走 schema XML）

- 业务下发通道**不**按 software version 路由（**已被 T1.13e 证实无效**）
- 业务下发通道**不**按 device.model 路由（**S6850 R6555 与 S6850 T7064P15 行为相同**——同 LSTN 平台）
- 业务下发通道**按 device.platform 路由**（**3 维证据链证实**）

**3 维证据链**：
- T1.13a：H3C V7 探针初步失败（错因：namespace 错误，非通道错误）
- T1.13d：.26 V9850 (RSTN) schema 化 NETCONF L2VPN **完整可写**
- T1.13e：.177 S6850 (LSTN) schema 化 NETCONF L2VPN **不可达**，**与 .5 R6555 行为相同**

**T1.13f 补充**：LSTN 设备 `<Configuration>` 包裹 CLI 文本通道**真实可写**（推翻 T1.13a 错误结论）。

**根因**：H3C Comware V7 L2VPN/EVPN/VXLAN 业务 NETCONF 实现走芯片驱动，**LSTN 老芯片驱动不实现 schema 化 XML**。

### ADR-110: TemplateUnit 结构（cli_commands + xml_payloads + undo 双套）

```python
@dataclass
class TemplateUnit:
    """6 unit 之一，描述一组配置命令 + undo 反向命令

    Attributes:
        name: Unit 标识（"vsi-l2" | "evpn" | "l3vpn" | "vsi-l3" | "port-bind" | "global"）
        description: Unit 描述（中文，给前端/排错用）
        cli_commands: LSTN 走 CLI 文本（List[str]，每条 system-view 下的命令）
        xml_payloads: RSTN 走 schema 化 NETCONF XML（List[str]，每条完整 <config> XML）
        undo_cli: LSTN 走 CLI 文本反向
        undo_xml: RSTN 走 schema 化 NETCONF XML 反向
    """
    name: str
    description: str
    cli_commands: List[str]
    xml_payloads: List[str]
    undo_cli: List[str] = field(default_factory=list)
    undo_xml: List[str] = field(default_factory=list)
```

**依据**：
- 同一业务在两套设备上的"配置语言"完全不同
- 模板输出**两套**，executor 下发时**按 device.platform 选一套**
- 不简化（输出"一个 unified payload"）—— H3C V7 没有统一格式

### ADR-111: device.platform 字段（alembic 009）

- `Device.platform: Optional[str]`（默认 None）
- 业务代码不依赖 platform 字段存在性（fallback: 用 get_platform_for_model 推算）
- 数据迁移：alembic 009 幂等添加（用 insp.get_columns 守卫）
- 老数据：platform = None → executor 调 get_platform_for_model 推算

**依据**：
- model 字段已存在（Asset.model）
- platform 可由 model 推导，存 platform 是缓存/预计算
- 避免每次下发都跑 model → platform 推算

### ADR-112: VPCConfigTemplate ABC render() 改 List[TemplateUnit]

- 现 ABC: `render(context) -> List[{mode, command}]`（CLI 文本列表）
- 新 ABC: `render(context) -> List[TemplateUnit]`（结构化双套 payload）
- 兼容性：T5 executor 才会消费 TemplateUnit，T3 仅完成模板层

**依据**：
- 双套 payload 必须结构化（cli + xml + undo + metadata）
- List[dict] 无法表达"两个并行列表"（cli vs xml）
- TemplateUnit dataclass 提供类型安全和 IDE 提示

### ADR-113: 5 路径评估——RESTful / gRPC / Ansible 不投入

| 路径 | 评估 | 结论 |
|---|---|---|
| H3C schema 化 NETCONF（XML）| L3vpn 可达；L2vpn 在 RSTN 可达、LSTN 不可达 | L3vpn 用 / L2vpn 在 RSTN 用 |
| CLI-over-NETCONF（`<Configuration>` 文本）| LSTN 真实可写（T1.13f 验证）| L2vpn 在 LSTN 用 |
| RESTful API | .5 设备 token 端点可达 + 业务 API 端点全 404（T1.13b 验证）| **不投入** |
| gRPC | .5 设备 enable 命令 Unrecognized（T1.13b 验证）| **不投入** |
| Ansible + RESTful | 依赖 RESTful 业务 API 端点 | **不投入** |

**依据**：H3C V7 设备实际能力限定（v3.0 边界），投入产出比低。

## 验收标准

### 1. 模板层验证

- [ ] `H3cV7VpcCreateTemplate.render()` 返回 `List[TemplateUnit]`，长度 = 6
- [ ] 6 个 unit name ∈ {vsi-l2, evpn, l3vpn, vsi-l3, port-bind, global}（port-bind 为预留，vpc_create 不输出）
- [ ] 每个 unit 的 cli_commands 非空
- [ ] 每个 unit 的 xml_payloads 非空
- [ ] 每个 unit 的 undo_cli 非空
- [ ] 每个 unit 的 undo_xml 非空
- [ ] xml_payloads 中 namespace 正确：`http://www.h3c.com/netconf/config:1.0`
- [ ] xml_payloads 中每个 payload 是 well-formed XML（用 xml.etree 解析不报错）

### 2. Planner 层验证

- [ ] `VPCConfigPlanner.plan_vpc_create(vpc, tenant)` 返回 `List[TemplateUnit]`
- [ ] `VPCConfigPlanner.serialize(units)` 输出 JSON 字符串
- [ ] `VPCConfigPlanner.deserialize(json_str)` 还原 `List[TemplateUnit]`
- [ ] serialize → deserialize 往返一致

### 3. 数据层验证

- [ ] `Device.platform` 字段存在
- [ ] alembic 009 幂等（重跑不报错）
- [ ] `DeviceResponse` 包含 `platform: Optional[str]`
- [ ] `get_platform_for_model("S6850")` 返回 `"LSTN"`
- [ ] `get_platform_for_model("V9850-256H")` 返回 `"RSTN"`
- [ ] `get_platform_for_model("UnknownModel")` 返回 `"UNKNOWN"`

### 4. Executor 层验证（T5）

- [ ] `SdnDeploymentExecutor` 解析 planned_config 为 `List[TemplateUnit]`
- [ ] device.platform = LSTN → 每条 unit.cli_commands 走 `<Configuration>` 通道 NETCONF edit-config
- [ ] device.platform = RSTN → 每条 unit.xml_payloads 直接 NETCONF edit-config
- [ ] undo 链路：按 platform 选 undo_cli 或 undo_xml
- [ ] 失败立即停 + 错误定位（command_index + error）

### 5. 回归验证

- [ ] qa-backend **37+ 个 SDN 单测全过**（32 现有 + 5+ 新增）
- [ ] qa-backend 全量 pytest（37+ SDN + 225+ baseline = 262+ 全过）
- [ ] config 容器 `alembic current` = `009 (head)`

### 6. 设备状态验证

- [ ] .5 设备（生产测试）状态干净，无 vpc9999 / vpc_t113d_v2 残留
- [ ] .26 设备（EVE-NG 借）状态干净
- [ ] .177 设备（HCL 测试）状态干净

### 7. 真机验证（**T6 范围**，不在 T3 验收）

- [ ] .5 (LSTN) CLI-over-NETCONF 真实可写（vsi-l2 → evpn → l3vpn → vsi-l3 → global 顺序）
- [ ] .26 (RSTN) schema NETCONF 真实可写
- [ ] .5 / .26 跨平台 running-config 业务命令 union 一致
- [ ] .5 业务效果（`display current-configuration | include vpc`）验证通过
- [ ] undo 链路验证通过（.5 + .26 双向清理）

## 风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| LSTN 设备 `<Configuration>` 通道被拒（T1.13a 错误探针遗留）| 极低 | T5 executor 必须设计新通道 | T1.13f 已验证通道可写 + namespace 正确 |
| 双套 payload 维护成本高（6 unit × 4 字段 × 2 platform = 48 个字符串）| 中 | 模板易错 | 严格单测覆盖 + unit 是 V3 最小集，未来 unit 增加不增加维护成本 |
| Device.platform 字段老数据（None）执行路径慢 | 低 | executor 每次都调 get_platform_for_model | 用 lru_cache 缓存推导结果 |
| 跨设备 running-config 文本对比失败（H3C V7 内部命令顺序差异）| 中 | 验证失败 | 对比**业务命令的 union**（不论顺序），不强制 byte-to-byte 一致 |
| 5 unit 拆分的 VSI-L2 + EVPN 在 LSTN 走 CLI 时命令顺序敏感 | 中 | vsi 未建时 evpn encapsulation 失败 | 单测覆盖每个 unit 独立可下发 + undo 干净 |

## 设备使用规则

| 设备 | 平台 | 角色 | 是否参与 v3.0 业务验证 |
|---|---|---|---|
| .5 S6850 | LSTN | 生产测试（已接入生产路由 + 与 .2/.3 建 EVPN 邻居）| ✅ 主测试目标 |
| .26 V9850 | RSTN | EVE-NG 借的纯测试 | ✅ 跨平台对比 |
| .177 S6850 | LSTN | HCL 纯测试 | ❌ 不参与 v3.0 业务验证 |
| .2/.3 S6850 | LSTN | 参考机（仅读）| ❌ 仅参考配置模板 |
| .6 Leaf-05 | — | 未来 RSTN 设备 | ⏳ 待 RSTN 设备到位 |
