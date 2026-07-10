# sdn-vpc-device-templates — Tasks

> 每个 Task = 1 commit，符合 OpenSpec "小步增量" 规范

---

## Task 1: i18n error_key 扩展（前置，6 个新错误码）

- [ ] `backend/app/i18n_keys.py` 追加 6 个 SDN 错误码
  - `SDN_DEVICE_MODEL_UNSUPPORTED`
  - `SDN_PREFLIGHT_FAILED`
  - `SDN_VPC_ALREADY_EXISTS`
  - `SDN_VLAN_CONFLICT`
  - `SDN_BGP_PEER_NOT_ESTABLISHED`
  - `SDN_L3VPN_NOT_FOUND`
- [ ] 中英双语翻译
- [ ] commit: `feat(sdn): add 6 i18n error_key for device templates`

## Task 2: SdnDeviceAdapter 设备型号适配层

- [ ] `backend/app/services/__init__.py` 新增
- [ ] `backend/app/services/sdn_device_adapter.py` 新增
- [ ] 基类 `SdnDeviceAdapter`（abstract）
- [ ] 实现 `H3cV7Adapter`：SUPPORTED_MODELS + `supports_model()` + `get_template()`
- [ ] 型号不匹配返 `SDN_DEVICE_MODEL_UNSUPPORTED`
- [ ] commit: `feat(sdn): add SdnDeviceAdapter + H3cV7Adapter`

## Task 3: H3C V7 vpc_create_template 模板

- [ ] `backend/app/services/templates/__init__.py` 新增
- [ ] `backend/app/services/templates/h3c_v7_vpc_create.py` 新增
- [ ] 模板拼装：vsi / vxlan / evpn / vpn-instance / vsi-interface
- [ ] 变量替换：{vsi_name} / {vni} / {rd} / {gateway_ip} 等
- [ ] 第 1 轮 RD = 1:vni/10 + 共享 l3vpn + 省略 import-rt/export-rt
- [ ] commit: `feat(sdn): add h3c_v7 vpc_create_template`

## Task 4: VPCConfigPlanner 配置计划生成器

- [ ] `backend/app/services/vpc_config_planner.py` 新增
- [ ] `plan_vpc_create(vpc, tenant) -> List[ConfigCommand]`
- [ ] `plan_vpc_delete(vpc) -> List[ConfigCommand]`
- [ ] `plan_port_bind(binding) -> List[ConfigCommand]`
- [ ] `plan_port_unbind(binding) -> List[ConfigCommand]`
- [ ] `dry_run` 参数支持
- [ ] 序列化为 JSON 存入 `SdnDeployment.planned_config`
- [ ] commit: `feat(sdn): add VPCConfigPlanner for create/delete/port_bind`

## Task 5: SdnPreflight 设备预检

- [ ] `backend/app/services/sdn_preflight.py` 新增
- [ ] 6 个 check 方法（型号 / online / vpc 不存在 / vlan 不冲突 / BGP peer / l3vpn 存在）
- [ ] `preflight_vpc_deploy(vpc, device_id) -> PreflightResult`
- [ ] 失败返 `SDN_PREFLIGHT_FAILED` + 详细 reason
- [ ] commit: `feat(sdn): add SdnPreflight with 6 checks`

## Task 6: ops-toolkit 3 脚本

- [ ] `ops-toolkit/scripts/vpc-apply.sh` 新增
  - 读 SdnDeployment.planned_config
  - 调 paramiko 下发到设备
  - 成功后更新 SdnDeployment.status
- [ ] `ops-toolkit/scripts/vpc-reset.sh` 新增
  - 删 vsi / vxlan / evpn / vsi-interface（保留 l3vpn）
  - 仅在用户显式 --force 时执行
- [ ] `ops-toolkit/scripts/vpc-show.sh` 新增
  - display l2vpn vsi / display vxlan tunnel / display bgp peer
  - 仅 read-only
- [ ] 全部走 `_lib.sh` 设备别名 + 凭据 env 注入
- [ ] `ops-toolkit/Dockerfile` 复制 3 脚本
- [ ] commit: `feat(openspec): add vpc-apply/vpc-reset/vpc-show tools to ops-toolkit`

## Task 7: 单测

- [ ] `backend/tests/test_sdn_device_adapter.py` (8 用例)
  - H3cV7Adapter.supports_model(S6850) = True
  - supports_model(CE6865) = False → error
  - get_template("vpc_create") returns H3cV7VpcCreateTemplate
- [ ] `backend/tests/test_vpc_config_planner.py` (10 用例)
  - plan_vpc_create with SdnVpc mock → 5+ commands
  - plan_vpc_delete reverses
  - plan_port_bind with service-instance
  - plan_port_bind fallback to access vlan
  - dry_run mode doesn't persist
  - .2/.3 现状 dry-run 比对 (与 display l2vpn vsi 一致)
- [ ] `backend/tests/test_sdn_preflight.py` (6 用例)
  - 型号不支持 → 失败
  - 设备 offline → 失败
  - vpc 已存在 → 失败
  - vlan 冲突 → 失败
  - BGP peer not established → 失败
  - l3vpn 不存在 → 失败
- [ ] 24/24 通过
- [ ] commit: `test(sdn): add 24 test cases for device templates`

## Task 8: ops-toolkit 文档同步

- [ ] `docs/ops-toolkit.md` 追加 3 工具说明
- [ ] 用法 + 凭据 + 默认 device
- [ ] commit: `docs(ops-toolkit): add vpc-apply/reset/show usage`

## 验收 checklist

- [ ] 8 commit 顺序与 task 顺序一致
- [ ] 每个 commit 跑 `pytest backend/tests/test_sdn_*.py` 通过
- [ ] `pytest backend/tests/ -q` 全量通过
- [ ] dry-run 输出与 .2/.3 现状的 display l2vpn vsi 完全一致
- [ ] ops-toolkit 3 脚本在 .177 上 dry-run 通过
- [ ] 不修改 .2 / .3 设备
- [ ] 不连真实设备跑 .5 测试（必须用户在场手动跑）
- [ ] no debug print / no TODO / no hardcoded credentials
