"""评论挖掘→选题服务 — cheat-retro 的评论分析增强

分析爆款视频的评论，挖掘新的选题方向。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.services.llm import call_llm_json

logger = structlog.get_logger()


async def analyze_comments(
    data_dir: Path,
    video_id: str,
    comments: list[str],
    platform: str = "douyin",
) -> dict[str, Any]:
    """分析评论 → 挖掘选题方向

    Pre-conditions:
      - comments 至少 3 条
    Post-conditions:
      - 返回聚类结果 + 选题建议
    Side effects:
      - LLM 调用 (tag="comment_analyze")
      - 写入 candidates.md
    """
    logger.info("comment_analyze_start", video_id=video_id, count=len(comments))

    comments_text = "\n".join(f"- {c}" for c in comments[:50])  # 最多 50 条

    prompt = f"""分析以下来自 {platform} 视频（ID: {video_id}）的评论，挖掘选题方向。

评论内容:
{comments_text}

请完成以下分析：

1. 将评论按主题聚类（3-5 个簇）
2. 每个簇提炼出一个选题方向
3. 评估每个选题的潜力

返回 JSON：
```json
{{
  "clusters": [
    {{
      "theme": "评论主题",
      "representative_comments": ["代表性评论1", "代表性评论2"],
      "topic_suggestion": "建议选题",
      "potential": "high/medium/low",
      "reasoning": "为什么这个选题有潜力"
    }}
  ],
  "audience_insight": "受众洞察总结",
  "content_gap": "当前内容未覆盖但受众关心的点"
}}
```"""

    result = await call_llm_json(prompt, tag="comment_analyze", temperature=0.3)

    # 将选题写入 candidates.md
    clusters = result.get("clusters", [])
    if clusters:
        await _write_to_candidates(data_dir, video_id, clusters)

    logger.info("comment_analyze_complete", video_id=video_id, clusters=len(clusters))
    return {
        "video_id": video_id,
        "platform": platform,
        "clusters": clusters,
        "audience_insight": result.get("audience_insight", ""),
        "content_gap": result.get("content_gap", ""),
    }


async def recommend_candidates(data_dir: Path, limit: int = 5) -> dict[str, Any]:
    """推荐选题

    Pre-conditions:
      - candidates.md 存在
    Post-conditions:
      - 返回按优先级排序的选题推荐
    Side effects:
      - 无
    """
    from backend.app.services.file_io import read_file

    candidates_path = data_dir / "candidates.md"
    if not candidates_path.exists():
        return {"candidates": [], "message": "选题池为空，请先分析评论或导入热点"}

    content = read_file(candidates_path)

    prompt = f"""基于以下选题池内容，推荐 {limit} 个最值得写的选题。

选题池:
{content[:3000]}

返回 JSON：
```json
{{
  "recommendations": [
    {{
      "topic": "选题标题",
      "source": "来源（评论分析/热点/手动）",
      "priority": "high/medium/low",
      "reasoning": "推荐理由",
      "suggested_angle": "建议切入角度"
    }}
  ]
}}
```"""

    result = await call_llm_json(prompt, tag="candidate_recommend", temperature=0.3)
    return {"candidates": result.get("recommendations", [])}


async def _write_to_candidates(
    data_dir: Path,
    video_id: str,
    clusters: list[dict[str, Any]],
) -> None:
    """将分析结果追加到 candidates.md

    Pre-conditions:
      - data_dir 存在
    Post-conditions:
      - candidates.md 被追加新选题
    Side effects:
      - 写文件系统
    """
    from backend.app.services.file_io import read_file, safe_write

    candidates_path = data_dir / "candidates.md"
    existing = read_file(candidates_path) if candidates_path.exists() else "# 选题池\n"

    new_entries = []
    for cluster in clusters:
        potential = cluster.get("potential", "medium")
        tier = "Tier 1" if potential == "high" else "Tier 2" if potential == "medium" else "Tier 3"
        topic = cluster.get("topic_suggestion", "未命名选题")
        reason = cluster.get("reasoning", "")
        new_entries.append(f"- [{tier}] **{topic}** — 来源: 评论分析({video_id}) — {reason}")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    append_text = f"\n## {timestamp} 评论分析 ({video_id})\n\n" + "\n".join(new_entries) + "\n"
    safe_write(candidates_path, existing + append_text)
