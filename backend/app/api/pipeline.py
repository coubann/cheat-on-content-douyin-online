"""全链路追踪路由

提供内容生命周期追踪接口。

用户数据隔离：从 request.state.user_id 获取当前用户，传入 service 层。
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.config import DATA_DIR
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services import pipeline_service

router = APIRouter()


@router.get("")
async def get_pipeline(request: Request) -> ApiResponse:
    """获取全链路追踪数据

    Pre-conditions:
      - 项目已初始化
    Post-conditions:
      - 返回所有内容的生命周期追踪数据
    Side effects:
      - 无
    """
    user_id = getattr(request.state, "user_id", 0)
    try:
        data = pipeline_service.get_pipeline(DATA_DIR, user_id=user_id)
        return ApiResponse(ok=True, data=data)
    except FileNotFoundError:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(code="NOT_INITIALIZED", message="项目未初始化，请先执行初始化"),
        )
