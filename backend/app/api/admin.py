"""管理员路由 — 用户管理、系统配置、LLM 配置等"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Header
from pydantic import BaseModel

from backend.app.db.session import async_session_factory
from backend.app.errors import AUTH_UNAUTHORIZED, INVALID_REQUEST
from backend.app.models.announcement import Announcement
from backend.app.models.order import Order
from backend.app.models.points_log import PointsLog
from backend.app.models.system_config import SystemConfig
from backend.app.models.user import User
from backend.app.models.user_action import UserAction
from backend.app.models.invite_record import InviteRecord
from backend.app.services.jwt_service import get_user_id_from_token, hash_password
from backend.app.models.response import ApiResponse, ErrorDetail

router = APIRouter()


# ---- Helpers ----


def _get_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return None


async def _require_admin(authorization: str | None) -> tuple[int, ApiResponse | None]:
    """验证管理员身份，返回 (user_id, None) 或 (None, error_response)"""
    token = _get_token(authorization)
    if token is None:
        return 0, ApiResponse(
            ok=False,
            error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="未登录"),
        )
    user_id = get_user_id_from_token(token)
    if user_id is None:
        return 0, ApiResponse(
            ok=False,
            error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="Token 无效"),
        )
    async with async_session_factory() as session:
        user = await session.get(User, user_id)
        if user is None or user.role != "admin":
            return 0, ApiResponse(
                ok=False,
                error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="无权访问，需要管理员权限"),
            )
        if user.disabled:
            return 0, ApiResponse(
                ok=False,
                error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="账号已被禁用"),
            )
        return user_id, None


# ---- Request Models ----


class UpdateUserRequest(BaseModel):
    points: int | None = None
    membership_type: str | None = None
    role: str | None = None
    disabled: bool | None = None
    new_password: str | None = None


class UpdateConfigRequest(BaseModel):
    key: str
    value: str


class AnnouncementCreateRequest(BaseModel):
    title: str
    content: str
    type: str = "info"


class AnnouncementUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    type: str | None = None
    active: bool | None = None


# ---- User Management ----


@router.get("/users")
async def list_users(authorization: str | None = Header(None)) -> ApiResponse:
    """用户列表"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(User).order_by(User.created_at.desc())
        )
        users = result.scalars().all()
        return ApiResponse(ok=True, data=[u.to_dict() for u in users])


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    req: UpdateUserRequest,
    authorization: str | None = Header(None),
) -> ApiResponse:
    """编辑用户（点数/会员/角色/密码重置）"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code="USER_NOT_FOUND", message="用户不存在"),
            )

        changed = []

        # 修改点数
        if req.points is not None:
            change = req.points - user.points
            if change != 0:
                user.points = req.points
                session.add(PointsLog(
                    user_id=user.id,
                    change=change,
                    reason="admin_grant" if change > 0 else "admin_deduct",
                    detail=f"管理员调整点数: {change:+d}",
                    balance_after=user.points,
                ))
                changed.append(f"points: {change:+d}")

        # 修改会员类型
        if req.membership_type is not None:
            if req.membership_type not in ("none", "basic", "standard", "premium"):
                return ApiResponse(
                    ok=False,
                    error=ErrorDetail(code=INVALID_REQUEST, message="会员类型无效"),
                )
            user.membership_type = req.membership_type
            changed.append(f"membership: {req.membership_type}")

        # 修改角色
        if req.role is not None:
            if req.role not in ("admin", "user"):
                return ApiResponse(
                    ok=False,
                    error=ErrorDetail(code=INVALID_REQUEST, message="角色无效"),
                )
            user.role = req.role
            changed.append(f"role: {req.role}")

        # 禁用/启用
        if req.disabled is not None:
            user.disabled = req.disabled
            changed.append(f"disabled: {req.disabled}")

        # 重置密码
        if req.new_password:
            if len(req.new_password) < 8:
                return ApiResponse(
                    ok=False,
                    error=ErrorDetail(code="WEAK_PASSWORD", message="密码至少 8 位"),
                )
            user.password_hash = hash_password(req.new_password)
            changed.append("password_reset")

        await session.commit()

        return ApiResponse(ok=True, data={
            "user": user.to_dict(),
            "changed": changed,
        })


# ---- System Config ----


@router.get("/config")
async def get_config(authorization: str | None = Header(None)) -> ApiResponse:
    """获取所有系统配置"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(select(SystemConfig))
        configs = result.scalars().all()
        return ApiResponse(ok=True, data={
            c.key: c.value for c in configs
        })


@router.put("/config")
async def update_config(
    req: UpdateConfigRequest,
    authorization: str | None = Header(None),
) -> ApiResponse:
    """更新系统配置"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        config = await session.get(SystemConfig, req.key)
        if config is None:
            config = SystemConfig(key=req.key, value=req.value, updated_by=uid)
            session.add(config)
        else:
            config.value = req.value
            config.updated_by = uid
        await session.commit()
        return ApiResponse(ok=True, data={req.key: req.value})


# ---- Announcements ----


@router.get("/announcements")
async def list_announcements(authorization: str | None = Header(None)) -> ApiResponse:
    """公告列表"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Announcement).order_by(Announcement.created_at.desc())
        )
        items = result.scalars().all()
        return ApiResponse(ok=True, data=[{
            "id": a.id,
            "title": a.title,
            "content": a.content,
            "type": a.type,
            "active": a.active,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        } for a in items])


@router.post("/announcements")
async def create_announcement(
    req: AnnouncementCreateRequest,
    authorization: str | None = Header(None),
) -> ApiResponse:
    """发布公告"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        ann = Announcement(
            title=req.title,
            content=req.content,
            type=req.type,
            created_by=uid,
        )
        session.add(ann)
        await session.commit()
        await session.refresh(ann)
        return ApiResponse(ok=True, data={
            "id": ann.id,
            "title": ann.title,
        })


@router.put("/announcements/{ann_id}")
async def update_announcement(
    ann_id: int,
    req: AnnouncementUpdateRequest,
    authorization: str | None = Header(None),
) -> ApiResponse:
    """编辑公告"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        ann = await session.get(Announcement, ann_id)
        if ann is None:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code="NOT_FOUND", message="公告不存在"),
            )
        if req.title is not None:
            ann.title = req.title
        if req.content is not None:
            ann.content = req.content
        if req.type is not None:
            ann.type = req.type
        if req.active is not None:
            ann.active = req.active
        await session.commit()
        return ApiResponse(ok=True, data={"id": ann.id})


@router.delete("/announcements/{ann_id}")
async def delete_announcement(
    ann_id: int,
    authorization: str | None = Header(None),
) -> ApiResponse:
    """删除公告"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        ann = await session.get(Announcement, ann_id)
        if ann is None:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code="NOT_FOUND", message="公告不存在"),
            )
        await session.delete(ann)
        await session.commit()
        return ApiResponse(ok=True, data={"deleted": True})


# ---- Orders ----


@router.get("/orders")
async def list_orders(authorization: str | None = Header(None)) -> ApiResponse:
    """订单列表"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Order).order_by(Order.created_at.desc())
        )
        items = result.scalars().all()
        return ApiResponse(ok=True, data=[{
            "id": o.id,
            "user_id": o.user_id,
            "out_trade_no": o.out_trade_no,
            "tier": o.tier,
            "amount": o.amount,
            "points_granted": o.points_granted,
            "status": o.status,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        } for o in items])


# ---- Statistics ----


@router.get("/stats/users")
async def get_user_stats(authorization: str | None = Header(None)) -> ApiResponse:
    """用户统计"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        from sqlalchemy import func, select
        # 总用户数
        total = await session.execute(select(func.count(User.id)))
        total_users = total.scalar()

        # 今日注册
        today = date.today()
        today_count = await session.execute(
            select(func.count(User.id)).where(
                func.date(User.created_at) == today
            )
        )
        today_users = today_count.scalar()

        # 活跃用户（近7天登录）
        from datetime import timedelta, datetime, timezone
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        active = await session.execute(
            select(func.count(User.id)).where(
                User.last_login_at >= week_ago
            )
        )
        active_users = active.scalar()

        return ApiResponse(ok=True, data={
            "total_users": total_users,
            "today_users": today_users or 0,
            "active_users_7d": active_users or 0,
        })


@router.get("/stats/actions")
async def get_action_stats(authorization: str | None = Header(None)) -> ApiResponse:
    """行为统计"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    async with async_session_factory() as session:
        from sqlalchemy import func, select
        result = await session.execute(
            select(
                UserAction.action,
                func.count(UserAction.id).label("count"),
            ).group_by(UserAction.action).order_by(func.count(UserAction.id).desc())
        )
        rows = result.all()
        return ApiResponse(ok=True, data={
            row.action: row.count for row in rows
        })


@router.get("/llm-providers")
async def admin_get_llm_providers(authorization: str | None = Header(None)) -> ApiResponse:
    """获取 LLM Provider 配置（管理员用）"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    from backend.app.services.settings_service import get_provider_settings
    data = get_provider_settings()
    return ApiResponse(ok=True, data=data)


class UpdateLLMProviderRequest(BaseModel):
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None


@router.put("/llm-providers/{provider_name}")
async def admin_update_llm_provider(
    provider_name: str,
    req: UpdateLLMProviderRequest,
    authorization: str | None = Header(None),
) -> ApiResponse:
    """保存 LLM Provider 配置（管理员用）"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    from backend.app.services.settings_service import save_provider_settings
    result = save_provider_settings(
        provider_name=provider_name,
        api_key=req.api_key,
        model=req.model,
        base_url=req.base_url,
    )
    if result.get("status") == "error":
        return ApiResponse(ok=False, error=ErrorDetail(code=INVALID_REQUEST, message=result["message"]))
    return ApiResponse(ok=True, data=result)


@router.post("/llm-providers/{provider_name}/test")
async def admin_test_llm_connection(
    provider_name: str,
    authorization: str | None = Header(None),
) -> ApiResponse:
    """测试 LLM 连接（管理员用）"""
    uid, err = await _require_admin(authorization)
    if err:
        return err

    from backend.app.services.settings_service import test_provider_connection
    result = await test_provider_connection(provider_name)
    if result.get("ok"):
        return ApiResponse(ok=True, data=result)
    return ApiResponse(ok=False, error=ErrorDetail(code="LLM_CALL_FAILED", message=result.get("message", "连接失败")))
