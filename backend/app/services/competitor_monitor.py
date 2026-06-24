"""竞品监控服务

持续追踪对标账号的新内容，自动检测更新并提醒。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.services.file_io import read_file, safe_write

logger = structlog.get_logger()

_MONITORS_FILE = "monitors.json"


def _load_monitors_data(data_dir: Path) -> dict[str, Any]:
    """加载监控数据

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回监控数据（monitors + update_history）
    Side effects:
      - 无
    """
    path = data_dir / _MONITORS_FILE
    if not path.exists():
        return {"monitors": [], "update_history": []}
    return json.loads(read_file(path))


def _save_monitors_data(data_dir: Path, data: dict[str, Any]) -> None:
    """保存监控数据

    Pre-conditions:
      - data 为合法的监控数据结构
    Post-conditions:
      - monitors.json 被写入
    Side effects:
      - 写文件系统
    """
    safe_write(data_dir / _MONITORS_FILE, json.dumps(data, ensure_ascii=False, indent=2))


async def add_monitor(
    data_dir: Path,
    account_name: str,
    platform: str,
    check_interval_hours: int = 24,
) -> dict[str, Any]:
    """添加竞品监控

    Pre-conditions:
      - account_name 非空
      - platform 为 bilibili/douyin/xiaohongshu/wechat 之一
    Post-conditions:
      - monitors.json 中新增一条监控记录
      - 返回监控详情
    Side effects:
      - 写文件系统
    Error codes:
      - INVALID_REQUEST: platform 不支持
    """
    from backend.app.errors import INVALID_REQUEST

    valid_platforms = {"bilibili", "douyin", "xiaohongshu", "wechat"}
    if platform not in valid_platforms:
        raise ValueError(f"{INVALID_REQUEST}: 不支持的平台 {platform}，支持: {', '.join(sorted(valid_platforms))}")

    data = _load_monitors_data(data_dir)

    # 检查是否已存在同名同平台的监控
    for m in data["monitors"]:
        if m["account_name"] == account_name and m["platform"] == platform:
            raise ValueError(f"{INVALID_REQUEST}: 已存在对 {account_name}({platform}) 的监控")

    monitor_id = f"mon_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()

    monitor = {
        "id": monitor_id,
        "account_name": account_name,
        "platform": platform,
        "check_interval_hours": check_interval_hours,
        "last_check": None,
        "last_content_hash": None,
        "last_content_count": 0,
        "new_content_detected": False,
        "created_at": now,
    }

    data["monitors"].append(monitor)
    _save_monitors_data(data_dir, data)

    logger.info("monitor_added", monitor_id=monitor_id, account=account_name, platform=platform)
    return monitor


async def list_monitors(data_dir: Path) -> list[dict[str, Any]]:
    """列出所有监控

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回监控列表
    Side effects:
      - 无
    """
    data = _load_monitors_data(data_dir)
    return data["monitors"]


async def remove_monitor(data_dir: Path, monitor_id: str) -> dict[str, Any]:
    """移除监控

    Pre-conditions:
      - 无
    Post-conditions:
      - 监控被移除
      - 返回被移除的监控
    Side effects:
      - 写文件系统
    Error codes:
      - MONITOR_NOT_FOUND
    """
    from backend.app.errors import MONITOR_NOT_FOUND

    data = _load_monitors_data(data_dir)

    original_len = len(data["monitors"])
    data["monitors"] = [m for m in data["monitors"] if m["id"] != monitor_id]

    if len(data["monitors"]) == original_len:
        raise FileNotFoundError(f"{MONITOR_NOT_FOUND}: {monitor_id}")

    # 同时移除相关的更新历史
    data["update_history"] = [h for h in data["update_history"] if h["monitor_id"] != monitor_id]

    _save_monitors_data(data_dir, data)

    logger.info("monitor_removed", monitor_id=monitor_id)
    return {"removed": monitor_id}


async def check_updates(data_dir: Path, monitor_id: str) -> dict[str, Any]:
    """检查指定监控是否有新内容

    Pre-conditions:
      - 监控存在
    Post-conditions:
      - last_check 被更新
      - 如有新内容，new_content_detected=True
      - 返回检查结果
    Side effects:
      - 启动浏览器（通过 account_fetcher）
      - 写文件系统
    Error codes:
      - MONITOR_NOT_FOUND
    """
    from backend.app.errors import MONITOR_NOT_FOUND
    from backend.app.services.account_fetcher import fetch_account_samples

    data = _load_monitors_data(data_dir)

    monitor = None
    for m in data["monitors"]:
        if m["id"] == monitor_id:
            monitor = m
            break

    if not monitor:
        raise FileNotFoundError(f"{MONITOR_NOT_FOUND}: {monitor_id}")

    logger.info("check_updates_start", monitor_id=monitor_id, account=monitor["account_name"])

    # 抓取当前内容
    samples = await fetch_account_samples(
        account_name=monitor["account_name"],
        platform=monitor["platform"],
        count=10,
    )

    # 计算内容 hash
    content_str = "\n".join(samples)
    content_hash = hashlib.md5(content_str.encode()).hexdigest()[:12]
    content_count = len(samples)

    now = datetime.now().isoformat()

    # 检测新内容
    new_samples = []
    is_new = False

    if monitor["last_content_hash"] is not None:
        if content_hash != monitor["last_content_hash"]:
            is_new = True
            # 找出新增的内容（简单比较：当前有但之前没有的）
            # 由于之前没有存储完整内容列表，这里只能基于数量变化和 hash 变化判断
            if content_count > monitor["last_content_count"]:
                # 新增的内容大概率在列表前面
                diff = content_count - monitor["last_content_count"]
                new_samples = samples[:diff]
            else:
                # 内容变化但数量未增，标记所有为可能有更新
                new_samples = [f"[内容已变化，hash: {content_hash}]"]
    else:
        # 首次检查，不算新内容
        new_samples = []

    # 更新监控记录
    monitor["last_check"] = now
    monitor["last_content_hash"] = content_hash
    monitor["last_content_count"] = content_count
    monitor["new_content_detected"] = is_new

    # 记录更新历史
    if is_new:
        action = "none"
        if new_samples and not any("抓取失败" in s or "暂无" in s for s in new_samples):
            action = "notified"

        data["update_history"].append({
            "monitor_id": monitor_id,
            "detected_at": now,
            "new_samples": new_samples,
            "action_taken": action,
        })

    _save_monitors_data(data_dir, data)

    result = {
        "monitor_id": monitor_id,
        "account_name": monitor["account_name"],
        "platform": monitor["platform"],
        "new_content_detected": is_new,
        "new_samples": new_samples,
        "current_content_count": content_count,
        "checked_at": now,
    }

    logger.info("check_updates_complete", monitor_id=monitor_id, new_content=is_new)
    return result


async def check_all_updates(data_dir: Path) -> list[dict[str, Any]]:
    """检查所有监控是否有新内容

    Pre-conditions:
      - 无
    Post-conditions:
      - 所有监控被检查
      - 返回所有检查结果
    Side effects:
      - 启动浏览器（通过 account_fetcher）
      - 写文件系统
    """
    data = _load_monitors_data(data_dir)
    results = []

    for monitor in data["monitors"]:
        try:
            result = await check_updates(data_dir, monitor["id"])
            results.append(result)
        except Exception as e:
            logger.warning("check_all_updates_failed", monitor_id=monitor["id"], error=str(e))
            results.append({
                "monitor_id": monitor["id"],
                "account_name": monitor["account_name"],
                "error": str(e),
            })

    logger.info("check_all_updates_complete", count=len(results))
    return results


async def get_update_history(data_dir: Path, monitor_id: str) -> list[dict[str, Any]]:
    """获取指定监控的更新历史

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回更新历史列表（按时间倒序）
    Side effects:
      - 无
    """
    data = _load_monitors_data(data_dir)
    history = [h for h in data["update_history"] if h["monitor_id"] == monitor_id]
    # 按时间倒序
    history.sort(key=lambda h: h.get("detected_at", ""), reverse=True)
    return history
