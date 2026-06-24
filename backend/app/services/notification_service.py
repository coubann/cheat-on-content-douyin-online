"""通知服务 — 复盘提醒 + bump 建议 + buffer 预警

提供三类通知：
1. pending_retros: 已发布 T+3 天但尚未复盘的预测
2. bump_suggestions: 触发 bump 条件时的升级建议
3. low_buffer: buffer 不足（红/橙）时的写稿提醒
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.models.state import CheatState
from backend.app.services.file_io import read_file, safe_write
from backend.app.services.status_service import _check_bump_trigger, _compute_buffer_color

logger = structlog.get_logger()

_NOTIFICATIONS_FILE = "notifications.json"


def check_pending_retros(data_dir: Path) -> list[dict[str, Any]]:
    """检查需要复盘的预测

    读取 state.pending_retros 和预测文件，找出已发布 T+3 天
    但尚未完成复盘的预测。

    Pre-conditions:
      - .cheat-state.json 存在
    Post-conditions:
      - 返回待复盘通知列表
    Side effects:
      - 无（纯读取）
    Error codes:
      - 无
    """
    state_path = data_dir / ".cheat-state.json"
    if not state_path.exists():
        return []

    state = CheatState.model_validate_json(read_file(state_path))
    notifications: list[dict[str, Any]] = []

    for retro_id in state.pending_retros:
        # retro_id 格式: script_id|platform|published_at
        parts = retro_id.split("|")
        script_id = parts[0]
        platform = parts[1] if len(parts) > 1 else "unknown"
        published_at_str = parts[2] if len(parts) > 2 else ""

        # 判断是否已过 T+3 天
        is_overdue = False
        days_since = 0
        if published_at_str:
            try:
                published_at = datetime.fromisoformat(published_at_str)
                days_since = (datetime.now() - published_at).days
                is_overdue = days_since >= 3
            except (ValueError, TypeError):
                is_overdue = True
                days_since = -1

        # 检查预测文件是否已有复盘
        pred_path = data_dir / "predictions" / f"{script_id}.md"
        has_retro = False
        if pred_path.exists():
            content = read_file(pred_path)
            has_retro = "## 复盘" in content and "尚未复盘" not in content

        if not has_retro:
            notifications.append({
                "id": f"retro-{retro_id}",
                "type": "pending_retro",
                "script_id": script_id,
                "platform": platform,
                "published_at": published_at_str,
                "days_since_publish": days_since,
                "is_overdue": is_overdue,
                "message": f"预测 {script_id} 已发布 {days_since} 天，请完成复盘",
            })

    return notifications


def get_notification_summary(data_dir: Path) -> dict[str, Any]:
    """获取通知摘要

    汇总所有待处理通知：待复盘、bump 建议、buffer 不足。

    Pre-conditions:
      - .cheat-state.json 存在
    Post-conditions:
      - 返回通知摘要（各类计数 + 详情）
    Side effects:
      - 无
    Error codes:
      - 无
    """
    state_path = data_dir / ".cheat-state.json"
    if not state_path.exists():
        return {
            "pending_retros": 0,
            "bump_suggestions": 0,
            "low_buffer_warnings": 0,
            "total_unread": 0,
        }

    state = CheatState.model_validate_json(read_file(state_path))

    # 1. 待复盘
    pending_retros = check_pending_retros(data_dir)

    # 2. bump 建议
    bump_info = _check_bump_trigger(data_dir, state)
    bump_suggestions: list[dict[str, Any]] = []
    if bump_info["triggered"]:
        bump_suggestions.append({
            "id": "bump-suggestion",
            "type": "bump_suggestion",
            "trigger_type": bump_info["trigger_type"],
            "reason": bump_info["reason"],
            "message": f"Rubric 升级建议: {bump_info['reason']}",
        })

    # 3. buffer 不足
    buffer_color = _compute_buffer_color(state)
    low_buffer_warnings: list[dict[str, Any]] = []
    if buffer_color in ("red", "orange"):
        buffer_days = len(state.shoots) * state.target_publish_cadence_days
        low_buffer_warnings.append({
            "id": f"low-buffer-{buffer_color}",
            "type": "low_buffer",
            "buffer_color": buffer_color,
            "buffer_days": buffer_days,
            "message": f"Buffer 不足（{buffer_color}，仅 {buffer_days} 天），建议写新稿",
        })

    # 读取已读通知
    read_ids = _load_read_notification_ids(data_dir)

    all_notifications = pending_retros + bump_suggestions + low_buffer_warnings
    unread = [n for n in all_notifications if n["id"] not in read_ids]

    return {
        "pending_retros": len(pending_retros),
        "bump_suggestions": len(bump_suggestions),
        "low_buffer_warnings": len(low_buffer_warnings),
        "total_unread": len(unread),
        "notifications": all_notifications,
    }


def mark_notification_read(data_dir: Path, notification_id: str) -> dict[str, Any]:
    """标记通知为已读

    将通知 ID 写入 notifications.json 的 read_ids 列表。

    Pre-conditions:
      - notification_id 非空
    Post-conditions:
      - notifications.json 被更新
      - 返回标记结果
    Side effects:
      - 写文件系统
    Error codes:
      - NOTIFICATION_NOT_FOUND: 通知 ID 不在当前通知列表中
    """
    # 验证通知存在
    summary = get_notification_summary(data_dir)
    all_ids = [n["id"] for n in summary.get("notifications", [])]
    if notification_id not in all_ids:
        from backend.app.errors import NOTIFICATION_NOT_FOUND
        raise ValueError(f"{NOTIFICATION_NOT_FOUND}: {notification_id}")

    read_ids = _load_read_notification_ids(data_dir)
    if notification_id not in read_ids:
        read_ids.append(notification_id)
        _save_read_notification_ids(data_dir, read_ids)

    logger.info("notification_marked_read", notification_id=notification_id)
    return {
        "notification_id": notification_id,
        "read": True,
    }


def _load_read_notification_ids(data_dir: Path) -> list[str]:
    """从 notifications.json 加载已读通知 ID 列表

    Pre-conditions:
      - data_dir 存在
    Post-conditions:
      - 返回已读 ID 列表
    Side effects:
      - 无
    """
    notif_path = data_dir / _NOTIFICATIONS_FILE
    if not notif_path.exists():
        return []

    try:
        content = read_file(notif_path)
        data = json.loads(content)
        return data.get("read_ids", [])
    except (json.JSONDecodeError, KeyError):
        return []


def _save_read_notification_ids(data_dir: Path, read_ids: list[str]) -> None:
    """保存已读通知 ID 列表到 notifications.json

    Pre-conditions:
      - data_dir 存在
    Post-conditions:
      - notifications.json 被写入
    Side effects:
      - 写文件系统
    """
    notif_path = data_dir / _NOTIFICATIONS_FILE
    data = {"read_ids": read_ids, "updated_at": datetime.now().isoformat()}
    safe_write(notif_path, json.dumps(data, indent=2, ensure_ascii=False))
