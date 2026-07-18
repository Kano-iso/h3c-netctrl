# v312-ztp-onboard-and-asset-sync — Proposal

> 状态：Propose → Apply
> 版本：v3.1.2
> 日期：2026-07-18

## 背景

v3.1.1 已完成 ZTP 落地：设备空配置启动后可以通过 DHCP/TFTP 拉取 autocfg.cfg，并把 physical OOB 口写入 static 管理地址。下一步不是监听 DHCP lease，而是基于这个 static 管理地址完成平台纳管。

原 v3.1.2“自动纳管”和 v3.1.3“资产可见”合并为本 change：后端把设备写入 `devices` 与 `assets`，前端通过现有 Devices / CMDB / Dashboard 接口自然可见。

## 范围

- 新增 ZTP onboard API：输入 static 管理地址、可选名称/平台/凭据，完成设备创建或更新。
- 纳管前执行 SSH 22 / NETCONF 830 探测，失败返回明确原因。
- 纳管成功后触发资产采集；采集成功写入 CMDB，失败保留设备记录并标记资产 offline。
- split 模式下 ctrl 负责 device，data 负责 asset；通过 internal API 同步资产。
- QA 使用虚构 IP 与 mock SSHExecutor，不连真实设备，覆盖增删改查式闭环。

## 不做

- 不监听 DHCP lease。
- 不做专门 ZTP 前端页面。
- 不推 VPC / 端口绑定 / 路由协议 / 业务 VLAN。
- 不把业务逻辑放进 ops-toolkit。

## 验收

- 给定一个 static 管理 IP，`POST /api/ztp/onboard` 可创建设备与资产。
- 同一 host 重复 onboard 幂等更新，不产生重复设备。
- 资产采集成功时 CMDB 状态为 online，并写入 model / serial / firmware / software。
- 资产采集失败时接口返回 partial，设备仍入库，资产状态为 offline。
- `GET /api/devices`、`GET /api/assets/device/{id}`、Dashboard 统计能看到结果。
- QA 容器中 mock 测试通过。
