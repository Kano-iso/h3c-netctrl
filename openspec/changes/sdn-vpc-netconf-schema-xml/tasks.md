# sdn-vpc-netconf-schema-xml — Tasks

## 拆解原则（v2 - 应用户 review 修正）

**老拆法问题**：T1 探针 → T2 模板 → T3 executor → T4 真机验证。T2/T3 写代码时没真机反馈，错一次又一次。

**新拆法**：每个 task 都自带"真机小步验证"环节——探针和写代码交叉进行，每写一段就丢到 .5 设备上试，错了立刻知道再调，写完就验证能跑。

## 进度总览

- [x] **T0** (Done 2026-07-11) NETCONF 探针定位 H3C V7 schema 化入口
- [x] **T0.5** (Done 2026-07-13) SdnDeployment 数据模型扩展：加 `unit` / `parent_deployment_id` 字段（alembic 迁移 008，32 个 SDN 单测全过）
- [ ] **T1** 探针 VSI 子结构（network-instance 下 VXLAN / EVPN / encapsulation / gateway 等）+ 探针完立刻真机最小验证
- [ ] **T2** 探针 Vsi-interface 子结构（Ifmgr module 下 Vsi-interface 创建）+ 探针完立刻真机最小验证
- [ ] **T3** 重写 H3cV7VpcCreateTemplate 输出 schema 化 XML（按 unit 拆分）+ 真机单 unit 验证
- [ ] **T4** 扩 H3cV7VpcCreateTemplate 到 5 个 unit 全覆盖 + 真机 vpc9999 完整验证
- [ ] **T5** 重写 H3cV7VpcDeleteTemplate / H3cV7PortBindTemplate / H3cV7PortUnbindTemplate + 真机小步验证
- [ ] **T6** 重写 SdnDeploymentExecutor 按 unit 执行 + 端到端真机 POST /units/{unit} 验证
- [ ] **T7** 单测补全 + 真机 vpc-show.sh 全状态验证 + undo 恢复

---

## T0: 探针定位入口 ✅ (2026-07-11)

**目的**：定位 H3C V7 NETCONF 业务下发的正确路径（替代旧 `<Configuration>CLI 文本</Configuration>`）。

**实测**（在 .5 设备 192.168.100.5）：

| 探针 | 格式 | 响应 | 结论 |
|---|---|---|---|
| 1 | `<config xmlns="h3c-ns"><Configuration>vsi vpc9999</Configuration></config>` | `Element [h3c-ns]config does not meet requirement` | ❌ config 元素不能带 h3c-ns |
| 2 | `<config><top xmlns="h3c-ns"><Configuration>vsi vpc9999</Configuration></top></config>` | `Configuration can not have a textual child element` | ❌ H3C V7 不接受 CLI 文本 |
| 3 | 同上 + `<Configuration><Text>` / `<Command>` | `Unexpected element 'Text' under Configuration` | ❌ 不支持 Text/Command 子元素 |
| 4 | `<top><L2VPN>...` | `Unexpected element 'L2VPN' under top` | ❌ L2VPN 不在 top 直接子节点 |
| 5 | `<top><L2vpnVSI xmlns="...-L2VPN">` | `Unexpected element 'L2vpnVSI' under top` | ❌ 即使带 module NS 也不接受 |
| 6 | `<top><MVPN><Name>vpc9999</Name></MVPN>` | `Unexpected element 'Name' under MVPN` | ❌ MVPN wrapper 接受但子元素不对 |
| 7 | `<top><network-instances><network-instance><name>vpc9999</name></network-instance></network-instances></top>` | **edit-config 成功 + get-config 验证 + undo 成功** | ✅ 入口走 OpenConfig `network-instances` |

**设备脏数据自查**：所有探针完成时 .5 状态只剩 mgt，vpc9999 已 clean undo。

**输出**：
- 写入 [design.md](design.md) §探针发现
- 决定 T0.5-T7 工作方向

---

## T0.5: SdnDeployment 数据模型扩展

**目的**：unit 拆分需要数据模型支持——SdnDeployment 加 `unit` / `parent_deployment_id` 字段。

**预计改动**：
- `backend/app/models.py`：`SdnDeployment` 加 `unit: str` / `parent_deployment_id: Optional[int]` 字段
- `backend/migrations/versions/008_add_sdn_deployment_unit.py`：alembic 迁移（upgrade / downgrade）
- `backend/app/schemas.py`：SdnDeploymentResponse 加 unit / parent_deployment_id

**依赖**：T0 ✅

**估时**：0.5 个 session

---

## T1: 探针 VSI 子结构（network-instance 下 VXLAN / EVPN / 配套参数）

**目的**：在 .5 设备上探针，定位 network-instance 下 VSI 的完整 schema 化 XML（VXLAN id / EVPN 封装 / gateway 接口 / route-distinguisher / etc）。

**做法**（探针+真机小步验证交叉）：

1. 在 .5 上建 vpc9999（network-instance），T0 已验证
2. 探针加 `<vsi>` 或 `<vxlan>` 子元素，看哪个 wrapper 被接受
3. 找到 wrapper 后探针其子结构（vni-id / encapsulation / gateway-interface）
4. **每个探针都立刻 undo**，不积累脏数据
5. 关键探针用 vpc9999 落地后跑 `vpc-show.sh` 看实际生效

**真机验证**：
- 探针过程中 keep get-config 验证修改可应用
- 最终一次性建完整 VSI 配置 → 验证 `display l2vpn vsi` 看到 vpc9999 → undo 干净

**产出**：
- 完整 VSI 创建 schema 化 XML 样例
- 写入 design.md §附录 A

**依赖**：T0 ✅

**估时**：1-2 个 session

---

## T2: 探针 Vsi-interface 子结构（Ifmgr module）

**目的**：定位 Vsi-interface 创建的 schema 化 XML 写法（Ifmgr module 下）。

**做法**（沿用 T1 探针节奏）：

1. 探针 vpc9999 的 Vsi-interface（N 号）创建：`interface Vsi-interface9999`
2. 探针 Vsi-interface 下挂 ip binding / ip address / l3-vni 配置
3. **每个探针立刻 undo**

**真机验证**：
- 探针成功后建完整 Vsi-interface 配置
- 跑 `display interface Vsi-interface9999` 验证存在
- 跑 `display l3vpn vpn-instance` 验证绑定成功
- undo 干净

**产出**：
- 完整 Vsi-interface 创建 schema 化 XML 样例
- 写入 design.md §附录 B

**依赖**：T1（VSI 实例存在才能挂 Vsi-interface）

**估时**：0.5-1 个 session

---

## T3: 重写 H3cV7VpcCreateTemplate 输出 schema 化 XML（按 unit 拆分）

**目的**：把 vpc_create 模板从 CLI 文本列表改为按 5 个 unit 输出的完整 edit-config XML 列表。

**预计改动**：
- `backend/app/services/templates/h3c_v7_vpc_create.py`：render() 改输出 `List[TemplateUnit]`，每个 unit 包含 name / description / commands / preflight / undo_commands
- 5 个 unit：vsi-l2 / l3vpn / vsi-l3 / global / port-bind（按 design.md §前端粒度）

**真机小步验证**（不是最后才验证）：
- 写完 vsi-l2 unit → 在 .5 上 POST 单 unit edit-config → `vpc-show.sh` 看 vpc0001 network-instance + VXLAN 20000 是否出现
- 失败立刻调整模板（不继续往下写）
- 通过后写 l3vpn unit → 真机验证
- 通过后写 vsi-l3 unit → 真机验证
- 通过后写 global unit → 真机验证
- 最后写 port-bind unit → 真机验证

**真机验证通过标准**：
- 每个 unit 在设备上能看到预期效果
- 每个 unit undo 后 .5 干净

**依赖**：T0.5 + T1 + T2

**估时**：1-2 个 session（每 unit 真机 1 次）

---

## T4: 扩 H3cV7VpcCreateTemplate 到 5 个 unit 全覆盖

**目的**：确认 5 个 unit 模板覆盖完整场景，5 个 unit 全部独立可触发。

**真机小步验证**：
- vpc9999 完整流程：vsi-l2 → port-bind (1 个) → l3vpn → vsi-l3 → global
- 每步都跑 vpc-show.sh 看对应状态
- 每步都独立 undo
- 最后一次性 vpc9999 全跑（5 个 unit 全部下发） + 全状态验证

**真机验证通过标准**：
- vpc-show.sh 输出包含 vpc9999 VSI + VXLAN 9999 + l3vpn VPN + Vsi-interface + service-instance
- `display l3vpn vpn-instance` 看到 l3vpn 实例
- `display bgp peer l2vpn evpn` 仍 Established
- 任何单 unit 都能独立 undo 干净

**依赖**：T3

**估时**：1 个 session

---

## T5: 重写 Delete / PortBind / PortUnbind 模板

**目的**：把删除模板、端口绑定/解绑模板都从 CLI 文本列表改为按 unit 输出的完整 edit-config XML 列表。

**预计改动**：
- `backend/app/services/templates/h3c_v7_vpc_delete.py`：按 unit 反向（vsi-l2 undo / vsi-l3 undo / l3vpn undo / global undo）
- `backend/app/services/templates/h3c_v7_port_bind.py`：unit=port-bind
- `backend/app/services/templates/h3c_v7_port_unbind.py`：unit=port-unbind

**真机小步验证**：
- 每个模板各建 1 个 vpc_test 真实业务 + 用模板下发 + vpc-show.sh 验证 + 模板反向 undo 验证

**依赖**：T4（vpc_create 模板稳定后）

**估时**：1 个 session

---

## T6: 重写 SdnDeploymentExecutor 按 unit 执行 + 端到端真机 POST /units/{unit} 验证

**目的**：executor 改为按 unit 执行，每 unit 独立 SdnDeployment / 独立 undo / 独立 preflight。

**预计改动**：
- `backend/app/services/sdn_deployment_executor.py`：每 SdnDeployment.unit 独立执行
- 去掉 h3c_ns / `<Configuration>` 包裹代码
- planned_config 解析逻辑改：JSON → TemplateUnit 列表
- `backend/app/routers/sdn.py`：API 拆分
  - `POST /api/sdn/vpcs/{id}/units/vsi-l2`
  - `POST /api/sdn/vpcs/{id}/units/l3vpn`
  - `POST /api/sdn/vpcs/{id}/units/vsi-l3`
  - `POST /api/sdn/devices/{id}/init` (global)
  - `POST /api/sdn/ports/{id}/bind`
  - `POST /api/sdn/ports/{id}/unbind`

**真机端到端验证**：
- 准备 vpc0001（DB 中已有）
- 备份 .5 running config
- POST /api/sdn/vpcs/1/units/vsi-l2 → status=success → vpc-show.sh 验证
- POST /api/sdn/ports/1/bind → status=success → vpc-show.sh 验证
- POST /api/sdn/vpcs/1/units/l3vpn → status=success → vpc-show.sh 验证
- POST /api/sdn/vpcs/1/units/vsi-l3 → status=success → vpc-show.sh 验证
- POST /api/sdn/devices/4/init → status=success → vpc-show.sh 验证
- **每步之间间隔 5s**（避免 H3C V7 状态刷新延迟）
- 任意步失败 → 只 undo 当前 unit，**不**回滚前面

**依赖**：T5

**估时**：1-2 个 session

---

## T7: 单测补全 + 全状态真机验证 + undo 恢复

**目的**：确保回归不破坏，.5 设备最终干净。

**子任务**：
- T7.1 模板 render 单测（`test_templates_h3c_v7.py` 加新断言）
- T7.2 executor mock 单测（`test_sdn_deployment_executor.py` 验证入参 XML）
- T7.3 qa-backend 全量 pytest（67 SDN + 225+ baseline 全过）
- T7.4 真机 vpc-show.sh 全状态验证（VSI/VXLAN/BGP peer/Vsi-interface/ARP/MAC/路由）
- T7.5 真机 undo 恢复 .5 到探针前状态（只有 mgt）
- T7.6 备份 .5 running config 持久化（commit 留档）

**依赖**：T6

**估时**：0.5 个 session

---

## Archive 闭环

- [ ] git status 干净
- [ ] change archive 迁到 archive/2026-07-XX-sdn-vpc-netconf-schema-xml/
- [ ] VERSION-ROADMAP.md 同步（如有需要）
- [ ] README.md 同步（如有需要）
- [ ] RELEASE-NOTES-v3.0.0.md 更新
