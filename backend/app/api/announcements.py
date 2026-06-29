"""公开公告路由 — 获取当前生效公告"""
from __future__ import annotations

from fastapi import APIRouter, Header
from sqlalchemy import desc, select

from backend.app.db.session import async_session_factory
from backend.app.models.announcement import Announcement
from backend.app.models.dismissed_announcement import DismissedAnnouncement
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.jwt_service import get_user_id_from_token

router = APIRouter()


def _get_token(authorization: str | None) -> str | None:
    """从 Authorization header 提取 token"""
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return None


@router.get("/active")
async def get_active_announcement(authorization: str | None = Header(None)) -> ApiResponse:
    """获取当前生效的最新公告（已登录用户排除已关闭的）"""
    # 解析用户
    user_id = None
    token = _get_token(authorization)
    if token:
        user_id = get_user_id_from_token(token)

    async with async_session_factory() as session:
        query = (
            select(Announcement)
            .where(Announcement.active == True)
            .order_by(desc(Announcement.created_at))
            .limit(1)
        )
        result = await session.execute(query)
        ann = result.scalar_one_or_none()
        if ann is None:
            return ApiResponse(ok=True, data=None)

        # 如果用户已登录，检查是否已关闭此公告
        if user_id is not None:
            dismissed = await session.execute(
                select(DismissedAnnouncement).where(
                    DismissedAnnouncement.user_id == user_id,
                    DismissedAnnouncement.announcement_id == ann.id,
                )
            )
            if dismissed.scalar_one_or_none() is not None:
                return ApiResponse(ok=True, data=None)

        return ApiResponse(ok=True, data={
            "id": ann.id,
            "title": ann.title,
            "content": ann.content,
            "type": ann.type,
            "created_at": ann.created_at.isoformat() if ann.created_at else None,
        })


@router.post("/{ann_id}/dismiss")
async def dismiss_announcement(ann_id: int, authorization: str | None = Header(None)) -> ApiResponse:
    """用户关闭公告（不再显示）"""
    token = _get_token(authorization)
    if not token:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(code="UNAUTHORIZED", message="未登录"),
        )
    user_id = get_user_id_from_token(token)
    if not user_id:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(code="UNAUTHORIZED", message="Token无效"),
        )

    async with async_session_factory() as session:
        existing = await session.execute(
            select(DismissedAnnouncement).where(
                DismissedAnnouncement.user_id == user_id,
                DismissedAnnouncement.announcement_id == ann_id,
            )
        )
        if existing.scalar_one_or_none() is None:
            session.add(DismissedAnnouncement(user_id=user_id, announcement_id=ann_id))
            await session.commit()

    return ApiResponse(ok=True, data={"dismissed": True})
