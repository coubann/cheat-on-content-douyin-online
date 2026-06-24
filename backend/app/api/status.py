"""状态看板路由"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.config import DATA_DIR
from backend.app.models.response import ApiResponse
from backend.app.services.status_service import get_status, get_today

router = APIRouter()


@router.get("")
async def status_endpoint() -> ApiResponse:
    """buffer / confidence / 校准进度 / 健康度"""
    result = await get_status(DATA_DIR)
    return ApiResponse(ok=True, data=result)


@router.get("/today")
async def today_endpoint() -> ApiResponse:
    """今日 todo（按优先级）"""
    result = await get_today(DATA_DIR)
    return ApiResponse(ok=True, data=result)
