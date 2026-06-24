"""数据库初始化 — 建表 + 创建默认 admin 账号"""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import async_session_factory, create_tables
from backend.app.services.jwt_service import hash_password

logger = structlog.get_logger()


async def init_database() -> None:
    """初始化数据库：建表 + 创建 admin 账号"""
    # 1. 创建表
    await create_tables()

    # 2. 创建默认 admin 账号
    async with async_session_factory() as session:
        from backend.app.config import INIT_ADMIN_PASSWORD
        from backend.app.models.user import User

        result = await session.execute(
            select(User).where(User.role == "admin")
        )
        existing_admin = result.scalar_one_or_none()

        if existing_admin is None:
            hashed = hash_password(INIT_ADMIN_PASSWORD)
            from backend.app.services.jwt_service import generate_invite_code
            admin = User(
                email="admin@content-studio.local",
                username="admin",
                password_hash=hashed,
                role="admin",
                points=999999,
                invite_code=generate_invite_code(),
            )
            session.add(admin)
            await session.commit()
            logger.info("admin_account_created", email=admin.email)
        else:
            logger.info("admin_account_exists", email=existing_admin.email)
