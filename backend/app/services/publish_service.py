"""发布登记服务 — cheat-shoot + cheat-publish 的 Python 实现

cheat-shoot: 登记拍摄 + diff 检测 v2
cheat-publish: 发布元数据登记 + 多平台回传
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.models.state import CheatState
from backend.app.services.file_io import read_file, safe_write

logger = structlog.get_logger()


async def register_shoot(
    data_dir: Path,
    script_id: str,
    shoot_content: str,
) -> dict[str, Any]:
    """登记拍摄 — cheat-shoot

    对比脚本和拍摄稿的差异，如果 >=30% 则触发 v2 预测。

    Pre-conditions:
      - scripts/<id>.md 存在
    Post-conditions:
      - videos/<id>.md 被创建
      - state.shoots 被更新
      - 返回 diff 比例 + 是否需要 v2
    Side effects:
      - 写文件系统
      - 更新 .cheat-state.json
    """
    script_path = data_dir / "scripts" / f"{script_id}.md"
    script_content = read_file(script_path)

    # 计算 diff
    diff_ratio = _compute_diff_ratio(script_content, shoot_content)
    needs_v2 = diff_ratio >= 0.3

    # 创建视频记录
    videos_dir = data_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    video_path = videos_dir / f"{script_id}.md"
    video_content = f"""# 拍摄记录: {script_id}

> 登记时间: {datetime.now().isoformat()}

## 拍摄稿

{shoot_content}

## Diff 分析

- 与脚本差异: {diff_ratio:.0%}
- 触发 v2 预测: {'是' if needs_v2 else '否'}

## 发布信息

> （尚未发布）
"""
    safe_write(video_path, video_content)

    # 更新 state
    state_path = data_dir / ".cheat-state.json"
    state = CheatState.model_validate_json(read_file(state_path))
    if script_id not in state.shoots:
        state.shoots.append(script_id)
    state.in_progress_session = script_id
    safe_write(state_path, state.model_dump_json(indent=2))

    logger.info("shoot_registered", script_id=script_id, diff_ratio=diff_ratio, needs_v2=needs_v2)
    return {
        "script_id": script_id,
        "diff_ratio": round(diff_ratio, 3),
        "needs_v2": needs_v2,
        "video_path": str(video_path),
    }


async def register_publish(
    data_dir: Path,
    script_id: str,
    platform: str,
    publish_url: str | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    """发布登记 — cheat-publish

    Pre-conditions:
      - videos/<id>.md 存在（已登记拍摄）
    Post-conditions:
      - videos/<id>.md 追加发布信息
      - state.pending_retros 追加（T+3d 后需要复盘）
      - state.shoots 移除该条（已发布）
      - state.calibration_samples +1
    Side effects:
      - 写文件系统
      - 更新 .cheat-state.json
    """
    video_path = data_dir / "videos" / f"{script_id}.md"
    if not video_path.exists():
        from backend.app.errors import FILE_NOT_FOUND
        raise FileNotFoundError(f"{FILE_NOT_FOUND}: 视频记录不存在 {script_id}")

    published_at = published_at or datetime.now().isoformat()

    # 追加发布信息到视频记录
    existing = read_file(video_path)
    publish_section = f"""

## 发布信息

- 平台: {platform}
- 发布时间: {published_at}
- 链接: {publish_url or '未提供'}
- 状态: 已发布

## 复盘

> T+3d 后追加复盘数据
"""
    safe_write(video_path, existing + publish_section)

    # 更新 state
    state_path = data_dir / ".cheat-state.json"
    state = CheatState.model_validate_json(read_file(state_path))

    # 移入 pending_retros
    retro_id = f"{script_id}|{platform}|{published_at}"
    if retro_id not in state.pending_retros:
        state.pending_retros.append(retro_id)

    # 从 shoots 移除
    if script_id in state.shoots:
        state.shoots.remove(script_id)

    # calibration_samples +1
    state.calibration_samples += 1

    safe_write(state_path, state.model_dump_json(indent=2))

    logger.info("publish_registered", script_id=script_id, platform=platform)
    return {
        "script_id": script_id,
        "platform": platform,
        "published_at": published_at,
        "retro_id": retro_id,
        "calibration_samples": state.calibration_samples,
    }


async def list_published(data_dir: Path) -> list[dict[str, Any]]:
    """列出所有内容（合并预测 + 发布 + 复盘数据）

    从 predictions/ 和 videos/ 目录合并数据，
    展示完整的内容生命周期状态。

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回内容列表，按时间倒序
    Side effects:
      - 无
    """
    import re

    results: dict[str, dict[str, Any]] = {}

    # 1. 从预测文件收集数据
    preds_dir = data_dir / "predictions"
    if preds_dir.exists():
        for f in sorted(preds_dir.glob("*.md"), reverse=True):
            content = read_file(f)
            script_id = f.stem
            pred_time = ""
            virality_score = None
            composite = None
            has_retro = "## 复盘" in content and "尚未复盘" not in content
            actual_plays = None
            accuracy = ""
            rubric_version = ""

            for line in content.split("\n"):
                if "脚本 ID:" in line:
                    script_id = line.split(":", 1)[1].strip()
                elif "预测时间:" in line:
                    pred_time = line.split(":", 1)[1].strip()
                elif "爆款分" in line:
                    m = re.search(r"(\d+\.?\d*)\s*/\s*100", line)
                    if m:
                        virality_score = float(m.group(1))
                elif "综合分" in line:
                    m = re.search(r"(\d+\.?\d*)\s*/\s*10", line)
                    if m:
                        composite = float(m.group(1))
                elif "Rubric 版本:" in line:
                    rubric_version = line.split(":", 1)[1].strip()
                elif "播放量:" in line and has_retro:
                    m = re.search(r"(\d+)", line)
                    if m:
                        actual_plays = int(m.group(1))
                elif "预测准确性:" in line and has_retro:
                    accuracy = line.split(":", 1)[1].strip()

            results[script_id] = {
                "id": script_id,
                "title": _extract_title(script_id),
                "predicted": True,
                "published": False,
                "has_retro": has_retro,
                "pred_time": pred_time,
                "virality_score": virality_score,
                "composite": composite,
                "rubric_version": rubric_version,
                "actual_plays": actual_plays,
                "accuracy": accuracy,
                "platform": "",
                "publish_url": "",
                "updated_at": datetime.fromtimestamp(
                    f.stat().st_mtime
                ).isoformat(),
            }

    # 2. 从视频文件补充发布信息
    videos_dir = data_dir / "videos"
    if videos_dir.exists():
        for f in sorted(videos_dir.glob("*.md"), reverse=True):
            content = read_file(f)
            script_id = f.stem
            is_published = "状态: 已发布" in content
            platform = ""
            publish_url = ""

            for line in content.split("\n"):
                if "平台:" in line:
                    platform = line.split(":", 1)[1].strip()
                elif "链接:" in line:
                    publish_url = line.split(":", 1)[1].strip()

            if script_id in results:
                # 合并到已有预测记录
                results[script_id]["published"] = is_published
                results[script_id]["platform"] = platform
                results[script_id]["publish_url"] = (
                    publish_url if publish_url != "未提供" else ""
                )
            else:
                # 只有视频记录，没有预测
                results[script_id] = {
                    "id": script_id,
                    "title": _extract_title(script_id),
                    "predicted": False,
                    "published": is_published,
                    "has_retro": False,
                    "pred_time": "",
                    "virality_score": None,
                    "composite": None,
                    "rubric_version": "",
                    "actual_plays": None,
                    "accuracy": "",
                    "platform": platform,
                    "publish_url": (
                        publish_url if publish_url != "未提供" else ""
                    ),
                    "updated_at": datetime.fromtimestamp(
                        f.stat().st_mtime
                    ).isoformat(),
                }

    # 3. 按更新时间倒序
    return sorted(
        results.values(), key=lambda x: x["updated_at"], reverse=True
    )


def _extract_title(script_id: str) -> str:
    """从 script_id 提取可读标题

    格式: 2026-06-10_6a688060_不要再用AI只会聊天了 → 不要再用AI只会聊天了
    """
    parts = script_id.split("_")
    if len(parts) >= 3:
        return "_".join(parts[2:])
    return script_id


def _compute_diff_ratio(original: str, modified: str) -> float:
    """计算两个文本的差异比例（简单字符级 diff）

    Pre-conditions:
      - 两个字符串非空
    Post-conditions:
      - 返回 0-1 的差异比例
    Side effects:
      - 无
    """
    if not original or not modified:
        return 1.0

    # 简单实现：基于 hash 的行级比较
    orig_lines = set(line.strip() for line in original.split("\n") if line.strip())
    mod_lines = set(line.strip() for line in modified.split("\n") if line.strip())

    if not orig_lines:
        return 1.0

    # 差异 = 不在原文中的行数 / 总行数
    new_lines = mod_lines - orig_lines
    return min(1.0, len(new_lines) / max(len(orig_lines), 1))
