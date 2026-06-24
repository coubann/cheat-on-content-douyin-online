"""JWT 认证服务 — 生成/验证 JWT Token、密码哈希"""
from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
import structlog

from backend.app.config import JWT_ALGORITHM, JWT_EXPIRE_HOURS, JWT_SECRET_KEY

logger = structlog.get_logger()

# 如果 SECRET_KEY 未设置，生成一个随机密钥（重启后所有 token 失效）
_SECRET_KEY: str = JWT_SECRET_KEY or os.urandom(32).hex()


def hash_password(password: str) -> str:
    """bcrypt 密码哈希"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码"""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


def create_token(user_id: int, role: str) -> str:
    """生成 JWT Token"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_EXPIRE_HOURS)).timestamp()),
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    """解码 JWT Token，返回 payload 或 None"""
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("jwt_expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("jwt_invalid", error=str(e))
        return None


def get_user_id_from_token(token: str) -> int | None:
    """从 JWT Token 中提取用户 ID"""
    payload = decode_token(token)
    if payload is None:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        return None


def generate_invite_code() -> str:
    """生成 6 位邀请码"""
    import random
    import string

    chars = string.ascii_uppercase + string.digits
    # 排除容易混淆的字符
    chars = chars.translate(str.maketrans("", "", "0O1Il"))
    return "".join(random.choice(chars) for _ in range(6))
