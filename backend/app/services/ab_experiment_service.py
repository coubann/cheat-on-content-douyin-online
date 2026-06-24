"""A/B 对照实验服务

对同一选题的两种脚本风格进行对比预测，发布后对比实际表现，
验证 rubric 有效性。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.services.file_io import read_file, safe_write

logger = structlog.get_logger()


async def create_experiment(
    data_dir: Path,
    topic: str,
    script_a_id: str,
    script_b_id: str,
    hypothesis: str,
) -> dict[str, Any]:
    """创建 A/B 对照实验

    Pre-conditions:
      - topic 非空
      - script_a_id 和 script_b_id 对应的脚本存在
      - script_a_id != script_b_id
    Post-conditions:
      - experiments/<id>.json 被创建
      - 返回实验详情
    Side effects:
      - 写文件系统
    Error codes:
      - SCRIPT_NOT_FOUND: 脚本不存在
      - INVALID_REQUEST: script_a_id == script_b_id
    """
    from backend.app.errors import INVALID_REQUEST, SCRIPT_NOT_FOUND

    if script_a_id == script_b_id:
        raise ValueError(f"{INVALID_REQUEST}: script_a_id 和 script_b_id 不能相同")

    # 校验脚本存在
    for sid in (script_a_id, script_b_id):
        script_path = data_dir / "scripts" / f"{sid}.md"
        if not script_path.exists():
            raise FileNotFoundError(f"{SCRIPT_NOT_FOUND}: {sid}")

    experiment_id = f"exp_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()

    experiment = {
        "id": experiment_id,
        "topic": topic,
        "script_a_id": script_a_id,
        "script_b_id": script_b_id,
        "hypothesis": hypothesis,
        "status": "created",
        "prediction_a": None,
        "prediction_b": None,
        "actual_plays_a": None,
        "actual_plays_b": None,
        "result": None,
        "created_at": now,
        "completed_at": None,
    }

    exp_dir = data_dir / "experiments"
    exp_dir.mkdir(parents=True, exist_ok=True)
    exp_path = exp_dir / f"{experiment_id}.json"
    safe_write(exp_path, json.dumps(experiment, ensure_ascii=False, indent=2))

    logger.info("experiment_created", experiment_id=experiment_id, topic=topic)
    return experiment


async def list_experiments(data_dir: Path) -> list[dict[str, Any]]:
    """列出所有实验

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回实验列表（按创建时间倒序）
    Side effects:
      - 无
    """
    exp_dir = data_dir / "experiments"
    if not exp_dir.exists():
        return []

    results = []
    for path in sorted(exp_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(read_file(path))
            results.append(data)
        except Exception as e:
            logger.warning("experiment_load_failed", path=str(path), error=str(e))

    return results


async def get_experiment(data_dir: Path, experiment_id: str) -> dict[str, Any] | None:
    """获取实验详情

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回实验详情或 None
    Side effects:
      - 无
    Error codes:
      - EXPERIMENT_NOT_FOUND
    """
    exp_path = data_dir / "experiments" / f"{experiment_id}.json"
    if not exp_path.exists():
        return None
    return json.loads(read_file(exp_path))


async def predict_both(data_dir: Path, experiment_id: str) -> dict[str, Any]:
    """对实验中的两个脚本分别运行预测

    Pre-conditions:
      - 实验存在且状态为 created
    Post-conditions:
      - 实验状态变为 predicted
      - prediction_a 和 prediction_b 被填充
    Side effects:
      - LLM 调用（full_predict）
      - 写文件系统
    Error codes:
      - EXPERIMENT_NOT_FOUND
      - INVALID_REQUEST: 实验状态不是 created
    """
    from backend.app.errors import EXPERIMENT_NOT_FOUND, INVALID_REQUEST
    from backend.app.services.predict_service import full_predict

    exp = await get_experiment(data_dir, experiment_id)
    if not exp:
        raise FileNotFoundError(f"{EXPERIMENT_NOT_FOUND}: {experiment_id}")

    if exp["status"] != "created":
        raise ValueError(f"{INVALID_REQUEST}: 实验状态不是 created，当前状态: {exp['status']}")

    logger.info("experiment_predict_start", experiment_id=experiment_id)

    # 预测脚本 A
    try:
        prediction_a = await full_predict(data_dir, exp["script_a_id"])
    except FileExistsError:
        # 预测已存在，读取已有预测
        prediction_a = {"script_id": exp["script_a_id"], "note": "prediction_already_exists"}
    except Exception as e:
        logger.warning("experiment_predict_a_failed", error=str(e))
        prediction_a = {"script_id": exp["script_a_id"], "error": str(e)}

    # 预测脚本 B
    try:
        prediction_b = await full_predict(data_dir, exp["script_b_id"])
    except FileExistsError:
        prediction_b = {"script_id": exp["script_b_id"], "note": "prediction_already_exists"}
    except Exception as e:
        logger.warning("experiment_predict_b_failed", error=str(e))
        prediction_b = {"script_id": exp["script_b_id"], "error": str(e)}

    # 更新实验
    exp["status"] = "predicted"
    exp["prediction_a"] = prediction_a
    exp["prediction_b"] = prediction_b

    exp_path = data_dir / "experiments" / f"{experiment_id}.json"
    safe_write(exp_path, json.dumps(exp, ensure_ascii=False, indent=2))

    logger.info("experiment_predict_complete", experiment_id=experiment_id)
    return exp


async def complete_experiment(
    data_dir: Path,
    experiment_id: str,
    actual_plays_a: int,
    actual_plays_b: int,
) -> dict[str, Any]:
    """用实际播放量完成实验，对比预测与实际

    Pre-conditions:
      - 实验存在且状态为 predicted
    Post-conditions:
      - 实验状态变为 completed
      - actual_plays_a/b 被填充
      - result 包含对比结论
    Side effects:
      - 写文件系统
    Error codes:
      - EXPERIMENT_NOT_FOUND
      - INVALID_REQUEST: 实验状态不是 predicted
    """
    from backend.app.errors import EXPERIMENT_NOT_FOUND, INVALID_REQUEST

    exp = await get_experiment(data_dir, experiment_id)
    if not exp:
        raise FileNotFoundError(f"{EXPERIMENT_NOT_FOUND}: {experiment_id}")

    if exp["status"] != "predicted":
        raise ValueError(f"{INVALID_REQUEST}: 实验状态不是 predicted，当前状态: {exp['status']}")

    exp["actual_plays_a"] = actual_plays_a
    exp["actual_plays_b"] = actual_plays_b
    exp["completed_at"] = datetime.now().isoformat()

    # 生成对比结论
    result = _build_result(exp, actual_plays_a, actual_plays_b)
    exp["result"] = result
    exp["status"] = "completed"

    exp_path = data_dir / "experiments" / f"{experiment_id}.json"
    safe_write(exp_path, json.dumps(exp, ensure_ascii=False, indent=2))

    logger.info("experiment_completed", experiment_id=experiment_id, winner=result.get("winner"))
    return exp


def _build_result(
    exp: dict[str, Any],
    actual_plays_a: int,
    actual_plays_b: int,
) -> dict[str, Any]:
    """构建实验结论

    比较实际播放量与预测方向是否一致，验证 rubric 有效性。
    """
    # 实际胜者
    if actual_plays_a > actual_plays_b:
        actual_winner = "A"
    elif actual_plays_b > actual_plays_a:
        actual_winner = "B"
    else:
        actual_winner = "tie"

    # 预测胜者（基于爆款分）
    pred_a_score = None
    pred_b_score = None
    prediction_a = exp.get("prediction_a") or {}
    prediction_b = exp.get("prediction_b") or {}

    virality_a = prediction_a.get("virality", {})
    virality_b = prediction_b.get("virality", {})
    pred_a_score = virality_a.get("virality_score")
    pred_b_score = virality_b.get("virality_score")

    if pred_a_score is not None and pred_b_score is not None:
        if pred_a_score > pred_b_score:
            predicted_winner = "A"
        elif pred_b_score > pred_a_score:
            predicted_winner = "B"
        else:
            predicted_winner = "tie"
    else:
        predicted_winner = "unknown"

    # 预测是否正确
    prediction_correct = predicted_winner == actual_winner if predicted_winner != "unknown" else None

    # 播放量差异
    plays_diff = abs(actual_plays_a - actual_plays_b)
    plays_ratio = max(actual_plays_a, actual_plays_b) / max(min(actual_plays_a, actual_plays_b), 1)

    # 结论
    if prediction_correct is True:
        conclusion = "预测方向正确，rubric 有效"
    elif prediction_correct is False:
        conclusion = "预测方向错误，rubric 可能需要调整"
    else:
        conclusion = "无法判断预测准确性（缺少预测分数）"

    return {
        "actual_winner": actual_winner,
        "predicted_winner": predicted_winner,
        "prediction_correct": prediction_correct,
        "actual_plays_a": actual_plays_a,
        "actual_plays_b": actual_plays_b,
        "plays_diff": plays_diff,
        "plays_ratio": round(plays_ratio, 2),
        "pred_score_a": pred_a_score,
        "pred_score_b": pred_b_score,
        "conclusion": conclusion,
        "hypothesis": exp.get("hypothesis", ""),
    }
