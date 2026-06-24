"""Schema 迁移 API 路由 — cheat-migrate 的 Web 接口"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.config import DATA_DIR
from backend.app.errors import FILE_NOT_FOUND
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.migrate_service import get_migration_status, migrate

router = APIRouter()


@router.post("")
async def migrate_endpoint(target_version: str | None = None) -> ApiResponse:
    """执行 schema 迁移"""
    result = migrate(DATA_DIR, target_version=target_version)
    if result.get("status") == "no_state":
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=FILE_NOT_FOUND,
                message=".cheat-state.json 不存在",
                suggested_action="请先执行 POST /api/init 初始化项目",
            ),
        )
    return ApiResponse(data=result)


@router.get("/status")
async def migration_status_endpoint() -> ApiResponse:
    """获取迁移状态"""
    result = get_migration_status(DATA_DIR)
    return ApiResponse(data=result)
