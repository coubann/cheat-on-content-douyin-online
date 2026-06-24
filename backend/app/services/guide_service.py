"""操作指引服务 — guide_step 推进逻辑"""
from __future__ import annotations

import structlog
from sqlalchemy import select

from backend.app.db.session import async_session_factory

logger = structlog.get_logger()

# 操作：对应的 guide_step 目标推进
GUIDE_ADVANCE_MAP = {
    "analyze_script": 2,
    "generate_copy": 3,
}


async def advance_guide_step(user_id: int, action: str) -> None:
    """根据用户操作自动推进 guide_step"""
    target_step = GUIDE_ADVANCE_MAP.get(action)
    if target_step is None:
        return

    from backend.app.models.guide_status import GuideStatus

    async with async_session_factory() as session:
        result = await session.execute(
            select(GuideStatus).where(GuideStatus.user_id == user_id)
        )
        gs = result.scalar_one_or_none()

        if gs is None:
            gs = GuideStatus(user_id=user_id, guide_step=1, dismissed=False)
            session.add(gs)

        # 只有当前 step 小于目标时才推进
        if gs.guide_step < target_step:
            old_step = gs.guide_step
            gs.guide_step = target_step
            logger.info("guide_step_advanced", user_id=user_id, action=action, old=old_step, new=target_step)
            await session.commit()
