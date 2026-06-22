## Why

v20-bugfix-interface-safety-guard 变更中给 `DeviceResponse` 加了 `protected_interfaces: List[int]`，但实现方式不对：

```python
@classmethod
def model_validate(cls, obj, *args, **kwargs):
    instance = super().model_validate(obj, *args, **kwargs)
    # ...
    instance.protected_interfaces = json.loads(obj.protected_interfaces or "[]")
    return instance
```

Pydantic v2 的 `model_validate` 在赋值前会做类型校验，super().model_validate 后 protected_interfaces 已经是 `str`（数据库里是 JSON 字符串），改属性赋值触发类型校验失败，抛 ValidationError。

结果：
- `GET /api/devices` 返回 500 Internal Server Error
- 设备管理界面显示"服务不可用"
- 我之前 PUT /devices/1 时也是 500，但没注意到（直接用了 Python 直接改数据库）

**这是自测漏掉的严重问题** —— 之前测了"接口配置"和"接口查询"，但**没测设备管理界面最基础的 GET /api/devices**。

## What Changes

- 改用 Pydantic v2 推荐的 `field_validator` 处理 `protected_interfaces` 字段
- 输入是 string（数据库存储的 JSON），自动解析为 list[int]
- 解析失败时返回空 list，不抛错

## Capabilities

### Modified Capabilities

- `device-management`: DeviceResponse 字段转换修复
- `interface-safety-guard`: 保护接口字段类型转换

## Impact

- 后端：schemas.py DeviceResponse
- 用户体验：设备管理界面恢复可用
