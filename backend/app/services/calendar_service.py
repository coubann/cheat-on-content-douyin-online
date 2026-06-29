"""内容日历服务

管理内容排期，将选题、脚本、发布计划可视化。

用户数据隔离：scripts、predictions 路径使用 data/{user_id}/ 子目录。
排期数据 (schedules.json) 保留在根目录（共享排期表）。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from backend.app.services.file_io import read_file, safe_write

logger = structlog.get_logger()


def get_calendar(data_dir: Path, user_id: int = 0, days: int = 14) -> dict[str, Any]:
    """获取内容日历

    Pre-conditions:
      - .cheat-state.json 存在
    Post-conditions:
      - 返回未来 days 天的日历数据
    Side effects:
      - 无
    """
    from backend.app.models.state import CheatState

    state_path = data_dir / ".cheat-state.json"
    state = CheatState.model_validate_json(read_file(state_path))

    # 收集所有相关数据
    scripts = _collect_scripts(data_dir, user_id=user_id)
    predictions = _collect_predictions(data_dir, user_id=user_id)
    schedules = _load_schedules(data_dir)

    # 生成日历
    today = datetime.now().date()
    calendar_days = []

    for i in range(days):
        date = today + timedelta(days=i)
        date_str = date.isoformat()
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][date.weekday()]

        # 查找该日的排期
        day_schedule = [s for s in schedules if s.get("date") == date_str]

        # 查找该日创建的脚本
        day_scripts = [s for s in scripts if s.get("created_at", "").startswith(date_str)]

        # 查找该日的预测
        day_predictions = [p for p in predictions if p.get("pred_time", "").startswith(date_str)]

        calendar_days.append({
            "date": date_str,
            "weekday": weekday,
            "is_today": i == 0,
            "is_weekend": date.weekday() >= 5,
            "scheduled": day_schedule,
            "scripts": day_scripts,
            "predictions": day_predictions,
        })

    # 生成建议
    suggestions = _generate_suggestions(state, calendar_days, schedules)

    return {
        "days": calendar_days,
        "suggestions": suggestions,
        "buffer": len(state.shoots),
        "cadence": state.target_publish_cadence_days,
        "total_scheduled": len(schedules),
    }


def add_schedule(
    data_dir: Path,
    user_id: int = 0,
    date: str = "",
    script_id: str = "",
    platform: str = "douyin",
    notes: str = "",
) -> dict[str, Any]:
    """添加排期

    Pre-conditions:
      - date 格式为 YYYY-MM-DD
      - script_id 对应的脚本存在
    Post-conditions:
      - 排期被保存
    Side effects:
      - 写文件系统
    """
    schedules = _load_schedules(data_dir)

    schedule_id = f"sch_{len(schedules) + 1:03d}_{datetime.now().strftime('%H%M%S')}"

    new_schedule = {
        "id": schedule_id,
        "date": date,
        "script_id": script_id,
        "platform": platform,
        "notes": notes,
        "status": "planned",  # planned → published → retro'd
        "created_at": datetime.now().isoformat(),
    }

    schedules.append(new_schedule)
    _save_schedules(data_dir, schedules)

    logger.info("schedule_added", schedule_id=schedule_id, date=date, script_id=script_id, user_id=user_id)
    return new_schedule


def update_schedule(data_dir: Path, user_id: int = 0, schedule_id: str = "", updates: dict[str, Any] | None = None) -> dict[str, Any]:
    """更新排期

    Pre-conditions:
      - schedule_id 对应的排期存在
    Post-conditions:
      - 排期被更新
    Side effects:
      - 写文件系统
    """
    if updates is None:
        updates = {}
    schedules = _load_schedules(data_dir)

    for s in schedules:
        if s["id"] == schedule_id:
            s.update({k: v for k, v in updates.items() if k in ("date", "platform", "notes", "status")})
            _save_schedules(data_dir, schedules)
            return s

    raise ValueError(f"排期不存在: {schedule_id}")


def remove_schedule(data_dir: Path, user_id: int = 0, schedule_id: str = "") -> None:
    """删除排期

    Pre-conditions:
      - 无
    Post-conditions:
      - 指定排期被移除
    Side effects:
      - 写文件系统
    """
    schedules = _load_schedules(data_dir)
    schedules = [s for s in schedules if s["id"] != schedule_id]
    _save_schedules(data_dir, schedules)


def _collect_scripts(data_dir: Path, user_id: int = 0) -> list[dict[str, Any]]:
    """收集脚本信息

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
        })
    return results


def _collect_predictions(data_dir: Path, user_id: int = 0) -> list[dict[str, Any]]:
    """收集预测信息

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
        pred_time = ""
        for line in content.split("\n"):
            if "预测时间:" in line:
                pred_time = line.split(":", 1)[1].strip()
                break
        results.append({
            "id": f.stem,
            "pred_time": pred_time,
            "has_retro": "## 复盘" in content and "尚未复盘" not in content,
        })
    return results


def _load_schedules(data_dir: Path) -> list[dict[str, Any]]:
    """加载排期数据

    排期表 (schedules.json) 保留在根目录，为共享数据。

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回排期列表
    Side effects:
      - 无
    """
    path = data_dir / "schedules.json"
    if not path.exists():
        return []
    try:
        return json.loads(read_file(path))
    except Exception:
        return []


def _save_schedules(data_dir: Path, schedules: list[dict[str, Any]]) -> None:
    """保存排期数据

    排期表 (schedules.json) 保留在根目录，为共享数据。

    Pre-conditions:
      - data_dir 目录存在
    Post-conditions:
      - 排期数据被保存到 schedules.json
    Side effects:
      - 写文件系统
    """
    path = data_dir / "schedules.json"
    safe_write(path, json.dumps(schedules, indent=2, ensure_ascii=False))


def _generate_suggestions(state: Any, calendar_days: list[dict], schedules: list[dict]) -> list[dict[str, Any]]:
    """生成排期建议

    Pre-conditions:
      - state 和 calendar_days 数据有效
    Post-conditions:
      - 返回建议列表（最多 5 条）
    Side effects:
      - 无
    """
    suggestions = []

    # 检查 buffer 不足
    buffer = len(state.shoots)
    cadence = state.target_publish_cadence_days
    if buffer * cadence < 3:
        suggestions.append({
            "type": "warning",
            "message": f"Buffer 不足（{buffer} 篇，约 {buffer * cadence} 天），建议尽快写新稿",
        })

    # 检查空白天
    scheduled_dates = {s["date"] for s in schedules}
    for day in calendar_days[:7]:
        if not day["is_weekend"] and day["date"] not in scheduled_dates and buffer > 0:
            suggestions.append({
                "type": "info",
                "message": f"{day['date']} ({day['weekday']}) 尚无排期，建议安排发布",
            })

    # 检查 pending retros
    if state.pending_retros:
        suggestions.append({
            "type": "action",
            "message": f"有 {len(state.pending_retros)} 篇待复盘内容",
        })

    return suggestions[:5]
