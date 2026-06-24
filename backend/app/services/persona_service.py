"""受众画像服务 — cheat-persona 的 Python 实现

从复盘评论数据聚类 → 派生受众画像（谁在看、为什么点赞、为什么转发）
blind scorer 硬禁读 audience.md（含实绩信号）
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.services.file_io import read_file, safe_write
from backend.app.services.llm import call_llm_json

logger = structlog.get_logger()


async def build_persona(data_dir: Path) -> dict[str, Any]:
    """从已复盘数据构建受众画像

    Pre-conditions:
      - 至少有 1 篇已复盘的预测（含评论数据）
    Post-conditions:
      - audience.md 被创建/更新（blind scorer 硬禁读此文件）
      - 返回受众画像结构
    Side effects:
      - LLM 调用 (tag="persona_build")
      - 写文件系统
    Error codes:
      - LLM_CALL_FAILED
      - LLM_JSON_PARSE_FAILED
    """
    logger.info("persona_build_start")

    # 收集所有评论数据
    comments_data = _collect_comments(data_dir)
    if not comments_data:
        return {"status": "no_data", "message": "尚无评论数据，无法构建画像"}

    # LLM 分析受众画像
    persona = await _analyze_audience(comments_data)

    # 写入 audience.md
    _save_persona(data_dir, persona)

    logger.info("persona_build_complete", persona_name=persona.get("name", "unknown"))
    return {"status": "ok", "persona": persona}


async def update_persona(data_dir: Path, updates: dict[str, Any]) -> dict[str, Any]:
    """更新受众画像

    Pre-conditions:
      - audience.md 存在
    Post-conditions:
      - audience.md 被更新
      - 返回更新后的画像
    Side effects:
      - LLM 调用 (tag="persona_update")
      - 写文件系统
    """
    persona_path = data_dir / "audience.md"
    if not persona_path.exists():
        return {"status": "not_found", "message": "受众画像不存在，请先构建"}

    existing = read_file(persona_path)

    # LLM 合并更新
    prompt = f"""基于新信息更新受众画像。

## 当前画像
{existing[:2000]}

## 新信息
{json.dumps(updates, ensure_ascii=False, indent=2)}

返回 JSON：
```json
{{
  "name": "受众名称",
  "demographics": {{"age_range": "25-35", "occupation": "白领", "region": "一二线城市"}},
  "interests": ["兴趣1", "兴趣2"],
  "engagement_patterns": {{
    "why_like": "点赞原因",
    "why_share": "转发原因",
    "why_comment": "评论原因"
  }},
  "content_preferences": ["偏好1", "偏好2"],
  "updated_at": "{datetime.now().isoformat()}"
}}
```"""

    result = await call_llm_json(prompt, tag="persona_update", temperature=0.3)

    _save_persona(data_dir, result)
    return {"status": "ok", "persona": result}


def get_persona(data_dir: Path) -> dict[str, Any] | None:
    """读取受众画像

    Pre-conditions:
      - audience.md 存在
    Post-conditions:
      - 返回画像数据或 None
    Side effects:
      - 无

    注意：此函数不应被 blind_scorer 调用。
    """
    persona_path = data_dir / "audience.md"
    if not persona_path.exists():
        return None

    content = read_file(persona_path)
    # 从 markdown 中提取 JSON 块
    import re
    json_match = re.search(r"```json\n(.+?)\n```", content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    return {"raw": content}


def _collect_comments(data_dir: Path) -> list[str]:
    """从已复盘的预测文件中收集评论数据

    Pre-conditions:
      - predictions/ 目录存在
    Post-conditions:
      - 返回评论列表
    Side effects:
      - 无
    """
    preds_dir = data_dir / "predictions"
    if not preds_dir.exists():
        return []

    comments: list[str] = []
    for f in sorted(preds_dir.glob("*.md")):
        content = read_file(f)
        if "## 复盘" not in content:
            continue

        # 提取评论关键词/内容
        import re
        comment_matches = re.findall(r"评论[：:]\s*(.+)", content)
        comments.extend(comment_matches)

        # 提取 Top 评论
        top_comment_matches = re.findall(r"Top\s*评论[：:]\s*(.+)", content)
        comments.extend(top_comment_matches)

    return comments


async def _analyze_audience(comments_data: list[str]) -> dict[str, Any]:
    """LLM 分析受众画像

    Pre-conditions:
      - comments_data 非空
    Post-conditions:
      - 返回受众画像结构
    Side effects:
      - LLM 调用 (tag="persona_build")
    """
    comments_text = "\n".join(f"- {c}" for c in comments_data[:30])

    prompt = f"""基于以下评论数据，分析受众画像。

## 评论数据
{comments_text}

请分析：
1. 这些评论者是谁？（年龄/职业/地域）
2. 他们为什么点赞？（情感共鸣点）
3. 他们为什么转发？（社交动机）
4. 他们偏好什么类型的内容？

返回 JSON：
```json
{{
  "name": "受众名称（如'焦虑的职场新人'）",
  "demographics": {{
    "age_range": "25-35",
    "occupation": "白领/学生/自由职业",
    "region": "一二线城市/下沉市场"
  }},
  "interests": ["兴趣1", "兴趣2", "兴趣3"],
  "engagement_patterns": {{
    "why_like": "点赞的核心原因",
    "why_share": "转发的核心动机",
    "why_comment": "评论的核心驱动力"
  }},
  "content_preferences": ["偏好1", "偏好2", "偏好3"],
  "created_at": "{datetime.now().isoformat()}"
}}
```"""

    result = await call_llm_json(prompt, tag="persona_build", temperature=0.3)
    return result


def _save_persona(data_dir: Path, persona: dict[str, Any]) -> None:
    """保存受众画像到 audience.md

    Pre-conditions:
      - persona 非空
    Post-conditions:
      - audience.md 被写入
    Side effects:
      - 写文件系统

    注意：此文件包含实绩信号，blind scorer 硬禁读。
    """
    persona_path = data_dir / "audience.md"

    md_content = f"""# 受众画像

> 此文件包含实绩信号，blind scorer 硬禁读此文件。
> 更新时间: {persona.get('updated_at', persona.get('created_at', datetime.now().isoformat()))}

## 基本信息

- 名称: {persona.get('name', '未知')}
- 年龄段: {persona.get('demographics', {}).get('age_range', '未知')}
- 职业: {persona.get('demographics', {}).get('occupation', '未知')}
- 地域: {persona.get('demographics', {}).get('region', '未知')}

## 兴趣标签

{chr(10).join(f'- {i}' for i in persona.get('interests', [])) or '- 暂无'}

## 互动模式

- **点赞原因**: {persona.get('engagement_patterns', {}).get('why_like', '未知')}
- **转发动机**: {persona.get('engagement_patterns', {}).get('why_share', '未知')}
- **评论驱动力**: {persona.get('engagement_patterns', {}).get('why_comment', '未知')}

## 内容偏好

{chr(10).join(f'- {p}' for p in persona.get('content_preferences', [])) or '- 暂无'}

## 原始数据

```json
{json.dumps(persona, ensure_ascii=False, indent=2)}
```
"""
    safe_write(persona_path, md_content)
