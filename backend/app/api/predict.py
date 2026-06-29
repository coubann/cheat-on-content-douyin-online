"""预测引擎路由 — 已接入点数扣减"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.app.config import DATA_DIR
from backend.app.errors import LLM_CALL_FAILED, PREDICTION_EXISTS, PREDICTION_NOT_FOUND, SCRIPT_NOT_FOUND
from backend.app.errors import POINTS_INSUFFICIENT
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.blind_scorer import score_script
from backend.app.services.llm import LLMCallError
from backend.app.services.points_service import POINTS_COST, check_balance_enough, deduct_points
from backend.app.services.guide_service import advance_guide_step
from backend.app.services.predict_service import (
    full_predict,
    generate_optimized_script,
    get_prediction_detail,
    list_predictions,
)

router = APIRouter()


@router.get("/list")
async def list_all_predictions(request: Request) -> ApiResponse:
    """列出所有已预测的脚本"""
    user_id = getattr(request.state, "user_id", 0)
    result = await list_predictions(DATA_DIR, user_id=user_id)
    return ApiResponse(ok=True, data={"predictions": result})


class ScoreRequest(BaseModel):
    script_id: str


@router.post("/score")
async def score_script_endpoint(req: ScoreRequest, request: Request) -> ApiResponse:
    """仅打分（不写文件）— 盲打分 Channel B — 扣 10 点"""
    user_id = getattr(request.state, "user_id", None)

    # 检查点数
    cost = POINTS_COST["analyze_script"]
    if user_id:
        enough, msg = await check_balance_enough(user_id, cost)
        if not enough:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code=POINTS_INSUFFICIENT, message=msg),
            )

    try:
        # 盲打分使用用户隔离的 data_dir
        user_data_dir = DATA_DIR / str(user_id or 0)
        result = await score_script(user_data_dir, req.script_id)

        # 扣减点数
        if user_id:
            await deduct_points(user_id, cost, "analyze_script")
            await advance_guide_step(user_id, "analyze_script")

        return ApiResponse(ok=True, data=result)
    except FileNotFoundError:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=SCRIPT_NOT_FOUND,
                message=f"脚本不存在: {req.script_id}",
                suggested_action="请先 POST /api/scripts 创建草稿",
            ),
        )
    except LLMCallError as e:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=LLM_CALL_FAILED,
                message=f"LLM 调用失败: {e.message}",
                suggested_action="请检查 .env 中的 API Key 是否正确配置",
            ),
        )


@router.post("/full")
async def full_predict_endpoint(req: ScoreRequest, request: Request) -> ApiResponse:
    """完整预测流程（盲打分 + 爆款预测 + 落盘）— 扣 5 点"""
    user_id = getattr(request.state, "user_id", None)

    cost = POINTS_COST["predict"]
    if user_id:
        enough, msg = await check_balance_enough(user_id, cost)
        if not enough:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code=POINTS_INSUFFICIENT, message=msg),
            )

    try:
        result = await full_predict(DATA_DIR, req.script_id, user_id=(user_id or 0))

        if user_id:
            await deduct_points(user_id, cost, "predict")

        return ApiResponse(ok=True, data=result)
    except FileNotFoundError as e:
        error_code = SCRIPT_NOT_FOUND
        if PREDICTION_EXISTS in str(e):
            error_code = PREDICTION_EXISTS
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=error_code,
                message=str(e),
                suggested_action="请检查脚本ID是否正确，或预测是否已存在",
            ),
        )
    except FileExistsError as e:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=PREDICTION_EXISTS,
                message=str(e),
                suggested_action="该脚本已有预测，查看 GET /api/predict/<id>",
            ),
        )
    except LLMCallError as e:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=LLM_CALL_FAILED,
                message=f"LLM 调用失败: {e.message}",
                suggested_action="请检查 .env 中的 DEEPSEEK_API_KEY 是否正确配置",
            ),
        )


@router.get("/{prediction_id}")
async def get_prediction(prediction_id: str, request: Request) -> ApiResponse:
    """预测详情 — 不扣点"""
    user_id = getattr(request.state, "user_id", 0)
    try:
        result = await get_prediction_detail(DATA_DIR, prediction_id, user_id=user_id)
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=PREDICTION_NOT_FOUND,
                message=f"预测不存在: {prediction_id}",
                suggested_action="请先 POST /api/predict/full 创建预测",
            ),
        )


@router.post("/{prediction_id}/optimize")
async def optimize_script_endpoint(prediction_id: str, request: Request) -> ApiResponse:
    """基于预测结果生成最优文案 — 扣 20 点"""
    user_id = getattr(request.state, "user_id", None)

    cost = POINTS_COST["generate_copy"]
    if user_id:
        enough, msg = await check_balance_enough(user_id, cost)
        if not enough:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code=POINTS_INSUFFICIENT, message=msg),
            )

    try:
        result = await generate_optimized_script(DATA_DIR, prediction_id, user_id=(user_id or 0))

        if user_id:
            await deduct_points(user_id, cost, "generate_copy")
            await advance_guide_step(user_id, "generate_copy")

        return ApiResponse(ok=True, data=result)
    except FileNotFoundError as e:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=PREDICTION_NOT_FOUND,
                message=str(e),
            ),
        )
    except LLMCallError as e:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=LLM_CALL_FAILED,
                message=f"LLM 调用失败: {e.message}",
            ),
        )
