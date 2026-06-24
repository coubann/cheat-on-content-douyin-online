"""公开公告路由 — 获取当前生效公告"""
from __future__ import annotations

from fastapi import APIRouter

from backend.app.db.session import async_session_factory
from backend.app.models.announcement import Announcement
from backend.app.models.response import ApiResponse

router = APIRouter()


@router.get("/active")
async def get_active_announcement() -> ApiResponse:
    """获取当前生效的最新公告（首页显示）"""
    async with async_session_factory() as session:
        from sqlalchemy import select, desc
        result = await session.execute(
            select(Announcement)
            .where(Announcement.active == True)
            .order_by(desc(Announcement.created_at))
            .limit(1)
        )
        ann = result.scalar_one_or_none()
        if ann is None:
            return ApiResponse(ok=True, data=None)
        return ApiResponse(ok=True, data={
            "id": ann.id,
            "title": ann.title,
            "content": ann.content,
            "type": ann.type,
            "created_at": ann.created_at.isoformat() if ann.created_at else None,
        })
