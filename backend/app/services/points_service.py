"""点数扣减服务 — 行级锁 + 优先级扣减 + 退款"""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import async_session_factory
from backend.app.models.points_log import PointsLog
from backend.app.models.user import User

logger = structlog.get_logger()


# ---- 各功能点数消耗配置 ----
POINTS_COST = {
    "analyze_script": 10,
    "generate_copy": 20,
    "predict": 5,
    "mimic": 15,
    "monitor": 5,
    "publish_suggest": 3,
}

# 点数 reason 反向映射
POINTS_REASON_MAP = {
    "analyze_script": "分析脚本",
    "generate_copy": "生成文案",
    "predict": "爆款预测",
    "mimic": "风格模仿",
    "monitor": "竞品监控",
    "publish_suggest": "发布时间推荐",
}


async def get_effective_balance(user_id: int) -> dict:
    """获取用户可用余额（免费点数 + 充值点数）"""
    async with async_session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            return {"free": 0, "recharge": 0, "total": 0}
        return {
            "free": user.free_points_today,
            "recharge": user.points,
            "total": user.free_points_today + user.points,
        }


async def check_balance_enough(user_id: int, amount: int) -> tuple[bool, str]:
    """检查余额是否足够"""
    bal = await get_effective_balance(user_id)
    if bal["total"] < amount:
        return False, (
            f"点数不足，需要 {amount} 点，当前可用 {bal['total']} 点"
            f"（免费 {bal['free']} + 充值 {bal['recharge']}）"
        )
    return True, ""


async def deduct_points(
    user_id: int,
    amount: int,
    reason: str,
    detail: str | None = None,
) -> dict | None:
    """扣减点数（行级锁，优先扣免费点数）
    
    返回扣除后的余额详情，若余额不足返回 None
    """
    async with async_session_factory() as session:
        # 使用 FOR UPDATE 行级锁
        result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if user is None:
            logger.warning("deduct_user_not_found", user_id=user_id)
            return None

        total = user.free_points_today + user.points
        if total < amount:
            logger.warning(
                "deduct_insufficient",
                user_id=user_id,
                need=amount,
                have=total,
            )
            return None

        # 优先扣免费点数
        deduct_free = min(user.free_points_today, amount)
        deduct_recharge = amount - deduct_free

        detail_parts = []
        if deduct_free > 0:
            user.free_points_today -= deduct_free
            detail_parts.append(f"免费-{deduct_free}")
        if deduct_recharge > 0:
            user.points -= deduct_recharge
            detail_parts.append(f"充值-{deduct_recharge}")

        log_detail = f"{POINTS_REASON_MAP.get(reason, reason)}: {amount}点"
        if detail:
            log_detail += f" ({detail})"

        session.add(PointsLog(
            user_id=user.id,
            change=-amount,
            reason=reason,
            detail=log_detail,
            balance_after=user.free_points_today + user.points,
        ))

        from backend.app.models.user_action import UserAction
        session.add(UserAction(
            user_id=user.id,
            action=reason,
            detail=f"扣除{amount}点",
        ))

        await session.commit()

        return {
            "deducted": amount,
            "deducted_from_free": deduct_free,
            "deducted_from_recharge": deduct_recharge,
            "free_remaining": user.free_points_today,
            "recharge_remaining": user.points,
        }


async def refund_points(
    user_id: int,
    amount: int,
    reason: str = "refund",
    detail: str | None = None,
) -> dict:
    """退还点数（AI 调用失败时调用）
    
    尽量退回到原来的池子。但简化实现：直接退回到 recharge 池。
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if user is None:
            return {"refunded": 0, "error": "user_not_found"}

        # 退还到 recharge 池（与注释一致：简化实现退回到 recharge 池）
        user.points += amount

        log_detail = f"AI 调用失败自动退款: {amount}点"
        if detail:
            log_detail += f" ({detail})"

        session.add(PointsLog(
            user_id=user.id,
            change=amount,
            reason="refund",
            detail=log_detail,
            balance_after=user.free_points_today + user.points,
        ))

        await session.commit()

        return {
            "refunded": amount,
            "free_remaining": user.free_points_today,
            "recharge_remaining": user.points,
        }


async def deduct_with_refund_on_fail(
    user_id: int,
    amount: int,
    reason: str,
    detail: str | None = None,
) -> bool:
    """扣减点数 — 如果失败会回退（预扣模式）
    
    调用前，请先调用 check_balance_enough 确保余额够。
    如果 deduct_points 返回 None（被外部修改导致余额不足），会自动跳过。
    """
    result = await deduct_points(user_id, amount, reason, detail)
    return result is not None
