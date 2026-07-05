# asset-split-password-fix — Spec

> v2.6.1 fix-asset-split-password-decrypt

## 背景

v2.6.1 `fix-asset-collect-failure` 修了 split 模式 asset 路由 404 问题。路由修通后 `POST /api/assets/device/{id}/refresh` 在 split 模式下仍然失败。

## 根因

`backend/app/routers/asset.py::refresh_asset` 的密码处理逻辑：

```python
# 现状
device, error = _get_device_or_error(db, device_id)  # split 模式返回 SimpleNamespace(device_id=1, password_encrypted="明文")
if error:
    return error
asset = _get_asset_or_create(db, device_id)

try:
    password = decrypt_password(device.password_encrypted)  # 明文当密文解 → InvalidToken
except Exception as e:
    return error_response(err.DEVICE_CRYPTO_DECRYPT_FAILED)
```

**split 模式链路**：

1. `device_access.get_device_with_password` 走 `internal_api.get_device(1)`
2. ctrl 容器查本地 DB → 拿到密文 → 调 `decrypt_password` → 返回明文
3. ctrl 容器返回 `{id, name, host, ..., password: "明文"}`
4. data 容器 `_wrap_device_dict(d)` 把 `d["password"]` 塞到 `device.password_encrypted` 字段（**语义误用，但兼容老代码**）
5. data 容器 `refresh_asset` 再调 `decrypt_password(device.password_encrypted)` → Fernet `InvalidToken` 异常
6. catch → 返回 `DEVICE_CRYPTO_DECRYPT_FAILED`（用户看到的"采集失败"）

## 修复

`refresh_asset` 改用 `device_access.get_device_with_password(db, device_id)` 统一拿明文 password：

```python
# 修复后
from app.utils.device_access import get_device_with_password

device, password, error = get_device_with_password(db, device_id)
if error:
    return error
asset = _get_asset_or_create(db, device_id)
# password 已是明文，直接用
```

**monolith 模式**：device 是真 Device ORM，password_encrypted 真是密文 → `get_device_with_password` 内部 `decrypt_password` → 行为不变
**split 模式**：device 是 wrapped SimpleNamespace，`get_device_with_password` 走 internal_api → password 已是明文 → 直接用

## 设计决策

### 决策 1：复用 `get_device_with_password`

- **理由**：device_access 已经是统一封装（v241-container-split Task 4.4 闭环）
- **位置**：`backend/app/utils/device_access.py`
- **行为**：
  - monolith 模式：本地查 Device ORM → `decrypt_password(device.password_encrypted)`
  - split 模式：internal_api.get_device → 内部已解密 → 直接返回明文

### 决策 2：保留 `password_encrypted` 字段名误用

- **理由**：v2.6.0 i18n 闭环时已使用 `_password_decrypted` 兼容字段；其他 router 可能也用
- **代价**：字段名在 split 模式下语义不准（实际是明文），但有 `_password_decrypted` 字段正确承载
- **新代码约束**：禁止直接 `decrypt_password(device.password_encrypted)`，必须用 `get_device_with_password`

### 决策 3：不改 i18n key 集合

- 错误信息仍走 `ASSET_ROUTE_REFRESH_FAILED`（v2.6.1 fix-asset-collect-failure 已加）
- `DEVICE_CRYPTO_DECRYPT_FAILED` 保留（device 编辑等场景仍可能触发真解密失败）

## 验证

### 单元测试（3 case）

1. **monolith 模式**：mock Device ORM + 密文 password_encrypted → 成功采集
2. **split 模式**：mock internal_api 返回明文 → 成功采集（不二次 decrypt）
3. **错误凭据**：mock internal_api 返回 None → DEVICE_NOT_FOUND 错误

### 真机集成

- split 模式 data 容器：POST /api/assets/device/1/refresh → 200 + status=online
- split 模式 data 容器：POST /api/assets/device/4/refresh → 200 + status=offline（.4 不可达）
- monolith 模式：同样行为验证

## 影响

- **代码**：`backend/app/routers/asset.py`（5 行改动）
- **测试**：`backend/tests/test_asset_password_decrypt.py`（新建，3 case）
- **文档**：`RELEASE-NOTES-v2.6.1.md` §3 增补
- **baseline**：238 → 241+ passed
