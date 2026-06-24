"""简单认证服务

单用户密码认证，适合个人使用场景。
密码存储在 .env 中，使用 session token 机制。
"""
from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any

import structlog

from backend.app.services.file_io import read_file, safe_write

logger = structlog.get_logger()

# Session 有效期（秒）
SESSION_TTL = 86400 * 7  # 7 天


def verify_password(password: str) -> bool:
    """验证密码

    Pre-conditions:
      - APP_PASSWORD 已配置
    Post-conditions:
      - 返回密码是否匹配
    Side effects:
      - 无
    """
    from backend.app.config import APP_PASSWORD
    if not APP_PASSWORD:
        return False
    return password == APP_PASSWORD


def create_session() -> dict[str, Any]:
    """创建登录会话

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回包含 token 和过期时间的会话数据
    Side effects:
      - 无
    """
    token = secrets.token_hex(32)
    expires_at = int(time.time()) + SESSION_TTL
    return {
        "token": token,
        "expires_at": expires_at,
        "created_at": int(time.time()),
    }


def save_session(data_dir: Path, session: dict[str, Any]) -> None:
    """保存会话到文件

    Pre-conditions:
      - data_dir 目录存在
    Post-conditions:
      - 会话被保存到 sessions.json
    Side effects:
      - 写文件系统
    """
    import json
    sessions_path = data_dir / "sessions.json"
    sessions = []
    if sessions_path.exists():
        try:
            sessions = json.loads(read_file(sessions_path))
        except Exception:
            sessions = []
    sessions.append(session)
    # 清理过期会话
    now = int(time.time())
    sessions = [s for s in sessions if s.get("expires_at", 0) > now]
    safe_write(sessions_path, json.dumps(sessions, indent=2))


def validate_token(data_dir: Path, token: str) -> bool:
    """验证 token 是否有效

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回 token 是否有效且未过期
    Side effects:
      - 无
    """
    sessions_path = data_dir / "sessions.json"
    if not sessions_path.exists():
        return False
    import json
    try:
        sessions = json.loads(read_file(sessions_path))
    except Exception:
        return False
    now = int(time.time())
    return any(s.get("token") == token and s.get("expires_at", 0) > now for s in sessions)


def logout(data_dir: Path, token: str) -> None:
    """注销会话

    Pre-conditions:
      - 无
    Post-conditions:
      - 指定 token 的会话被移除
    Side effects:
      - 写文件系统
    """
    sessions_path = data_dir / "sessions.json"
    if not sessions_path.exists():
        return
    import json
    try:
        sessions = json.loads(read_file(sessions_path))
    except Exception:
        return
    sessions = [s for s in sessions if s.get("token") != token]
    safe_write(sessions_path, json.dumps(sessions, indent=2))


def is_auth_configured() -> bool:
    """检查是否配置了密码

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回是否配置了 APP_PASSWORD
    Side effects:
      - 无
    """
    from backend.app.config import APP_PASSWORD
    return bool(APP_PASSWORD)
