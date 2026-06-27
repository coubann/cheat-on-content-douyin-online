"""配置模块 — 全部走环境变量驱动"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

# ---- Paths ----
BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
DATA_DIR: Path = BASE_DIR / "data"
CHEAT_CONTENT_DIR: Path = BASE_DIR / "cheat-on-content"

# ---- App ----
APP_ENV: Literal["development", "staging", "production"] = os.getenv("APP_ENV", "development")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
SCHEMA_VERSION: str = "1.4-ext"

# ---- LLM ----
DEFAULT_LLM_PROVIDER: str = os.getenv("DEFAULT_LLM_PROVIDER", "deepseek")
OPENROUTER_API_KEY: str | None = os.getenv("OPENROUTER_API_KEY")
DEEPSEEK_API_KEY: str | None = os.getenv("DEEPSEEK_API_KEY")
DASHSCOPE_API_KEY: str | None = os.getenv("DASHSCOPE_API_KEY")

# ---- Database ----
DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR / 'content_studio.db'}")

# ---- Trending APIs ----
TREND_API_TIMEOUT: int = int(os.getenv("TREND_API_TIMEOUT", "10"))
TREND_USE_REAL_API: bool = os.getenv("TREND_USE_REAL_API", "true").lower() == "true"

# ---- Auth (Legacy, 保留兼容) ----
APP_PASSWORD: str | None = os.getenv("APP_PASSWORD")

# ---- JWT 认证 ----
_JWT_KEY = os.getenv("JWT_SECRET_KEY")
if not _JWT_KEY:
    import secrets as _secrets
    _JWT_KEY = _secrets.token_hex(32)
    import structlog
    structlog.get_logger().warning("JWT_SECRET_KEY not set, using auto-generated random key (tokens invalidated on restart)")
JWT_SECRET_KEY: str = _JWT_KEY
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "168"))

# ---- 管理员初始密码 ----
INIT_ADMIN_PASSWORD: str = os.getenv("INIT_ADMIN_PASSWORD", "")

# ---- 爱发电对接 ----
IFDIAN_TOKEN: str = os.getenv("IFDIAN_TOKEN", "")
IFDIAN_USER_ID: str = os.getenv("IFDIAN_USER_ID", "")

# ---- 点数配置 ----
DAILY_FREE_POINTS: int = int(os.getenv("DAILY_FREE_POINTS", "80"))
CHECKIN_POINTS: int = int(os.getenv("CHECKIN_POINTS", "20"))
INVITE_REWARD_POINTS: int = int(os.getenv("INVITE_REWARD_POINTS", "100"))
MAX_INVITE_COUNT: int = int(os.getenv("MAX_INVITE_COUNT", "10"))

# ---- 注册开关 ----
REGISTRATION_OPEN: bool = os.getenv("REGISTRATION_OPEN", "true").lower() == "true"
INVITE_CODE_REQUIRED: bool = os.getenv("INVITE_CODE_REQUIRED", "false").lower() == "true"

# ---- 签到加成 ----
CHECKIN_STREAK_7_BONUS: int = int(os.getenv("CHECKIN_STREAK_7_BONUS", "50"))
CHECKIN_STREAK_30_BONUS: int = int(os.getenv("CHECKIN_STREAK_30_BONUS", "200"))
