"""状态看板路由

用户数据隔离：从 request.state.user_id 获取当前用户，传入 service 层。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.config import DATA_DIR
from backend.app.models.response import ApiResponse
from backend.app.services.status_service import get_status, get_today

router = APIRouter()


@router.get("")
async def status_endpoint(request: Request) -> ApiResponse:
    """buffer / confidence / 校准进度 / 健康度"""
    user_id = getattr(request.state, "user_id", 0)
    result = await get_status(DATA_DIR, user_id=user_id)
    return ApiResponse(ok=True, data=result)


@router.get("/today")
async def today_endpoint(request: Request) -> ApiResponse:
    """今日 todo（按优先级）"""
    user_id = getattr(request.state, "user_id", 0)
    result = await get_today(DATA_DIR, user_id=user_id)
    return ApiResponse(ok=True, data=result)
