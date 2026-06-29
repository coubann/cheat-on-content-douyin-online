"""全链路追踪服务

追踪内容从选题到复盘的完整生命周期。

用户数据隔离：scripts、predictions 路径使用 data/{user_id}/ 子目录。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.services.file_io import read_file

logger = structlog.get_logger()


def get_pipeline(data_dir: Path, user_id: int = 0) -> dict[str, Any]:
    """获取全链路追踪数据

    将选题→脚本→预测→发布→复盘的完整流程串联起来。

    Pre-conditions:
      - .cheat-state.json 存在
    Post-conditions:
      - 返回所有内容的生命周期追踪数据
    Side effects:
      - 无
    """
    from backend.app.models.state import CheatState

    state_path = data_dir / ".cheat-state.json"
    CheatState.model_validate_json(read_file(state_path))

    # 收集各阶段数据
    scripts = _collect_scripts(data_dir, user_id=user_id)
    predictions = _collect_predictions(data_dir, user_id=user_id)
    publishes = _collect_publishes(data_dir)
    retros = _collect_retros(data_dir, user_id=user_id)
    candidates = _collect_candidates(data_dir)
    experiments = _collect_experiments(data_dir)

    # 串联全链路
    pipelines = []
    all_ids = set()

    # 从脚本出发串联
    for script in scripts:
        sid = script["id"]
        all_ids.add(sid)

        pipeline = {
            "id": sid,
            "title": script.get("title", sid),
            "stages": {
                "candidate": None,
                "script": script,
                "prediction": None,
                "publish": None,
                "retro": None,
            },
            "experiment": None,
            "status": _compute_pipeline_status(script, predictions, publishes, retros),
            "timeline": [],
        }

        # 匹配预测
        for pred in predictions:
            if pred.get("script_id") == sid or pred.get("id") == sid:
                pipeline["stages"]["prediction"] = pred
                pipeline["timeline"].append({"stage": "prediction", "time": pred.get("pred_time", ""), "data": pred})

        # 匹配发布
        for pub in publishes:
            if pub.get("script_id") == sid or pub.get("prediction_id") == sid:
                pipeline["stages"]["publish"] = pub
                pipeline["timeline"].append({"stage": "publish", "time": pub.get("published_at", ""), "data": pub})

        # 匹配复盘
        for retro in retros:
            if retro.get("prediction_id") == sid or retro.get("script_id") == sid:
                pipeline["stages"]["retro"] = retro
                pipeline["timeline"].append({"stage": "retro", "time": retro.get("retro_time", ""), "data": retro})

        # 匹配实验
        for exp in experiments:
            if exp.get("script_a_id") == sid or exp.get("script_b_id") == sid:
                pipeline["experiment"] = {
                    "id": exp["id"],
                    "topic": exp.get("topic", ""),
                    "role": "A" if exp.get("script_a_id") == sid else "B",
                }

        # 匹配候选选题
        for cand in candidates:
            if cand.get("script_id") == sid:
                pipeline["stages"]["candidate"] = cand

        # 排序 timeline
        pipeline["timeline"].sort(key=lambda x: x.get("time", ""))

        pipelines.append(pipeline)

    # 添加只有预测没有脚本的条目
    for pred in predictions:
        if pred.get("id") not in all_ids and pred.get("script_id") not in all_ids:
            pid = pred["id"]
            all_ids.add(pid)
            pipelines.append({
                "id": pid,
                "title": pred.get("script_id", pid),
                "stages": {"candidate": None, "script": None, "prediction": pred, "publish": None, "retro": None},
                "experiment": None,
                "status": "predicted",
                "timeline": [{"stage": "prediction", "time": pred.get("pred_time", ""), "data": pred}],
            })

    # 统计
    stats = {
        "total": len(pipelines),
        "by_status": {},
    }
    for p in pipelines:
        status = p["status"]
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

    return {
        "pipelines": sorted(
            pipelines,
            key=lambda x: (
                x.get("timeline", [{}])[0].get("time", "")
                if x.get("timeline")
                else ""
            ),
            reverse=True,
        ),
        "stats": stats,
    }


def _compute_pipeline_status(script: dict, predictions: list, publishes: list, retros: list) -> str:
    """计算管道状态

    Pre-conditions:
      - script 包含 id 字段
    Post-conditions:
      - 返回状态字符串 (completed/published/predicted/draft)
    Side effects:
      - 无
    """
    sid = script.get("id", "")
    has_prediction = any(p.get("script_id") == sid or p.get("id") == sid for p in predictions)
    has_publish = any(p.get("script_id") == sid or p.get("prediction_id") == sid for p in publishes)
    has_retro = any(r.get("prediction_id") == sid or r.get("script_id") == sid for r in retros)

    if has_retro:
        return "completed"
    elif has_publish:
        return "published"
    elif has_prediction:
        return "predicted"
    else:
        return "draft"


def _collect_scripts(data_dir: Path, user_id: int = 0) -> list[dict[str, Any]]:
    """收集脚本

    从 data/{user_id}/scripts/ 目录读取。

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回脚本列表
    Side effects:
      - 无
    """
    scripts_dir = data_dir / str(user_id) / "scripts"
    if not scripts_dir.exists():
        return []
    results = []
    for f in scripts_dir.glob("*.md"):
        content = read_file(f)
        title = f.stem
        for line in content.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break
        results.append({
            "id": f.stem,
            "title": title,
            "created_at": datetime.fromtimestamp(f.stat().st_ctime).isoformat(),
            "updated_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return results


def _collect_predictions(data_dir: Path, user_id: int = 0) -> list[dict[str, Any]]:
    """收集预测

    从 data/{user_id}/predictions/ 目录读取。

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回预测列表
    Side effects:
      - 无
    """
    preds_dir = data_dir / str(user_id) / "predictions"
    if not preds_dir.exists():
        return []
    results = []
    for f in preds_dir.glob("*.md"):
        content = read_file(f)
        script_id = f.stem
        pred_time = ""
        virality_score = None
        for line in content.split("\n"):
            if "脚本 ID:" in line:
                script_id = line.split(":", 1)[1].strip()
            elif "预测时间:" in line:
                pred_time = line.split(":", 1)[1].strip()
            elif "爆款分" in line:
                m = re.search(r"(\d+\.?\d*)\s*/\s*100", line)
                if m:
                    virality_score = float(m.group(1))
        results.append({
            "id": f.stem,
            "script_id": script_id,
            "pred_time": pred_time,
            "virality_score": virality_score,
            "has_retro": "## 复盘" in content and "尚未复盘" not in content,
        })
    return results


def _collect_publishes(data_dir: Path) -> list[dict[str, Any]]:
    """收集发布记录

    从系统级 .cheat-state.json 读取（共享状态）。

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回发布记录列表
    Side effects:
      - 无
    """
    state_path = data_dir / ".cheat-state.json"
    if not state_path.exists():
        return []
    from backend.app.models.state import CheatState
    state = CheatState.model_validate_json(read_file(state_path))
    # 从 shoots 列表推断
    return [{"script_id": s, "published_at": ""} for s in state.shoots]


def _collect_retros(data_dir: Path, user_id: int = 0) -> list[dict[str, Any]]:
    """收集复盘记录

    从 data/{user_id}/predictions/ 目录读取。

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回复盘记录列表
    Side effects:
      - 无
    """
    preds_dir = data_dir / str(user_id) / "predictions"
    if not preds_dir.exists():
        return []
    results = []
    for f in preds_dir.glob("*.md"):
        content = read_file(f)
        if "## 复盘" not in content or "尚未复盘" in content:
            continue
        script_id = f.stem
        retro_time = ""
        actual_plays = None
        accuracy = ""
        for line in content.split("\n"):
            if "复盘时间:" in line:
                m = re.search(r"(\d{4}-\d{2}-\d{2})", line)
                retro_time = m.group(1) if m else ""
            elif "播放量:" in line:
                m = re.search(r"(\d+)", line)
                actual_plays = int(m.group(1)) if m else None
            elif "预测准确性:" in line:
                accuracy = line.split(":", 1)[1].strip()
        results.append({
            "prediction_id": f.stem,
            "script_id": script_id,
            "retro_time": retro_time,
            "actual_plays": actual_plays,
            "accuracy": accuracy,
        })
    return results


def _collect_candidates(data_dir: Path) -> list[dict[str, Any]]:
    """收集候选选题

    从系统级根目录 candidates.md 读取。

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回候选选题列表
    Side effects:
      - 无
    """
    cand_path = data_dir / "candidates.md"
    if not cand_path.exists():
        return []
    content = read_file(cand_path)
    results = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- [") and "]" in line:
            results.append({"topic": line, "source": "candidates"})
    return results


def _collect_experiments(data_dir: Path) -> list[dict[str, Any]]:
    """收集 A/B 实验

    从系统级根目录 experiments/ 读取。

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回实验列表
    Side effects:
      - 无
    """
    exp_dir = data_dir / "experiments"
    if not exp_dir.exists():
        return []
    import json
    results = []
    for f in exp_dir.glob("*.json"):
        try:
            data = json.loads(read_file(f))
            results.append(data)
        except Exception:
            pass
    return results
