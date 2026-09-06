# Release Notes v3.4.0

> 发布日期：2026-09-06
> 主题：SDN/VPC 工作台 + UX
> OpenSpec：`v34-sdn-vpc-workspace`

## 背景

v3.3 已经完成 VPC/EVPN 后端配置闭环，但用户还需要在多个 API 与部署记录之间切换，才能完成创建 VPC、选择 EVPN Leaf、生成变更、绑定接入口、扩容和同步状态。

v3.4 将这些能力收束到前端“运营管理 → SDN / VPC”工作台。首轮目标不是一次性做完整大屏，而是先把 v3.3 的后端能力变成用户能点、能看、能判断下一步的运维入口。

## 完成范围

- 新增 SDN/VPC 工作台页面与导航入口：
  - VPC 清单；
  - 选中 VPC 详情；
  - 当前 VPC 的设备落地；
  - 创建 VPC；
  - 接入口扩容；
  - 概览与状态；
  - 轻量拓扑。
- 新增前端 `sdnApi` 客户端：
  - tenant / VPC 创建与列表；
  - deployment 列表；
  - VPC deploy / withdraw；
  - port binding；
  - expansion；
  - validation sync / latest。
- 增加状态解释与最佳实践弹层：
  - 解释 pending / planned / active / degraded / failed / withdrawn；
  - 区分“创建 VPC 只写平台”和“生成变更单/立即执行才影响设备”；
  - display 状态采用手动同步，不做高频轮询。
- 增加中英文 i18n 文案。
- 增加前端组件测试，覆盖核心渲染、下发变更、状态同步、最佳实践弹层、接口列表不可用时手填 `if_index`。

## 关键修复与设计收口

- SDN/VPC 目标设备准入从“名字/平台推断”改为显式 `sdn_role`：
  - 只有 `sdn_role=evpn_leaf` 的设备可作为 VPC 下发、撤回、校验和扩容目标；
  - `platform=LSTN/RSTN` 只表示配置通道和设备能力，不再表示 Fabric 成员身份；
  - 名字像 Leaf 但未标记 `evpn_leaf` 的接入设备不会混入目标列表。
- 设备管理新增 SDN 角色字段：
  - `evpn_leaf`；
  - `evpn_spine`；
  - `access`；
  - 未设置。
- 后端显式拒绝非 EVPN Leaf 设备参与 SDN/VPC 操作，避免误下发到接入交换机。
- VPC 列表 `binding_count` 改为按 `sdn_port_bindings` 真实统计，避免页面总数和详情计数不一致。
- Vite split proxy 增加 `/api/sdn/*` 到 config 容器路由，保证前端工作台在 split 模式下可用。

## 现场数据整理

本次发布过程中，在本地运行库中手工登记了现网存量 VPC，用于页面联调和状态查看：

- `vpc-192-168-1-legacy`
  - `192.168.1.0/24`
  - `vpna`
  - `VNI 10`
  - `Vsi-interface1`
  - `gateway 192.168.1.254`
  - `gateway MAC 0001-0001-0001`
  - `.2/.3` 两个接入口绑定
- `vpc-192-168-2-legacy`
  - `192.168.2.0/24`
  - `vpnb`
  - `VNI 20`
  - `Vsi-interface2`
  - `gateway 192.168.2.254`
  - `gateway MAC 0002-0002-0002`
  - `.2/.3` 两个接入口绑定

这些是本地数据整理，不属于 Git 代码发布内容。它们标记为 `auto_assigned=false`，表示不是平台自动下发创建的资源。

## QA

```bash
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend pytest
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-frontend
openspec validate v34-sdn-vpc-workspace --strict
git diff --check
```

结果：

- 后端全量 pytest：469 passed / 23 skipped / 5 warnings
- 前端完整 QA：lint、type-check、build、60 unit、42 e2e 全部通过
- OpenSpec strict validate：通过
- diff check：通过

## 浏览器验证

- 页面地址：`http://localhost:5173/#/sdn-vpc`
- API：
  - `/api/sdn/tenants` 200；
  - `/api/sdn/vpcs` 200；
  - `/api/devices` 200；
  - `/api/sdn/port-bindings` 200；
  - `/api/sdn/deployments` 200；
  - `/api/sdn/vpcs/{id}/devices/{id}/validation/latest` 200。
  - `/favicon.svg` 200。
- 页面可见：
  - VPC 清单；
  - 当前 VPC 详情；
  - EVPN Leaf 目标选择；
  - 创建 VPC；
  - 接入口扩容；
  - 端口绑定；
  - 部署记录；
  - 状态快照；
  - 轻量拓扑；
  - 最佳实践弹层。
- 浏览器控制台无 error/warn。
- 接口列表不可用时，页面保留手填 `if_index` / 接口名称降级路径。

## 边界

- 不做完整实时大屏。
- 不做 5 秒级 display 轮询。
- 不引入 d3 / echarts / vis.js。
- 不做 ops-toolkit VPC/EVPN 专用探测脚本。
- 不做存量 VPC 自动发现/自动认领；本次只允许人工登记存量数据用于当前环境整理。
- 不替代 v3.3 后端配置执行与状态校验逻辑。
