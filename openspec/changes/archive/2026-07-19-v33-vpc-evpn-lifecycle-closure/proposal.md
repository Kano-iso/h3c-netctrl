# v33-vpc-evpn-lifecycle-closure

## Why

v3.0 已经具备 VPC 数据模型、配置模板和 create deployment 下发能力，但业务闭环仍停在“能生成/能下发创建配置”。用户视角下还缺少端口接入、撤回、局部撤回、状态回写等动作，导致平台不能支撑“端口随接随入”和 VPC 生命周期管理。

v3.3 的目标是把已沉淀的 EVPN/VXLAN 模板能力接成可操作的后端闭环：创建、下发、端口绑定、端口解绑、整 VPC 撤回、三层网关局部撤回。

## What Changes

- 扩展 SDN deployment action，支持 `delete`、`port_bind`、`port_unbind`、`gateway_delete`。
- 新增端口绑定 API：创建、查询、删除未激活绑定、生成绑定/解绑 deployment。
- 新增 VPC 三层网关撤回 API：只生成 Vsi-interface 撤回 deployment，不删除 L2 VSI/EVPN。
- deployment 成功执行后回写 VPC 或端口绑定状态，前端可以直接基于资源状态展示。
- deployment 增加 `port_binding_id`，保留端口级审计链路。
- 新增 display 手动同步与 latest 快照读取，围绕 `{vpc_id, device_id}` 校验 BGP EVPN peer、VSI/Vsi-interface、AC、MAC、ARP、Type-2/Type-3。

## Non-Goals

- 不做前端大屏和完整产品化页面。
- 不做批量作业编排器。
- 不碰现有管理接口和已有业务配置。
- 不引入实时高频设备采集；本 change 只提供手动同步与 600 秒缓存的 display 校验闭环。
