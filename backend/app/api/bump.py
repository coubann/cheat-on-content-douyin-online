"""bump API 路由 — cheat-bump 的 Web 接口

用户数据隔离：从 request.state.user_id 获取当前用户，传入 service 层。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.config import DATA_DIR
from backend.app.errors import FILE_NOT_FOUND
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.bump_service import BumpError, execute_bump

router = APIRouter()


@router.post("")
async def bump_rubric(request: Request, force: bool = False) -> ApiResponse:
    """执行 rubric bump — 5 步升级流程

    当校准池 >= 5 样本时，LLM 提议新权重 → blind 全量重打 → 排序一致性审计 → 写入。
    """
    user_id = getattr(request.state, "user_id", 0)
    try:
        result = await execute_bump(DATA_DIR, user_id=user_id, force=force)
        return ApiResponse(ok=True, data=result)
    except BumpError as e:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=e.code,
                message=e.message,
                suggested_action="请确保至少有 3 篇已复盘样本后再执行 bump",
            ),
        )
    except FileNotFoundError as e:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code=FILE_NOT_FOUND,
                message=str(e),
                suggested_action="请先执行 POST /api/init 初始化项目",
            ),
        )
