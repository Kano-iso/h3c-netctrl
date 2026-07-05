# backend-i18n-key（后端 APIResponse 错误改 i18n key）

## 目标

后端 routers 返回的 APIResponse 增加 `error_key` + `error_params` 字段供前端 i18n 翻译，原 `error` 字段保留中文兼容。集中维护 i18n key 表，避免散落。

## 范围

**包含**：
- `backend/app/schemas.py`：`APIResponse` 加 `error_key: Optional[str]` + `error_params: Optional[dict]` 字段
- `backend/app/i18n_keys.py`（新建）：集中维护所有 error key 列表 + 描述（按模块分组：device.* / interface.* / vlan.* / cmdb.* / backup.* / batch.* / execute.* / log.*）
- `backend/app/routers/*.py` × 9：所有 `APIResponse(success=False, error="...")` 调用改为传 `error="中文原 error"` + `error_key="module.error_name"` + `error_params={...}`
- 10 个后端单测（key 映射 + error_key 必填场景 + 兼容原 error 字段）

**不包含**：
- 不做后端真实翻译（仅返 key）
- 不做 Accept-Language 头处理
- 不改后端日志（运维日志保持中文）
- 不动业务逻辑

## 设计决策

### 决策 1: APIResponse schema 扩展（非破坏性）

```python
# backend/app/schemas.py
class APIResponse(BaseModel):
    success: bool
    data: Optional[object] = None
    error: Optional[str] = None
    # v2.6 新增（i18n 支持）
    error_key: Optional[str] = None
    error_params: Optional[dict] = None
```

- 原 `error` 字段保留（中文，运维日志友好）
- 新增 `error_key` + `error_params` 供前端 i18n 翻译
- 前端用 `error_key` 查 i18n 表，找不到 fallback 到 `error`
- 兼容性：现有前端代码不动（只读 `error`）也能继续工作

### 决策 2: i18n key 集中表

```python
# backend/app/i18n_keys.py
"""i18n key 集中表

每个 key 包含：
- key: i18n key 字符串（如 'device.not_found'）
- module: 所属模块（device / interface / vlan / cmdb / backup / batch / execute / log）
- description: 中文描述（开发参考，不影响用户）
- params: 占位符列表（如 ['id'] 表示前端翻译时需传 {id: 123}）
"""

DEVICE_KEYS = [
    {"key": "device.not_found", "params": ["id"]},
    {"key": "device.name_required", "params": []},
    {"key": "device.host_required", "params": []},
    {"key": "device.username_required", "params": []},
    {"key": "device.password_required", "params": []},
    {"key": "device.create_failed", "params": ["error"]},
    {"key": "device.update_failed", "params": ["error"]},
    {"key": "device.delete_failed", "params": ["error"]},
    {"key": "device.delete_in_use", "params": []},
    {"key": "device.test_connection_failed", "params": ["error"]},
]

INTERFACE_KEYS = [
    {"key": "interface.not_found", "params": ["if_index"]},
    {"key": "interface.config_invalid", "params": ["error"]},
    {"key": "interface.deploy_failed", "params": ["error"]},
    {"key": "interface.ipv4_invalid", "params": ["address"]},
    {"key": "interface.ipv4_deploy_failed", "params": ["error"]},
    {"key": "interface.link_type_deploy_failed", "params": ["error"]},
    {"key": "interface.vpn_bind_failed", "params": ["error"]},
    {"key": "interface.vpn_unbind_failed", "params": ["error"]},
    {"key": "interface.trunk_vlan_failed", "params": ["error"]},
]

# ... VLAN / CMDB / BACKUP / BATCH / EXECUTE / LOG / TASK / COMMON

ALL_KEYS = DEVICE_KEYS + INTERFACE_KEYS + VLAN_KEYS + CMDB_KEYS + BACKUP_KEYS + BATCH_KEYS + EXECUTE_KEYS + LOG_KEYS + TASK_KEYS + COMMON_KEYS

def is_valid_key(key: str) -> bool:
    """校验 key 是否在集中表里（开发期调试用）"""
    return any(k["key"] == key for k in ALL_KEYS)
```

- 集中表 ≈ 80-120 key（覆盖所有 router 错误场景）
- 按模块分组 dict list，方便维护
- `is_valid_key()` 供 router 内部 assert（开发期捕获漏写 key 的 bug）

### 决策 3: router 改造模式

```python
# backend/app/routers/device.py 改造前
return APIResponse(success=False, error=f"设备不存在: id={device_id}")

# 改造后
return APIResponse(
    success=False,
    error=f"设备不存在: id={device_id}",  # 保留中文（兼容）
    error_key="device.not_found",
    error_params={"id": device_id},
)
```

- 每个 `APIResponse(success=False, error=...)` 都改为同时传 `error_key` + `error_params`
- 错误参数用 dict 占位符（如 `{"id": 123}`），前端用 `t('device.not_found', {id: 123})` 翻译

### 决策 4: helper 函数减少样板代码

```python
# backend/app/i18n_keys.py
def error_response(key: str, error: str, params: dict = None) -> APIResponse:
    """构造 i18n 错误响应（保留 error 字段兼容）"""
    return APIResponse(
        success=False,
        error=error,
        error_key=key,
        error_params=params or {},
    )

# router 使用
from app.i18n_keys import error_response

return error_response("device.not_found", f"设备不存在: id={device_id}", {"id": device_id})
```

- helper 减少 5-6 个 router 文件的样板代码
- helper 内部可加 assert（开发期捕获 key 不在表里的 bug）

### 决策 5: 占位符格式（与 vue-i18n 一致）

- vue-i18n 命名占位符：`{name}` 格式
- 后端 error_params dict 与 vue-i18n 一致：`{"id": 123, "name": "Device-1"}`
- 模板示例：
  - `t('device.not_found', {id: 123})` → "Device not found: id=123"（英文）/ "设备不存在: id=123"（中文）
  - `t('common.required', {field: 'username'})` → "Username is required" / "缺少必填字段: username"

## 验收标准

1. ✅ `backend/app/schemas.py` APIResponse 加 `error_key` + `error_params` 字段
2. ✅ `backend/app/i18n_keys.py` 集中表创建，包含 ≥ 80 key
3. ✅ `is_valid_key()` 函数实现，可被 router 内部 assert 调用
4. ✅ `error_response()` helper 函数实现
5. ✅ 9 个 router 文件（device / interface / vlan / asset / backup / batch / execute / log / dashboard）的所有 `APIResponse(success=False, error=...)` 调用都加上 `error_key` + `error_params`
6. ✅ qa-backend 275+ passed（+ 10 单测：key 集中表完整性 / error_response helper / 各 router 错误场景带 key / is_valid_key 校验）
7. ✅ 原 `error` 字段保留（兼容性）
8. ✅ 现有 APIResponse 调用方代码不破坏（error 字段不变）
9. ✅ 现有 265 baseline 测试不破坏
10. ✅ qa-frontend 切换到 en-US 后，触发的错误 toast 显示英文（前端 i18n 表有对应 key 翻译）

## 风险

- **key 散落（不在集中表）**：用 `is_valid_key()` assert 捕获
- **占位符不一致**（后端用 `{device_id}` 前端用 `{id}`）：统一规范（key 集中表的 `params` 字段标注）
- **后端错误信息修改影响运维日志**：原 `error` 字段保留，仅新增字段，运维不变
- **i18n key 命名冲突**：模块前缀避免
- **APIResponse schema 变化破坏 OpenAPI 文档**：新增 optional 字段不破坏，向后兼容
