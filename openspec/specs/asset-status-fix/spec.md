# asset-status-fix Specification

## Purpose
TBD - created by archiving change fix-asset-status-and-cmdb-layout. Update Purpose after archive.
## Requirements
### Requirement: SSH 不可达时 status 判为 offline

当 `POST /api/devices/{id}/asset/refresh` 被调用时，若设备 SSH 不可达或命令无输出（连接失败/超时/认证失败/命令返回空），MUST 将 `asset.status` 设为 `offline` 并返回 `success=false` + 中文错误信息。

#### Scenario: 不可达设备
- **WHEN** 设备 1.1.1.1 不可连通（TCP 22 timeout）时调用 refresh
- **THEN** 后端 MUST 返回 `success=false, error="采集硬件信息失败: ..."`，且 `asset.status` 改为 `"offline"`

#### Scenario: 错误认证
- **WHEN** 设备可达但 SSH 认证失败（密码错误）
- **THEN** 后端 MUST 返回 `success=false`，且 `asset.status` 改为 `"offline"`

#### Scenario: 可达设备正常采集
- **WHEN** 设备可达且 SSH 认证成功，命令返回有效硬件信息
- **THEN** 后端 MUST 返回 `success=true`，`asset.status` 设为 `"online"`，4 个硬件字段填充

### Requirement: 双层防护：collect_hardware_info 主动抛异常

`backend/app/utils/ssh_executor.py::collect_hardware_info` MUST 在 SSH 连接失败（第一条 `execute` 返回 `success=false`）时主动 `raise ConnectionError(f"SSH 连接失败或命令无输出: {host}")`，而非静默返回空 dict。

#### Scenario: connect 失败抛异常
- **WHEN** `execute("display device")` 返回 `success=false`
- **THEN** `collect_hardware_info` MUST 立即 `raise ConnectionError`，不继续执行后续 `display version`

#### Scenario: 已有 status 不被错误覆盖
- **WHEN** 设备之前 `status="online"`（错误状态），本次 refresh 连接失败
- **THEN** `collect_hardware_info` 抛异常后 `asset.py::refresh_asset` 的 except 分支 MUST 执行，覆盖 `status` 为 `offline`

### Requirement: 双层防护：info 全空判定

`backend/app/routers/asset.py::refresh_asset` MUST 在 `info = executor.collect_hardware_info()` 后判定：当 `info` 4 个字段（model/serial_number/firmware_version/software_package）全部为空时，视为采集失败，设 `status="offline"`、返回 `success=false`。

#### Scenario: 防御性兜底
- **WHEN** 未来 `collect_hardware_info` 行为变化（即便连接成功但所有字段解析失败）
- **THEN** `asset.py` 仍 MUST 检测 `not any(info.values())` 并走失败路径

### Requirement: CMDB 表格行操作列宽度修复

`frontend/src/views/CMDB.vue` 表格行操作列 MUST 使用 `w-32`（128px）以适配"采集 + 编辑资产"两个按钮。

#### Scenario: 操作列不撑大
- **WHEN** 表格显示且任意行操作列含两个按钮
- **THEN** 整列宽度 MUST 稳定在 128px 之内，不应撑大整行

### Requirement: 已有错误数据不主动修复

数据库中已存在的错误 `status`（如设备 id=7 因 SSH 失败被错误标记为 online）MUST NOT 由本次 change 自动修正。前端用户触发"全量刷新"或单设备"采集"时由正常流程覆盖。

#### Scenario: 静默修正
- **WHEN** 用户在 CMDB 顶部点击"全量刷新"按钮
- **THEN** 所有设备的 `status` 在采集成功后更新；不可达设备的 `status` 在采集失败后被改为 `offline`（无需手工 SQL）

