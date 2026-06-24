"""智能选题推荐服务 — cheat-seed 的 Python 实现

融合多源信号（评论挖掘 + 热点匹配 + 对标分析 + 受众画像），
给出综合选题推荐，解决冷启动问题。
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


async def recommend_topics(
    data_dir: Path,
    count: int = 5,
    strategy: str = "balanced",
) -> dict[str, Any]:
    """智能选题推荐 — 融合多源信号

    Pre-conditions:
      - 项目已初始化（.cheat-state.json 存在）
    Post-conditions:
      - 返回推荐选题列表
      - 推荐结果追加到 candidates.md
    Side effects:
      - LLM 调用 (tag="seed_recommend")
      - 写文件系统
    Error codes:
      - LLM_CALL_FAILED
      - LLM_JSON_PARSE_FAILED
    """
    logger.info("seed_recommend_start", count=count, strategy=strategy)

    # 收集多源信号
    signals = await _collect_signals(data_dir)

    # LLM 综合推荐
    recommendations = await _generate_recommendations(signals, count, strategy)

    # 写入 candidates.md
    _append_to_candidates(data_dir, recommendations)

    logger.info("seed_recommend_complete", count=len(recommendations.get("topics", [])))
    return {"status": "ok", "recommendations": recommendations, "signals_used": list(signals.keys())}


async def _collect_signals(data_dir: Path) -> dict[str, Any]:
    """收集多源信号

    Pre-conditions:
      - data_dir 存在
    Post-conditions:
      - 返回信号字典
    Side effects:
      - 可能的 LLM 调用（trends、candidates）
    """
    signals: dict[str, Any] = {}

    # 1. 热点信号
    try:
        from backend.app.services.trends_service import fetch_trends
        trends = await fetch_trends()
        if trends:
            signals["trends"] = trends[:5]
    except Exception as e:
        logger.warning("seed_trends_failed", error=str(e))

    # 2. 评论选题信号
    try:
        candidates_path = data_dir / "candidates.md"
        if candidates_path.exists():
            candidates_content = read_file(candidates_path)
            signals["existing_candidates"] = candidates_content[:1000]
    except Exception:
        pass

    # 3. 对标信号
    try:
        benchmarks_dir = data_dir / "benchmarks"
        if benchmarks_dir.exists():
            benchmark_files = list(benchmarks_dir.glob("*.md"))
            if benchmark_files:
                # 读取第一个对标的摘要
                first_benchmark = read_file(benchmark_files[0])[:500]
                signals["benchmark"] = first_benchmark
    except Exception:
        pass

    # 4. 受众画像信号
    try:
        from backend.app.services.persona_service import get_persona
        persona = get_persona(data_dir)
        if persona:
            signals["persona"] = persona
    except Exception:
        pass

    # 5. 历史表现信号
    try:
        state_path = data_dir / ".cheat-state.json"
        if state_path.exists():
            from backend.app.models.state import CheatState
            state = CheatState.model_validate_json(read_file(state_path))
            signals["calibration_samples"] = state.calibration_samples
            signals["content_form"] = state.content_form
            signals["platforms"] = state.platforms
    except Exception:
        pass

    return signals


async def _generate_recommendations(
    signals: dict[str, Any],
    count: int,
    strategy: str,
) -> dict[str, Any]:
    """LLM 综合推荐

    Pre-conditions:
      - signals 非空
    Post-conditions:
      - 返回推荐结果
    Side effects:
      - LLM 调用 (tag="seed_recommend")
    """
    signals_text = json.dumps(signals, ensure_ascii=False, indent=2, default=str)[:3000]

    strategy_desc = {
        "balanced": "平衡策略：60%稳妥选题 + 40%实验选题",
        "safe": "稳妥策略：只推高信心选题（基于已有数据和热点）",
        "experimental": "实验策略：80%创新选题，探索新方向",
    }.get(strategy, "平衡策略")

    prompt = f"""基于以下多源信号，推荐 {count} 个选题。

## 多源信号
{signals_text}

## 推荐策略
{strategy_desc}

## 要求
1. 每个选题包含：标题、核心观点、预估维度分、推荐理由
2. 选题应覆盖不同角度（情感/争议/实用/娱乐）
3. 考虑当前热点与账号垂直度的匹配度
4. 冷启动期（<5篇）优先选择"容易出数据"的选题

返回 JSON：
```json
{{
  "topics": [
    {{
      "title": "选题标题",
      "core_angle": "核心观点/角度",
      "estimated_dimensions": {{"HP": 5, "ER": 3, "TS": 4}},
      "estimated_composite": 7.2,
      "tier": 1,
      "reason": "推荐理由",
      "hook_suggestion": "开头钩子建议",
      "risk": "潜在风险"
    }}
  ],
  "strategy_used": "{strategy}",
  "cold_start_tips": ["冷启动建议1", "冷启动建议2"]
}}
```"""

    result = await call_llm_json(prompt, tag="seed_recommend", temperature=0.4)
    return result


def _append_to_candidates(data_dir: Path, recommendations: dict[str, Any]) -> None:
    """将推荐选题追加到 candidates.md

    Pre-conditions:
      - recommendations 非空
    Post-conditions:
      - candidates.md 被追加
    Side effects:
      - 写文件系统
    """

    candidates_path = data_dir / "candidates.md"
    if not candidates_path.exists():
        return

    existing = read_file(candidates_path)
    topics = recommendations.get("topics", [])

    new_entries = []
    for t in topics:
        tier = t.get("tier", 2)
        title = t.get("title", "未命名")
        composite = t.get("estimated_composite", 0)
        new_entries.append(
            f"- [ ] {datetime.now().strftime('%Y-%m-%d')}_{title} "
            f"— est_composite {composite}, tier{tier}"
        )

    if new_entries:
        section = f"\n\n## 智能推荐 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"
        section += "\n".join(new_entries)
        safe_write(candidates_path, existing + section)
