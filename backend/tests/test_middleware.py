"""鉴权中间件单测（v241-container-split）

验证：
- /internal/* 路径无 token → 403
- /internal/* 路径有正确 token → 200
- /internal/* 路径未配置 token → 503
- /api/* 路径不受中间件影响
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.middleware import InternalTokenMiddleware


def _make_app(token: str = "") -> FastAPI:
    """构造测试 app，注册中间件 + 测试路由"""
    app = FastAPI()
    app.add_middleware(InternalTokenMiddleware, token=token)

    @app.get("/internal/devices")
    def internal_devices():
        return {"success": True, "data": []}

    @app.get("/api/devices")
    def api_devices():
        return {"success": True, "data": []}

    return app


def test_internal_no_token_returns_403():
    """/internal/ 无 token → 403"""
    app = _make_app(token="secret-123")
    client = TestClient(app)
    resp = client.get("/internal/devices")
    assert resp.status_code == 403


def test_internal_wrong_token_returns_403():
    """/internal/ 错误 token → 403"""
    app = _make_app(token="secret-123")
    client = TestClient(app)
    resp = client.get("/internal/devices", headers={"X-Internal-Token": "wrong"})
    assert resp.status_code == 403


def test_internal_correct_token_returns_200():
    """/internal/ 正确 token → 200"""
    app = _make_app(token="secret-123")
    client = TestClient(app)
    resp = client.get("/internal/devices", headers={"X-Internal-Token": "secret-123"})
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "data": []}


def test_internal_no_token_configured_returns_503():
    """未配置 token → 503（安全默认）"""
    app = _make_app(token="")
    client = TestClient(app)
    resp = client.get("/internal/devices", headers={"X-Internal-Token": "anything"})
    assert resp.status_code == 503


def test_api_path_not_affected():
    """/api/ 路径不受中间件影响"""
    app = _make_app(token="secret-123")
    client = TestClient(app)
    resp = client.get("/api/devices")
    assert resp.status_code == 200
