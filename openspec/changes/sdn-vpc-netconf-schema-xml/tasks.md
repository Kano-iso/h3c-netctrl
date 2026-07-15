# sdn-vpc-netconf-schema-xml — Tasks

## 拆解原则（v3 - 应用户 2026-07-13 review 修正 + 2026-07-15 路径定稿）

**v1 拆法问题**：T1 探针 → T2 模板 → T3 executor → T4 真机验证。T2/T3 写代码时没真机反馈，错一次又一次。

**v2 拆法**：每个 task 都自带"真机小步验证"环节。但 T1-T2 探针方向错误（OpenConfig `network-instances`），走偏了。

**v3 拆法（应用户 2026-07-13 "杠上" + 借 .26 设备 + 2026-07-15 路径定稿）**：
- T1.13a-e 探针 **3 维证据链证实** H3C V7 L2VPN 业务下发按 **device platform 路由**（不是软件版本 / device model）
- T1.13f-g (隐含) 验证 LSTN 平台 `<Configuration>` 文本通道真实可用
- T3 模板改为**双套 payload**（cli_commands + xml_payloads），executor 按 device.platform 动态选
- 业务下发通道**最终定稿**（应用户 2026-07-15 验证）：
  - L3vpn/VRF/RD/RT → schema 化 NETCONF XML（v2.4 已验）
  - L2vpn/VSI/VXLAN/EVPN → **按 device platform 路由**：
    - LSTN 老平台（.5/.177 S6850）→ CLI 文本走 NETCONF `<Configuration>` 通道（T1.13 探针真实可写）
    - RSTN 新平台（.26 V9850）→ schema 化 NETCONF XML
  - SSH 22 CLI → fallback
  - RESTful / gRPC / Ansible → 不投入

## 设备角色澄清（应用户 review）

| 设备 | 平台 | 软件 | 角色 | 验证范围 |
|---|---|---|---|---|
| .5  S6850 | LSTN | R6555 | **生产测试**（已接入生产路由 + 与 .2/.3 建 EVPN 邻居）| **完整业务效果**（EVPN/ARP/路由学习）|
| .26 V9850 | RSTN | R7643P02 | EVE-NG 借的纯测试 | 配置下发 + **.5/.26 跨平台 running-config 对比** |
| .177 S6850 | LSTN | T7064P15 | HCL 纯测试（ops-toolkit 临时小命令）| ❌ **不参与 v3.0 业务验证** |
| .2/.3 S6850 | LSTN | — | 参考机（仅读）| 参考 EVPN/VXLAN/VSI 配置模板 |

## 进度总览

- [x] **T0** (2026-07-11) NETCONF 探针定位 H3C V7 schema 化入口
- [x] **T0.5** (2026-07-13) SdnDeployment 数据模型扩展：加 `unit` / `parent_deployment_id` 字段（alembic 008, 32 个 SDN 单测全过, commit `aa65dd3`）
- [x] **T1.13a** (2026-07-11) 错误格式探针（H3C 不接受 CLI 文本 + L2VPN 不在 top 子节点）
- [x] **T1.13b** (2026-07-11) RESTful API 探针（.5 设备无业务 API，全部 404）
- [x] **T1.13c** (2026-07-11) 设备 .26 RSTN 探针 + 正确 namespace（H3C 官方 h3cdassai_switch.go 结构）
- [x] **T1.13d** (2026-07-11) **设备 .26 终极探针**——schema 化 NETCONF L2VPN/VSI/VXLAN/EVPN **完整可写**（与 LSTN 设备 .5 截然相反）
- [x] **T1.13e** (2026-07-13) **设备 .177 探针**——S6850 T7064P15（LSTN）同样 **schema 化 NETCONF L2VPN 不可达**——证实真根因 = **device platform (LSTN vs RSTN) 而非软件版本**
- [x] **T1.13f** (2026-07-15) **LSTN 平台 CLI-over-NETCONF 验证**——`.5` 设备探针 `<Configuration>vsi vpc9999</Configuration>` 真实可写（undo 干净）→ 推翻 T1.13a 错误结论
- [x] **T2 前期** (2026-07-15) Device 模型加 platform + alembic 009 + schemas/i18n 同步 + sdn_device_adapter.py 加 platform 映射 + TemplateUnit 定义（未 commit）
- [x] **T1** 探针 VSI 子结构（**撤销原 v2 任务，因 T1.13a-e 已证 network-instances 不是 L2VPN 正确路径**）
- [x] **T2** 探针 Vsi-interface 子结构（**撤销原 v2 任务，因 T1.13d 在 .26 已发现完整 schema 树**）
- [x] **T3** (2026-07-15) H3cV7VpcCreateTemplate 输出双套 payload（5 unit × 4 字段）+ planner 适配 + 单测覆盖
- [x] **T4** (2026-07-15) H3cV7VpcDeleteTemplate + H3cV7PortBindTemplate + H3cV7PortUnbindTemplate 双套 payload
- [x] **T5** (2026-07-15) SdnDeploymentExecutor 改按 device.platform 选择通道（LSTN 走 CLI / RSTN 走 schema XML）
- [ ] **T6** .5/.26 真机对比验证（双套 payload running-config 一致性 + .5 业务效果验证）
- [ ] **T7** 单测补全 + .5 undo 恢复 + .5/.26 设备干净

---

## T0: 探针定位入口 ✅ (2026-07-11)

（详见 design.md §T0 探针结果）

---

## T0.5: SdnDeployment 数据模型扩展 ✅ (2026-07-13)

**目的**：unit 拆分需要数据模型支持。

**已做**：
- `backend/app/models.py`：SdnDeployment 加 `unit: str` / `parent_deployment_id: Optional[int]` 字段
- `backend/migrations/versions/008_add_sdn_deployment_unit.py`：alembic 迁移（幂等：insp.get_columns() 守卫）
- `backend/app/schemas.py`：SdnDeploymentCreate / SdnDeploymentResponse 加 unit / parent_deployment_id
- `.gitignore`：加 `backend/*_tmp.py` 防明文凭据入库
- commit `aa65dd3`（**未 push**）

**回归**：
- config 容器 `alembic current` = `008 (head)` ✓
- qa-backend **32 个 SDN 单测全过** ✓
- 3 个 FK 正确（devices.id / sdn_vpcs.id / **sdn_deployments.id** 自关联）✓

---

## T1.13a-e: H3C V7 L2VPN 业务下发能力多轮探针 ✅ (2026-07-11/13)

**目的**：定位 H3C V7 L2VPN/VSI/VXLAN/EVPN 业务 NETCONF 下发的正确路径。

**结论**（**3 维证据链**）：

| 证据维度 | 结果 |
|---|---|
| T1.13a：错误格式探针 | H3C V7 不接受 `<Configuration>` 文本子节点（LSTN 错误）|
| T1.13b：RESTful API 路径 | .5 设备 RESTful 服务能开 + token 认证 OK，**但无业务 API**（14 个路径全 404）|
| T1.13c：RSTN 正确 namespace 探针 | 按 H3C 官方 h3cdassai_switch.go 286KB 结构体 + 正确 namespace `http://www.h3c.com/netconf/config:1.0`，但 .5 设备仍 `Unexpected element 'L2VPN' under top` |
| T1.13d：.26 V9850 设备探针 | **schema 化 NETCONF L2VPN/VSI/VXLAN/EVPN 完整可写**（4/4 成功）|
| T1.13e：.177 S6850 探针 | **与 .5 相同**：schema 化 L2VPN 不可达；证实真根因 = **device platform (LSTN vs RSTN)**，不是软件版本 |

**最终定稿（2026-07-13）**：
- **device platform (LSTN 老芯片 vs RSTN 新芯片)** 决定 L2VPN NETCONF 可达性
- 同设备型号（S6850）跨平台测试，**软件版本无关**（R6555 与 T7064P15 行为相同）
- LSTN 平台（.5/.177 S6850 系列）走 **CLI 文本走 NETCONF `<Configuration>` 通道**（T1.13f 验证可写）
- RSTN 平台（.26 V9850）走 schema 化 NETCONF
- v3.0 业务下发按 **device.platform 路由**

**输出**：design.md 1949-2044 行 + AB-AG 章节完整记录

---

## T1.13f: LSTN 平台 CLI-over-NETCONF 真实可写性验证 ✅ (2026-07-15)

**目的**：推翻 T1.13a 结论——LSTN 设备 `<Configuration>` 包裹 CLI 文本是真实可写的。

**测试报文**（.5 设备，H3C V7 S6850 R6555）：
```xml
<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0">
  <top xmlns="http://www.h3c.com/netconf/config:1.0" xc:operation="create">
    <Configuration>
      vsi vpc9999
      vxlan 20000
    </Configuration>
  </top>
</config>
```

**结果**：✅ `<ok/>` 完整成功 + `display l2vpn vsi verbose` 验证 vpc9999 存在 + undo 后 `display` 无 vpc9999

**修订结论**：
- **LSTN 设备 `<Configuration>` 通道是真实可用的**（T1.13a 探针的失败是 namespace 错误，不是通道本身错误）
- 因此 **LSTN 设备 L2VPN/VSI/VXLAN/EVPN 业务下发通道 = CLI 文本走 NETCONF `<Configuration>` 通道**
- 业务下发通道按 device platform 路由：**LSTN 走 CLI / RSTN 走 schema XML**

---

## T2 前期: Device 模型 platform 字段 + adapter 双套 payload 框架 ✅ (2026-07-15)

**目的**：为 T3 模板改造做数据 + 框架准备。

**已做（未 commit）**：
- `backend/app/models.py`：Device 加 `platform: Optional[str]` 字段（已加 index）
- `backend/migrations/versions/009_add_device_platform.py`：alembic 009 幂等迁移
- `backend/app/schemas.py`：DeviceResponse 加 `platform: Optional[str]`
- `backend/app/i18n_keys.py`：加 `SDN_DEVICE_PLATFORM_UNKNOWN`
- `backend/app/services/sdn_device_adapter.py`：
  - 加 `H3C_V7_PLATFORM_BY_MODEL` 映射（LSTN / RSTN / 型号）
  - 加 `PLATFORM_LSTN` / `PLATFORM_RSTN` / `PLATFORM_UNKNOWN` 常量
  - 加 `get_platform_for_model()` 函数（lru_cache 缓存）
  - 加 `TemplateUnit` dataclass（cli_commands / xml_payloads / undo_cli / undo_xml）
  - 加 `UNIT_VSI_L2` / `UNIT_EVPN` / `UNIT_L3VPN` / `UNIT_VSI_L3` / `UNIT_PORT_BIND` / `UNIT_GLOBAL` / `UNIT_PORT_UNBIND` / `UNIT_VPC_CREATE_ALL` 常量
  - 改 `VPCConfigTemplate` ABC：`render()` 返回 `List[TemplateUnit]`
  - `H3cV7Adapter.get_platform()` 委托给 `get_platform_for_model()`

**依赖**：T1.13a-e + T1.13f
**下一步**：T3 模板改造（h3c_v7_vpc_create.py 输出 List[TemplateUnit]）

---

## T3: H3cV7VpcCreateTemplate 改双套 payload

**目的**：把模板从 List[CLI 文本] 改为 **List[TemplateUnit]**，5 unit × 4 字段双套 payload。

**预计改动**：

| 文件 | 改动 |
|---|---|
| `backend/app/services/templates/h3c_v7_vpc_create.py` | 重写：`H3cV7VpcCreateTemplate.render()` 返回 6 个 unit（VSI-L2 / EVPN / L3VPN / VSI-L3 / Global），每个含 cli + xml + undo_cli + undo_xml |
| `backend/app/services/vpc_config_planner.py` | `plan_vpc_create()` 适配新 render 接口（返回 `List[TemplateUnit]`，不是 `List[{mode, command}]`）|
| `backend/app/routers/sdn.py` | `create_deployment` 适配新序列化（planned_config = JSON 序列化 List[TemplateUnit]）|
| `backend/tests/test_templates_h3c_v7.py` | 加 6 unit × 4 字段断言 + XML 合法性校验 |
| `backend/tests/test_vpc_config_planner.py` | 加 TemplateUnit 序列化往返一致断言 |

**6 Unit 设计**（含 Global）：

| Unit | 包含 H3C 配置 | cli_commands (LSTN) | xml_payloads (RSTN) | undo (双套) |
|---|---|---|---|---|
| **VSI-L2** | VSI 实例 + VXLAN 绑定 + Vsi-interface 创建 | `vsi vpc0001 / vxlan 20000 / evpn encapsulation vxlan / route-distinguisher 1:200` + `interface Vsi-interface1` | `<L2VPN><VSIs><VSI>...</VSI></VSIs></L2VPN>` + `<L2VPN><VSIInterfaces><Interface>...</Interface></VSIInterfaces></L2VPN>` + `<VXLAN><VXLANs><Vxlan>...</Vxlan></VXLANs></VXLAN>` | undo vsi + undo interface |
| **EVPN** | EVPN RD/IRT/ERT 绑定 VSI | `vsi vpc0001 / evpn encapsulation vxlan / route-distinguisher 1:200 / vpn-target 1:200 import-extcommunity / vpn-target 1:200 export-extcommunity` | `<VXLAN><EvpnVxlanEncaps><VxlanEncap>...</VxlanEncap></EvpnVxlanEncaps></VXLAN>` | undo evpn encapsulation / undo route-distinguisher |
| **L3VPN** | 共享 l3vpn vpn-instance（首 VPC 创建/末 VPC 删除）| `ip vpn-instance l3vpn / route-distinguisher 1:10000 / address-family evpn` | `<L3vpn><L3vpnVRF><VRF>...</VRF></L3vpnVRF></L3vpn>` | undo vpn-instance（仅末 VPC）|
| **VSI-L3** | Vsi-interface L3 绑定（IP + MAC + L3-VNI）| `interface Vsi-interface1 / ip binding vpn-instance l3vpn / ip address 10.0.1.1 255.255.255.0 / mac-address 00-00-00-00-4e20-01 / l3-vni 10000` | `<L3vpn><If>...</If></L3vpn>` + `<Ifmgr><Interfaces><Interface>...<IPv4>...</IPv4>...</Interface></Interfaces></Ifmgr>` | undo ip binding / undo ip address / undo l3-vni |
| **PortBind** | service-instance + xconnect VSI（v3.0 P0 不在 vpc_create 中，单独走 port_bind 端点）| （vpc_create 不输出，由 port_bind 端点输出）| （vpc_create 不输出）| （vpc_create 不输出）|
| **Global** | vxlan tunnel mac-learning disable（设备级，一次性）| `vxlan tunnel mac-learning disable` | （无 XML 等价物，RSTN 也走 CLI 兜底）| undo vxlan tunnel mac-learning |

**真机小步验证**（**T6 统一验证**，T3 暂不真机）：
- 写完 5 unit 模板 → 单测覆盖（render 输出校验 + XML 合法性）
- **不**真机下发（T3 模板变更不影响 executor 行为；T5 executor 路由后再真机验证）

**依赖**：T2 前期 ✅
**估时**：1 个 session
**commit**：1 个 commit 包含所有 T3 改动（template + planner + tests）

---

## T4: Delete / PortBind / PortUnbind 模板重写（双套 payload）

**目的**：参照 T3 模板重写模式，把 vpc_delete / port_bind / port_unbind 也改为 List[TemplateUnit]。

**预计改动**：
- `backend/app/services/templates/h3c_v7_vpc_create.py`：保留 H3cV7VpcDeleteTemplate（删 vsi + vsi-interface，共享 l3vpn 保留）
- `backend/app/services/templates/h3c_v7_port_bind.py`：重写 H3cV7PortBindTemplate 输出 1 unit (PortBind)，含 cli + xml + undo
- `backend/app/services/templates/h3c_v7_port_unbind.py`：重写 H3cV7PortUnbindTemplate 输出 1 unit (PortUnbind)
- `backend/app/services/vpc_config_planner.py`：plan_vpc_delete / plan_port_bind / plan_port_unbind 适配
- 单测覆盖

**真机小步验证**：T6 统一验证
**依赖**：T3
**估时**：0.5 个 session

---

## T5: SdnDeploymentExecutor 改按 device.platform 路由

**目的**：executor 解析 planned_config（List[TemplateUnit]）后，根据 device.platform 选 cli_commands 或 xml_payloads 下发。

**预计改动**：
- `backend/app/services/sdn_deployment_executor.py`：
  - 去掉直接 NETCONF 路径（V2.0.1）改用**双套 payload 通道**：
    - LSTN 平台：每条 cli_command 用 `<Configuration>{cli}</Configuration>` 包裹后 NETCONF edit-config
    - RSTN 平台：每条 xml_payload 直接 NETCONF edit-config
  - 解析 planned_config 为 `List[TemplateUnit]`
  - 失败立即停 + 错误定位
  - undo 链路：按 platform 选 undo_cli 或 undo_xml

**LSTN 通道真实可用性（T1.13f 探针已验证 ✓）**：
- LSTN 设备 `<Configuration>` 通道真实可写（T1.13f 探针 vpc9999 create + undo 成功）
- T1.13a 探针失败是 namespace 错误，不是通道错误
- 实施时**必须**用正确的 namespace `http://www.h3c.com/netconf/config:1.0`（不是 `h3c-ns`）

**依赖**：T3 + T4
**估时**：1 个 session

---

## T6: 真机验证（.5 + .26 跨平台对比）

**目的**：在真实设备上验证双套 payload 通道设计 + 跨平台 running-config 一致性 + 业务效果。

**.5 设备（生产测试，LSTN）— 完整业务验证**：
- CLI 文本走 NETCONF `<Configuration>` 通道下发
- `display current-configuration` 看到 VSI vpc0001 + VXLAN 20000 + RD
- `display l2vpn vsi verbose` 看到 vpc0001
- `display vxlan vni 20000` 看到 VXLAN
- `display bgp peer l2vpn evpn` 看到 .2/.3 邻居 Established
- `display arp` 看到从 .2/.3 学到的 ARP
- `display bgp l2vpn evpn routing-table` 收到 EVPN 路由
- undo 清理：5 unit 全部反向清理

**.26 设备（EVE-NG 借，RSTN）— 配置 + 跨平台对比**：
- schema 化 NETCONF XML 下发
- `display current-configuration` 看到 VSI vpc0001 + VXLAN 20000 + RD（**与 .5 业务命令 union 一致**）
- `display l2vpn vsi verbose` 看到 vpc0001
- undo 清理

**跨平台 running-config 一致性对比**：
- 提取 .5 和 .26 的 `display current-configuration` 中 VSI vpc0001 相关行
- **业务命令 union 一致**（不强求 byte-to-byte；H3C V7 内部命令顺序可能差异）
- 对比工具：vpc-show.sh（已支持 running-config 提取）

**业务效果验证**（.5，应用户需求）：
- "我们能看到这个动作...在配置上的哪里，实现了什么样的效果"
- 验证 `display current-configuration | include vpc` 包含 5 unit 的所有命令
- 不验证 data plane EVPN/ARP 路由学习（因为 .26 没有 EVPN 对等）

**依赖**：T5
**估时**：1 个 session（含 2 设备 + 5 unit + undo + 业务验证）

---

## T7: 单测补全 + 真机 undo 恢复

**目的**：确保回归不破坏，2 设备最终干净。

**子任务**：
- T7.1 模板 render 单测（`test_templates_h3c_v7.py` 加双套 payload 断言）
- T7.2 planner serialize/deserialize 单测（`test_vpc_config_planner.py` 加 TemplateUnit 断言）
- T7.3 executor mock 单测（`test_sdn_deployment_executor.py` 加 platform 路由断言）
- T7.4 qa-backend 全量 pytest（32 SDN + 5+ 新增 = 37+ SDN + 225+ baseline 全过）
- T7.5 真机 undo 恢复（.5 + .26 跑回 pending 状态）
- T7.6 备份 .5 + .26 running config 持久化（commit 留档）

**依赖**：T6
**估时**：0.5 个 session

---

## Archive 闭环

- [ ] git status 干净
- [ ] change archive 迁到 archive/2026-07-XX-sdn-vpc-netconf-schema-xml/
- [ ] VERSION-ROADMAP.md 同步（如有需要）
- [ ] README.md 同步（如有需要）
- [ ] RELEASE-NOTES-v3.0.0.md 更新
