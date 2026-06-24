"""受众画像 API 路由 — cheat-persona 的 Web 接口 — 已接入点数扣减"""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.config import DATA_DIR
from backend.app.errors import FILE_NOT_FOUND, LLM_CALL_FAILED, POINTS_INSUFFICIENT
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.persona_service import build_persona, get_persona, update_persona
from backend.app.services.points_service import POINTS_COST, check_balance_enough, deduct_points

router = APIRouter()


@router.post("/build")
async def build_persona_endpoint(request: Request) -> ApiResponse:
    """从已复盘数据构建受众画像 — 扣 15 点"""
    user_id = getattr(request.state, "user_id", None)

    cost = POINTS_COST["mimic"]
    if user_id:
        enough, msg = await check_balance_enough(user_id, cost)
        if not enough:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code=POINTS_INSUFFICIENT, message=msg),
            )

    result = await build_persona(DATA_DIR)
    # 即使 build_persona 内部调 LLM 失败，也不重复扣点（因为没成功）
    # 但 build_persona 没有捕获 LLM 异常，需要额外处理
    if result.get("status") == "no_data":
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=FILE_NOT_FOUND,
                message="尚无评论数据，无法构建画像",
                suggested_action="请先完成至少一篇复盘（POST /api/publish/retro/<id>）",
            ),
        )
    if result.get("status") == "error":
        # LLM 调用失败的情况，不扣点
        if user_id:
            pass  # 不扣点
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=LLM_CALL_FAILED,
                message=result.get("message", "构建画像失败"),
            ),
        )

    # 成功，扣点
    if user_id:
        await deduct_points(user_id, cost, "mimic")
    return ApiResponse(ok=True, data=result)


@router.get("")
async def get_persona_endpoint() -> ApiResponse:
    """获取当前受众画像 — 不扣点"""
    persona = get_persona(DATA_DIR)
    if persona is None:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=FILE_NOT_FOUND,
                message="受众画像尚未构建",
                suggested_action="请先 POST /api/persona/build 构建画像",
            ),
        )
    return ApiResponse(ok=True, data=persona)


@router.put("")
async def update_persona_endpoint(updates: dict, request: Request) -> ApiResponse:
    """更新受众画像 — 扣 15 点"""
    user_id = getattr(request.state, "user_id", None)

    cost = POINTS_COST["mimic"]
    if user_id:
        enough, msg = await check_balance_enough(user_id, cost)
        if not enough:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code=POINTS_INSUFFICIENT, message=msg),
            )

    result = await update_persona(DATA_DIR, updates)
    if result.get("status") == "not_found":
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=FILE_NOT_FOUND,
                message="受众画像尚未构建",
                suggested_action="请先 POST /api/persona/build 构建画像",
            ),
        )
    if result.get("status") == "error":
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=LLM_CALL_FAILED,
                message=result.get("message", "更新画像失败"),
            ),
        )

    if user_id:
        await deduct_points(user_id, cost, "mimic")
    return ApiResponse(ok=True, data=result)
