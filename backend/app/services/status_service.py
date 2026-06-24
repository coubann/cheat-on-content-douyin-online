"""状态看板服务 — cheat-status 的 Python 实现"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

from backend.app.models.state import CheatState
from backend.app.services.file_io import read_file

logger = structlog.get_logger()


async def get_status(data_dir: Path) -> dict[str, Any]:
    """获取项目状态看板

    Pre-conditions:
      - .cheat-state.json 存在
    Post-conditions:
      - 返回结构化状态数据
    Side effects:
      - 无（纯读取）
    """
    state_path = data_dir / ".cheat-state.json"
    if not state_path.exists():
        return {
            "initialized": False,
            "message": "项目未初始化，请先 POST /api/init",
        }

    state_content = read_file(state_path)
    state = CheatState.model_validate_json(state_content)

    # 计算 buffer 颜色
    buffer_color = _compute_buffer_color(state)

    # 计算 confidence 等级
    confidence_level = _compute_confidence(state.calibration_samples)

    # 检查是否需要 bump
    bump_info = _check_bump_trigger(data_dir, state)

    return {
        "initialized": True,
        "rubric_version": state.rubric_version,
        "content_form": state.content_form,
        "platforms": state.platforms,
        "calibration_samples": state.calibration_samples,
        "confidence_level": confidence_level,
        "buffer_color": buffer_color,
        "pending_retros": len(state.pending_retros),
        "shoots_in_buffer": len(state.shoots),
        "bump_suggested": bump_info["triggered"],
        "bump_trigger_type": bump_info["trigger_type"],
        "bump_trigger_reason": bump_info["reason"],
        "in_progress_session": state.in_progress_session,
        "rubric_weights": state.rubric_weights.model_dump(),
    }


async def get_today(data_dir: Path) -> dict[str, Any]:
    """获取今日 todo（按优先级排序）

    Pre-conditions:
      - .cheat-state.json 存在
    Post-conditions:
      - 返回按优先级排序的任务清单
    Side effects:
      - 无
    """
    status = await get_status(data_dir)
    if not status.get("initialized"):
        return {"todos": [{"priority": 1, "action": "初始化项目", "endpoint": "POST /api/init"}]}

    todos: list[dict[str, Any]] = []

    # 1. pending_retros 最高优先级
    if status["pending_retros"] > 0:
        todos.append({
            "priority": 1,
            "action": f"完成 {status['pending_retros']} 篇复盘",
            "endpoint": "POST /api/retro/<id>",
        })

    # 2. bump 建议
    if status["bump_suggested"]:
        trigger_reason = status.get("bump_trigger_reason", "连续同向偏差")
        todos.append({
            "priority": 2,
            "action": f"rubric 升级建议（{trigger_reason}）",
            "endpoint": "cheat-bump",
        })

    # 3. buffer 红/橙 → 写稿
    if status["buffer_color"] in ("red", "orange"):
        todos.append({
            "priority": 3,
            "action": "buffer 不足，建议写新稿",
            "endpoint": "POST /api/scripts",
        })

    # 4. 通用
    if not todos:
        todos.append({
            "priority": 5,
            "action": "状态良好，继续创作",
            "endpoint": "POST /api/scripts",
        })

    return {"todos": todos}


def _compute_buffer_color(state: CheatState) -> str:
    """计算 buffer 颜色

    buffer_days = buffer × cadence
    <1 红 / 1-2 橙 / 3-5 绿 / >5 蓝
    """
    buffer = len(state.shoots)
    cadence = state.target_publish_cadence_days
    buffer_days = buffer * cadence

    if buffer_days < 1:
        return "red"
    elif buffer_days <= 2:
        return "orange"
    elif buffer_days <= 5:
        return "green"
    else:
        return "blue"


def _compute_confidence(calibration_samples: int) -> str:
    """计算 confidence 等级"""
    if calibration_samples == 0:
        return "none"
    elif calibration_samples < 3:
        return "low"
    elif calibration_samples < 5:
        return "medium"
    else:
        return "high"


def _check_bump_trigger(data_dir: Path, state: CheatState) -> dict[str, Any]:
    """检查是否触发 bump — 完整三条件实现

    触发条件（任一满足即触发）：
    1. 连续 ≥3 同向偏差：最近 3+ 次复盘偏差方向一致
    2. 1 次 ≥10x 偏差：某次复盘实际播放 ≥10x 预测或 ≤ 预测/10
    3. 2 次同向偏差 + 评论反向证据：2 次同向偏差 + 评论分析显示反向信号

    Pre-conditions:
      - data_dir/predictions/ 目录存在（可选）
      - .cheat-state.json 存在
    Post-conditions:
      - 返回 dict: triggered, reason, trigger_type
    Side effects:
      - 无（纯读取）
    Error codes:
      - 无
    """
    default_result: dict[str, Any] = {
        "triggered": False,
        "reason": "",
        "trigger_type": None,
    }

    # 如果已经 bump 过且校准样本不足，不再触发
    if state.calibration_samples < 3:
        return default_result

    # 收集所有已复盘的预测文件中的偏差数据
    retros = _collect_retro_deviations(data_dir)
    if not retros:
        return default_result

    # 条件 1: 连续 ≥3 同向偏差
    consecutive_result = _check_consecutive_deviation(retros)
    if consecutive_result["triggered"]:
        return consecutive_result

    # 条件 2: 1 次 ≥10x 偏差
    tenx_result = _check_10x_deviation(retros)
    if tenx_result["triggered"]:
        return tenx_result

    # 条件 3: 2 次同向偏差 + 评论反向证据
    comment_result = _check_comment_reverse_evidence(data_dir, retros)
    if comment_result["triggered"]:
        return comment_result

    return default_result


def _collect_retro_deviations(data_dir: Path) -> list[dict[str, Any]]:
    """从预测文件中收集复盘偏差数据

    读取 predictions/ 目录下所有含 ## 复盘 段的文件，
    提取偏差方向 (overestimated/underestimated) 和实际/预测播放量。

    Pre-conditions:
      - data_dir/predictions/ 目录存在（可选）
    Post-conditions:
      - 返回偏差列表，按文件修改时间排序（旧→新）
    Side effects:
      - 无
    """
    preds_dir = data_dir / "predictions"
    if not preds_dir.exists():
        return []

    retros: list[dict[str, Any]] = []
    for f in sorted(preds_dir.glob("*.md"), key=lambda p: p.stat().st_mtime):
        content = read_file(f)
        if "## 复盘" not in content:
            continue
        # 跳过尚未实际复盘的占位段
        if "尚未复盘" in content:
            continue

        deviation = _parse_retro_deviation(content, f.stem)
        if deviation:
            retros.append(deviation)

    return retros


def _parse_retro_deviation(content: str, prediction_id: str) -> dict[str, Any] | None:
    """从预测文件内容中解析复盘偏差数据

    提取：
    - prediction_accuracy: overestimated / underestimated / accurate
    - actual_plays: 实际播放量
    - predicted_bucket: 预测 bucket 值（数值）

    Pre-conditions:
      - content 包含 ## 复盘 段
    Post-conditions:
      - 返回偏差字典，或 None（解析失败时）
    Side effects:
      - 无
    """
    # 提取预测准确性方向
    accuracy_match = re.search(
        r"预测准确性[：:]\s*(overestimated|underestimated|accurate)",
        content,
    )
    if not accuracy_match:
        return None
    accuracy = accuracy_match.group(1)

    # 提取实际播放量
    plays_match = re.search(r"播放量[：:]\s*(\d+)", content)
    actual_plays = int(plays_match.group(1)) if plays_match else 0

    # 提取预测 bucket（从 ## 预测 段）
    # 格式: "Bucket: ratio → 1K-5K" 或 "Bucket: ratio → 500-1K"
    predicted_bucket = _extract_predicted_bucket(content)

    return {
        "prediction_id": prediction_id,
        "direction": accuracy,
        "actual_plays": actual_plays,
        "predicted_bucket": predicted_bucket,
    }


def _extract_predicted_bucket(content: str) -> int:
    """从预测文件中提取预测 bucket 的数值中值

    支持格式: "1K-5K", "500-1K", "10K-50K", "0-500" 等。
    返回 bucket 中值（如 1K-5K → 3000）。

    Pre-conditions:
      - content 包含 ## 预测 段
    Post-conditions:
      - 返回 bucket 中值，解析失败返回 0
    Side effects:
      - 无
    """
    # 查找 Bucket 行
    bucket_match = re.search(r"Bucket:.*?→\s*([\d.Kk]+)\s*[-–]\s*([\d.Kk]+)", content)
    if not bucket_match:
        return 0

    def parse_bucket_val(s: str) -> int:
        s = s.strip().upper()
        if "K" in s:
            return int(float(s.replace("K", "")) * 1000)
        return int(s)

    try:
        low = parse_bucket_val(bucket_match.group(1))
        high = parse_bucket_val(bucket_match.group(2))
        return (low + high) // 2
    except (ValueError, IndexError):
        return 0


def _check_consecutive_deviation(retros: list[dict[str, Any]]) -> dict[str, Any]:
    """条件 1: 连续 ≥3 同向偏差

    Pre-conditions:
      - retros 非空列表
    Post-conditions:
      - 返回 trigger 结果
    Side effects:
      - 无
    """
    if len(retros) < 3:
        return {"triggered": False, "reason": "", "trigger_type": None}

    # 取最近 N 次复盘，检查最后 3+ 是否同向
    directions = [r["direction"] for r in retros if r["direction"] != "accurate"]
    if len(directions) < 3:
        return {"triggered": False, "reason": "", "trigger_type": None}

    # 从末尾向前检查连续同向
    last_dir = directions[-1]
    consecutive = 1
    for i in range(len(directions) - 2, -1, -1):
        if directions[i] == last_dir:
            consecutive += 1
        else:
            break

    if consecutive >= 3:
        direction_cn = "高估" if last_dir == "overestimated" else "低估"
        return {
            "triggered": True,
            "reason": f"连续 {consecutive} 次同向偏差（{direction_cn}），建议执行 bump",
            "trigger_type": "consecutive_deviation",
        }

    return {"triggered": False, "reason": "", "trigger_type": None}


def _check_10x_deviation(retros: list[dict[str, Any]]) -> dict[str, Any]:
    """条件 2: 1 次 ≥10x 偏差

    检查是否有某次复盘 actual_plays >= 10x predicted_bucket
    或 actual_plays <= predicted_bucket / 10。

    Pre-conditions:
      - retros 非空列表
    Post-conditions:
      - 返回 trigger 结果
    Side effects:
      - 无
    """
    for r in retros:
        predicted = r["predicted_bucket"]
        actual = r["actual_plays"]
        if predicted <= 0 or actual <= 0:
            continue

        if actual >= predicted * 10:
            return {
                "triggered": True,
                "reason": (
                    f"预测 {r['prediction_id']} 实际播放 ({actual}) "
                    f"≥ 10x 预测 ({predicted})，严重低估"
                ),
                "trigger_type": "10x_deviation",
            }

        if actual <= predicted / 10:
            return {
                "triggered": True,
                "reason": (
                    f"预测 {r['prediction_id']} 实际播放 ({actual}) "
                    f"≤ 预测/10 ({predicted / 10:.0f})，严重高估"
                ),
                "trigger_type": "10x_deviation",
            }

    return {"triggered": False, "reason": "", "trigger_type": None}


def _check_comment_reverse_evidence(
    data_dir: Path, retros: list[dict[str, Any]]
) -> dict[str, Any]:
    """条件 3: 2 次同向偏差 + 评论反向证据

    检查最近复盘是否有 2 次同向偏差，且评论分析文件
    (candidates.md) 中存在与偏差方向相反的信号。

    Pre-conditions:
      - retros 非空列表
      - data_dir/candidates.md 存在（可选）
    Post-conditions:
      - 返回 trigger 结果
    Side effects:
      - 无
    """
    # 检查最近 2 次是否同向（排除 accurate）
    directions = [r["direction"] for r in retros if r["direction"] != "accurate"]
    if len(directions) < 2:
        return {"triggered": False, "reason": "", "trigger_type": None}

    last_two = directions[-2:]
    if len(set(last_two)) != 1:
        return {"triggered": False, "reason": "", "trigger_type": None}

    same_direction = last_two[0]

    # 检查评论反向证据 — 读取 candidates.md
    candidates_path = data_dir / "candidates.md"
    if not candidates_path.exists():
        return {"triggered": False, "reason": "", "trigger_type": None}

    try:
        candidates_content = read_file(candidates_path)
    except FileNotFoundError:
        return {"triggered": False, "reason": "", "trigger_type": None}

    # 判断评论是否提供反向证据
    # 如果连续高估，但评论中有高需求/高潜力选题 → 反向证据（说明内容有市场但预测保守）
    # 如果连续低估，但评论中有负面/质疑 → 反向证据（说明内容实际不如预测乐观）
    reverse_evidence = _detect_comment_reverse_signal(same_direction, candidates_content)

    if reverse_evidence:
        direction_cn = "高估" if same_direction == "overestimated" else "低估"
        return {
            "triggered": True,
            "reason": (
                f"2 次同向偏差（{direction_cn}）+ 评论反向证据，"
                f"建议执行 bump 重新校准"
            ),
            "trigger_type": "comment_reverse_evidence",
        }

    return {"triggered": False, "reason": "", "trigger_type": None}


def _detect_comment_reverse_signal(direction: str, candidates_content: str) -> bool:
    """检测评论分析中是否存在与偏差方向相反的信号

    高估 + 评论中有高潜力/高需求选题 → 反向证据
    低估 + 评论中有负面/质疑/失望 → 反向证据

    Pre-conditions:
      - direction 为 overestimated 或 underestimated
      - candidates_content 非空
    Post-conditions:
      - 返回是否存在反向证据
    Side effects:
      - 无
    """
    if direction == "overestimated":
        # 连续高估，但评论显示受众有强烈需求 → 说明 rubric 可能过于保守
        high_potential_keywords = ["high", "高潜力", "强烈需求", "Tier 1", "热门"]
        return any(kw in candidates_content for kw in high_potential_keywords)

    if direction == "underestimated":
        # 连续低估，但评论显示负面反馈 → 说明 rubric 可能过于乐观
        negative_keywords = ["失望", "质疑", "负面", "吐槽", "差评", "不满"]
        return any(kw in candidates_content for kw in negative_keywords)

    return False
