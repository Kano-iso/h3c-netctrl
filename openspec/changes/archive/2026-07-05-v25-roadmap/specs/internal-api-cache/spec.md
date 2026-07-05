## ADDED Requirements

### Requirement: internal_api GET 请求 SHALL 支持 5s TTL 本地缓存

`backend/app/internal_api.py` 中的 GET 请求（`get_device` / `get_devices` / `get_assets` 等）SHALL 在 process-local dict 中缓存响应，TTL = 5 秒。缓存命中时 SHALL 跳过 HTTP 调用直接返回缓存数据。POST / PUT / DELETE 请求 MUST NOT 缓存。

#### Scenario: 缓存命中跳过 HTTP

- **WHEN** 5s 内对同一 URL + params + headers 发起第二次 GET 请求
- **THEN** 系统从 process-local dict 返回缓存数据，不发起 HTTP 调用

#### Scenario: 缓存过期自动回源

- **WHEN** 距离上次请求超过 5s
- **THEN** 系统发起 HTTP 调用获取最新数据，并更新缓存

#### Scenario: 写操作不缓存

- **WHEN** 调用 `internal_api.post` / `internal_api.put` / `internal_api.delete`
- **THEN** 系统发起 HTTP 调用，不写入缓存

#### Scenario: 写操作不主动失效缓存

- **WHEN** 调用写操作后立即发起 GET 请求
- **THEN** 系统仍可能返回 5s 内的缓存数据（接受短暂陈旧，TTL 自然过期）

### Requirement: 缓存 key SHALL 包含 url + params + headers

缓存 key MUST 由 `(url, params, headers)` 三元组构成，确保不同参数的请求不互相污染。headers 中 `X-Internal-Token` MUST 参与 key 计算（虽然实际值不变，避免误用）。

#### Scenario: 不同 params 分别缓存

- **WHEN** 对 `GET /api/devices` 和 `GET /api/devices?status=up` 发起请求
- **THEN** 系统分别缓存两份响应，互不覆盖

#### Scenario: 同 params 共享缓存

- **WHEN** 5s 内连续两次发起 `GET /api/devices`（同 params）
- **THEN** 第二次命中缓存，不发起 HTTP

### Requirement: 缓存 SHALL 提供显式清除入口

`internal_api` 模块 SHALL 提供 `clear_cache()` 函数，用于测试和手动失效场景。测试 fixture MUST 在每个 test 之间调用 `clear_cache()` 避免污染。

#### Scenario: 测试间清缓存

- **WHEN** pytest fixture setup 调用 `clear_cache()`
- **THEN** 下一个 test 的 GET 请求必定发起 HTTP，不命中缓存

#### Scenario: 手动失效

- **WHEN** 业务代码调用 `clear_cache()` 后立即发起 GET
- **THEN** 系统发起 HTTP 调用获取最新数据
