"""FastAPI 入口 — 尽量薄"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api import (
    admin,
    announcements as announcements_api,
    auth,
    benchmark,
    bump,
    calendar,
    comments,
    comments_fetch,
    experiments,
    health,
    init,
    invite,
    membership,
    migrate,
    monitors,
    notifications,
    persona,
    pipeline,
    points,
    predict,
    publish,
    publish_time,
    scripts,
    seed,
    settings,
    sse,
    status,
    tasks,
    virality,
)
from backend.app.config import APP_ENV, LOG_LEVEL
from backend.app.db.init_db import init_database
from backend.app.errors import LLM_CALL_FAILED
from backend.app.middleware.auth import AuthMiddleware
from backend.app.services.llm import LLMCallError
from backend.app.services.task_queue import task_queue

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer() if APP_ENV == "development" else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

scheduler = AsyncIOScheduler()


async def reset_daily_free_points():
    """每日 23:59:59 定时任务 — 免费点数清零"""
    logger.info("daily_free_points_reset_start")
    try:
        from backend.app.db.session import async_session_factory
        from backend.app.models.user import User
        from sqlalchemy import update

        async with async_session_factory() as session:
            result = await session.execute(
                update(User)
                .where(User.free_points_today > 0)
                .values(free_points_today=0, free_points_date=None)
            )
            await session.commit()
            affected = result.rowcount
            logger.info("daily_free_points_reset_done", affected_users=affected)
    except Exception as e:
        logger.error("daily_free_points_reset_failed", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app_start", env=APP_ENV)
    # 初始化数据库（建表 + 创建 admin）
    await init_database()
    await task_queue.start()

    # 启动每日免费点数清零定时任务
    scheduler.add_job(
        reset_daily_free_points,
        CronTrigger(hour=23, minute=59, second=59),
        id="daily_free_points_reset",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("scheduler_started", jobs=[j.id for j in scheduler.get_jobs()])

    yield

    scheduler.shutdown()
    await task_queue.stop()
    logger.info("app_stop")


app = FastAPI(
    title="Content Studio API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — 开发环境允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 认证中间件 — 必须在 CORS 之后添加
app.add_middleware(AuthMiddleware)


# 全局 LLM 错误处理 — 避免未捕获的 LLMCallError 导致 500
@app.exception_handler(LLMCallError)
async def llm_error_handler(request: Request, exc: LLMCallError):
    logger.error("llm_call_failed", error=str(exc))
    return JSONResponse(
        status_code=502,
        content={
            "ok": False,
            "error": {
                "code": LLM_CALL_FAILED,
                "message": f"LLM 调用失败: {exc.message}",
                "suggested_action": "请检查 .env 中的 API Key 是否正确配置",
            },
            "meta": None,
        },
    )


# 响应时间中间件
@app.middleware("http")
async def add_response_time(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Response-Time-Ms"] = str(ms)
    return response


# 注册路由
app.include_router(health.router, tags=["health"])
app.include_router(init.router, prefix="/api/init", tags=["init"])
app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
app.include_router(predict.router, prefix="/api/predict", tags=["predict"])
app.include_router(status.router, prefix="/api/status", tags=["status"])
app.include_router(virality.router, prefix="/api/virality", tags=["virality"])
app.include_router(benchmark.router, prefix="/api/benchmark", tags=["benchmark"])
app.include_router(comments.router, prefix="/api/comments", tags=["comments"])
app.include_router(publish.router, prefix="/api/publish", tags=["publish"])
app.include_router(bump.router, prefix="/api/bump", tags=["bump"])
app.include_router(persona.router, prefix="/api/persona", tags=["persona"])
app.include_router(seed.router, prefix="/api/seed", tags=["seed"])
app.include_router(migrate.router, prefix="/api/migrate", tags=["migrate"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(publish_time.router, prefix="/api/publish-time", tags=["publish-time"])
app.include_router(sse.router, prefix="/api/sse", tags=["sse"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(experiments.router, prefix="/api/experiments", tags=["experiments"])
app.include_router(monitors.router, prefix="/api/monitors", tags=["monitors"])
app.include_router(comments_fetch.router, prefix="/api/comments-fetch", tags=["comments-fetch"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["calendar"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])

# ---- 新增路由 ----
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(points.router, prefix="/api/points", tags=["points"])
app.include_router(membership.router, prefix="/api/membership", tags=["membership"])
app.include_router(invite.router, prefix="/api/invite", tags=["invite"])
app.include_router(announcements_api.router, prefix="/api/announcements", tags=["announcements"])
