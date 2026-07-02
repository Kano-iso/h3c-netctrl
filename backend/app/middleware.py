"""中间件：内部 API 鉴权（v241-container-split）

仅拦截 /internal/* 路径，验证 X-Internal-Token 头。
其他路径不受影响。
"""
import os
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class InternalTokenMiddleware(BaseHTTPMiddleware):
    """验证 /internal/* 路径的 X-Internal-Token 头

    token 从环境变量 INTERNAL_API_TOKEN 读取，初始化时固定。
    """

    def __init__(self, app, token: str = None):
        super().__init__(app)
        self._token = token if token is not None else os.getenv("INTERNAL_API_TOKEN", "")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/internal/"):
            token = request.headers.get("X-Internal-Token", "")
            if not self._token:
                # 未配置 token 时拒绝所有内部请求（安全默认）
                return JSONResponse(
                    status_code=503,
                    content={"success": False, "error": "内部 API 未配置鉴权令牌"},
                )
            if token != self._token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "内部 API 鉴权失败"},
                )
        return await call_next(request)
