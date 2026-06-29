"""A/B 实验路由"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.app.config import DATA_DIR
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.ab_experiment_service import (
    complete_experiment,
    create_experiment,
    get_experiment,
    list_experiments,
    predict_both,
)

router = APIRouter()


class CreateExperimentRequest(BaseModel):
    topic: str
    script_a_id: str
    script_b_id: str
    hypothesis: str = ""


class CompleteExperimentRequest(BaseModel):
    actual_plays_a: int = Field(ge=0)
    actual_plays_b: int = Field(ge=0)


@router.post("")
async def create_experiment_endpoint(req: CreateExperimentRequest, request: Request) -> ApiResponse:
    """创建 A/B 实验"""
    try:
        result = await create_experiment(
            DATA_DIR, req.topic, req.script_a_id, req.script_b_id, req.hypothesis
        )
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError as e:
        return ApiResponse(ok=False, error=ErrorDetail(code="SCRIPT_NOT_FOUND", message=str(e)))
    except ValueError as e:
        return ApiResponse(ok=False, error=ErrorDetail(code="INVALID_REQUEST", message=str(e)))


@router.get("")
async def list_experiments_endpoint() -> ApiResponse:
    """列出所有实验"""
    result = await list_experiments(DATA_DIR)
    return ApiResponse(ok=True, data={"experiments": result})


@router.get("/{experiment_id}")
async def get_experiment_endpoint(experiment_id: str) -> ApiResponse:
    """获取实验详情"""
    result = await get_experiment(DATA_DIR, experiment_id)
    if not result:
        return ApiResponse(ok=False, error=ErrorDetail(code="EXPERIMENT_NOT_FOUND", message="实验不存在"))
    return ApiResponse(ok=True, data=result)


@router.post("/{experiment_id}/predict")
async def predict_both_endpoint(experiment_id: str, request: Request) -> ApiResponse:
    """对实验的两个脚本分别运行预测"""
    user_id = getattr(request.state, "user_id", 0)
    try:
        result = await predict_both(DATA_DIR, experiment_id, user_id=user_id)
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError as e:
        return ApiResponse(ok=False, error=ErrorDetail(code="EXPERIMENT_NOT_FOUND", message=str(e)))
    except ValueError as e:
        return ApiResponse(ok=False, error=ErrorDetail(code="INVALID_REQUEST", message=str(e)))


@router.post("/{experiment_id}/complete")
async def complete_experiment_endpoint(experiment_id: str, req: CompleteExperimentRequest) -> ApiResponse:
    """用实际播放量完成实验"""
    try:
        result = await complete_experiment(
            DATA_DIR, experiment_id, req.actual_plays_a, req.actual_plays_b
        )
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError as e:
        return ApiResponse(ok=False, error=ErrorDetail(code="EXPERIMENT_NOT_FOUND", message=str(e)))
    except ValueError as e:
        return ApiResponse(ok=False, error=ErrorDetail(code="INVALID_REQUEST", message=str(e)))
