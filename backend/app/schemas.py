from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Device 请求/响应模型 ---

class DeviceCreate(BaseModel):
    name: str
    host: str
    port: int = 830
    username: str
    password: str


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None


class DeviceResponse(BaseModel):
    id: int
    name: str
    host: str
    port: int
    username: str
    created_at: datetime
    updated_at: datetime

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
