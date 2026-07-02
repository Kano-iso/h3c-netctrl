"""ctrl 容器内部端点单测（v241-container-split）

验证：
- GET /internal/devices — 返回设备列表（含解密密码）
- GET /internal/devices/{id} — 返回单个设备
- POST /internal/logs — 写操作日志
"""
import os
from unittest.mock import patch

import pytest


def test_internal_list_devices(client, created_device):
    """GET /internal/devices 返回设备列表"""
    resp = client.get("/internal/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["data"]) >= 1
    d = data["data"][0]
    assert "id" in d
    assert "host" in d
    assert "password" in d  # 内部端点返回解密密码


def test_internal_get_device_found(client, created_device):
    """GET /internal/devices/{id} 设备存在"""
    resp = client.get(f"/internal/devices/{created_device['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["id"] == created_device["id"]
    assert data["data"]["name"] == "Test-Device"


def test_internal_get_device_not_found(client):
    """GET /internal/devices/{id} 设备不存在"""
    resp = client.get("/internal/devices/99999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False


def test_internal_write_log(client, created_device):
    """POST /internal/logs 写日志"""
    resp = client.post("/internal/logs", json={
        "device_id": created_device["id"],
        "action": "backup_create",
        "status": "成功",
        "detail": "测试内部日志",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "id" in data["data"]

    # 验证日志确实写了
    resp = client.get("/api/logs")
    assert resp.status_code == 200
    logs_data = resp.json()["data"]
    # logs API 返回分页格式，items 是日志列表
    logs = logs_data.get("items", logs_data) if isinstance(logs_data, dict) else logs_data
    assert any(l["action"] == "backup_create" for l in logs)


def test_internal_write_log_auto_device_name(client, created_device):
    """POST /internal/logs 不传 device_name 时自动查"""
    resp = client.post("/internal/logs", json={
        "device_id": created_device["id"],
        "action": "config_change",
        "status": "成功",
        "detail": "自动查设备名",
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True
