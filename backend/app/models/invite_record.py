"""邀请记录模型"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class InviteRecord(Base):
    __tablename__ = "invite_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inviter_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    invitee_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    reward_granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
