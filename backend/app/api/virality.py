"""爆款预测路由 — virality API"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.config import DATA_DIR
from backend.app.errors import SCRIPT_NOT_FOUND
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.models.state import CheatState, ScoreResult
from backend.app.services.blind_scorer import score_script
from backend.app.services.file_io import read_file
from backend.app.services.predictor import predict_virality

router = APIRouter()


class ViralityPredictRequest(BaseModel):
    script_id: str


@router.post("/predict")
async def virality_predict(req: ViralityPredictRequest) -> ApiResponse:
    """爆款预测 — 仅返回爆款分 + 诊断，不落盘"""
    try:
        # 读取 state
        state = CheatState.model_validate_json(read_file(DATA_DIR / ".cheat-state.json"))
        # 盲打分
        score_data = await score_script(DATA_DIR, req.script_id)
        score_result = ScoreResult(**score_data)
        # 爆款预测
        result = await predict_virality(DATA_DIR, req.script_id, score_result, state)
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


@router.get("/history")
async def virality_history() -> ApiResponse:
    """爆款预测历史"""
    predictions_dir = DATA_DIR / "predictions"
    if not predictions_dir.exists():
        return ApiResponse(ok=True, data={"history": []})

    history = []
    for f in sorted(predictions_dir.glob("*.md"), reverse=True):
        history.append({"id": f.stem, "path": str(f)})

    return ApiResponse(ok=True, data={"history": history})


@router.post("/suggest-edits")
async def suggest_edits(req: ViralityPredictRequest) -> ApiResponse:
    """改稿建议 — 基于打分结果给出具体修改建议"""
    try:
        state = CheatState.model_validate_json(read_file(DATA_DIR / ".cheat-state.json"))
        score_data = await score_script(DATA_DIR, req.script_id)
        score_result = ScoreResult(**score_data)
        result = await predict_virality(DATA_DIR, req.script_id, score_result, state)
        return ApiResponse(ok=True, data={"suggestions": result.get("suggestions", [])})
    except FileNotFoundError:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=SCRIPT_NOT_FOUND,
                message=f"脚本不存在: {req.script_id}",
                suggested_action="请先 POST /api/scripts 创建草稿",
            ),
        )
