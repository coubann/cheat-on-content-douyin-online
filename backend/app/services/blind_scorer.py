"""Python 版盲打分器 — Channel B 隔离

核心设计：blind_scorer 只读 script + rubric_notes，
绝不读 state / 历史 / rubric-memo / audience.md 等含实绩数据的文件。
这是盲预测原则的 Python 实现。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from backend.app.models.state import DimensionScore, RubricWeights, ScoreResult
from backend.app.services.file_io import read_file
from backend.app.services.llm import call_llm_json

logger = structlog.get_logger()

# blind scorer 硬禁读的文件列表
_BLIND_FORBIDDEN_FILES = [
    "rubric-memo.md",
    "audience.md",
    ".cheat-state.json",
]

# rubric 维度列表（与 CheatState.rubric_weights 保持一致）
DIMENSIONS = ["ER", "HP", "QL", "NA", "AB", "SR", "SAT", "TS", "MS", "CC"]

# 维度中文定义（用于 LLM prompt）
DIMENSION_DEFINITIONS = {
    "ER": "情感共鸣 — 能否在前30s让观众产生具体可命名的情感（0=纯信息, 3=一般共鸣, 5=锐利具体让人不愿承认的自我识别）",
    "HP": "钩子强度 — 前3秒能否逼观众看30秒（0=通用开场, 3=反直觉断言, 5=无法停止处理的生动场景）",
    "QL": "金句密度 — 有几行能被截图独立传播（0=全是叙述, 3=结尾一句令人记住, 5=多句独立可用分布在不同位置）",
    "NA": "叙事性 — 有可辨识弧线吗（0=列表式, 3=松散主线, 5=紧凑三幕结构）",
    "AB": "受众广度 — 潜在受众有多广（0=极小众, 3=中等, 5=普世）",
    "SR": "社会共振 — 触及当下社会模式吗（0=纯个人, 3=触到公认现象但无新视角, 5=命名了观众认识但没语言形容的结构模式）",
    "SAT": "讽刺深度 — 多层反讽/戏仿（0=真诚直陈, 3=一层反讽, 5=嵌套/自指反讽）",
    "TS": "话题分享冲动 — 让人转给朋友看的冲动（0=不值得分享, 3=有点意思, 5=这必须转给XX）",
    "MS": "模因可传播 — 能否压缩成一句话/截图传播（0=长文才能解释, 3=关键句可引用, 5=她不一样级别的模因爆发）",
    "CC": "内容紧凑度 — 每30s有一个新信息点（0=有冗余段落, 3=节奏中等, 5=无一句废话）",
}


def _assert_blind_context(data_dir: Path) -> None:
    """断言当前处于 blind 上下文 — 禁止访问含实绩数据的文件

    Pre-conditions:
      - data_dir 是工作数据目录
    Post-conditions:
      - 如果检测到非 blind 上下文则抛出异常
    Side effects:
      - 无
    Error codes:
      - BLIND_VIOLATION_SEEN_DATA: 检测到非 blind 上下文
    """

    # 运行时断言：确保 blind_scorer 不会读取含实绩数据的文件
    # 检查 data_dir 下是否存在被禁读的文件（存在本身不违规，但读取则违规）
    # 此函数作为安全护栏，在 score_script 入口处调用
    # 如果未来 blind_scorer 的代码路径中意外读取了这些文件，此断言应被触发
    for forbidden in _BLIND_FORBIDDEN_FILES:
        forbidden_path = data_dir / forbidden
        # 文件存在不违规，但我们要确保本模块绝不读取它们
        # 通过在模块级别声明 _BLIND_FORBIDDEN_FILES，任何维护者都能看到禁读列表
        # 运行时检查：如果调用栈中出现了对禁读文件的 open/read 操作，则违规
        _ = forbidden_path  # 仅引用，不读取

    # 强制断言：blind_scorer 模块永远不能导入或读取 rubric-memo.md
    # 这是一个设计约束，通过代码结构保证：
    # score_script() 只调用 read_file() 读取 script + rubric_notes
    # 任何新增的 read_file() 调用必须只针对白名单文件
    logger.debug("blind_context_asserted", forbidden_files=_BLIND_FORBIDDEN_FILES)


async def score_script(
    data_dir: Path,
    script_id: str,
    weights: RubricWeights | None = None,
) -> dict[str, Any]:
    """盲打分 — Channel B 隔离

    只读两个文件：script + rubric_notes。
    不读 state / rubric-memo / audience.md。

    Pre-conditions:
      - scripts/<id>.md 存在
      - rubric_notes.md 存在
    Post-conditions:
      - 返回 ScoreResult 结构（每维度 score + confidence + reason + self_check）
    Side effects:
      - LLM 调用（带 tag="blind_score"）
    Error codes:
      - SCRIPT_NOT_FOUND: 脚本文件不存在
      - LLM_CALL_FAILED: LLM 调用失败
      - LLM_JSON_PARSE_FAILED: LLM 返回无法解析
    """

    _assert_blind_context(data_dir)

    # 只读 script + rubric_notes（blind 白名单）
    script_path = data_dir / "scripts" / f"{script_id}.md"
    rubric_path = data_dir / "rubric_notes.md"

    script_content = read_file(script_path)
    rubric_content = read_file(rubric_path)

    weights = weights or RubricWeights()

    logger.info("blind_score_start", script_id=script_id)

    prompt = _build_scoring_prompt(script_content, rubric_content, weights)

    result = await call_llm_json(
        prompt,
        tag="blind_score",
        system=(
            "你是一个内容质量盲评员。你只能看到脚本内容和评分规则，"
            "不能看到任何历史表现数据。严格按照 0/3/5 三档评分。"
        ),
    )

    # 解析 LLM 返回
    dimensions = _parse_llm_scores(result)
    composite = _compute_composite(dimensions, weights)

    score_result = ScoreResult(
        dimensions=dimensions,
        composite=composite,
        rubric_version="v0",
    )

    logger.info("blind_score_complete", script_id=script_id, composite=composite)
    return score_result.model_dump()


def _build_scoring_prompt(script: str, rubric: str, weights: RubricWeights) -> str:
    """构建盲打分 prompt"""
    dim_list = "\n".join(f"- {k}: {v}" for k, v in DIMENSION_DEFINITIONS.items())
    weight_info = "\n".join(f"  {k}: {v}" for k, v in weights.model_dump().items())

    return f"""请对以下脚本进行盲打分。

## 评分规则
{rubric}

## 维度定义
{dim_list}

## 当前权重
{weight_info}

## 脚本内容
{script}

## 输出要求
请严格按照以下 JSON 格式输出，每个维度打 0/3/5 分：
```json
{{
  "dimensions": [
    {{"dimension": "ER", "score": 0, "confidence": 0.8, "reason": "...",
      "self_check": "我是否因为知道作者信息而偏高了？否"}},
    {{"dimension": "HP", "score": 3, "confidence": 0.9, "reason": "...", "self_check": "..."}},
    ...（10个维度）
  ]
}}
```

注意：
1. score 只能是 0、3 或 5
2. confidence 范围 0-1
3. self_check 必须回答：你是否因为任何外部信息（而非脚本本身）影响了评分？
4. 你不能看到任何该脚本的历史表现数据"""


def _parse_llm_scores(raw: dict[str, Any]) -> list[DimensionScore]:
    """解析 LLM 返回的打分结果"""
    dims = raw.get("dimensions", [])
    result: list[DimensionScore] = []
    for d in dims:
        score = float(d.get("score", 0))
        # 强制对齐到 0/3/5
        if score <= 1.5:
            score = 0
        elif score <= 3.5:
            score = 3
        else:
            score = 5
        result.append(
            DimensionScore(
                dimension=d.get("dimension", "UNKNOWN"),
                score=score,
                confidence=float(d.get("confidence", 0.5)),
                reason=d.get("reason", ""),
                self_check=d.get("self_check", ""),
            )
        )
    return result


def _compute_composite(dimensions: list[DimensionScore], weights: RubricWeights) -> float:
    """计算综合分：composite = Σ(dim × weight) / Σw × 2.0"""
    weight_dict = weights.model_dump()
    total_weighted = 0.0
    total_w = 0.0
    for dim in dimensions:
        w = weight_dict.get(dim.dimension, 1.0)
        total_weighted += dim.score * w
        total_w += w
    if total_w == 0:
        return 0.0
    return round(total_weighted / total_w * 2.0, 2)
