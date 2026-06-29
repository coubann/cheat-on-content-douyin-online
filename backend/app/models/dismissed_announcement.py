"""用户已关闭的公告记录"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class DismissedAnnouncement(Base):
    __tablename__ = "dismissed_announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    announcement_id: Mapped[int] = mapped_column(Integer, ForeignKey("announcements.id"), nullable=False)
    dismissed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
