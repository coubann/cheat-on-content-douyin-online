"""会员/充值路由 — 爱发电对接"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from backend.app.config import IFDIAN_TOKEN, IFDIAN_USER_ID
from backend.app.db.session import async_session_factory
from backend.app.errors import AUTH_UNAUTHORIZED
from backend.app.models.order import Order
from backend.app.models.points_log import PointsLog
from backend.app.models.user import User
from backend.app.models.user_action import UserAction
from backend.app.services.jwt_service import get_user_id_from_token
from backend.app.models.response import ApiResponse, ErrorDetail

router = APIRouter()


# ---- 档位配置 ----
TIERS = {
    "basic": {
        "label": "Basic ¥10",
        "price": 1000,  # 分
        "points": 1800,
        "item_id": "d61da8826fa611f1b53f52540025c377",
        "url": "https://ifdian.net/item/d61da8826fa611f1b53f52540025c377",
    },
    "standard": {
        "label": "Standard ¥18",
        "price": 1800,
        "points": 5000,
        "item_id": "b4aebd6c6fa611f19d5352540025c377",
        "url": "https://ifdian.net/item/b4aebd6c6fa611f19d5352540025c377",
    },
    "premium": {
        "label": "Premium ¥50",
        "price": 5000,
        "points": 30000,
        "item_id": "fd9007666fa611f182f952540025c377",
        "url": "https://ifdian.net/item/fd9007666fa611f182f952540025c377",
    },
}


def _get_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return None


@router.get("/tiers")
async def get_tiers() -> ApiResponse:
    """获取所有会员档位"""
    return ApiResponse(ok=True, data=[
        {
            "tier": key,
            **tier,
        }
        for key, tier in TIERS.items()
    ])


@router.post("/create-order")
async def create_order(
    body: dict,
    authorization: str | None = Header(None),
) -> ApiResponse:
    """创建充值订单（生成 out_trade_no）"""
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

    tier = body.get("tier", "")
    if tier not in TIERS:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(code="INVALID_TIER", message="无效的会员档位"),
        )

    tier_config = TIERS[tier]
    import time

    out_trade_no = f"UID_{user_id}_{int(time.time())}"

    async with async_session_factory() as session:
        order = Order(
            user_id=user_id,
            out_trade_no=out_trade_no,
            tier=tier,
            amount=tier_config["price"],
            points_granted=tier_config["points"],
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

        return ApiResponse(ok=True, data={
            "order_id": order.id,
            "out_trade_no": out_trade_no,
            "tier": tier,
            "amount": tier_config["price"],
            "points_granted": tier_config["points"],
            "pay_url": tier_config["url"],
            "status": "pending",
        })


@router.get("/orders")
async def get_my_orders(authorization: str | None = Header(None)) -> ApiResponse:
    """查询我的订单列表"""
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
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(desc(Order.created_at))
        )
        orders = result.scalars().all()
        return ApiResponse(ok=True, data=[{
            "id": o.id,
            "out_trade_no": o.out_trade_no,
            "tier": o.tier,
            "amount": o.amount,
            "points_granted": o.points_granted,
            "status": o.status,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        } for o in orders])


# ---- item_id 到 tier 的反向映射 ----
_ITEM_ID_TO_TIER = {
    v["item_id"]: k
    for k, v in TIERS.items()
}


@router.post("/ifdian-callback")
async def ifdian_callback(request: Request) -> dict:
    """爱发电 Webhook 回调

    收到用户支付成功通知后，解析 out_trade_no 找到对应用户，充值点数。
    安全验证：通过 X-Ifdian-Token 头部与配置的 IFDIAN_TOKEN 比对。
    此接口返回普通 dict 而非 ApiResponse，因为爱发电需要 {ec:200} 格式。
    """
    # 获取原始 body
    body_bytes = await request.body()
    try:
        body = json.loads(body_bytes)
    except json.JSONDecodeError:
        return {"ec": 400, "em": "invalid json"}

    # Token 验证（爱发电使用 X-Ifdian-Token 头部）
    header_token = request.headers.get("X-Ifdian-Token", "")
    if header_token != IFDIAN_TOKEN:
        return {"ec": 400, "em": "invalid token"}

    # 解析订单数据
    order_data = body.get("order", {})
    out_trade_no = order_data.get("out_trade_no", "")
    ifdian_order_id = order_data.get("order_id", "")
    item_id = order_data.get("item_id", "")
    status = order_data.get("status", "")

    if status != "paid":
        return {"ec": 400, "em": "order not paid"}

    # 解析 out_trade_no 获取用户 ID
    # format: UID_{user_id}_{timestamp}
    if not out_trade_no.startswith("UID_"):
        return {"ec": 400, "em": "invalid out_trade_no"}
    try:
        user_id = int(out_trade_no.split("_")[1])
    except (IndexError, ValueError):
        return {"ec": 400, "em": "cannot parse user_id"}

    # 判断档位
    tier = _ITEM_ID_TO_TIER.get(item_id)
    if tier is None:
        return {"ec": 400, "em": f"unknown item_id: {item_id}"}

    tier_config = TIERS[tier]

    async with async_session_factory() as session:
        # 检查订单是否已处理
        from sqlalchemy import select
        result = await session.execute(
            select(Order).where(Order.out_trade_no == out_trade_no)
        )
        order = result.scalar_one_or_none()

        if order is not None and order.status == "paid":
            # 已处理过，直接返回成功
            return {"ec": 200, "em": "ok"}

        # 查找或创建订单
        if order is None:
            order = Order(
                user_id=user_id,
                out_trade_no=out_trade_no,
                ifdian_order_id=ifdian_order_id,
                tier=tier,
                amount=tier_config["price"],
                points_granted=tier_config["points"],
            )
            session.add(order)

        # 给用户充值
        user = await session.get(User, user_id)
        if user is None:
            return {"ec": 400, "em": "user not found"}

        user.points += tier_config["points"]

        # 更新订单状态
        order.status = "paid"
        order.ifdian_order_id = ifdian_order_id
        order.paid_at = datetime.now(timezone.utc)

        # 记录日志
        session.add(PointsLog(
            user_id=user_id,
            change=tier_config["points"],
            reason="membership_recharge",
            detail=f"爱发电充值 {tier} ({tier_config['label']}): +{tier_config['points']}点",
            balance_after=user.points,
        ))

        session.add(UserAction(
            user_id=user_id,
            action="recharge",
            detail=f"{tier} 充值成功",
        ))

        await session.commit()

    return {"ec": 200, "em": "ok"}


@router.get("/check-order/{order_id}")
async def check_order_status(
    order_id: int,
    authorization: str | None = Header(None),
) -> ApiResponse:
    """轮询订单支付状态"""
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
        order = await session.get(Order, order_id)
        if order is None or order.user_id != user_id:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code="ORDER_NOT_FOUND", message="订单不存在"),
            )

        return ApiResponse(ok=True, data={
            "id": order.id,
            "status": order.status,
            "tier": order.tier,
            "points_granted": order.points_granted,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        })
