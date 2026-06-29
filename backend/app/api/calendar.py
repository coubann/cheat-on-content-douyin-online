"""内容日历路由

提供日历查看、排期管理接口。

用户数据隔离：从 request.state.user_id 获取当前用户，传入 service 层。
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from backend.app.config import DATA_DIR
from backend.app.models.response import ApiResponse
from backend.app.services import calendar_service

router = APIRouter()


class ScheduleRequest(BaseModel):
    """添加排期请求"""
    date: str = Field(..., description="排期日期，格式 YYYY-MM-DD")
    script_id: str = Field(..., description="脚本 ID")
    platform: str = Field(default="douyin", description="发布平台")
    notes: str = Field(default="", description="备注")


class ScheduleUpdateRequest(BaseModel):
    """更新排期请求"""
    date: str | None = None
    platform: str | None = None
    notes: str | None = None
    status: str | None = None


@router.get("")
async def get_calendar(days: int = Query(default=14, ge=1, le=90, description="天数"), request: Request = None) -> ApiResponse:
    """获取内容日历

    Pre-conditions:
      - 项目已初始化
    Post-conditions:
      - 返回日历数据
    Side effects:
      - 无
    """
    user_id = getattr(request.state, "user_id", 0)
    try:
        data = calendar_service.get_calendar(DATA_DIR, user_id=user_id, days=days)
        return ApiResponse(ok=True, data=data)
    except FileNotFoundError:
        return ApiResponse(
            ok=False,
            error={"code": "NOT_INITIALIZED", "message": "项目未初始化，请先执行初始化"},
        )


@router.post("/schedule")
async def add_schedule(req: ScheduleRequest, request: Request) -> ApiResponse:
    """添加排期

    Pre-conditions:
      - 项目已初始化
      - date 格式为 YYYY-MM-DD
    Post-conditions:
      - 排期被创建
    Side effects:
      - 写文件系统
    """
    user_id = getattr(request.state, "user_id", 0)
    try:
        schedule = calendar_service.add_schedule(
            DATA_DIR,
            user_id=user_id,
            date=req.date,
            script_id=req.script_id,
            platform=req.platform,
            notes=req.notes,
        )
        return ApiResponse(ok=True, data=schedule)
    except Exception as e:
        return ApiResponse(
            ok=False,
            error={"code": "SCHEDULE_ERROR", "message": str(e)},
        )


@router.put("/schedule/{schedule_id}")
async def update_schedule(schedule_id: str, req: ScheduleUpdateRequest, request: Request) -> ApiResponse:
    """更新排期

    Pre-conditions:
      - 排期存在
    Post-conditions:
      - 排期被更新
    Side effects:
      - 写文件系统
    """
    user_id = getattr(request.state, "user_id", 0)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        return ApiResponse(
            ok=False,
            error={"code": "NO_UPDATES", "message": "没有需要更新的字段"},
        )
    try:
        schedule = calendar_service.update_schedule(DATA_DIR, user_id=user_id, schedule_id=schedule_id, updates=updates)
        return ApiResponse(ok=True, data=schedule)
    except ValueError as e:
        return ApiResponse(
            ok=False,
            error={"code": "NOT_FOUND", "message": str(e)},
        )


@router.delete("/schedule/{schedule_id}")
async def remove_schedule(schedule_id: str, request: Request) -> ApiResponse:
    """删除排期

    Pre-conditions:
      - 无
    Post-conditions:
      - 排期被删除
    Side effects:
      - 写文件系统
    """
    user_id = getattr(request.state, "user_id", 0)
    calendar_service.remove_schedule(DATA_DIR, user_id=user_id, schedule_id=schedule_id)
    return ApiResponse(ok=True, data={"message": "排期已删除"})
