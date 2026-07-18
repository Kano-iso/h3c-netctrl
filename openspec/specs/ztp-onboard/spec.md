# ztp-onboard Specification

## Requirements

### Requirement: ZTP static 管理地址纳管

系统 MUST 提供 API，基于 v3.1.1 写入的 static 管理地址完成设备纳管。

#### Scenario: 新设备纳管成功

- WHEN 调用 `POST /api/ztp/onboard` 并传入未存在的 host
- AND SSH 22 与 NETCONF 830 探测成功
- AND 资产采集成功
- THEN 系统 MUST 创建 device
- AND 创建或更新 asset
- AND 返回 `status=success`

#### Scenario: 重复 host 幂等更新

- WHEN 同一 host 已存在 device
- AND 再次调用 `POST /api/ztp/onboard`
- THEN 系统 MUST 更新已有 device
- AND MUST NOT 创建重复 device

#### Scenario: 资产采集失败

- WHEN SSH/NETCONF 探测通过
- AND 资产采集失败
- THEN 系统 MUST 保留 device 记录
- AND asset 状态 MUST 为 `offline`
- AND 返回 `status=partial`

#### Scenario: 探测失败不入库

- WHEN SSH 22 或 NETCONF 830 探测失败
- THEN 系统 MUST 返回明确错误
- AND MUST NOT 创建新 device

### Requirement: split 模式资产同步

在 split 模式下，ctrl 容器 MUST 通过 data internal API 写入资产数据。

#### Scenario: split asset upsert

- WHEN `SERVICE_NAME=ctrl`
- AND onboard 需要写入 asset
- THEN ctrl MUST 调用 data internal API
- AND data 容器 MUST upsert `assets.device_id` 对应记录

### Requirement: 不依赖 DHCP lease 监听

v3.1.2 MUST NOT 依赖 dnsmasq lease 监听作为纳管触发源。

#### Scenario: ZTP watcher 回调

- WHEN ztp-server 启用 `ZTP_ONBOARD_ENABLED=true`
- AND `ZTP_MGMT_IP` 的 SSH 22 与 NETCONF 830 均已开放
- THEN ztp-server MUST POST `/api/ztp/onboard`
- AND payload MUST include host / credential / platform / source
