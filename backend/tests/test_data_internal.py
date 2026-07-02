"""data 容器内部端点单测（v241-container-split）

验证：
- GET /internal/assets — 返回资产列表
- GET /internal/backups/{device_id} — 返回设备备份列表
"""
import pytest


def test_internal_list_assets_empty(client):
    """GET /internal/assets 空列表"""
    resp = client.get("/internal/assets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


def test_internal_list_backups_empty(client):
    """GET /internal/backups/{device_id} 无备份"""
    resp = client.get("/internal/backups/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
