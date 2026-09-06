# v34-sdn-vpc-workspace

## Why

v3.3 已经完成 VPC/EVPN 后端配置闭环，但前端仍没有一个面向用户的入口。用户现在需要理解多个 API 与 deployment 细节，才能完成“创建 VPC、下发到 EVPN 节点、绑定端口、扩容、同步状态”等动作。

v3.4 首轮目标是把这些后端能力收束成一个可用的 SDN/VPC 工作台，先解决日常使用路径，再逐步扩展端口大屏与拓扑视图。

## What Changes

- 调整 PRD-V3.4：从一次性“大屏全量蓝图”收敛为 P0 工作台 + P1 大屏/拓扑增强。
- 新增前端 `SdnVpcWorkspace.vue`，挂到运营管理导航。
- 新增 `sdnApi` 前端客户端，覆盖 tenant/vpc/binding/deployment/validation/expansion 常用入口。
- 工作台提供：
  - VPC 列表与详情；
  - 租户与 VPC 创建；
  - VPC 下发/撤回变更单；
  - 端口绑定与已有 VPC 扩容；
  - validation 手动同步与 latest 快照；
  - 基于现有数据的端口矩阵和轻量拓扑。
- 收紧 SDN/VPC 目标设备准入：只有 `sdn_role=evpn_leaf` 的 EVPN Fabric 成员可被选择或显式传入，设备名、型号和 `platform=LSTN/RSTN` 不再作为准入依据。
- 增加中英文 i18n 文案与前端单测。

## Non-Goals

- 不做高频 5s display 轮询。
- 不引入 d3/echarts 等新可视化库。
- 不做 ops-toolkit-probes，后续结合真实排障痛点单独起 change。
- 不替代 v3.3 后端的配置执行与状态校验逻辑。
