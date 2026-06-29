"""SSE (Server-Sent Events) 路由 — 长时间运行操作的流式进度

提供 predict 和 bump 的 SSE 端点，将现有服务函数拆分为步骤，
在步骤之间发送进度事件，避免重复业务逻辑。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.config import DATA_DIR
from backend.app.models.state import CheatState, ScoreResult
from backend.app.services.blind_scorer import score_script as blind_score
from backend.app.services.bump_service import (
    BumpError,
    _append_bump_memo,
    _bump_version,
    _collect_calibration_pool,
    _compute_ranking_consistency,
    _compute_rankings,
    _parse_weights,
    _propose_new_weights,
    _rescore_pool,
)
from backend.app.services.file_io import read_file, safe_write
from backend.app.services.leak_guard import check_rubric_leak
from backend.app.services.predictor import predict_virality

logger = structlog.get_logger()

router = APIRouter()


def _sse_event(data: dict[str, Any]) -> str:
    """格式化 SSE 事件

    Pre-conditions:
      - data 为可序列化字典
    Post-conditions:
      - 返回 `data: {json}\\n\\n` 格式字符串
    Side effects:
      - 无
    """
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---- Request Models ----


class PredictSseRequest(BaseModel):
    script_id: str


class BumpSseRequest(BaseModel):
    force: bool = False


# ---- Predict SSE ----


async def _predict_sse_generator(script_id: str, user_id: int = 0) -> Any:
    """SSE 生成器 — 逐步执行 predict 并发送进度

    使用用户隔离路径：data/{user_id}/scripts/ 和 data/{user_id}/predictions/
    系统级文件（.cheat-state.json, rubric_notes.md）保持共享。

    Pre-conditions:
      - scripts/<id>.md 存在
      - .cheat-state.json 存在
    Post-conditions:
      - 流式发送进度事件，最终发送 complete 或 error
    Side effects:
      - LLM 调用、文件写入
    """
    user_data_dir = DATA_DIR / str(user_id)

    try:
        # Phase 1: 读取脚本 + state
        yield _sse_event({"phase": "reading_script", "progress": 10})

        script_path = user_data_dir / "scripts" / f"{script_id}.md"
        if not script_path.exists():
            yield _sse_event({"phase": "error", "message": f"脚本不存在: {script_id}"})
            return

        state_path = DATA_DIR / ".cheat-state.json"
        state = CheatState.model_validate_json(read_file(state_path))
        script_content = read_file(script_path)
        script_hash = hashlib.sha256(script_content.encode()).hexdigest()[:12]

        # Phase 2: 盲打分（传入用户隔离目录）
        yield _sse_event({"phase": "blind_scoring", "progress": 30})

        score_data = await blind_score(user_data_dir, script_id)
        score_result = ScoreResult(**score_data)

        # Phase 3: 爆款预测（传入用户隔离目录）
        yield _sse_event({"phase": "virality_predict", "progress": 60})

        virality = await predict_virality(user_data_dir, script_id, score_result, state)

        # Phase 4-5: 生成预测文件 + 落盘
        yield _sse_event({"phase": "writing_prediction", "progress": 90})

        prediction_id = f"{script_id}"
        prediction_path = user_data_dir / "predictions" / f"{prediction_id}.md"

        if prediction_path.exists():
            yield _sse_event({"phase": "error", "message": f"预测已存在: {prediction_id}"})
            return

        from backend.app.services.predict_service import _build_prediction_file

        prediction_content = _build_prediction_file(
            script_id=script_id,
            script_hash=script_hash,
            score_result=score_result,
            virality=virality,
            state=state,
        )

        (user_data_dir / "predictions").mkdir(parents=True, exist_ok=True)
        safe_write(prediction_path, prediction_content)

        # Phase 6: 更新 state
        state.in_progress_session = prediction_id
        safe_write(state_path, state.model_dump_json(indent=2))

        # Phase 7: 完成
        result = {
            "prediction_id": prediction_id,
            "script_id": script_id,
            "script_hash": script_hash,
            "score": score_data,
            "virality": virality,
            "prediction_path": str(prediction_path),
        }

        yield _sse_event({"phase": "complete", "progress": 100, "result": result})

    except Exception as e:
        logger.error("sse_predict_error", script_id=script_id, user_id=user_id, error=str(e))
        yield _sse_event({"phase": "error", "message": str(e)})


@router.post("/predict")
async def predict_sse(req: PredictSseRequest, request: Request) -> StreamingResponse:
    """启动完整预测并流式返回进度

    支持用户数据隔离，从 request.state.user_id 获取当前用户。

    Pre-conditions:
      - scripts/<id>.md 存在
    Post-conditions:
      - 返回 SSE 流
    Side effects:
      - LLM 调用、文件写入
    """
    user_id = getattr(request.state, "user_id", 0)
    return StreamingResponse(
        _predict_sse_generator(req.script_id, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---- Bump SSE ----


async def _bump_sse_generator(force: bool) -> Any:
    """SSE 生成器 — 逐步执行 bump 并发送进度

    Pre-conditions:
      - .cheat-state.json 存在
      - 至少有 3 篇已复盘样本（或 force=True）
    Post-conditions:
      - 流式发送进度事件，最终发送 complete 或 error
    Side effects:
      - 多次 LLM 调用、文件写入
    """
    try:
        # Step 1: 收集校准池
        yield _sse_event({"phase": "collecting_pool", "progress": 10})

        state_path = DATA_DIR / ".cheat-state.json"
        state = CheatState.model_validate_json(read_file(state_path))

        calibration_pool = _collect_calibration_pool(DATA_DIR)
        if len(calibration_pool) < 3 and not force:
            yield _sse_event({
                "phase": "error",
                "message": f"校准池仅 {len(calibration_pool)} 篇，至少需要 3 篇已复盘样本才能 bump",
            })
            return

        if len(calibration_pool) == 0:
            yield _sse_event({"phase": "error", "message": "校准池为空，无法执行 bump"})
            return

        # Step 2: LLM 提议新权重
        yield _sse_event({"phase": "proposing_weights", "progress": 30})

        old_weights = state.rubric_weights
        proposal = await _propose_new_weights(DATA_DIR, calibration_pool, old_weights)
        new_weights = _parse_weights(proposal.get("new_weights", {}))
        rubric_diff = proposal.get("rubric_diff", "")

        # Step 3: blind sub-agent 全量重打分校准池
        yield _sse_event({
            "phase": "rescoring_pool",
            "progress": 50,
            "current": 0,
            "total": len(calibration_pool),
        })

        old_rankings = _compute_rankings(calibration_pool, "old_composite")
        new_scores = await _rescore_pool(DATA_DIR, calibration_pool, new_weights)
        new_rankings = _compute_rankings(new_scores, "new_composite")

        # Step 4: 排序一致性审计
        yield _sse_event({"phase": "consistency_audit", "progress": 80})

        consistency = _compute_ranking_consistency(old_rankings, new_rankings)
        consistency_threshold = 0.8
        passed = consistency >= consistency_threshold

        if not passed:
            yield _sse_event({
                "phase": "complete",
                "progress": 100,
                "result": {
                    "status": "rejected",
                    "reason": f"排序一致性 {consistency:.2f} < {consistency_threshold}，升级被拒",
                    "consistency": consistency,
                    "old_weights": old_weights.model_dump(),
                    "proposed_weights": new_weights.model_dump(),
                    "old_rankings": old_rankings,
                    "new_rankings": new_rankings,
                },
            })
            return

        # Step 5: 写入新 rubric + 更新 state
        if rubric_diff:
            rubric_path = DATA_DIR / "rubric_notes.md"
            existing_rubric = read_file(rubric_path)
            new_rubric = existing_rubric + "\n\n" + rubric_diff

            try:
                check_rubric_leak(new_rubric)
            except Exception as e:
                yield _sse_event({
                    "phase": "error",
                    "message": f"新 rubric 包含真实数据泄露，升级被拒: {e}",
                })
                return

            safe_write(rubric_path, new_rubric)

        _append_bump_memo(DATA_DIR, old_weights, new_weights, consistency, calibration_pool)

        old_version = state.rubric_version
        new_version = _bump_version(old_version)
        state.rubric_weights = new_weights
        state.rubric_version = new_version

        state.last_bump_at = datetime.now().isoformat()
        safe_write(state_path, state.model_dump_json(indent=2))

        result = {
            "status": "accepted",
            "old_version": old_version,
            "new_version": new_version,
            "consistency": consistency,
            "old_weights": old_weights.model_dump(),
            "new_weights": new_weights.model_dump(),
            "rubric_diff": rubric_diff,
            "pool_size": len(calibration_pool),
            "rescored": new_scores,
        }

        yield _sse_event({"phase": "complete", "progress": 100, "result": result})

    except BumpError as e:
        logger.error("sse_bump_error", error=str(e))
        yield _sse_event({"phase": "error", "message": f"{e.code}: {e.message}"})
    except Exception as e:
        logger.error("sse_bump_error", error=str(e))
        yield _sse_event({"phase": "error", "message": str(e)})


@router.post("/bump")
async def bump_sse(req: BumpSseRequest) -> StreamingResponse:
    """启动 bump 并流式返回进度

    Pre-conditions:
      - 至少有 3 篇已复盘样本（或 force=True）
    Post-conditions:
      - 返回 SSE 流
    Side effects:
      - 多次 LLM 调用、文件写入
    """
    return StreamingResponse(
        _bump_sse_generator(req.force),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
