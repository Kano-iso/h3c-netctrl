from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator


# --- Device 请求/响应模型 ---

class DeviceCreate(BaseModel):
    name: str
    host: str
    port: int = 830
    username: str
    password: str
    protected_interfaces: Optional[List[int]] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    protected_interfaces: Optional[List[int]] = None


class DeviceResponse(BaseModel):
    id: int
    name: str
    host: str
    port: int
    username: str
    protected_interfaces: List[int] = []
    created_at: datetime
    updated_at: datetime
    # v2.6.2 fix-backup-restore-support Task 6: 设备是否支持 SCP 推回
    # True = 不支持（如 S6850），前端可在 UI 上禁用"回滚"按钮 + 提示
    # None = 未知（未探测过 / 探测失败），前端按"未知"处理
    # False = 支持
    restore_unsupported: Optional[bool] = None

    @field_validator("protected_interfaces", mode="before")
    @classmethod
    def _parse_protected_interfaces(cls, v):
        """数据库里存的是 JSON 字符串，这里解析为 list"""
        import json
        if isinstance(v, str):
            try:
                parsed = json.loads(v or "[]")
                if not isinstance(parsed, list):
                    return []
                # 强制 int 转换，过滤无效值
                return [int(x) for x in parsed if isinstance(x, (int, str)) and str(x).lstrip("-").isdigit()]
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        if isinstance(v, list):
            return v
        return []

    model_config = {"from_attributes": True}


# --- VLAN 请求/响应模型 ---

class VLANCreate(BaseModel):
    vlan_id: int = Field(ge=1, le=4094)
    name: str


class VLANUpdate(BaseModel):
    name: str


class VLANResponse(BaseModel):
    vlan_id: int
    name: str


# --- 统一返回格式 ---

class APIResponse(BaseModel):
    success: bool
    data: Optional[object] = None
    error: Optional[str] = None
    # v2.6 i18n: error_key 给前端用 vue-i18n 查翻译；error_params 是 i18n 插值参数
    # 兼容策略：error 必填（中文降级），error_key 可选；前端优先用 error_key 翻译，找不到再 fallback 到 error
    error_key: Optional[str] = None
    error_params: Optional[dict] = None


# --- Log 响应模型 ---

class LogResponse(BaseModel):
    id: int
    device_id: int
    device_name: str
    action: str
    detail: str
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Asset 请求/响应模型 ---

class AssetUpdate(BaseModel):
    location: Optional[str] = None
    tags: Optional[str] = None
    status: Optional[str] = None
