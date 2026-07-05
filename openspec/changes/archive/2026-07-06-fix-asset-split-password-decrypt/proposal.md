# fix-asset-split-password-decrypt — Proposal

## Why

v2.6.1 `fix-asset-collect-failure` 修了 split 模式下 asset 路由 404 问题（path 从 `/api/devices/{id}/asset/*` 改为 `/api/assets/device/{id}/*`）。**但路由修通后调用仍然失败**——根因是 `asset.py::refresh_asset` 的**密码二次解密 bug**。

### 复现链路

1. 浏览器 / 前端 → `POST /api/assets/device/1/refresh` → 走 vite proxy → data 容器
2. data 容器 `refresh_asset` 调 `_get_device_or_error(db, 1)`
3. `_get_device_or_error` 调 `device_access.get_device_or_error` → 调 `get_device_with_password`
4. **split 模式**：本地 Device 表不存在 → 走 `internal_api.get_device(1)` → 调 ctrl 容器 `GET /api/internal/devices/1`
5. ctrl 容器查本地 DB → `device.password_encrypted` 是 Fernet 密文 → **ctrl 端**调 `decrypt_password(...)` → 返回明文 + device dict
6. data 容器 `_wrap_device_dict(d)` 把 `d["password"]`（已解密明文）塞到 `device.password_encrypted` 字段（兼容老代码语义）
7. data 容器 `refresh_asset` 调 `decrypt_password(device.password_encrypted)` → **明文当密文解** → Fernet `InvalidToken` 异常
8. catch 住 → 返回 `DEVICE_CRYPTO_DECRYPT_FAILED`（用户看到的"采集失败"）

### 影响面

- **split 模式**（默认 / VITE_API_MODE=split）：所有 `assetApi.refresh` 调用全失败
- **monolith 模式**（VITE_API_MODE=core）：不触发（device 是真 Device ORM 对象，`password_encrypted` 真是密文）
- **即将上线的 add-auto-collect**：auto-collect scheduler 在 data 容器内调 refresh 业务逻辑 → **完全跑不通**

### 修复方案

`refresh_asset` 不应再调 `decrypt_password(device.password_encrypted)`。应改用 `device_access.get_device_with_password(db, device_id)` —— 它已经统一处理了 monolith / split 两种模式：

- **monolith 模式**：本地查 Device → `decrypt_password(device.password_encrypted)` → 返回明文
- **split 模式**：internal_api.get_device → 内部已解密 → 直接返回明文

**重要**：`get_device_with_password` 已经返回 `(device_obj, password, error)`，但当前 `refresh_asset` 只用了 device 没拿 password（还要自己再 decrypt 一次）。修复就是把 password 也接住直接用。

## What Changes

- **后端 `backend/app/routers/asset.py::refresh_asset`**：用 `device_access.get_device_with_password` 替代 `_get_device_or_error + decrypt_password(device.password_encrypted)` 两次调用
- **新增 3 个单测**（`backend/tests/test_asset_password_decrypt.py`）：
  - monolith 模式：device 是 ORM，password_encrypted 是密文 → decrypt 成功
  - split 模式：device 是 wrapped dict，password_encrypted 是明文 → 不二次 decrypt
  - split 模式 + decrypt 真密文：即使 device 字段是密文，也能正确处理（防御性）
- **无前端改动**
- **无 API 路径改动**（v2.6.1 fix-asset-collect-failure 已完成）

## 设计决策

### 决策 1：统一用 `get_device_with_password`，不再调 `decrypt_password`

- **理由**：device_access 已经是统一封装；refresh_asset 是第一个违反这约定的路由
- **替代方案（已否决）**：在 `_wrap_device_dict` 里把 `password_encrypted` 字段删掉，强制调用方拿 `_password_decrypted`
  - **否决理由**：侵入性大，且影响 v2.6.0 i18n 已闭环的代码
- **替代方案（已否决）**：检测 device 类型（ORM vs SimpleNamespace）走不同解密路径
  - **否决理由**：双重逻辑维护成本高；device_access 已经做了这件事

### 决策 2：不改 `_wrap_device_dict` 行为

- **理由**：v2.6.0 i18n 闭环时已使用 `_password_decrypted` 字段；不动它
- **代价**：device.password_encrypted 字段在 split 模式语义误用（实际是明文），但有 `_password_decrypted` 字段正确承载明文，新代码统一用 `get_device_with_password` 拿明文即可

### 决策 3：不改 i18n key 集合

- 错误信息仍走 `ASSET_ROUTE_REFRESH_FAILED`（v2.6.1 fix-asset-collect-failure 已加）
- `DEVICE_CRYPTO_DECRYPT_FAILED` 保留（其他场景如 device 编辑仍可能用到）

## Capabilities

### Modified Capabilities

- 无（修复 bug，不改 spec 语义）

## Impact

- **代码**：
  - `backend/app/routers/asset.py`（refresh_asset 改 1 个函数，约 5 行改动）
  - `backend/tests/test_asset_password_decrypt.py`（新建，3 case）
- **API**：无破坏性变更（行为修复）
- **配置**：无
- **文档**：
  - `RELEASE-NOTES-v2.6.1.md` §3 增补 split 模式密码解密 bug 修复
  - `VERSION-ROADMAP.md` §v2.6.1 章节
- **测试 baseline**：238 → 241+ passed（+3 password-decrypt 单元测试）
- **用户体验**：
  - 修复前：split 模式采集按钮永远失败
  - 修复后：split 模式采集正常工作（前提是设备 .177 可达 + 凭据有效）

## Non-Goals

- 不重写 device_access（v241-container-split Task 4.4 已闭环）
- 不改 monolith 模式行为（已正常工作）
- 不改 SSHExecutor（已正确接收明文 password 参数）
- 不改 fix-asset-collect-failure（已闭环）
- 不做"自动降级"（add-auto-collect 的事）

## QA 验证计划

### 1. 涉及端点 / UI / 设备

| 类别 | 名称 | 涉及文件 |
|---|---|---|
| 后端 API | `POST /api/assets/device/{id}/refresh` | `backend/app/routers/asset.py` |
| 后端 utility | `get_device_with_password` | `backend/app/utils/device_access.py` |
| 真实设备 | 192.168.100.177 (Test-Switch-177) | - |
| 真实设备 | 192.168.100.4/.5 (Leaf-03/04) | - |
| 前端 UI | CMDB.vue / Devices.vue "采集" 按钮 | `frontend/src/views/CMDB.vue` |

### 2. QA 验证项

#### 2.1 后端单元（qa-backend 容器跑）

- [ ] monolith 模式 refresh_asset：mock Device ORM + 密文 password_encrypted → decrypt 成功
- [ ] split 模式 refresh_asset：mock internal_api 返回明文 password → refresh 成功
- [ ] split 模式 + 错误凭据：mock internal_api 返回 None → DEVICE_NOT_FOUND 错误
- [ ] split 模式 + 内部 API 失败：mock internal_api 抛异常 → 错误信息可读

#### 2.2 真机集成（pytest --integration 跑 .177）

- [ ] 启动 data 容器（split 模式），curl `POST /api/assets/device/1/refresh` → 200 + asset.status=online
- [ ] 启动 data 容器（split 模式），curl `POST /api/assets/device/4/refresh` → 200 + asset.status=offline（.4 不可达）
- [ ] 启动 monolith 容器（VITE_API_MODE=core），curl 同上 → 200（同行为验证）
- [ ] **最后必须 restore_original_state**

#### 2.3 回归

- [ ] qa-backend 241+ tests 全 PASS
- [ ] 手动 refresh 端点（monolith）仍正常工作
- [ ] 手动 refresh 端点（split）从"永远失败"恢复为"正常工作"
- [ ] 不破坏 v2.6.0 i18n / v2.6.1 fix-asset-collect-failure / fix-asset-stale-status
