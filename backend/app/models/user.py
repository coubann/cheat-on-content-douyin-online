"""用户模型"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")  # admin / user
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    free_points_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    free_points_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    checkin_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_checkin_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    membership_type: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    # none / basic / standard / premium
    invite_code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    invited_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 关系（方便查询）
    points_logs = relationship("PointsLog", back_populates="user", lazy="selectin")
    orders = relationship("Order", back_populates="user", lazy="selectin")

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """序列化用户信息"""
        d = {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "role": self.role,
            "points": self.points,
            "free_points_today": self.free_points_today,
            "membership_type": self.membership_type,
            "checkin_streak": self.checkin_streak,
            "invite_code": self.invite_code,
            "disabled": self.disabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }
        if include_sensitive:
            d["password_hash"] = self.password_hash
        return d
