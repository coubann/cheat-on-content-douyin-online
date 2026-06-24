"""发布时间优化服务

基于历史数据 + 平台特征 + 热点周期，推荐最佳发布时间。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.models.state import CheatState
from backend.app.services.file_io import read_file
from backend.app.services.llm import call_llm_json

logger = structlog.get_logger()


async def suggest_publish_time(
    data_dir: Path,
    script_id: str | None = None,
    platform: str = "douyin",
) -> dict[str, Any]:
    """推荐最佳发布时间

    Pre-conditions:
      - .cheat-state.json 存在
    Post-conditions:
      - 返回推荐发布时间 + 原因
    Side effects:
      - LLM 调用 (tag="publish_time")
    """
    # 1. 收集历史发布时间数据（从 retro 文件中提取）
    historical_data = _collect_historical_timing(data_dir)

    # 2. 读取平台和内容形态
    state_path = data_dir / ".cheat-state.json"
    state = CheatState.model_validate_json(read_file(state_path))

    # 3. LLM 分析推荐
    prompt = f"""基于以下信息，推荐最佳发布时间。

## 平台: {platform}
## 内容形态: {state.content_form}
## 目标发布节奏: 每{state.target_publish_cadence_days}天一篇

## 历史发布数据
{historical_data or "暂无历史数据"}

## 当前时间
{datetime.now().strftime('%Y-%m-%d %H:%M')} ({'周' + ['一','二','三','四','五','六','日'][datetime.now().weekday()]})

## 任务
1. 推荐今天/明天的最佳发布时间段（精确到小时）
2. 推荐本周最佳发布日
3. 说明推荐原因

返回 JSON：
```json
{{
  "recommended_today": {{
    "time_slots": ["18:00-19:00", "21:00-22:00"],
    "reason": "..."
  }},
  "recommended_this_week": {{
    "best_days": ["周三", "周五"],
    "time_slots": ["18:00-20:00"],
    "reason": "..."
  }},
  "platform_tips": ["平台特定建议1", "平台特定建议2"],
  "avoid_times": ["13:00-14:00 (午休低谷)"],
  "confidence": "high/medium/low"
}}
```"""

    result = await call_llm_json(prompt, tag="publish_time", temperature=0.3)

    return {
        "platform": platform,
        "script_id": script_id,
        "recommendation": result,
        "historical_samples": len(historical_data.split("\n")) if historical_data else 0,
        "generated_at": datetime.now().isoformat(),
    }


def _collect_historical_timing(data_dir: Path) -> str:
    """从复盘文件中收集历史发布时间数据

    Pre-conditions:
      - data_dir/predictions 目录可能存在
    Post-conditions:
      - 返回历史发布时间文本（最多 20 条）
    Side effects:
      - 无
    """
    preds_dir = data_dir / "predictions"
    if not preds_dir.exists():
        return ""

    lines: list[str] = []
    for f in sorted(preds_dir.glob("*.md")):
        content = read_file(f)
        if "## 复盘" not in content:
            continue

        # 提取预测时间和复盘时间
        pred_time = ""
        retro_time = ""
        actual_plays = ""

        for line in content.split("\n"):
            if "预测时间:" in line:
                pred_time = line.split(":", 1)[1].strip()[:10]
            elif "复盘时间:" in line:
                retro_time = line.split(":", 1)[1].strip()[:10]
            elif "播放量:" in line:
                m = re.search(r"(\d+)", line)
                actual_plays = m.group(1) if m else ""

        if pred_time:
            lines.append(f"- 预测:{pred_time} 复盘:{retro_time or 'N/A'} 播放:{actual_plays or 'N/A'}")

    return "\n".join(lines[:20])
