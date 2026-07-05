# asset-staleness-auto-degrade Specification

## Purpose

为 `Asset` 表增加"过期资产自动降级"机制：当 asset 的 `updated_at` 距今超过阈值（默认 1h，可配）时，主动将其 `status` 从 `online` 降级为 `offline`，避免 dashboard 误把"采集时刻的快照"当作"当前在线"。

## Requirements

### Requirement: 阈值配置

`backend/app/config.py` MUST 暴露 `ASSET_STALE_HOURS`（默认 1h，整数 + 浮点皆可，支持 0.01 等小数值做调试）和 `ASSET_STALE_ENABLED`（默认 `True`，布尔）两个配置项。两者 MUST 可通过环境变量注入，且 MUST 出现在 `.env.example`。

#### Scenario: 默认值生效
- **WHEN** 未设置环境变量
- **THEN** `settings.ASSET_STALE_HOURS == 1.0` 且 `settings.ASSET_STALE_ENABLED == True`

#### Scenario: 自定义阈值
- **WHEN** 环境变量 `ASSET_STALE_HOURS=12`
- **THEN** `settings.ASSET_STALE_HOURS == 12.0`

#### Scenario: 关闭降级
- **WHEN** 环境变量 `ASSET_STALE_ENABLED=False`
- **THEN** 启动时不执行降级，dashboard 也不按 staleness 过滤

### Requirement: data 容器启动时主动降级

`backend/app/main.py::on_startup` MUST 在 `SERVICE_NAME=data` 且 `ASSET_STALE_ENABLED=True` 时执行 SQL：`UPDATE assets SET status='offline' WHERE status='online' AND updated_at < datetime('now', '-' || :hours || ' hours')`。其他容器（ctrl / config / core）MUST NOT 执行此 SQL。

#### Scenario: 降级生效
- **WHEN** data 容器启动时存在 asset 满足 `status='online' AND updated_at` 距今 > 阈值（默认 1h）
- **THEN** 该 asset 的 `status` 在启动后变为 `'offline'`

#### Scenario: 幂等
- **WHEN** 重复启动 data 容器，无 matching 行
- **THEN** UPDATE 影响行数 = 0，不抛异常

#### Scenario: 关闭时不执行
- **WHEN** `ASSET_STALE_ENABLED=False`
- **THEN** 启动时即使存在陈旧 online 资产，status 也不变

### Requirement: dashboard 读取时 staleness 过滤

`backend/app/routers/dashboard.py::_get_asset_stats` MUST 在 `ASSET_STALE_ENABLED=True` 时按 `updated_at >= now - threshold` 过滤 `status='online'` 行；过期 online 不计入 online 也不计入 offline，而是单独计入 `stale` 字段。

#### Scenario: 全部陈旧
- **WHEN** 7 条 assets 全部 `updated_at` 距今 > 1h
- **THEN** `device_stats` 返回 `{total: 7, online: 0, offline: 0, stale: 7}`

#### Scenario: 部分陈旧
- **WHEN** 5 条 online 中 3 条 updated_at 在 1h 内，2 条超过
- **THEN** `device_stats` 返回 `{total: 5, online: 3, offline: 0, stale: 2}`

#### Scenario: 阈值关闭
- **WHEN** `ASSET_STALE_ENABLED=False`
- **THEN** `device_stats` 不返回 `stale` 字段（兼容历史行为），online 按 `status='online'` 全算

### Requirement: /internal/assets 返回 is_stale 字段

`backend/app/routers/data_internal.py::internal_list_assets` MUST 在 `ASSET_STALE_ENABLED=True` 时为每个 asset dict 增加 `is_stale: bool` 字段，值为 `(now - updated_at) > threshold`；否则 MUST NOT 增加此字段。

#### Scenario: 包含 is_stale
- **WHEN** asset.updated_at 距今 > 1h
- **THEN** 返回 dict 包含 `is_stale: true`

#### Scenario: 关闭时不包含
- **WHEN** `ASSET_STALE_ENABLED=False`
- **THEN** 返回 dict 不包含 `is_stale` 字段

### Requirement: refresh_asset 流程不变

`backend/app/routers/asset.py::refresh_asset` 的现有行为 MUST NOT 改动（成功→online + updated_at 自动更新，失败→offline）。staleness 降级与 refresh 是正交关系。

#### Scenario: 正常 refresh
- **WHEN** 用户点击"采集"且 SSH 成功
- **THEN** asset.status 设为 `online`，`updated_at` 由 SQLAlchemy `onupdate=func.now()` 自动更新为当前时间

#### Scenario: 失败 refresh
- **WHEN** 用户点击"采集"且 SSH 失败
- **THEN** asset.status 设为 `offline`，`updated_at` 同步更新

### Requirement: 不写实时降级

本 change MUST NOT 在每次 `GET /api/dashboard` 或 `GET /internal/assets` 请求时执行 UPDATE。降级只在 data 容器启动时发生一次；其他时间点 dashboard / internal 端点只读不算写。

#### Scenario: 实时读不算写
- **WHEN** 连续调用 `GET /api/dashboard` 多次
- **THEN** DB 写次数 = 0（仅启动时一次）

### Requirement: 调试场景支持

`ASSET_STALE_HOURS=0.01`（36 秒）时，新鲜采集的设备 36 秒后即被自动降级，便于开发调试 staleness 行为；`ASSET_STALE_HOURS=0` 视为立即过期（保留 `> threshold` 语义：0 表示"刚采集也不算在线"）。

#### Scenario: 调试阈值
- **WHEN** `ASSET_STALE_HOURS=0.01` 且 asset.updated_at 距今 > 36s
- **THEN** 启动后该 asset.status 变 offline
