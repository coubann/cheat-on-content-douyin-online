"""后台任务 API 路由 — 提交/查询/取消长时间运行的任务"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.task_queue import task_queue

router = APIRouter()


class SubmitTaskRequest(BaseModel):
    task_type: str
    params: dict[str, Any] = {}


@router.post("")
async def submit_task(req: SubmitTaskRequest) -> ApiResponse:
    """提交新任务

    Pre-conditions:
      - task_type 为 "predict" 或 "bump"
    Post-conditions:
      - 任务入队，返回 task_id
    Side effects:
      - 任务将在后台执行
    """
    if req.task_type not in ("predict", "bump"):
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code="INVALID_REQUEST",
                message=f"不支持的任务类型: {req.task_type}",
                suggested_action="请使用 predict 或 bump",
            ),
        )

    # 参数校验
    if req.task_type == "predict" and "script_id" not in req.params:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code="INVALID_REQUEST",
                message="predict 任务需要 script_id 参数",
                suggested_action="请提供 params.script_id",
            ),
        )

    task_id = task_queue.submit(req.task_type, req.params)
    return ApiResponse(ok=True, data={"task_id": task_id, "task_type": req.task_type})


@router.get("")
async def list_tasks(task_type: str | None = None) -> ApiResponse:
    """列出所有任务

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回最近 50 条任务
    Side effects:
      - 无
    """
    tasks = task_queue.list_tasks(task_type=task_type)
    return ApiResponse(ok=True, data={"tasks": tasks})


@router.get("/{task_id}")
async def get_task(task_id: str) -> ApiResponse:
    """获取任务状态

    Pre-conditions:
      - task_id 存在
    Post-conditions:
      - 返回任务详情
    Side effects:
      - 无
    """
    info = task_queue.get_task(task_id)
    if not info:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code="TASK_NOT_FOUND",
                message=f"任务不存在: {task_id}",
                suggested_action="请检查 task_id 是否正确",
            ),
        )

    result = {
        "task_id": info.task_id,
        "task_type": info.task_type,
        "status": info.status.value,
        "progress": info.progress,
        "current_phase": info.current_phase,
        "created_at": info.created_at,
        "started_at": info.started_at,
        "completed_at": info.completed_at,
        "error": info.error,
    }
    if info.status.value in ("completed",) and info.result is not None:
        result["result"] = info.result

    return ApiResponse(ok=True, data=result)


@router.delete("/{task_id}")
async def cancel_task(task_id: str) -> ApiResponse:
    """取消待执行的任务

    Pre-conditions:
      - task_id 存在且处于 PENDING 状态
    Post-conditions:
      - 任务被标记为取消
    Side effects:
      - 修改任务状态
    """
    cancelled = task_queue.cancel_task(task_id)
    if not cancelled:
        info = task_queue.get_task(task_id)
        if not info:
            return ApiResponse(
                ok=False,
                error=ErrorDetail(
                    code="TASK_NOT_FOUND",
                    message=f"任务不存在: {task_id}",
                ),
            )
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code="INVALID_REQUEST",
                message=f"任务状态为 {info.status.value}，无法取消",
                suggested_action="只能取消 PENDING 状态的任务",
            ),
        )

    return ApiResponse(ok=True, data={"task_id": task_id, "status": "cancelled"})
