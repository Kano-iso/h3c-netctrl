# EVPN/VXLAN 192.168.1.1-192.168.1.2 阶段性只读分析

日期：2026-07-07

范围：只读 `display` 观察，不改设备配置。

## 背景

当前实验目标是理解 EVPN/VXLAN 架构下，下联主机 `192.168.1.1` 与 `192.168.1.2` 未能互通的原因。用户说明 underlay / overlay / BGP EVPN 已基本配置，`display bgp l2vpn evpn` 两边能收到二类路由；本轮聚焦配置与状态分析，不做下发修改。

## 已观察设备角色

- `192.168.100.2`：SWA，VTEP `1.1.1.2`，承载 `vpna`/`vpnb`，VNI 10/20，L3VNI 3000。
- `192.168.100.3`：SWB，VTEP `1.1.1.3`，承载 `vpna`/`vpnb`，VNI 10/20，L3VNI 3000。
- `192.168.100.4`：LEAF03_TEST，下联二层接入交换机；GE1/0/1 trunk 允许 VLAN 100/200，GE1/0/3 access VLAN 100，GE1/0/2 access VLAN 200。
- `192.168.100.6`：SWD，RR/Spine 角色，BGP EVPN RR，已与 `1.1.1.2`、`1.1.1.3` Established；对 `1.1.1.4`、`1.1.1.5` 是 Connect。

## 关键证据

### 1. Underlay 与 EVPN peer 基本正常

- `192.168.100.6` OSPF 邻居：`1.1.1.2`、`1.1.1.3` Full。
- `192.168.100.6` BGP EVPN peer：`1.1.1.2`、`1.1.1.3` Established。
- SWA/SWB 到 RR 的 BGP EVPN peer 均 Established。

### 2. Type-2 MAC/IP 路由已经互相学习

SWA 上 `display bgp l2vpn evpn`：

- `RD 1:10` 本地 `192.168.1.2 / 96ba-d8a7-0606`。
- `RD 1:10` 远端 `192.168.1.1 / 96ba-e33b-0906`，NextHop `1.1.1.3`。

SWB 上反向成立：

- 本地 `192.168.1.1 / 96ba-e33b-0906`。
- 远端 `192.168.1.2 / 96ba-d8a7-0606`，NextHop `1.1.1.2`。

### 3. VXLAN L2 tunnel 与 VSI MAC 转发表也存在

SWA：

- VNI 10 `vpna` tunnel：`1.1.1.2 -> 1.1.1.3` UP。
- `display l2vpn mac-address vsi vpna`：
  - 本地 MAC `96ba-d8a7-0606` 在 `GE1/0/2`。
  - 远端 MAC `96ba-e33b-0906` 在 `Tunnel0`。

SWB：

- VNI 10 `vpna` tunnel：`1.1.1.3 -> 1.1.1.2` UP。
- `display l2vpn mac-address vsi vpna`：
  - 本地 MAC `96ba-e33b-0906` 在 `GE1/0/2`。
  - 远端 MAC `96ba-d8a7-0606` 在 `Tunnel0`。

这说明“EVPN 二类路由未学习”或“VNI 10 没隧道”不是当前最强假设。

### 4. 下联 `.4` 的二层接入状态正常

`192.168.100.4`：

- GE1/0/1 trunk，tagged VLAN 100/200。
- GE1/0/3 access VLAN 100，学到 `96ba-e33b-0906`。
- GE1/0/2 access VLAN 200，学到 `96ba-e0c3-0806`。

SWB GE1/0/2 上 service-instance 1000/2000 均 Up，分别接 `vpna`/`vpnb`。

### 5. 最可疑点：同网段主机路由被导向 L3VNI Vsi3

SWA 上查 `192.168.1.1`：

- 同时存在直连 `192.168.1.0/24 -> Vsi1`。
- 也存在 BGP `/32 192.168.1.1 -> 1.1.1.3 -> Vsi3`。
- 按最长匹配，去 `192.168.1.1` 会选 BGP `/32`，出接口 `Vsi3`。

SWB 上查 `192.168.1.2` 也是同样模式：

- 直连 `192.168.1.0/24 -> Vsi1`。
- BGP `/32 192.168.1.2 -> 1.1.1.2 -> Vsi3`。

两端都配置了：

- `Vsi-interface1`：`local-proxy-arp enable`、`distributed-gateway local`。
- `Vsi-interface3`：`ip binding vpn-instance l3vpn`、`l3-vni 3000`。

这意味着 `.1.1 <-> .1.2` 可能不是单纯通过 VNI 10 二层桥接，而是被分布式网关/本地代理 ARP/主机路由引导到 L3VNI 路径。

### 6. L3VNI 3000 状态异常/未形成可用承载

SWA/SWB：

- `Vsi-interface3` 本身 UP。
- 但自动 VSI `Auto_L3VNI3000_3` 是 Down。
- `display vxlan tunnel-interface` 只看到一条 `.2 <-> .3` 的 Tunnel0，没有看到 L3VNI 3000 独立承载状态。
- `display l2vpn vsi name Auto_L3VNI3000_3 verbose` 无 AC、无 tunnel，VSI State Down。

因此，如果同网段主机互访实际走 `/32 -> Vsi3` 的 L3VNI 路径，当前 L3VNI 状态非常可疑。

### 7. RT 差异：可能影响三层互通/Type-5，但未必是 `.1.1 <-> .1.2` 的唯一根因

SWA `l3vpn`：

- `RD 1:200`
- import/export `20:20`
- import/export `30:30`

SWB `l3vpn`：

- `RD 1:300`
- 只看到 import/export `30:30`

这与拓扑图里“IPv4RT 20:20 / EvpnRT 30:30”的期望不完全一致。该差异会影响三层 VPN/Type-5 路由互引。当前同网段主机 `/32` EVPN ARP/host route 已经存在，所以暂不把它定为唯一根因，但它是后续必须讨论的配置一致性问题。

## 暂时关闭/降级的猜想

- “BGP EVPN peer 没起来”：已关闭，SWA/SWB/RR 相关 peer Established。
- “Type-2 MAC/IP route 没学到”：已关闭，两端都有对方 `.1.1/.1.2` 的 MAC/IP route。
- “VNI 10 没隧道”：已关闭，`vpna` 的 VXLAN tunnel UP。
- “下联 `.4` VLAN 100 没学到主机 MAC”：已关闭，`.4` GE1/0/3 学到 `96ba-e33b-0906`。
- “SWB 下联 AC 没 Up”：已关闭，GE1/0/2 service-instance 1000/2000 均 Up。
- “ping display 是强证据”：降级。当前 SSH 工具对 H3C ping 输出截取不完整，只作为辅助现象，不作为结论依据。

## 阶段性判断

当前最强假设：

1. L2 EVPN 控制面与 VNI 10 MAC 转发表大体正常。
2. 由于 `local-proxy-arp enable` + `distributed-gateway local` + EVPN host `/32` 路由，`.1.1 <-> .1.2` 这类同网段访问可能被设备导向 `Vsi3` L3VNI 路径。
3. 但两端 `Auto_L3VNI3000_3` 为 Down，且 L3VNI/RT 配置存在不一致，导致经 `Vsi3` 的转发路径不可用或不完整。

因此，当前排查重心建议从“为什么 VNI 10 二层没学路由”转为“本地代理 ARP/分布式网关是否让同网段主机流量走 L3VNI，以及 L3VNI 3000 为什么未形成可用承载”。

## 后续建议，不在本轮执行

- 与用户一起确认实验目标：`.1.1 <-> .1.2` 是期望纯二层桥接，还是期望走分布式网关代理 ARP + L3VNI。
- 若期望纯二层桥接：讨论是否应临时关闭/调整 local-proxy-arp 或避免同网段 host route 干预。
- 若期望分布式网关：优先补齐 L3VNI 3000 的设计与配置一致性，确认 `Auto_L3VNI3000_3` Down 的原因。
- 对齐 SWA/SWB 的 `l3vpn` RT 策略，尤其 `20:20` 与 `30:30` 的 import/export 边界。
- 后续如果要验证主机侧，需要通过 VSI-interface/设备侧可用工具或打开 VM SSH/console；当前 VM 无 SSH 时，主机侧证据有限。

## 2026-07-08 补充观察

用户补充了 SWA 上的本地网关 ping：

```text
ping -a 192.168.2.254 -vpn-instance l3vpn 192.168.2.1
1 packet(s) transmitted, 0 packet(s) received, 100.0% packet loss
```

随后补查 SWA 本地路径：

- `display ip routing-table vpn-instance l3vpn 192.168.2.1` 只命中直连 `192.168.2.0/24 -> Vsi2`。
- `display arp vpn-instance l3vpn` 动态学到 `192.168.2.1 -> 96ba-ddca-0706 -> vpnb -> GE1/0/3`。
- `display l2vpn service-instance interface GigabitEthernet 1/0/3` 显示 `GE1/0/3 srv2000 -> vpnb` 为 Up。
- `display l2vpn mac-address vsi vpnb verbose` 显示 `96ba-ddca-0706` 是本地 Dynamic MAC，出接口 `GE1/0/3`。

这条失败不经过远端 VTEP、RR、EVPN Type-2 学习或 L3VNI 3000；它是 SWA 本地 `Vsi2` 网关到本地接入主机 `192.168.2.1` 的直连访问。当前更强的判断是：

1. `192.168.2.1` 的二层接入与 ARP 学习已经成立。
2. SWA 已经知道目的主机 MAC 与本地出接口。
3. ICMP Echo 没有收到 Echo Reply，问题更可能落在主机侧 IP/防火墙/网卡栈/回包路径，或主机并不响应来自 `192.168.2.254` 的 ICMP。

因此，在继续追 EVPN/L3VNI 前，应优先证明本地接入主机是否能响应本网关 ICMP。若本地网关到本地主机都不通，跨 VTEP 互通问题会被主机侧问题掩盖。

## 2026-07-08 破案补充：VXLAN tunnel 数据面学习与分布式网关冲突

用户执行全局学习抑制后，业务恢复：

```text
vxlan tunnel mac-learning disable
vxlan tunnel arp-learning disable
```

执行前，SWA 的 `display l2vpn mac-address` 曾出现异常表项：

```text
0001-0001-0001 Dynamic vpna Tunnel0 Aging
```

`0001-0001-0001` 是 Vsi-interface1 的网关 MAC，不应该作为普通动态 MAC 从 VXLAN Tunnel0 学回来。该表项很可能来自远端 SWB 的分布式网关接口/网关响应报文；当 VXLAN tunnel 数据面 MAC learning 未关闭时，SWA 会把远端 tunnel 中出现的源 MAC 当作普通二层 MAC 学入 `vpna`。

这会与 EVPN 分布式网关控制面冲突：

1. EVPN 已经通过控制面发布主机 MAC/IP、网关 GL、远端 BGP 表项。
2. VXLAN tunnel 又通过数据面学习到网关 MAC，并把它标记为 `Dynamic -> Tunnel0`。
3. 网关 MAC 被当作远端普通 MAC 后，本地 Vsi-interface 的 ARP 应答/网关收包处理可能被干扰。
4. 表面现象就是：ARP 表、EVPN route arp、VSI、AC 都对，但本地网关不回下联主机 ARP。

禁用 VXLAN tunnel MAC/ARP 学习后，SWA 当前只保留 EVPN 控制面学习到的远端主机 MAC：

```text
96ba-e33b-0906 EVPN vpna Tunnel0
96ba-e0c3-0806 EVPN vpnb Tunnel0
```

网关 MAC 不再作为 `Dynamic -> Tunnel0` 出现，分布式网关 ARP 行为恢复。

结论：后续 v3.0 自动化下发 EVPN/VXLAN fabric 时，`vxlan tunnel mac-learning disable` 至少应作为分布式网关场景的强制前置项；`vxlan tunnel arp-learning disable` 也应纳入同一能力模板进行确认。
