"""竞品监控路由"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.config import DATA_DIR
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.competitor_monitor import (
    add_monitor,
    check_all_updates,
    check_updates,
    get_update_history,
    list_monitors,
    remove_monitor,
)

router = APIRouter()


class AddMonitorRequest(BaseModel):
    account_name: str
    platform: str = "douyin"
    check_interval_hours: int = Field(default=24, ge=1)


@router.post("")
async def add_monitor_endpoint(req: AddMonitorRequest) -> ApiResponse:
    """添加竞品监控"""
    try:
        result = await add_monitor(DATA_DIR, req.account_name, req.platform, req.check_interval_hours)
        return ApiResponse(ok=True, data=result)
    except ValueError as e:
        return ApiResponse(ok=False, error=ErrorDetail(code="INVALID_REQUEST", message=str(e)))


@router.get("")
async def list_monitors_endpoint() -> ApiResponse:
    """列出所有监控"""
    result = await list_monitors(DATA_DIR)
    return ApiResponse(ok=True, data={"monitors": result})


@router.delete("/{monitor_id}")
async def remove_monitor_endpoint(monitor_id: str) -> ApiResponse:
    """移除监控"""
    try:
        result = await remove_monitor(DATA_DIR, monitor_id)
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError as e:
        return ApiResponse(ok=False, error=ErrorDetail(code="MONITOR_NOT_FOUND", message=str(e)))


@router.post("/{monitor_id}/check")
async def check_updates_endpoint(monitor_id: str) -> ApiResponse:
    """检查指定监控是否有新内容"""
    try:
        result = await check_updates(DATA_DIR, monitor_id)
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError as e:
        return ApiResponse(ok=False, error=ErrorDetail(code="MONITOR_NOT_FOUND", message=str(e)))


@router.post("/check-all")
async def check_all_updates_endpoint() -> ApiResponse:
    """检查所有监控是否有新内容"""
    result = await check_all_updates(DATA_DIR)
    return ApiResponse(ok=True, data={"results": result})


@router.get("/{monitor_id}/history")
async def get_update_history_endpoint(monitor_id: str) -> ApiResponse:
    """获取指定监控的更新历史"""
    result = await get_update_history(DATA_DIR, monitor_id)
    return ApiResponse(ok=True, data={"history": result})
