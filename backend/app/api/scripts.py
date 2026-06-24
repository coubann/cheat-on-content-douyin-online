"""草稿管理路由"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.config import DATA_DIR
from backend.app.errors import SCRIPT_NOT_FOUND
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


class CreateScriptRequest(BaseModel):
    title: str
    content: str


class UpdateScriptRequest(BaseModel):
    content: str


@router.get("")
async def list_scripts() -> ApiResponse:
    """列出所有草稿"""
    scripts = await svc_list(DATA_DIR)
    return ApiResponse(ok=True, data={"scripts": scripts})


@router.post("")
async def create_script(req: CreateScriptRequest) -> ApiResponse:
    """新建草稿"""
    result = await svc_create(DATA_DIR, req.title, req.content)
    return ApiResponse(ok=True, data=result)


@router.get("/{script_id}")
async def get_script(script_id: str) -> ApiResponse:
    """草稿详情"""
    try:
        result = await svc_get(DATA_DIR, script_id)
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
async def update_script(script_id: str, req: UpdateScriptRequest) -> ApiResponse:
    """更新草稿"""
    try:
        result = await svc_update(DATA_DIR, script_id, req.content)
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
async def delete_script(script_id: str) -> ApiResponse:
    """删除草稿"""
    try:
        result = await svc_delete(DATA_DIR, script_id)
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
