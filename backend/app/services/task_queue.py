"""后台任务队列 — 管理长时间运行的操作（predict/bump等）

使用 asyncio.Queue + 后台 worker 实现，无需外部依赖。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger()


class TaskStatus(StrEnum):
    """任务状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskInfo:
    """任务信息"""

    def __init__(self, task_id: str, task_type: str, params: dict[str, Any]):
        self.task_id = task_id
        self.task_type = task_type
        self.params = params
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.current_phase = ""
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.created_at = datetime.now().isoformat()
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.cancelled: bool = False


class TaskQueue:
    """简单内存任务队列

    Pre-conditions:
      - 无
    Post-conditions:
      - 提供 submit / get_task / list_tasks 接口
    Side effects:
      - 后台 worker 协程执行任务
    """

    def __init__(self, max_workers: int = 2):
        self._tasks: dict[str, TaskInfo] = {}
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._max_workers = max_workers
        self._workers: list[asyncio.Task] = []

    async def start(self) -> None:
        """启动 worker

        Pre-conditions:
          - 尚未启动
        Post-conditions:
          - max_workers 个 worker 协程在运行
        Side effects:
          - 创建 asyncio.Task
        """
        for i in range(self._max_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)

    async def stop(self) -> None:
        """停止 worker

        Pre-conditions:
          - worker 已启动
        Post-conditions:
          - 所有 worker 被取消
        Side effects:
          - 取消 asyncio.Task
        """
        for w in self._workers:
            w.cancel()
        self._workers.clear()

    def submit(self, task_type: str, params: dict[str, Any]) -> str:
        """提交任务，返回 task_id

        Pre-conditions:
          - task_type 为 "predict" 或 "bump"
        Post-conditions:
          - 任务入队，返回 8 位 task_id
        Side effects:
          - 向 asyncio.Queue 添加元素
        """
        task_id = str(uuid.uuid4())[:8]
        info = TaskInfo(task_id, task_type, params)
        self._tasks[task_id] = info
        self._queue.put_nowait((task_id, {"type": task_type, "params": params}))
        return task_id

    def get_task(self, task_id: str) -> TaskInfo | None:
        """获取任务信息

        Pre-conditions:
          - 无
        Post-conditions:
          - 返回 TaskInfo 或 None
        Side effects:
          - 无
        """
        return self._tasks.get(task_id)

    def list_tasks(self, task_type: str | None = None) -> list[dict[str, Any]]:
        """列出任务

        Pre-conditions:
          - 无
        Post-conditions:
          - 返回最近 50 条任务信息
        Side effects:
          - 无
        """
        tasks = list(self._tasks.values())
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]
        tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)[:50]
        return [
            {
                "task_id": t.task_id,
                "task_type": t.task_type,
                "status": t.status.value,
                "progress": t.progress,
                "current_phase": t.current_phase,
                "created_at": t.created_at,
                "started_at": t.started_at,
                "completed_at": t.completed_at,
                "error": t.error,
            }
            for t in tasks
        ]

    def cancel_task(self, task_id: str) -> bool:
        """取消待执行的任务

        Pre-conditions:
          - task_id 存在
        Post-conditions:
          - 如果任务处于 PENDING 状态则标记为取消并返回 True，否则返回 False
        Side effects:
          - 标记 cancelled 标志，worker 会在执行前跳过
        """
        info = self._tasks.get(task_id)
        if info and info.status == TaskStatus.PENDING:
            info.status = TaskStatus.FAILED
            info.cancelled = True
            info.error = "cancelled"
            info.completed_at = datetime.now().isoformat()
            return True
        return False

    async def _worker(self, worker_id: int) -> None:
        """Worker 协程

        Pre-conditions:
          - start() 已调用
        Post-conditions:
          - 持续从队列取任务执行
        Side effects:
          - 执行任务（LLM 调用、文件写入等）
        """
        logger.info("task_worker_start", worker_id=worker_id)
        while True:
            try:
                task_id, task_data = await self._queue.get()
                info = self._tasks.get(task_id)
                if not info:
                    continue

                # 如果任务已被取消，跳过执行
                if info.cancelled:
                    continue

                info.status = TaskStatus.RUNNING
                info.started_at = datetime.now().isoformat()

                try:
                    result = await self._execute_task(info)
                    info.status = TaskStatus.COMPLETED
                    info.result = result
                    info.progress = 100
                    info.current_phase = "complete"
                    info.completed_at = datetime.now().isoformat()
                except Exception as e:
                    info.status = TaskStatus.FAILED
                    info.error = str(e)
                    info.completed_at = datetime.now().isoformat()
                    logger.error("task_failed", task_id=task_id, error=str(e))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("worker_error", worker_id=worker_id, error=str(e))

    async def _execute_task(self, info: TaskInfo) -> dict[str, Any]:
        """执行任务 — 根据 task_type 分发

        Pre-conditions:
          - info.task_type 为已知类型
        Post-conditions:
          - 返回任务执行结果
        Side effects:
          - 根据 task_type 调用对应服务
        """
        from backend.app.config import DATA_DIR

        if info.task_type == "predict":
            from backend.app.services.predict_service import full_predict

            user_id = info.params.get("user_id", 0)
            return await full_predict(DATA_DIR, info.params["script_id"], user_id=user_id)
        elif info.task_type == "bump":
            from backend.app.services.bump_service import execute_bump

            return await execute_bump(DATA_DIR, force=info.params.get("force", False))
        else:
            raise ValueError(f"Unknown task type: {info.task_type}")


# 全局单例
task_queue = TaskQueue()
