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

### 2.2 端口绑定生命周期

- 创建端口绑定关系；
- 绑定模式支持 service-instance + xconnect VSI，保留 access VLAN fallback；
- 生成 port-bind / port-unbind 配置计划；
- apply 后更新 binding 状态；
- 用户可从 VPC 视角看到端口属于哪个 VPC，而不是只看到交换机命令。

### 2.3 撤回粒度

v3.3 P0 支持：

- **整 VPC / 单设备撤回**：撤回某个 VPC 在某台设备上的 VSI / EVPN / Vsi-interface 配置；
- **端口解绑**：撤回某个端口绑定；
- **VPC 三层网关撤回**：只撤回某台设备上某个 VPC 的 Vsi-interface / gateway 绑定，用于集中式网关、排障、降级验证。

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

## 3. 验证原则

允许在生产机器上创建专用测试资源，但必须遵守：

- 不动已有管理接口；
- 不改已有业务接口；
- 测试使用新建 VPC / 新 VNI / 新 Vsi-interface / 新 loopback 或明确测试端口；
- 测完必须撤回并确认设备侧配置清理干净；
- 所有真机 display 命令证据写入 change capture 或 release notes。

## 4. 验收标准

- [ ] VPC create deployment 可下发成功；
- [ ] VPC delete deployment 可撤回成功；
- [ ] port-bind deployment 可下发成功；
- [ ] port-unbind deployment 可撤回成功；
- [ ] gateway-only 撤回能只删除三层网关相关配置，不删除 L2VNI/VSI；
- [ ] 后端 API 能返回 VPC 视角的 deployment/binding 状态；
- [ ] 关键链路有单元测试；
- [ ] 至少一轮真实设备测试资源创建与清理验证。

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
