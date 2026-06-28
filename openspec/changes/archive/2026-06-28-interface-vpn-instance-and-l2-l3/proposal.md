## Why

v2.2 网控增强第二项。当前 `Interface.vue` 视图只展示二层（access/trunk）配置 + VLAN，**缺失三大量**：

1. **接口的二层 / 三层区分**（L2 vs L3）：H3C V7 设备有 `interface Vlan-interface X`（三层 VLANIF）/ `interface GigabitEthernet X`（二层物理口）/ `interface GigabitEthernet X.Y`（子接口，带 VPN instance 或 dot1q）等多种类型，但当前实现把所有接口都按物理二层口处理，**三层口无入口**
2. **VPN instance 绑定**：192.168.100.4 (Leaf-03) 的带外管理接口 `M-GigabitEthernet0/0/0` 绑了 `vpn-instance MGMT`，是常见运维场景（管理流量走独立 VRF）。当前无法查看 / 创建 / 绑定 VPN instance
3. **联动配置能力**：VPN instance 创建、接口绑 VPN instance 这两个动作目前只能 SSH 手工执行，无法通过平台一键完成

**用户原话**（2026-06-28 规划）：
> "再提一个要求啊，你就可以参考这个刚刚我说这个点四啊，它里面呢，它的这个带外管理接口。是有 ip vpn instance 的，所以说我觉得你可以把接口管理这里再做的细一点，就是有一个联动性的配置，就是你可以选择创建，或者说这分分为两个动作也行吧，就是你分为另就是这另外一个板块的动作，就是可以创建 vpn instance，然后也可以去把 ip 接口绑在这个把接口绑在这个 vpn in特斯下，然后再去呃这样那样的。"
> "而且也可以去展示这个接口，现在是二层还是三层，然后呢，它上面有没有 vpn instance，没有的话就是一个就是一个有一个空白。"

**参考设备**：192.168.100.4 (Leaf-03)，用户已明确为 v2.2 验证目标。

### 关键设计约束

- **H3C V7 NETCONF 实现验证**：VPN instance / L3 接口的 NETCONF 模型需实地探测；fallback 用 SSH CLI
- **L2 / L3 判定**：H3C 命名约定（`Vlan-interface` 开头 = L3，`GigabitEthernet` 物理口 = L2，子接口 `.Y` = L3 或 sub-L2 视配置），辅以 `Ifmgr/Interfaces/Interface/Ipv4Address` 存在判定
- **不做全量网段规划**：VPN instance 创建仅做"创建空实例"，不绑定 RD/RT（RD/RT 是更高级能力，超出 v2.2 范围）
- **不做"批量绑 VPN"**：每次只绑一个接口，避免误操作

### 风险

| 风险 | 缓解 |
|---|---|
| 误创建 VPN instance / 误绑接口 | 二次确认 Modal + 操作前显示当前接口配置预览 |
| H3C V7 NETCONF VPN 模型与文档差异 | 实施时探测；失败 fallback SSH CLI |
| L2/L3 判定错（误把 sub-interface 当 L2） | 命名规则 + 字段存在性双校验 |

## What Changes

### 后端 `backend/app/routers/interface.py` 扩展

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/devices/{id}/interfaces` | GET | **增强**：每个接口返回 `layer`（L2/L3）、`ip_addresses`、`vpn_instance`（绑定的 VPN instance 名，nullable）|
| `/api/devices/{id}/vpn-instances` | GET | 列出设备上所有 VPN instance（NETCONF get） |
| `/api/devices/{id}/vpn-instances` | POST | 创建 VPN instance（NETCONF edit-config：`<Ipv4Vrf><VRF><Name>X</Name><DefaultRD>auto</DefaultRD></VRF></Ipv4Vrf>`） |
| `/api/devices/{id}/vpn-instances/{name}` | DELETE | 删除 VPN instance（NETCONF delete-config；要求无接口绑定） |
| `/api/devices/{id}/interfaces/{if_index}/vpn-instance` | POST | 接口绑 VPN instance（NETCONF edit-config） |
| `/api/devices/{id}/interfaces/{if_index}/vpn-instance` | DELETE | 接口解绑 VPN instance（NETCONF delete-config） |

### 数据模型（不存数据库，纯展示缓存）

- **不新建 ORM 表**：VPN instance 状态以"实时 NETCONF 查询"为准，不落库
- 设备配置变更后无需做缓存同步，**永远以 NETCONF 当前值为准**

### 前端 `frontend/src/views/Interface.vue` 改造（假设 v2.2 起时已有独立页面）

> 注：当前 v2.1 中"接口管理"挂在设备详情页，v2.2 起独立页面 `Interface.vue`（todo 列入 v2.2 第一个 change，本 change 不含页面独立化）

- **表格列扩展**：现有 `if_index / name / mode / pvid / allowed_vlans` 基础上加 `layer`（"二层" / "三层" badge）、`ip_addresses`、`vpn_instance`（"MGMT" / "-"）
- **行操作列新增 2 个按钮**（仅 L3 接口或物理口显示）：
  - "创建 VPN" → 弹 Modal 输入 VPN instance 名 + 确认（新建后跳到绑定步骤）
  - "绑 VPN" → 弹 Select 选已有 VPN instance + 确认
- **复用 ConfirmModal**：所有写操作前二次确认

### 不改动

- VLAN 管理（vlan.py）
- 设备 CRUD（device.py）
- 备份功能（backup.py，与本 change 独立）
- 容器解耦蓝图（已 archive）

## Capabilities

### New Capabilities
- `interface-vpn-instance-and-l2-l3`：
  - 接口列表展示层类型（L2/L3）+ IP 地址 + VPN instance 绑定
  - VPN instance CRUD（创建 / 列表 / 删除）
  - 接口 ↔ VPN instance 绑定 / 解绑

### Modified Capabilities
- （无现有 spec 修改）

## Impact

- **代码**：
  - `backend/app/routers/interface.py` 增 6 个端点（~250 行）
  - `backend/app/utils/netconf_xml.py` 增 VPN instance XML 构造器（~80 行，新建）
  - `frontend/src/views/Interface.vue`（v2.2 第一个 change 创建）+ 表格列扩展 + 行操作按钮
  - `frontend/src/components/VpnInstanceBindModal.vue` 新建（~120 行）
- **API 兼容性**：纯增量，6 个新端点
- **数据库**：**无迁移**（VPN instance 状态走 NETCONF，不落库）
- **依赖**：无新增
- **回归**：现有 VLAN / 接口 / 设备 CRUD 行为不变
- **回退**：git revert 即可，无迁移影响
- **测试设备**：192.168.100.4 (Leaf-03)，用户现场配合
- **不依赖 v3.0 VPC**：本 change 独立可用，不引入 etcd

## Open Questions（待解决）

1. **VPN instance RD / RT 处理**：H3C 创建 VPN instance 时 RD 是必填还是可选？需探测 192.168.100.4 上的现有配置
2. **三层接口创建能力**：本 change 不做"创建三层接口"（超出范围），只做"识别 + 展示 + 绑 VPN"
3. **子接口场景**：`GigabitEthernet X.Y` 这种子接口（dot1q 终结）的 L2/L3 判定 + 绑 VPN 是否纳入？建议纳入，但列为 follow-up

## 验收标准

- [ ] `GET /api/devices/{id}/interfaces` 返回数据中每个接口都带 `layer` / `ip_addresses` / `vpn_instance` 三个新字段
- [ ] 192.168.100.4 上查询接口列表，能正确识别 M-GigabitEthernet0/0/0 为 L3 + 绑了 `MGMT` VPN instance
- [ ] `POST /api/devices/{id}/vpn-instances` 创建一个新 VPN instance 后，设备 `display ip vpn-instance` 能看到
- [ ] `POST /api/devices/{id}/interfaces/{if_index}/vpn-instance` 绑 VPN instance 后，NETCONF get-config 能查到该绑定
- [ ] `DELETE` 系列操作二次确认 Modal 正常工作
- [ ] 前端 Interface.vue 表格列扩展后，无新增 vite 报错 / 控制台 warning
- [ ] 回归：现有 VLAN CRUD / 接口 access-trunk 配置功能不变
