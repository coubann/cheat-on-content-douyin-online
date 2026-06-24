"""认证中间件

对所有 /api/* 路由进行 JWT 认证检查。
豁免路径：/api/auth/*、/api/health、/api/settings/llm-status、/docs、/openapi
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.app.services.jwt_service import get_user_id_from_token


# 不需要认证的路径前缀
PUBLIC_PATHS = (
    "/api/auth",
    "/api/health",
    "/api/settings/llm-status",
    "/api/settings/providers",
    "/api/announcements/active",
    "/api/membership/tiers",
    "/api/membership/ifdian-callback",
    "/api/status",
    "/api/notifications/summary",
    "/docs",
    "/openapi",
    "/redoc",
)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 公共路径跳过认证
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        # 非 API 路径跳过
        if not path.startswith("/api/"):
            return await call_next(request)

        # 检查 JWT Token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "ok": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "未登录或 Token 为空",
                        "suggested_action": "请先 POST /api/auth/login 登录",
                    },
                },
            )

        token = auth_header[7:]
        user_id = get_user_id_from_token(token)
        if user_id is None:
            return JSONResponse(
                status_code=401,
                content={
                    "ok": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Token 无效或已过期",
                        "suggested_action": "请重新 POST /api/auth/login 登录",
                    },
                },
            )

        # 将 user_id 注入到 request.state 供下游使用
        request.state.user_id = user_id
        return await call_next(request)
