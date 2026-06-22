## Context

v20-bugfix-interface-safety-guard 引入的 Pydantic schema 写法错误：

```python
class DeviceResponse(BaseModel):
    protected_interfaces: List[int] = []
    
    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        instance = super().model_validate(obj, *args, **kwargs)
        instance.protected_interfaces = json.loads(obj.protected_interfaces or "[]")  # 错误：触发类型校验
        return instance
```

Pydantic v2 中 `model_validate` 接受 dict/ORM 对象，校验类型后再赋值。`super().model_validate(obj)` 在 v2 行为是"按 schema 严格校验"，返回的 instance 字段类型必须匹配声明。`protected_interfaces` 声明为 `List[int]`，但数据库里是 str，所以从一开始 super() 就校验失败了。

## Goals / Non-Goals

**Goals:**
- 修复 `DeviceResponse.model_validate`，使其能处理数据库 str 字段
- 不影响接口配置保护检查（已 work）
- 自测时包含 GET /api/devices 这种基础接口

**Non-Goals:**
- 不改数据库 schema
- 不改前后端协议

## Decisions

### D1: 用 field_validator 而非重写 model_validate

**选择**：在 DeviceResponse 加 `field_validator("protected_interfaces", mode="before")` 处理 string→list 转换

**理由**：Pydantic v2 官方推荐做法，validator 在校验前介入，可改变原始值。

### D2: 解析失败返回空 list

**选择**：json.loads 失败时返回 []

**理由**：保护接口是辅助功能，解析失败不应阻塞主功能（设备 CRUD）

## Risks / Trade-offs

- 无重大风险
- 但要补自测：每次加 schema 字段必须测 GET /devices
