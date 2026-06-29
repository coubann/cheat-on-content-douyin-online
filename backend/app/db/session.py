"""SQLAlchemy 异步会话管理"""
from __future__ import annotations

from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

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
    """创建所有表 + 迁移新增字段"""
    from backend.app.models import user  # noqa: F401
    from backend.app.models import points_log  # noqa: F401
    from backend.app.models import order  # noqa: F401
    from backend.app.models import system_config  # noqa: F401
    from backend.app.models import guide_status  # noqa: F401
    from backend.app.models import user_action  # noqa: F401
    from backend.app.models import announcement  # noqa: F401
    from backend.app.models import invite_record  # noqa: F401
    from backend.app.models import dismissed_announcement  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # SQLite 不会自动添加新字段，需要手动 ALTER TABLE
        try:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 0"
            ))
        except Exception:
            pass  # 字段已存在
        try:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN verification_token VARCHAR(100)"
            ))
        except Exception:
            pass
        try:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN verification_token_expires DATETIME"
            ))
        except Exception:
            pass
    logger.info("database_tables_created", url=DATABASE_URL)


async def migrate_old_data(data_dir: Path) -> None:
    """将旧 data/scripts/* 迁移到 data/0/scripts/*"""
    import shutil

    for subdir in ["scripts", "predictions", "videos", "samples"]:
        old_dir = data_dir / subdir
        if old_dir.exists():
            target = data_dir / "0" / subdir
            target.mkdir(parents=True, exist_ok=True)
            for f in old_dir.glob("*"):
                if f.is_file():
                    shutil.move(str(f), str(target / f.name))
            try:
                old_dir.rmdir()
            except OSError:
                pass
    logger.info("old_data_migrated", data_dir=str(data_dir))
