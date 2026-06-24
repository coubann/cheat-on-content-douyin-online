"""SQLAlchemy 异步会话管理"""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.app.config import DATABASE_URL

logger = structlog.get_logger()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore
    """获取数据库会话（依赖注入用）"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """创建所有表"""
    from backend.app.models import user  # noqa: F401
    from backend.app.models import points_log  # noqa: F401
    from backend.app.models import order  # noqa: F401
    from backend.app.models import system_config  # noqa: F401
    from backend.app.models import guide_status  # noqa: F401
    from backend.app.models import user_action  # noqa: F401
    from backend.app.models import announcement  # noqa: F401
    from backend.app.models import invite_record  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_created", url=DATABASE_URL)
