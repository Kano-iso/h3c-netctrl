# H3C NetCtrl V3.3 PRD：VPC/EVPN 配置闭环

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| V3.3 Draft | 2026-07-18 | 用户拍板 + Codex 共创 | 原定为集中式网关降级/恢复 |
| V3.3 Revise | 2026-07-19 | 用户拍板 + Codex 共创 | v3.2 平台迁移暂缓后，v3.3 调整为 VPC/EVPN 创建、下发、撤回、局部撤回、端口绑定闭环 |

---

## 1. 背景与目标

### 1.1 背景

v3.0 已完成 SDN/VPC 配置骨架：

- 租户 / VPC / deployment 数据模型已存在；
- VPC create/delete、port bind/unbind 的配置模板已有双套 payload；
- LSTN 平台走 SSH CLI，RSTN 平台走 NETCONF/XML 的通道已定稿；
- 但当前仍偏“工程骨架”，缺少面向用户的完整生命周期闭环。

v3.2 原计划切换新平台后再做全量能力评级，但当前因 HCL/177 升级受限、EVE/V9850 二层广播不可信而暂缓。因此 v3.3 不再等待新平台，直接在现有可控平台上推进产品闭环。

### 1.2 目标

v3.3 的目标是让 VPC/EVPN 能力具备可用的后端闭环：

- 用户可以创建 VPC；
- 用户可以选择设备下发 VPC；
- 用户可以绑定端口到 VPC；
- 用户可以在已有 VPC 下扩容新的接入口；
- 已下发的配置可以按用户视角撤回；
- 支持整 VPC 撤回、单设备撤回、端口解绑、VPC 三层网关局部撤回等不同粒度；
- 后端记录“下发给了谁、下发了哪些单元、是否成功、能否撤回”。

底层允许混合通道：

- 能稳定走 NETCONF/XML 的能力继续走 NETCONF/XML；
- HCL/老 S6850 不支持或不完整的 EVPN/VXLAN 能力，走模板化 CLI over SSH；
- 产品目标是自动编排与自动校验，不把纯 XML 下发作为当前硬门槛。

## 2. 范围

### 2.1 VPC 生命周期

- 创建租户与 VPC；
- 自动分配 RD/RT/L3VNI/VNI/VSI/Vsi-interface/VLAN/gateway；
- 生成 VPC create/delete 配置计划；
- apply 后更新 deployment 与 VPC 状态；
- delete 能真正走 executor 撤回设备侧配置。
- 提供 VPC 级 deploy/withdraw 编排入口，默认面向 Leaf 设备展开 deployment 集合。

### 2.2 端口绑定生命周期

- 创建端口绑定关系；
- 绑定模式支持 service-instance + xconnect VSI，保留 access VLAN fallback；
- 生成 port-bind / port-unbind 配置计划；
- apply 后更新 binding 状态；
- 用户可从 VPC 视角看到端口属于哪个 VPC，而不是只看到交换机命令。

### 2.2.1 已有 VPC 接入口扩容

VPC 已存在时，用户可以发起一次“接入口扩容”：

- 只能选择 Leaf 设备；
- 选择该 Leaf 上的目标接口；
- 不需要重新填写 VPC 网段或掩码，扩容继承 VPC 的 CIDR、网关、VNI、VSI；
- 可选填写新接入主机 IP，用于扩容完成后的网关 ping 校验；
- 平台创建端口绑定并下发 `port_bind`；
- 下发成功后，VPC 与绑定进入 `expanding` 状态；
- 用户完成接线并给主机配置 IP/网关后，点击“扩容完成”；
- 平台从 VPC 网关源地址 ping 新主机，并强制同步一次 display 状态；
- ping 与 display 校验均通过时，绑定转 `active`，VPC 回到 `active`；
- 校验失败时，绑定转 `failed`，VPC 转 `degraded`，保留排障信息。

### 2.3 撤回粒度

v3.3 P0 支持：

- **整 VPC / 单设备撤回**：撤回某个 VPC 在某台设备上的 VSI / EVPN / Vsi-interface 配置；
- **整 VPC / 单设备补回**：按 VPC 定义把某个 VPC 的完整标准配置补回某台 Leaf；
- **端口解绑**：撤回某个端口绑定；
- **端口绑定**：把某个 Leaf 接口加入已有 VPC；
- **VPC 三层网关撤回**：只撤回某台设备上某个 VPC 的 Vsi-interface / gateway 绑定，用于集中式网关、排障、降级验证；
- **VPC 三层网关加回**：按 VPC 定义只补回 Vsi-interface / L3VNI / VPN binding / gateway 绑定，不重建 L2 VSI/EVPN。

v3.3 P1 可扩展：

- 批量选择多个设备撤回同一个 VPC；
- 批量选择多个端口解绑；
- 将多个 deployment 编排成一个用户可读的“操作批次”。

### 2.4 用户体验原则

后端 API 设计应优先体现用户动作：

- “给这个 VPC 下发到这些设备”；
- “把这个 VPC 从这台设备撤回”；
- “把这个端口加入/移出这个 VPC”；
- “只撤回这台设备上的三层网关”。

设备、命令、unit 仍要保留在 deployment 记录中，作为审计和排障细节，但不应成为主要用户入口。

### 2.5 当前编排策略

v3.3 当前后端采用保守策略：

- 未传 `device_ids` 时，系统按默认 Leaf 候选选择设备；
- 默认 Leaf 候选来自 `device.platform = LSTN/RSTN`、设备名包含 `Leaf`、或资产型号能推导出 H3C V7 平台；
- 用户显式传 `device_ids` 时，以用户选择为准；
- VPC deploy 默认只生成计划，不直接改设备；
- 只有 `auto_apply=true` 时才会按 deployment 创建顺序执行；
- VPC withdraw 会先生成端口解绑，再生成 VPC delete，避免先删 VPC 后端口残留。
- 单 Leaf VPC 补回复用完整 VPC create 模板，所有 RD/VNI/网关参数均来自 VPC 定义，不接受调用方重填。
- VPC delete 的设备命令顺序必须先清 EVPN/RD，再删 Vsi-interface，最后删 VSI；真机发现如果先 `undo vsi`，后续再进入 `vsi <name>` 清 EVPN 会把空壳 VSI 重新创建出来。
- 三层网关加回复用 `vsi-l3` unit，只补 Vsi-interface 与 gateway 绑定；三层网关撤回同样只操作 `vsi-l3` unit。
- 当前 `sdn_l3vpn` 按设备级共享对象处理，整 VPC 撤回默认保留；是否在租户/VPC 最后一份部署撤回后自动清理，需要后续单独冻结生命周期策略。

## 3. 验证原则

允许在生产机器上创建专用测试资源，但必须遵守：

- 不动已有管理接口；
- 不改已有业务接口；
- 测试使用新建 VPC / 新 VNI / 新 Vsi-interface / 新 loopback 或明确测试端口；
- 测完必须撤回并确认设备侧配置清理干净；
- 所有真机 display 命令证据写入 change capture 或 release notes。

### 3.1 当前真机验证记录

2026-07-19 在 `.5 / Leaf-04 / 192.168.100.5` 上完成第一轮隔离验证：

- 基线：设备可达，SSH 与 NETCONF 可达；用户回滚配置后，`display bgp peer l2vpn evpn` 显示对端 `1.1.1.1` 为 `Established`。
- 下发：通过 `POST /api/sdn/vpcs/{id}/deploy`，指定 `device_ids=[5]` 且 `auto_apply=true`，成功生成并执行 VPC create。
- 设备侧可见：`vsi vpc0003`、`gateway vsi-interface 1002`、`vxlan 20002`、`route-distinguisher 1:20002`、`interface Vsi-interface1002`、`ip binding vpn-instance sdn_l3vpn`、`l3-vni 10005` 均落地。
- 控制面：下发 VPC + 临时接入口后，`display bgp l2vpn evpn` 可见本地 Type-3 IMET 路由 `[3][0][32][1.1.1.4]/80`；`display bgp l2vpn evpn peer 1.1.1.1 advertised-routes` 确认该路由已向对端通告。
- 数据面补充验证：用户提供 `GigabitEthernet1/0/2` 下联主机 `192.168.2.2` 后，使用 `192.168.2.0/24` 临时 VPC、网关 `192.168.2.254`、`service-instance 3200` 完成验证；设备侧 `ping -a 192.168.2.254 -vpn-instance sdn_l3vpn 192.168.2.2` 为 5/5 成功。
- Type-2 证据：`display l2vpn mac-address` 学到 `96ba-e5f7-0a06 Dynamic vpc0002 GE1/0/2`；`display arp vpn-instance sdn_l3vpn` 学到 `192.168.2.2 -> 96ba-e5f7-0a06`；`display evpn route arp` 显示该 ARP 为 `DL`。
- BGP EVPN 证据：`display bgp l2vpn evpn` 显示 3 条本地路由，包括 MAC-only Type-2、MAC/IP Type-2、Type-3 IMET；`advertised-routes` 确认三条均通告给 `1.1.1.1`。
- 未完成项：本轮仍只验证 `.5` 本地接入与向对端通告，尚未验证远端同 VNI 接收、远端 Type-2 回灌以及跨 Leaf 主机互通。
- 撤回：通过 `POST /api/sdn/vpcs/{id}/withdraw` 成功撤回；修正删除顺序后，设备侧不再残留空壳 VSI，`Vsi-interface1002` 也已清理。
- 端口绑定：使用空闲口 `GigabitEthernet1/0/10` 与 `service-instance 3310` 验证 port-bind，设备侧出现 `encapsulation default` 与 `xconnect vsi vpc0002`，VSI 侧出现 AC `GE1/0/10 srv3310`。
- 端口解绑：通过 port-unbind 撤回后，`GigabitEthernet1/0/10` 恢复到原默认配置，仅保留 `port link-mode bridge` 与 `combo enable fiber`。
- 网关局部撤回：通过 gateway-only 撤回后，`Vsi-interface1001` 被删除，`vpc0002` 的 L2 VSI / VXLAN / EVPN 保留，符合局部降级/排障预期。
- 清理：本轮临时测试对象已从设备和平台测试数据中清理，设备恢复到测试前状态。

2026-07-19 在 `.5 / Leaf-04 / 192.168.100.5` 上完成一次保留现场的扩容演示：

- 创建 `192.168.1.0/24` VPC，网关 `192.168.1.254`，设备侧对象为 `vpc0002 / Vsi-interface1001 / VNI 20001`；
- 只补回 `.5` 上的 VPC 配置，不扩大到其他 Leaf；
- 通过扩容 API 绑定 `GigabitEthernet1/0/3`，`service-instance 3100`，目标主机 `192.168.1.3`；
- 扩容开始后，VPC 与绑定进入 `expanding`；
- 扩容完成接口执行网关 ping 与 display 校验，结果均成功，VPC 与绑定转 `active`；
- 设备侧证据：`GE1/0/3 srv3100` 为 Up，`display arp vpn-instance sdn_l3vpn` 学到 `192.168.1.3 -> 96ba-e815-0b06`；
- EVPN 证据：BGP EVPN 生成 MAC-only Type-2、MAC/IP Type-2、Type-3 IMET，并已向 `1.1.1.1` advertised-routes；
- 该演示配置当前保留，用于后续前端联调和扩容体验验证。

### 3.2 本地通信与远端通信边界

本轮 `.5` 验证已经证明“本设备 VPC 网关到本地下联主机”可以通信：

- VPC 网关：`192.168.2.254`；
- 本地下联主机：`192.168.2.2`；
- 测试命令：`ping -a 192.168.2.254 -vpn-instance sdn_l3vpn 192.168.2.2`；
- 结果：5/5 成功，0 丢包。

这说明本地 Vsi-interface、VSI、AC、ARP、MAC 学习、Type-2 生成链路是成立的。

尚未证明的是“远端同 VNI 主机互通”。这需要另一台 Leaf 上也存在同 VNI / 同租户 VPC，并具备 Up 的接入口和主机。当前实验条件不足，因此该项不作为 v3.3 当前收口阻塞项，转入后续环境具备后的验证任务。

### 3.3 Display 状态采集闭环

v3.3 已把人工 display 验证沉淀为平台可调用的状态采集能力。考虑到设备 SSH/CLI 不适合高频轮询，本版本采用：

- 手动同步：用户或前端主动触发一次状态同步；
- 缓存复用：默认 600 秒内复用最近快照；
- 强制刷新：排障时可传 `force=true` 跳过缓存；
- 最近快照：前端可只读 latest，不触发设备访问。

最小闭环不追求复杂拓扑判断，只要求能围绕一个 `{vpc_id, device_id}` 采集并存储：

- BGP EVPN peer 是否 Established；
- 目标 VSI 是否存在，状态是否 Up；
- 目标 AC 是否存在，状态是否 Up；
- Vsi-interface / L3VNI / VPN instance 是否存在；
- 本地 MAC / ARP / EVPN Type-2 / Type-3 是否具备可观测证据；
- 校验结果写入 `sdn_validation_snapshots`，返回 `active / degraded / failed` 与逐项明细。

## 4. 验收标准

- [x] VPC create deployment 可下发成功；
- [x] VPC delete deployment 可撤回成功；
- [x] port-bind deployment 可下发成功；
- [x] port-unbind deployment 可撤回成功；
- [x] 已有 VPC 接入口扩容可进入 expanding，并在完成验证后转 active/degraded；
- [x] 单 Leaf VPC 补回可生成完整 VPC create deployment；
- [x] gateway-only 撤回能只删除三层网关相关配置，不删除 L2VNI/VSI；
- [x] gateway-only 加回能只补回三层网关相关配置，不重建 L2VNI/VSI；
- [x] 后端 API 能返回 VPC 视角的 deployment/binding 状态；
- [x] 关键链路有单元测试；
- [x] 至少一轮真实设备测试资源创建与清理验证。
- [x] display 状态采集与二次校验结果可入库并通过 API 返回。

## 5. 不做

- 不做平台迁移，v3.2 保留为未来待办；
- 不做 etcd 协调；
- 不做 ACL；
- 不做自动接管已有业务配置；
- 不做大屏级拓扑展示，前端完整视觉化留后续版本。

## 6. 风险

- **风险 1：撤回粒度过粗**：用户只想撤一个端口或一个网关，系统却撤整 VPC。
  - 缓解：deployment 必须保留 unit 粒度，API 按用户动作生成最小计划。
- **风险 2：设备侧配置半成功**：H3C V7 无跨 unit 事务，失败可能留下半状态。
  - 缓解：失败即停，记录失败 unit / 命令 / payload；提供对应撤回计划。
- **风险 3：混合通道增加维护成本**：LSTN/RSTN 行为不同。
  - 缓解：planner 输出统一 TemplateUnit，executor 按 platform 路由，业务层不关心通道差异。
- **风险 4：生产验证误动现有配置**：测试资源可能碰到历史配置。
  - 缓解：编号自动避开前 1000，测试前 display 确认，测试后 delete/unbind 清理。
