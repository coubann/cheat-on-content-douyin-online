"""认证路由

提供注册、登录、个人信息等接口（多用户 JWT 认证）
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Header
from pydantic import BaseModel, field_validator

from backend.app.config import CHECKIN_POINTS, DAILY_FREE_POINTS, INVITE_CODE_REQUIRED, INVITE_REWARD_POINTS, MAX_INVITE_COUNT, REGISTRATION_OPEN
from backend.app.db.session import async_session_factory
from backend.app.errors import (
    AUTH_EMAIL_EXISTS,
    AUTH_INVALID_CREDENTIALS,
    AUTH_INVALID_INVITE_CODE,
    AUTH_INVITE_CODE_EXHAUSTED,
    AUTH_INVITE_CODE_REQUIRED,
    AUTH_REGISTRATION_CLOSED,
    AUTH_UNAUTHORIZED,
)
from backend.app.models.invite_record import InviteRecord
from backend.app.models.points_log import PointsLog
from backend.app.models.user import User
from backend.app.models.user_action import UserAction
from backend.app.services.jwt_service import (
    create_token,
    generate_invite_code,
    get_user_id_from_token,
    hash_password,
    verify_password,
)
from backend.app.models.response import ApiResponse, ErrorDetail

router = APIRouter()


# ---- Request Models ----


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    confirm_password: str
    invite_code: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("邮箱格式不正确")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2 or len(v) > 20:
            raise ValueError("用户名长度需在 2-20 字符之间")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少 8 位")
        return v

    @field_validator("confirm_password")
    @classmethod
    def check_passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("两次密码输入不一致")
        return v


class LoginRequest(BaseModel):
    credential: str  # 支持邮箱或用户名
    password: str


class UpdateProfileRequest(BaseModel):
    username: str | None = None
    current_password: str | None = None
    new_password: str | None = None
    confirm_new_password: str | None = None


# ---- Helper ----


def _get_token(authorization: str | None) -> str | None:
    """从 Authorization header 提取 token"""
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return None


# ---- Endpoints ----


@router.post("/register")
async def register(req: RegisterRequest) -> ApiResponse:
    """用户注册"""
    # 检查注册开关
    if not REGISTRATION_OPEN:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(code=AUTH_REGISTRATION_CLOSED, message="注册已关闭，请联系管理员"),
        )

    # 检查邀请码
    invitee_user_id: int | None = None
    if INVITE_CODE_REQUIRED or req.invite_code:
        if not req.invite_code:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code=AUTH_INVITE_CODE_REQUIRED, message="当前需要邀请码才能注册"),
            )
        # 验证邀请码
        async with async_session_factory() as session:
            # 需要查询邀请码
            from sqlalchemy import select
            result = await session.execute(
                select(User).where(User.invite_code == req.invite_code.upper())
            )
            inviter_user = result.scalar_one_or_none()
            if inviter_user is None:
                return ApiResponse(
                    ok=False,
                    error=ErrorDetail(code=AUTH_INVALID_INVITE_CODE, message="邀请码无效"),
                )
            # 检查邀请次数限制
            count_result = await session.execute(
                select(InviteRecord).where(InviteRecord.inviter_id == inviter_user.id)
            )
            invite_count = len(count_result.scalars().all())
            if invite_count >= MAX_INVITE_COUNT:
                return ApiResponse(
                    ok=False,
                    error=ErrorDetail(code=AUTH_INVITE_CODE_EXHAUSTED, message="该邀请码已使用达到上限"),
                )
            invitee_user_id = inviter_user.id

    async with async_session_factory() as session:
        # 检查邮箱是否已注册
        from sqlalchemy import select
        existing = await session.execute(
            select(User).where(User.email == req.email)
        )
        if existing.scalar_one_or_none() is not None:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code=AUTH_EMAIL_EXISTS, message="该邮箱已被注册"),
            )

        # 创建用户
        user_code = generate_invite_code()
        # 确保邀请码唯一
        while True:
            code_check = await session.execute(
                select(User).where(User.invite_code == user_code)
            )
            if code_check.scalar_one_or_none() is None:
                break
            user_code = generate_invite_code()

        user = User(
            email=req.email,
            username=req.username,
            password_hash=hash_password(req.password),
            role="user",
            points=0,
            invite_code=user_code,
            invited_by=invitee_user_id,
        )
        session.add(user)
        await session.flush()  # 获取 user.id

        # 如果使用邀请码，创建邀请记录并发放奖励
        if invitee_user_id is not None:
            invite_record = InviteRecord(
                inviter_id=invitee_user_id,
                invitee_id=user.id,
                reward_granted=False,
            )
            session.add(invite_record)

            # 给邀请人 +100 点
            inviter = await session.get(User, invitee_user_id)
            if inviter:
                inviter.points += INVITE_REWARD_POINTS
                session.add(PointsLog(
                    user_id=inviter.id,
                    change=INVITE_REWARD_POINTS,
                    reason="invite_reward",
                    detail=f"邀请用户 {user.email} 注册",
                    balance_after=inviter.points,
                ))

            # 给被邀请人 +100 点
            user.points += INVITE_REWARD_POINTS
            session.add(PointsLog(
                user_id=user.id,
                change=INVITE_REWARD_POINTS,
                reason="invite_reward",
                detail=f"通过邀请注册奖励",
                balance_after=user.points,
            ))

            invite_record.reward_granted = True

        # 注册时发放当日免费积分（与登录逻辑一致）
        from datetime import date
        today = date.today()
        free_granted = 0
        if user.free_points_date != today:
            user.free_points_today = DAILY_FREE_POINTS
            user.free_points_date = today
            free_granted = DAILY_FREE_POINTS

        await session.commit()

    # 生成 JWT
    token = create_token(user.id, user.role)

    return ApiResponse(ok=True, data={
        "token": token,
        "user": user.to_dict(),
        "free_points_granted": free_granted,
    })


@router.post("/login")
async def login(req: LoginRequest) -> ApiResponse:
    """登录 — 验证邮箱或用户名 + 密码，返回 JWT"""
    async with async_session_factory() as session:
        from sqlalchemy import or_, select

        login_value = req.credential.strip()

        # 同时查询邮箱和用户名
        result = await session.execute(
            select(User).where(
                or_(User.email == login_value, User.username == login_value)
            )
        )
        user = result.scalar_one_or_none()

        if user is None or not verify_password(req.password, user.password_hash):
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code=AUTH_INVALID_CREDENTIALS, message="账号或密码错误"),
            )

        if user.disabled:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="账号已被禁用，请联系管理员"),
            )

        # 更新登录时间
        user.last_login_at = datetime.now(timezone.utc)

        # 登录时发放每日免费点数
        today = date.today()
        free_granted = 0
        if user.free_points_date != today:
            user.free_points_today = DAILY_FREE_POINTS
            user.free_points_date = today
            free_granted = DAILY_FREE_POINTS

            # 会员每日免费点数加成
            membership_bonus = {
                "basic": 200,
                "standard": 300,
                "premium": 500,
            }.get(user.membership_type, 0)
            if membership_bonus > 0:
                user.free_points_today = DAILY_FREE_POINTS + membership_bonus
                free_granted = DAILY_FREE_POINTS + membership_bonus

        # 记录登录行为
        session.add(UserAction(
            user_id=user.id,
            action="login",
        ))

        await session.commit()

    token = create_token(user.id, user.role)

    return ApiResponse(ok=True, data={
        "token": token,
        "user": user.to_dict(),
        "free_points_granted": free_granted,
    })


@router.get("/me")
async def get_me(authorization: str | None = Header(None)) -> ApiResponse:
    """获取当前登录用户信息"""
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
            error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="Token 无效或已过期"),
        )

    async with async_session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="用户不存在"),
            )

        # 自动发放每日免费点数（用户无需重新登录）
        today = date.today()
        free_granted = 0
        if user.free_points_date != today:
            user.free_points_today = DAILY_FREE_POINTS
            user.free_points_date = today
            free_granted = DAILY_FREE_POINTS
            # 会员加成
            membership_bonus = {
                "basic": 200,
                "standard": 300,
                "premium": 500,
            }.get(user.membership_type or "none", 0)
            if membership_bonus:
                user.free_points_today += membership_bonus
                free_granted += membership_bonus
            await session.commit()

        # 获取 guide status
        from backend.app.models.guide_status import GuideStatus
        guide_result = await session.get(GuideStatus, user_id)
        guide_step = guide_result.guide_step if guide_result else 0

        return ApiResponse(ok=True, data={
            **user.to_dict(),
            "guide_step": guide_step,
            "free_points_granted": free_granted,
        })


@router.put("/profile")
async def update_profile(
    req: UpdateProfileRequest,
    authorization: str | None = Header(None),
) -> ApiResponse:
    """修改昵称或密码"""
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
        user = await session.get(User, user_id)
        if user is None:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(code=AUTH_UNAUTHORIZED, message="用户不存在"),
            )

        # 修改昵称
        if req.username is not None:
            if len(req.username.strip()) < 2 or len(req.username.strip()) > 20:
                return ApiResponse(
                    ok=False,
                    error=ErrorDetail(code="INVALID_USERNAME", message="用户名长度需在 2-20 字符之间"),
                )
            user.username = req.username.strip()

        # 修改密码
        if req.new_password:
            if not req.current_password:
                return ApiResponse(
                    ok=False,
                    error=ErrorDetail(code="PASSWORD_REQUIRED", message="修改密码需要提供当前密码"),
                )
            if not verify_password(req.current_password, user.password_hash):
                return ApiResponse(
                    ok=False,
                    error=ErrorDetail(code="INVALID_PASSWORD", message="当前密码错误"),
                )
            if len(req.new_password) < 8:
                return ApiResponse(
                    ok=False,
                    error=ErrorDetail(code="WEAK_PASSWORD", message="新密码至少 8 位"),
                )
            if req.new_password != req.confirm_new_password:
                return ApiResponse(
                    ok=False,
                    error=ErrorDetail(code="PASSWORD_MISMATCH", message="两次新密码输入不一致"),
                )
            user.password_hash = hash_password(req.new_password)

        # 更新 guide_step
        from backend.app.models.guide_status import GuideStatus
        guide = await session.get(GuideStatus, user_id)
        if guide is None:
            guide = GuideStatus(user_id=user_id, guide_step=0, dismissed=False)
            session.add(guide)
        if guide.guide_step == 0:
            guide.guide_step = 1  # 完成个人设置后进入 step 1

        await session.commit()

        return ApiResponse(ok=True, data=user.to_dict())


@router.put("/guide-status")
async def update_guide_status(body: dict, authorization: str | None = Header(None)) -> ApiResponse:
    """更新操作指引状态（guide_step / dismissed）"""
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
        from backend.app.models.guide_status import GuideStatus

        guide = await session.get(GuideStatus, user_id)
        if guide is None:
            guide = GuideStatus(user_id=user_id, guide_step=0, dismissed=False)
            session.add(guide)

        if "guide_step" in body:
            guide.guide_step = body["guide_step"]
        if "dismissed" in body:
            guide.dismissed = body["dismissed"]

        await session.commit()

        return ApiResponse(ok=True, data={
            "guide_step": guide.guide_step,
            "dismissed": guide.dismissed,
        })
