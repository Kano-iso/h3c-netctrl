# NEXT S1 可信业务工作台

## Why

S1 后端已具备接入预览、幂等执行、逐单元尝试、验证、对账和受控撤回，但现有前端仍以配置表单和设备动作分区，用户无法围绕一个 VPC 看清接入位置、终端和一次操作的真实过程。

## What Changes

- 将现有 SDN/VPC 页面重构为同一平台内的业务工作台，不建立第二套门户。
- 以 VPC 为主上下文，聚合覆盖节点、端口绑定、终端观测、校验时间与操作记录。
- 新增“接入终端”引导流程，真实调用 preview、execute、complete、withdraw 和 reconcile API。
- 状态分别表达配置、业务验证和证据完整性；未知、过期、待接线不冒充成功或失败。
- 保留 VPC 创建、部署等现有能力的入口，但不让其挤占日常接入主流程。

## Capabilities

### Modified Capabilities

- `sdn`: 增加 N1-01 至 N1-10 对应的前端工作台、接入流程和操作过程展示。

## Impact

- 前端：`SdnVpcWorkspace.vue`、API 客户端、i18n 与组件测试。
- 后端：不新增执行逻辑，直接消费 `next-s1-backend` 已复审契约。
- 设备：常规前端 QA 使用 mock，不连接设备；实景点测另行确认。

