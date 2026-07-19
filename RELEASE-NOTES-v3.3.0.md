# Release Notes v3.3.0

> 日期：2026-07-19
> 主题：VPC/EVPN 配置闭环
> OpenSpec：`v33-vpc-evpn-lifecycle-closure`

## 背景

v3.0 已经完成 SDN/VPC 业务下发通道骨架，v3.1 完成 ZTP 上线与恢复能力。v3.2 原计划做新平台迁移与能力评级，但受 HCL/177 镜像升级限制、EVE/V9850 二层广播不可信等环境因素影响，已转为未来迁移待办。

v3.3 因此不再等待新平台，直接在现有可控平台上补齐 VPC/EVPN 后端生命周期，让 VPC 能从“能生成配置”推进到“能下发、能撤回、能局部操作、能校验状态”。

## 完成范围

- VPC 级下发与撤回：
  - `POST /api/sdn/vpcs/{vpc_id}/deploy`
  - `POST /api/sdn/vpcs/{vpc_id}/withdraw`
  - 未指定设备时按 Leaf 候选展开；指定 `device_ids` 时按用户选择执行。
- 端口绑定生命周期：
  - 创建、查询、删除端口绑定；
  - 生成并执行 `port_bind` / `port_unbind` deployment；
  - 绑定成功后回写 binding 状态。
- 单设备 VPC 补回：
  - 复用 VPC 保存的 RD/VNI/VSI/Vsi-interface/gateway 定义；
  - 不允许调用方临时重填关键网络参数。
- 三层网关局部操作：
  - 支持单设备 VPC 网关撤回；
  - 支持单设备 VPC 网关加回；
  - 只操作 `vsi-l3` unit，不重建 L2 VSI/EVPN。
- 已有 VPC 接入口扩容：
  - 只允许选择 Leaf 设备；
  - 继承 VPC CIDR、网关、VNI、VSI；
  - 可选填写期望主机 IP；
  - 扩容完成时执行网关源地址 ping 与 display 校验。
- display 状态采集闭环：
  - 手动同步 API；
  - latest 快照 API；
  - 默认 600 秒缓存，避免高频 SSH；
  - 校验 BGP EVPN peer、VSI/Vsi-interface、AC、MAC、ARP、Type-2/Type-3，并写入 `sdn_validation_snapshots`。

## 关键修复

- VPC delete 顺序修正：先清 EVPN/RD，再删 Vsi-interface，最后删 VSI。
  - 真机发现如果先 `undo vsi`，后续再进入同名 `vsi <name>` 清 EVPN，会把空壳 VSI 重新创建出来。
- deployment 增加端口绑定审计关联：
  - `sdn_deployments.port_binding_id`
  - 可追踪“哪次配置下发/撤回对应哪个端口绑定”。
- VPC 状态与 binding 状态回写补齐：
  - 支持 `pending / deploying / active / expanding / degraded / withdrawn / failed` 等状态在用户动作后落库。

## 真机验证

验证设备：`.5 / Leaf-04 / 192.168.100.5`

完成项：

- VPC create：设备侧成功生成 VSI、EVPN、Vsi-interface、L3VNI、VPN binding。
- VPC delete：撤回后不再残留空壳 VSI / Vsi-interface。
- port-bind / port-unbind：使用 `GigabitEthernet1/0/10 + service-instance 3310` 验证，测后接口恢复默认配置。
- gateway-only withdraw：只删除 `Vsi-interface1001`，保留 L2 VSI / EVPN。
- 本地下联数据面：
  - 使用 `GigabitEthernet1/0/2` 下联主机 `192.168.2.2`；
  - 网关源地址 `192.168.2.254` ping 主机 5/5 成功；
  - 设备学到 MAC 与 ARP；
  - 生成 Type-2 与 Type-3 EVPN 路由，并向 `1.1.1.1` 通告。
- 扩容演示：
  - `GigabitEthernet1/0/3` 接入 `192.168.1.3`；
  - 扩容完成接口返回成功；
  - 该演示配置当前保留，用于后续前端联调。

未完成但不阻塞：

- 远端同 VNI 主机互通。
- 远端 Type-2 回灌。

原因是当前实验条件缺少另一台可控 Leaf + 下联主机组合；该项转入后续环境具备后的验证任务。

## QA

```bash
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend pytest tests/test_sdn_api.py tests/test_sdn_deployment_api.py tests/test_sdn_apply_endpoint.py tests/test_sdn_deployment_executor.py tests/test_sdn_port_binding_api.py tests/test_sdn_fabric_api.py tests/test_sdn_validation_api.py tests/test_sdn_expansion_api.py tests/test_vpc_config_planner.py tests/test_templates_h3c_v7.py
openspec validate v33-vpc-evpn-lifecycle-closure --strict
git diff --check
```

结果：

- 后端 SDN 相关测试：`121 passed, 5 warnings`
- OpenSpec strict validate：passed
- diff check：passed

## 边界

- 不做前端大屏和完整产品化页面，前端集中放到 v3.4。
- 不做批量作业编排器。
- 不动已有管理接口和已有业务配置。
- 不做高频自动采集，当前采用手动同步 + 600 秒缓存。
- v3.2 平台迁移仍为未来待办，不阻塞本版本。
