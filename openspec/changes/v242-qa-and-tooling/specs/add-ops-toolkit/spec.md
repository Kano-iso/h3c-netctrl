# add-ops-toolkit Spec Deltas (v242-qa-and-tooling)

> 本 change 在 [add-ops-toolkit](../../specs/add-ops-toolkit/spec.md) 之上 MODIFIED：
> ops-toolkit 脚本支持设备名→IP 别名映射 + 默认 test 设备。

---

## MODIFIED Requirements

### Requirement: ops-toolkit 脚本支持设备名→IP 别名映射

`ops-toolkit/scripts/*.sh` MUST 支持 `--device` 参数接受设备名别名，自动解析为对应 IP：

- **支持的别名**（小写不敏感）：
  - `test` / `Test-Switch` / `Test-Switch-177` → 192.168.100.177（默认）
  - `leaf-03` / `Leaf-03` → 192.168.100.4
  - `leaf-04` / `Leaf-04` → 192.168.100.5
  - `spine-01` / `Spine-01` → 192.168.100.100
  - 其他输入：透传（视为 IP）
- **缺省行为**：`--device` 不带参数 = 默认 `test`（指向 .177）
- **显式生产 IP**：不阻止，但日志输出 warn（"⚠️ 目标为生产设备 .X，注意操作"）
- **实现位置**：`ops-toolkit/scripts/_lib.sh` 新增 `_resolve_device()` + `_get_device_arg()` 函数
- **覆盖脚本**：check-host / ssh-test / check-netconf / capture-config / reboot-wait / audit-switch（6 个）

#### Scenario: 默认参数指向 .177

- **WHEN** `check-host.sh` 不带 `--device` 执行
- **THEN** 脚本 MUST 自动连 192.168.100.177（Test-Switch-177）
- **AND** banner 标注 "📌 默认目标：Test-Switch-177"

#### Scenario: 设备名别名解析

- **WHEN** `check-host.sh --device leaf-04`
- **THEN** 脚本 MUST 解析为 192.168.100.5 并连该设备

#### Scenario: 显式生产 IP warn

- **WHEN** `check-host.sh --device 192.168.100.5`（生产设备）
- **THEN** 脚本 MUST 输出 warn 日志
- **AND** 仍执行（不阻止）

#### Scenario: _lib.sh 缺失时报错

- **WHEN** `check-host.sh` 调用 `_get_device_arg` 但 `_lib.sh` 缺失
- **THEN** 脚本 MUST 报错退出（不静默走默认 IP）
