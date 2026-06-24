"""邀请相关路由"""
from __future__ import annotations

from fastapi import APIRouter, Header

from backend.app.db.session import async_session_factory
from backend.app.errors import AUTH_UNAUTHORIZED
from backend.app.models.invite_record import InviteRecord
from backend.app.models.points_log import PointsLog
from backend.app.models.user import User
from backend.app.services.jwt_service import get_user_id_from_token
from backend.app.models.response import ApiResponse, ErrorDetail

router = APIRouter()


def _get_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return None


@router.get("/my-code")
async def get_my_invite_code(authorization: str | None = Header(None)) -> ApiResponse:
    """获取我的邀请码"""
    token = _get_token(authorization)
    if token is None:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="未登录"),
        )
    user_id = get_user_id_from_token(token)
    if user_id is None:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="Token 无效"),
        )

    async with async_session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code="USER_NOT_FOUND", message="用户不存在"),
            )
        return ApiResponse(ok=True, data={
            "invite_code": user.invite_code,
        })


@router.get("/records")
async def get_my_invite_records(authorization: str | None = Header(None)) -> ApiResponse:
    """我的邀请记录"""
    token = _get_token(authorization)
    if token is None:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="未登录"),
        )
    user_id = get_user_id_from_token(token)
    if user_id is None:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="Token 无效"),
        )

    async with async_session_factory() as session:
        from sqlalchemy import select, desc
        result = await session.execute(
            select(InviteRecord)
            .where(InviteRecord.inviter_id == user_id)
            .order_by(desc(InviteRecord.created_at))
        )
        records = result.scalars().all()

        # 获取被邀请人信息
        invitees = []
        for r in records:
            invitee = await session.get(User, r.invitee_id)
            invitees.append({
                "id": r.id,
                "invitee_email": invitee.email if invitee else "unknown",
                "invitee_username": invitee.username if invitee else "unknown",
                "reward_granted": r.reward_granted,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

        # 统计
        total_reward = await session.execute(
            select(PointsLog)
            .where(
                PointsLog.user_id == user_id,
                PointsLog.reason == "invite_reward",
            )
        )
        total_points = sum(
            log.change for log in total_reward.scalars().all() if log.change > 0
        )

        return ApiResponse(ok=True, data={
            "total_invited": len(records),
            "total_reward_points": total_points,
            "records": invitees,
        })
