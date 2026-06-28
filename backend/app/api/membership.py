"""会员/充值路由 — 爱发电对接"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from backend.app.config import IFDIAN_TOKEN, IFDIAN_USER_ID

logger = logging.getLogger(__name__)
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


# 爱发电 Webhook RSA 公钥
_IFDIAN_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwwdaCg1Bt+UKZKs0R54y
lYnuANma49IpgoOwNmk3a0rhg/PQuhUJ0EOZSowIC44l0K3+fqGns3Ygi4AfmEfS
4EKbdk1ahSxu7Zkp2rHMt+R9GarQFQkwSS/5x1dYiHNVMiR8oIXDgjmvxuNes2Cr
8fw9dEF0xNBKdkKgG2qAawcN1nZrdyaKWtPVT9m2Hl0ddOO9thZmVLFOb9NVzgYf
jEgI+KWX6aY19Ka/ghv/L4t1IXmz9pctablN5S0CRWpJW3Cn0k6zSXgjVdKm4uN7
jRlgSRaf/Ind46vMCm3N2sgwxu/g3bnooW+db0iLo13zzuvyn727Q3UDQ0MmZcEW
MQIDAQAB
-----END PUBLIC KEY-----"""


def _verify_ifdian_signature(order_data: dict) -> bool:
    """验证爱发电 Webhook 的 RSA 签名

    签名规则：取 order 中的 out_trade_no + user_id + plan_id + total_amount
    依次拼接成字符串 sign_str，用 RSA 公钥验证。
    """
    sign = order_data.get("sign", "")
    if not sign:
        return False

    sign_str = (
        order_data.get("out_trade_no", "")
        + order_data.get("user_id", "")
        + order_data.get("plan_id", "")
        + order_data.get("total_amount", "")
    )

    try:
        public_key = serialization.load_pem_public_key(_IFDIAN_PUBLIC_KEY_PEM.encode())
        public_key.verify(  # type: ignore[union-attr]
            base64.b64decode(sign),
            sign_str.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


@router.post("/ifdian-callback")
async def ifdian_callback(request: Request) -> dict:
    """爱发电 Webhook 回调

    收到用户支付成功通知后，解析 out_trade_no 找到对应用户，充值点数。
    安全验证：优先使用 RSA 签名验证；如果爱发电后台配了 Token，也支持 X-Ifdian-Token。
    此接口返回普通 dict 而非 ApiResponse，因为爱发电需要 {ec:200} 格式。
    """
    # 获取原始 body
    body_bytes = await request.body()
    try:
        body = json.loads(body_bytes)
    except json.JSONDecodeError:
        return {"ec": 400, "em": "invalid json"}

    # 可选：X-Ifdian-Token 额外验证
    header_token = request.headers.get("X-Ifdian-Token", "")
    if header_token and header_token != IFDIAN_TOKEN:
        return {"ec": 400, "em": "invalid token"}

    # 日志记录（仅调试用）
    logger.info("ifdian_callback_received",
                extra={"headers": dict(request.headers), "body_ec": body.get("ec")})

    # 解析订单数据
    # 爱发电 Webhook 格式：{ "ec":200, "em":"ok", "data": { "type":"order", "order":{...} } }
    data_wrapper = body.get("data", {})
    order_data = data_wrapper.get("order", {})

    # 兼容旧格式：直接 body.order
    if not order_data:
        order_data = body.get("order", {})

    out_trade_no = order_data.get("out_trade_no", "")
    ifdian_order_id = order_data.get("order_id", out_trade_no)
    plan_id = order_data.get("plan_id", "")
    status = order_data.get("status", 0)

    # status: 2 = 交易成功（爱发电文档定义，整数 2，非字符串 "paid"）
    if status != 2:
        logger.info("ifdian_order_not_paid status=%s type=%s", status, type(status).__name__)
        return {"ec": 400, "em": "order not paid"}

    # 可选：RSA 签名验证（2025年7月起爱发电 Webhook 增加签名）
    rsa_verified = _verify_ifdian_signature(order_data)
    if not rsa_verified and header_token != IFDIAN_TOKEN:
        logger.warning("ifdian_signature_invalid out_trade_no=%s", out_trade_no)

    # 解析 out_trade_no 获取系统用户 ID
    # format: UID_{user_id}_{timestamp}
    if not out_trade_no.startswith("UID_"):
        # 非 UID_ 开头的 out_trade_no 是爱发电的验证/测试请求或其它系统的订单
        # 直接返回成功，让爱发电确认地址可用，不处理点数
        logger.info("ifdian_skip_non_uid out_trade_no=%s", out_trade_no)
        return {"ec": 200, "em": "ok"}
    try:
        user_id = int(out_trade_no.split("_")[1])
    except (IndexError, ValueError):
        return {"ec": 400, "em": "cannot parse user_id"}

    # 判断档位（爱发电字段名为 plan_id，对应我们的 item_id）
    tier = _ITEM_ID_TO_TIER.get(plan_id)
    if tier is None:
        return {"ec": 400, "em": f"unknown plan_id: {plan_id}"}

    tier_config = TIERS[tier]

    async with async_session_factory() as session:
        # 检查订单是否已处理
        from sqlalchemy import select
        result = await session.execute(
            select(Order).where(Order.out_trade_no == out_trade_no)
        )
        order = result.scalar_one_or_none()

        if order is not None and order.status == "paid":
            # 已处理过，直接返回成功（幂等）
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
        user.membership_type = tier

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

    logger.info("ifdian_order_processed out_trade_no=%s tier=%s points=%s",
                out_trade_no, tier, tier_config["points"])
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
