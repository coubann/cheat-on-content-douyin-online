"""通知路由 — 复盘提醒 + bump 建议 + buffer 预警"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.config import DATA_DIR
from backend.app.errors import NOTIFICATION_NOT_FOUND
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.notification_service import (
    get_notification_summary,
    mark_notification_read,
)

router = APIRouter()


@router.get("")
async def get_notifications() -> ApiResponse:
    """获取所有待处理通知

    返回 pending_retros、bump_suggestions、low_buffer_warnings。
    """
    summary = get_notification_summary(DATA_DIR)
    return ApiResponse(ok=True, data={
        "notifications": summary.get("notifications", []),
        "total_unread": summary.get("total_unread", 0),
    })


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str) -> ApiResponse:
    """标记通知为已读"""
    try:
        result = mark_notification_read(DATA_DIR, notification_id)
        return ApiResponse(ok=True, data=result)
    except ValueError as e:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=NOTIFICATION_NOT_FOUND,
                message=str(e),
                suggested_action="请检查 notification_id 是否正确",
            ),
        )


@router.get("/summary")
async def get_summary() -> ApiResponse:
    """获取通知摘要计数"""
    summary = get_notification_summary(DATA_DIR)
    return ApiResponse(ok=True, data={
        "pending_retros": summary["pending_retros"],
        "bump_suggestions": summary["bump_suggestions"],
        "low_buffer_warnings": summary["low_buffer_warnings"],
        "total_unread": summary["total_unread"],
    })
