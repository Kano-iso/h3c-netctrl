## Context

v2.2 网控增强第二项。系统在 v2.0 引入接口管理（access/trunk 配置），v2.1 修了 trunk allowed VLAN 在 H3C V7 上必须走 SSH 的限制。v2.2 用户反馈需要更细的接口管理能力：L2/L3 区分 + VPN instance 联动。

### 后端能力盘点

- `interface.py` 现有：`get_interfaces` / `configure_interface`（access/trunk）
- `netconf_client.py` 封装了 `NetconfClient`，提供 `get_config` / `edit_config` / `rpc` 三个原语
- `vlan.py` 已实现 VLAN CRUD（NETCONF `<VLAN><VLANID>` 模型）
- H3C V7 设备 NETCONF 模型参考：
  - `Ifmgr/Interfaces/Interface`：物理/逻辑接口
  - `Ifmgr/Interfaces/Interface/Ipv4Address`：L3 接口的 IP 配置
  - `Ipv4Vrf/VRF`：VPN instance（即 VRF）
  - **待实地探测**：H3C V7 实际的 `Ipv4Vrf` 命名空间与必填字段

### 前端能力盘点

- 当前"接口管理"在设备详情页的 Modal 中展示（v2.1），未独立
- `ConfirmModal.vue` 已存在可复用
- `Select.vue` 组件已存在可复用

### 设备侧能力盘点（待探测）

- 192.168.100.4 (Leaf-03) 已有 VPN instance `MGMT`，绑在 `M-GigabitEthernet0/0/0` 上
- 需探测：VPN instance 创建时 RD 是否必填 / 默认值
- 需探测：NETCONF 删 VPN instance 时是否会因有绑定而失败

## Goals / Non-Goals

**Goals:**
- 接口列表展示层类型（L2/L3）+ IP 地址 + VPN instance 绑定
- VPN instance 创建 / 列表 / 删除（NETCONF 优先，SSH fallback）
- 接口绑/解绑 VPN instance（NETCONF 优先，SSH fallback）
- 真实设备 192.168.100.4 验证全流程
- 前端 Interface.vue 表格列扩展 + 联动配置 Modal

**Non-Goals:**
- **不做** VPN instance RD/RT 详细配置（用户原话"创建 vpn instance"未提 RD/RT，超出 v2.2 范围）
- **不做**"批量绑 VPN"（单次一个接口，避免误操作）
- **不做**三层接口创建（仅识别 + 展示 + 绑 VPN）
- **不做**子接口（`GigabitEthernet X.Y`）的 L2/L3 自动判定（v2.2 仅根据命名约定，列 follow-up）
- **不做**数据库持久化（VPN instance 永远从 NETCONF 实时拉取）

## Decisions

### 1. VPN instance 存储：不落库

- **选择**：每次查询 / 操作都走 NETCONF 实时拉取，**不**新建 ORM 表
- **理由**：
  - VPN instance 是设备配置的一部分，单一真相源（single source of truth）就是设备本身
  - 落库会带来"数据库和设备不一致"的同步问题（用户已删 VPN instance 但数据库还在）
  - 现有 VLAN 也走 NETCONF 实时（vlan.py 无 VlanModel 表），保持范式一致
- **替代**：
  - 落库 + 定时同步 → 复杂度高，无业务价值
  - 落库 + 写操作时同步 → 写失败 / 网络抖动时回滚难

### 2. L2/L3 判定：命名规则 + 字段存在双校验

- **选择**：
  1. **L3 强信号**：`name` 以 `Vlan-interface` 开头 → L3
  2. **L3 强信号**：`Ipv4Address` 子元素存在且非空 → L3
  3. **L3 强信号**：`name` 匹配正则 `^.+?\.\d+$`（子接口，如 `GigabitEthernet0/0/0.100`）→ L3
  4. **L2 默认**：其他情况 → L2
- **理由**：
  - 命名约定是 H3C 官方规范，覆盖 95% 场景
  - 字段存在性兜底，覆盖命名特殊但实际是 L3 的情况
- **风险**：命名不规范 / 子接口配 L2 时可能误判，列为 follow-up

### 3. NETCONF 优先 + SSH Fallback

- **选择**：
  - 优先 NETCONF edit-config（`Ipv4Vrf` / `Ifmgr/Interfaces/Interface/IpBindVrfInstance`）
  - NETCONF 探测失败 → fallback 到 SSH CLI（`ip vpn-instance X` / `interface X; ip binding vpn-instance Y`）
- **理由**：与现有"trunk allowed VLANs 必须 SSH"决策保持一致
- **实施**：
  - VPN instance 创建：NETCONF `<Ipv4Vrf><VRF><Name>X</Name><DefaultRD>auto</DefaultRD></VRF></Ipv4Vrf>`
  - 接口绑 VPN：NETCONF `<Ifmgr><Interfaces><Interface><IfIndex>N</IfIndex><IpBindVrfInstance>Y</IpBindVrfInstance></Interface></Interfaces></Ifmgr>`
  - 验证流程：先在 192.168.100.4 上探测上述 XML 是否被设备接受

### 4. 删除 VPN instance 的安全护栏

- **选择**：
  - `DELETE /api/devices/{id}/vpn-instances/{name}` 前**先**查询该 VPN instance 上是否还有绑定接口
  - 有绑定 → 返回 400 "VPN instance {name} 还有 N 个接口绑定，请先解绑"
  - 无绑定 → 执行删除 + record_log
- **理由**：H3C 设备直接删带绑定的 VPN instance 通常会失败，但预校验给出明确错误信息
- **替代**：直接交给设备报错 → 错误信息不友好

### 5. 二次确认 Modal 复用

- **选择**：
  - 创建 / 删除 VPN instance：复用 `ConfirmModal.vue`
  - 接口绑 / 解绑 VPN instance：复用 `ConfirmModal.vue`，标题"绑 VPN instance 到接口 {name}？"
  - 显示目标操作前后的关键信息（VPN instance 名 / 接口名）
- **理由**：与现有 CRUD 模式一致

### 6. 前端表格列扩展

- **选择**：
  - `interface` 列：现有
  - `mode` 列：现有
  - `pvid / allowed_vlans` 列：现有
  - **新增** `layer` 列：badge "二层"（灰） / "三层"（蓝）
  - **新增** `ip` 列：L3 时显示 IP，例 `192.168.100.4/24`，L2 时显示 "-"
  - **新增** `vpn_instance` 列：显示绑定的 VPN instance 名，例 "MGMT"，无绑定显示 "-"
- **理由**：与现有表格风格一致，纯展示

### 7. 联动配置入口：分两个动作

- **选择**：
  - 行操作列加 "创建 VPN" 按钮 → 弹 Modal 输入名 → 确认后创建 + 自动跳到绑定步骤
  - 行操作列加 "绑 VPN" 按钮 → 弹 Select 选已有 → 确认后绑定
- **理由**：用户原话"可以分为两个动作也行吧"
- **替代**：
  - 合并为一个 "VPN 配置" 按钮 → 内部多步骤，操作路径长
  - 顶层独立 "VPN 管理" 页面 → 单个 VPN 操作频率不高，过度设计

### 8. 设备能力探测与降级

- **选择**：
  - 启动时（`on_startup`）**不**做能力探测（避免启动阻塞）
  - 第一次用户调用 VPN instance 相关端点时探测：调用 NETCONF get-config `<Ipv4Vrf>` 试取
  - 探测失败 → 缓存"该设备不支持 NETCONF VPN"，后续走 SSH
  - 缓存粒度：进程内 dict（重启后重测）
- **理由**：避免每个请求都探测；进程内缓存够用（非分布式）

## Risks / Trade-offs

- **[风险] H3C V7 NETCONF VPN 模型不工作** → **缓解**：实施时探测；失败 fallback SSH；fallback 也失败时返回明确错误
- **[风险] 误删 VPN instance** → **缓解**：删除前预校验绑定 + 二次确认 Modal
- **[风险] L2/L3 误判** → **缓解**：命名规则 + 字段存在性双校验；误判仅影响展示，不影响写操作
- **[风险] RD 默认值 `auto` 在某些场景不工作** → **缓解**：探测时记录 RD 默认值实际行为；fallback 让用户输入
- **[风险] 并发绑 VPN**：同接口同时绑两个不同 VPN instance → **缓解**：H3C 设备会原子拒绝；无需应用层加锁
- **[权衡] 实时 NETCONF 拉取 vs 缓存**：实时拉取增加设备交互（每查询 1 次 get-config），但保证数据一致

## Migration Plan

- **数据库**：**无迁移**（VPN instance 状态走 NETCONF，不落库）
- **部署**：
  1. 改 `backend/app/routers/interface.py`（增 6 端点）
  2. 新建 `backend/app/utils/netconf_xml.py`（VPN instance XML 构造器）
  3. 改 `frontend/src/views/Interface.vue`（v2.2 第一个 change 已建）+ 表格列 + 联动按钮
  4. 新建 `frontend/src/components/VpnInstanceBindModal.vue`
- **回退**：git revert 即可，无迁移
- **数据**：无历史数据迁移
- **测试**：
  1. 192.168.100.4 上识别 M-GigabitEthernet0/0/0 为 L3 + 显示绑定的 MGMT VPN
  2. 创建新 VPN instance `TEST_VPN` → 设备 `display ip vpn-instance` 能看到
  3. 把 TEST_VPN 绑到一个未用接口 → NETCONF get-config 能查到
  4. 解绑 → 设备 `display ip vpn-instance interface` 不再显示该接口
  5. 删 TEST_VPN（无绑定）→ 设备 `display ip vpn-instance` 不再显示
  6. 删 MGMT（带绑定）→ 后端返回 400 错误，UI 提示解绑
