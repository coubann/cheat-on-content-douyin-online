"""发布复盘路由"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.config import DATA_DIR
from backend.app.errors import FILE_NOT_FOUND, PREDICTION_NOT_FOUND
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.publish_service import list_published, register_publish, register_shoot
from backend.app.services.retro_report_service import generate_retro_report, get_retro_report, list_retro_reports
from backend.app.services.retro_service import retro_predict

router = APIRouter()


class ShootRequest(BaseModel):
    script_id: str
    shoot_content: str


class PublishRequest(BaseModel):
    script_id: str
    platform: str
    publish_url: str | None = None
    published_at: str | None = None


class RetroRequest(BaseModel):
    prediction_id: str
    actual_plays: int = Field(gt=0)
    actual_likes: int | None = None
    actual_comments: int | None = None
    actual_shares: int | None = None
    retro_notes: str | None = None
    days_since_publish: int = 3


@router.post("/shoot")
async def register_shoot_endpoint(req: ShootRequest) -> ApiResponse:
    """登记拍摄 — cheat-shoot"""
    try:
        result = await register_shoot(DATA_DIR, req.script_id, req.shoot_content)
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code="SCRIPT_NOT_FOUND",
                message=f"脚本不存在: {req.script_id}",
                suggested_action="请先 POST /api/scripts 创建草稿",
            ),
        )


@router.post("")
async def register_publish_endpoint(req: PublishRequest) -> ApiResponse:
    """发布登记 — cheat-publish"""
    try:
        result = await register_publish(
            DATA_DIR, req.script_id, req.platform, req.publish_url, req.published_at
        )
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError as e:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=FILE_NOT_FOUND,
                message=str(e),
                suggested_action="请先 POST /api/publish/shoot 登记拍摄",
            ),
        )


@router.get("")
async def list_published_endpoint() -> ApiResponse:
    """列出已发布内容"""
    result = await list_published(DATA_DIR)
    return ApiResponse(ok=True, data={"videos": result})


@router.post("/retro/{prediction_id}")
async def retro_endpoint(prediction_id: str, req: RetroRequest) -> ApiResponse:
    """复盘 — cheat-retro"""
    try:
        result = await retro_predict(
            DATA_DIR,
            prediction_id,
            req.actual_plays,
            req.actual_likes,
            req.actual_comments,
            req.actual_shares,
            req.retro_notes,
            req.days_since_publish,
        )
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError as e:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=PREDICTION_NOT_FOUND,
                message=str(e),
                suggested_action="请检查 prediction_id 是否正确",
            ),
        )


@router.get("/retro-report")
async def retro_report_endpoint() -> ApiResponse:
    """生成自动化复盘报告"""
    result = await generate_retro_report(DATA_DIR)
    return ApiResponse(ok=True, data=result)


@router.get("/retro-reports")
async def list_retro_reports_endpoint() -> ApiResponse:
    """列出历史复盘报告"""
    result = await list_retro_reports(DATA_DIR)
    return ApiResponse(ok=True, data={"reports": result})


@router.get("/retro-reports/{report_id}")
async def get_retro_report_endpoint(report_id: str) -> ApiResponse:
    """获取指定历史复盘报告"""
    result = await get_retro_report(DATA_DIR, report_id)
    if result is None:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code="REPORT_NOT_FOUND",
                message=f"报告不存在: {report_id}",
                suggested_action="请检查 report_id 或调用 GET /api/publish/retro-reports 查看可用报告",
            ),
        )
    return ApiResponse(ok=True, data=result)
