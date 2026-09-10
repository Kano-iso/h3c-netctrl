# S1-019 真机恢复清单（Recovery Manifest）

> 本文件不含凭据。状态原子更新，供 Codex 在 Harness 断线后人工恢复。
> 唯一测试名：`s1-019-nxt-real`。
>
> **S1-021 修订**：S1-020 历史执行时仓库内尚无自动 runner，共享对象兜底清理由**测试外的 ops-toolkit** 监督执行（见下「状态」表）。S1-021 起真机轮次一律走唯一宿主安全 runner `openspec/changes/next-s1-backend/qa/run_s1_019_real_lifecycle.sh`：pytest 前自动核对本清单基线、共享对象基线已存在则拒绝承担所有权、进入可写阶段后 trap 自动执行第 3 步精确兜底清理 + 最终 readback。本清单第 3 步的 undo 命令即 runner 的兜底命令集（system-view + undo sdn_l3vpn + undo vxlan + return）。

## 目标与范围

| 项 | 值 |
|---|---|
| 目标设备 | `.5 / 192.168.100.5 / SWC / S6850 T7064P15 / LSTN` |
| 设备身份交叉确认 | prompt `<SWC>` + `display version` S6850 T7064P15 + `display bgp peer l2vpn evpn` local Router ID `1.1.1.4`（peer `1.1.1.1` Established） |
| 允许写入接口 | 仅 `GigabitEthernet1/0/10` |
| 禁止 | 管理口 `MGE0/0/0`、`GE1/0/1～3`、underlay/OSPF/BGP 邻居、`.6`、`save`/startup-config |

## 基线（写入前已 readback，2026 本轮实测）

| 对象 | 基线 |
|---|---|
| `display l2vpn vsi verbose` | 空（无 VSI） |
| `display bgp l2vpn evpn` | `Total number of routes: 0` |
| `display bgp peer l2vpn evpn` | local Router ID `1.1.1.4`，peer `1.1.1.1` Established |
| `display current-configuration interface GigabitEthernet1/0/10` | `port link-mode bridge` + `combo enable fiber`（无 service-instance / xconnect） |
| `display current-configuration \| include sdn_l3vpn` | 无（仅存在 `ip vpn-instance mgt`） |
| `display current-configuration \| include vxlan` | 无（无 `vxlan tunnel mac-learning disable`） |

## 本轮预期新建对象（隔离库首个 tenant/VPC 的自动分配）

| 对象 | 预期值 | 归属 |
|---|---|---|
| tenant l3_vni | `10000` | 本轮新建 |
| VPC L2VNI / RD | `20000` / `1:20000` | 本轮新建 |
| VSI 名 | `vpc0001`（`vpc{vpc_id:04d}`） | 本轮新建 |
| Vsi-interface | `Vsi-interface1000` | 本轮新建 |
| 共享 L3VPN 实例 | `sdn_l3vpn`（RD `1:10000` + address-family evpn） | 本轮新建，**产品保留不删**，需兜底清理 |
| 全局 VXLAN | `vxlan tunnel mac-learning disable` | 本轮新建，**产品保留不删**，需兜底清理 |
| 端口接入 | `GE1/0/10` + `service-instance 3200` + xconnect `vsi vpc0001` | 本轮新建 |

## 清理顺序与命令（兜底仅限恢复清单证明的本轮新建对象）

1. 产品 API：access withdraw（`POST /api/sdn/operations/{op_id}/withdraw`）→ 解绑端口，删 AC/xconnect。
2. 产品 API：VPC withdraw（`POST /api/sdn/vpcs/{vpc_id}/withdraw`，auto_apply=true）→ delete deployment（undo EVPN RD / undo Vsi-interface / undo VSI）。
3. 兜底（仅基线不存在、产品保留的共享对象，走 ops-toolkit `paramiko-batch-exec.sh --device 192.168.100.5`）：
   - `undo ip vpn-instance sdn_l3vpn`
   - `undo vxlan tunnel mac-learning disable`
4. 前后 readback：`display l2vpn vsi verbose`、`display bgp l2vpn evpn`、`display current-configuration interface GigabitEthernet1/0/10`、`display current-configuration | include sdn_l3vpn`、`display current-configuration | include vxlan`。

## 状态（原子更新）

> S1-020 修复「首次接入自阻断」后，同一测试名 `s1-019-nxt-real` 于 2026-09-10 重跑一轮**完整生命周期**（execute/apply/complete 不再被 vsi_up 阻断）；本表为最新一轮结果。S1-019 首轮的「execute 诚实阻断 / apply/complete 未执行」已被本轮取代。

| 步骤 | 状态 | 时间 | 备注 |
|---|---|---|---|
| 基线 readback | ✅ done | 本轮 | 见上，全部为空 |
| VPC create/apply | ✅ done | 本轮 | 5 unit 成功下发（LSTN SSH22） |
| display 采集 + Type-3 scoped 核对 | ✅ done | 本轮 | vsi_exists/bgp_peer/type3_present=True（目标 RD 1:20000 块内 [3]）；vsi_up=False（无 AC，S1-020 起不阻断首个 AC） |
| GE1/0/10 access preview → execute | ✅ done | 本轮 | preview `predeploy_status=ready`；execute 成功建 operation（不再 sdn.predeploy_unknown） |
| GE1/0/10 access apply | ✅ done | 本轮 | port_bind 1 unit 成功；回读确认 `service-instance 3200` + `xconnect vsi vpc0001` 实际存在 |
| access complete | ✅ done（诚实） | 本轮 | 无下联主机 → `status=degraded`、`host_observed=False`（不冒充业务成功） |
| access withdraw | ✅ done | 本轮 | port_unbind 1 unit 成功；回读确认 service-instance/xconnect 已撤销 |
| VPC withdraw | ✅ done | 本轮 | delete deployment（3 unit）成功，VSI/Vsi-interface/RD 移除 |
| 兜底清理 sdn_l3vpn + vxlan global | ✅ done | 本轮 | ops-toolkit `undo ip vpn-instance sdn_l3vpn` + `undo vxlan tunnel mac-learning disable`，4/4 rc=0 |
| 最终 readback 确认残留为空 | ✅ done | 本轮 | VSI 空 / routes 0 / 无 sdn_l3vpn / 无 vxlan / 无 service-instance / GE1/0/10 回基线 |
| DB 收尾 | ✅ done | 本轮 | active_bindings=0 / unreleased_claims=0 |
