"""发布时间推荐路由 — 已接入点数扣减"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.app.config import DATA_DIR
from backend.app.errors import LLM_CALL_FAILED, POINTS_INSUFFICIENT
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.points_service import POINTS_COST, check_balance_enough, deduct_points
from backend.app.services.publish_time_service import suggest_publish_time

router = APIRouter()


class PublishTimeSuggestRequest(BaseModel):
    script_id: str | None = None
    platform: str = "douyin"


@router.post("/suggest")
async def suggest_publish_time_endpoint(req: PublishTimeSuggestRequest, request: Request) -> ApiResponse:
    """推荐最佳发布时间 — 扣 3 点"""
    user_id = getattr(request.state, "user_id", None)

    cost = POINTS_COST["publish_suggest"]
    if user_id:
        enough, msg = await check_balance_enough(user_id, cost)
        if not enough:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code=POINTS_INSUFFICIENT, message=msg),
            )

    try:
        result = await suggest_publish_time(
            DATA_DIR,
            user_id=user_id or 0,
            script_id=req.script_id,
            platform=req.platform,
        )

        if user_id:
            await deduct_points(user_id, cost, "publish_suggest")

        return ApiResponse(ok=True, data=result)
    except FileNotFoundError:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code="STATE_NOT_FOUND",
                message=".cheat-state.json 不存在，请先初始化项目",
                suggested_action="请先 POST /api/init 初始化项目",
            ),
        )
