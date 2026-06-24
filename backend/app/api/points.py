"""点数相关路由 — 余额查询、记录、签到"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Header
from pydantic import BaseModel

from backend.app.config import CHECKIN_POINTS, CHECKIN_STREAK_7_BONUS, CHECKIN_STREAK_30_BONUS
from backend.app.db.session import async_session_factory
from backend.app.errors import AUTH_UNAUTHORIZED
from backend.app.models.points_log import PointsLog
from backend.app.models.user import User
from backend.app.models.user_action import UserAction
from backend.app.services.jwt_service import get_user_id_from_token
from backend.app.models.response import ApiResponse, ErrorDetail

router = APIRouter()


def _get_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return None


async def _require_user(authorization: str | None) -> tuple[int, ApiResponse | None]:
    token = _get_token(authorization)
    if token is None:
        return 0, ApiResponse(
            ok=False,
            error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="未登录"),
        )
    user_id = get_user_id_from_token(token)
    if user_id is None:
        return 0, ApiResponse(
            ok=False,
            error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="Token 无效"),
        )
    return user_id, None


@router.get("/balance")
async def points_balance(authorization: str | None = Header(None)) -> ApiResponse:
    """查询当前用户点数余额"""
    uid, err = await _require_user(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        user = await session.get(User, uid)
        if user is None:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code="USER_NOT_FOUND", message="用户不存在"),
            )
        return ApiResponse(ok=True, data={
            "free_points_today": user.free_points_today,
            "total_points": user.points,
            "membership_type": user.membership_type,
        })


@router.get("/log")
async def points_log(
    limit: int = 50,
    offset: int = 0,
    authorization: str | None = Header(None),
) -> ApiResponse:
    """查询点数记录"""
    uid, err = await _require_user(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        from sqlalchemy import select, desc
        result = await session.execute(
            select(PointsLog)
            .where(PointsLog.user_id == uid)
            .order_by(desc(PointsLog.created_at))
            .offset(offset)
            .limit(limit)
        )
        logs = result.scalars().all()
        return ApiResponse(ok=True, data=[{
            "change": log.change,
            "reason": log.reason,
            "detail": log.detail,
            "balance_after": log.balance_after,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        } for log in logs])


@router.post("/checkin")
async def daily_checkin(authorization: str | None = Header(None)) -> ApiResponse:
    """每日签到"""
    uid, err = await _require_user(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        user = await session.get(User, uid)
        if user is None:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code="USER_NOT_FOUND", message="用户不存在"),
            )

        today = date.today()

        # 检查今日是否已签到
        if user.last_checkin_date == today:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code="ALREADY_CHECKED_IN", message="今日已签到"),
            )

        # 判断是否连续签到
        yesterday = date.fromordinal(today.toordinal() - 1)
        if user.last_checkin_date == yesterday:
            user.checkin_streak += 1
        elif user.last_checkin_date is None:
            user.checkin_streak = 1
        else:
            user.checkin_streak = 1  # 断签重置

        user.last_checkin_date = today

        # 发放签到点数
        earned = CHECKIN_POINTS

        # 连续签到加成
        bonus = 0
        if user.checkin_streak >= 30:
            bonus = CHECKIN_STREAK_30_BONUS
        elif user.checkin_streak >= 7:
            bonus = CHECKIN_STREAK_7_BONUS

        earned += bonus

        user.free_points_today += earned

        # 记录日志
        detail = f"签到连续 {user.checkin_streak} 天"
        if bonus > 0:
            detail += f" (+{bonus} 连续签到加成)"

        session.add(PointsLog(
            user_id=user.id,
            change=earned,
            reason="checkin",
            detail=detail,
            balance_after=user.free_points_today,
        ))

        session.add(UserAction(
            user_id=user.id,
            action="checkin",
            detail=detail,
        ))

        await session.commit()

        return ApiResponse(ok=True, data={
            "earned": earned,
            "bonus": bonus,
            "streak": user.checkin_streak,
            "free_points_today": user.free_points_today,
        })
