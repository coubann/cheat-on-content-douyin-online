"""验证充值功能"""
import asyncio
import sys
sys.path.insert(0, '/app')

from backend.app.db.session import async_session_factory
from backend.app.models.user import User
from backend.app.models.order import Order
from backend.app.models.points_log import PointsLog
from sqlalchemy import select


async def main():
    async with async_session_factory() as s:
        u = await s.get(User, 1)
        if u:
            print(f"[USER] points={u.points} membership={u.membership_type}")
        else:
            print("[USER] User 1 not found")

        r = await s.execute(
            select(Order).where(Order.user_id == 1).order_by(Order.id.desc())
        )
        orders = r.scalars().all()
        print(f"[ORDERS] count={len(orders)}")
        for o in orders[:5]:
            print(f"  #{o.id} tier={o.tier} status={o.status} +{o.points_granted}pts out_trade_no={o.out_trade_no}")

        r2 = await s.execute(
            select(PointsLog).where(PointsLog.user_id == 1).order_by(PointsLog.id.desc())
        )
        logs = r2.scalars().all()
        print(f"[POINTS LOG] count={len(logs)}")
        for log in logs[:5]:
            print(f"  #{log.id} change={log.change} reason={log.reason} balance={log.balance_after}")


asyncio.run(main())
