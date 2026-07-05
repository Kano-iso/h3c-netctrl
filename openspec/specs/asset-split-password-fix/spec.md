# asset-split-password-fix Specification

## Purpose

修复 v2.6.1 split 模式下 `refresh_asset` 密码二次解密 bug —— `device.password_encrypted` 在 split 模式已存 ctrl 容器解密后的明文（语义误用但兼容），旧代码再次 `decrypt_password` 导致 Fernet `InvalidToken` 异常。修复后改用 `device_access.get_device_with_password` 统一获取明文 password，避免重复解密。

## Requirements

### Requirement: refresh_asset 必须复用 get_device_with_password

`backend/app/routers/asset.py::refresh_asset` MUST 使用 `app.utils.device_access.get_device_with_password(db, device_id)` 一次性获取 device + 明文 password，禁止再调用 `decrypt_password(device.password_encrypted)`。

#### Scenario: monolith 模式 device 有密文 password_encrypted
- **WHEN** refresh_asset 在 monolith 模式被调用
- **THEN** `get_device_with_password` 内部 `decrypt_password(device.password_encrypted)` 返回明文 password
- **AND** refresh_asset 把明文 password 传给 SSHExecutor

#### Scenario: split 模式 device 是 wrapped dict（password_encrypted 字段实为明文）
- **WHEN** refresh_asset 在 split 模式被调用（data 容器）
- **THEN** `get_device_with_password` 走 `internal_api.get_device` → 内部已 decrypt → 直接返回明文 password
- **AND** refresh_asset 把明文 password 传给 SSHExecutor（不再二次 decrypt）

#### Scenario: split 模式设备不存在
- **WHEN** `internal_api.get_device` 返回 `success=false`
- **THEN** refresh_asset 返回 `DEVICE_NOT_FOUND` 错误（`i18n_key=device.not_found`），不暴露技术异常

### Requirement: 禁止新代码直接调 decrypt_password(device.password_encrypted)

任何新增 / 修改的 router 函数 MUST 复用 `device_access.get_device_with_password` 获取明文 password，禁止自己调 `decrypt_password(device.password_encrypted)`（split 模式会 InvalidToken）。

#### Scenario: 新增代码若直接调 decrypt_password
- **THEN** CI / code review MUST 拒绝（v2.6.1 复盘项）
