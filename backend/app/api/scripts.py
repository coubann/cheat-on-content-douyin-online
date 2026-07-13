"""草稿管理路由"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel
import structlog

from backend.app.config import DATA_DIR
from backend.app.errors import SCRIPT_NOT_FOUND, SCRIPT_EXISTS, SCRIPT_CREATE_FAILED
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.scripts_service import (
    create_script as svc_create,
)
from backend.app.services.scripts_service import (
    delete_script as svc_delete,
)
from backend.app.services.scripts_service import (
    get_script as svc_get,
)
from backend.app.services.scripts_service import (
    list_scripts as svc_list,
)
from backend.app.services.scripts_service import (
    update_script as svc_update,
)

router = APIRouter()
logger = structlog.get_logger()


class CreateScriptRequest(BaseModel):
    title: str
    content: str


class UpdateScriptRequest(BaseModel):
    content: str


@router.get("")
async def list_scripts(request: Request) -> ApiResponse:
    """列出所有草稿"""
    user_id = getattr(request.state, "user_id", 0)
    scripts = await svc_list(DATA_DIR, user_id=user_id)
    return ApiResponse(ok=True, data={"scripts": scripts})


@router.post("")
async def create_script(req: CreateScriptRequest, request: Request) -> ApiResponse:
    """新建草稿"""
    user_id = getattr(request.state, "user_id", 0)
    try:
        result = await svc_create(DATA_DIR, user_id, req.title, req.content)
        return ApiResponse(ok=True, data=result)
    except FileExistsError:
        # 同名脚本已存在（safe_write 前已做存在性校验并抛出）
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=SCRIPT_EXISTS,
                message="同名脚本已存在",
                suggested_action="请修改标题后重试",
            ),
        )
    except Exception as exc:  # noqa: BLE001 - 兜底，避免进程抛 500
        logger.error("create_script_failed", user_id=user_id, error=str(exc))
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=SCRIPT_CREATE_FAILED,
                message="创建脚本失败，请稍后重试",
                suggested_action="若问题持续，请联系管理员",
            ),
        )


@router.get("/{script_id}")
async def get_script(script_id: str, request: Request) -> ApiResponse:
    """草稿详情"""
    user_id = getattr(request.state, "user_id", 0)
    try:
        result = await svc_get(DATA_DIR, script_id, user_id=user_id)
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=SCRIPT_NOT_FOUND,
                message=f"脚本不存在: {script_id}",
                suggested_action="请先 POST /api/scripts 创建草稿",
            ),
        )


@router.put("/{script_id}")
async def update_script(script_id: str, req: UpdateScriptRequest, request: Request) -> ApiResponse:
    """更新草稿"""
    user_id = getattr(request.state, "user_id", 0)
    try:
        result = await svc_update(DATA_DIR, script_id, req.content, user_id=user_id)
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=SCRIPT_NOT_FOUND,
                message=f"脚本不存在: {script_id}",
                suggested_action="请先 POST /api/scripts 创建草稿",
            ),
        )


@router.delete("/{script_id}")
async def delete_script(script_id: str, request: Request) -> ApiResponse:
    """删除草稿"""
    user_id = getattr(request.state, "user_id", 0)
    try:
        result = await svc_delete(DATA_DIR, script_id, user_id=user_id)
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=SCRIPT_NOT_FOUND,
                message=f"脚本不存在: {script_id}",
                suggested_action="请检查脚本ID是否正确",
            ),
        )
