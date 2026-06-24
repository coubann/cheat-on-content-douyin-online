"""项目初始化服务 — cheat-init 的 Python 实现

对应 cheat-on-content 的 cheat-init skill：
问 6 个问题 + 创建脚手架文件。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.models.state import CheatState, RubricWeights
from backend.app.services.file_io import safe_write

logger = structlog.get_logger()


async def initialize_project(data_dir: Path, answers: dict[str, Any]) -> dict[str, Any]:
    """初始化项目 — 创建所有脚手架文件

    对应 cheat-init 的 6 个问题：
    1. 内容形态（content_form）
    2. 是否发过内容（has_published）
    3. 数据回收方式（data_collection_method）
    4. 选题池状态（topic_pool_status）
    5. 是否安装 hook（install_hooks）
    6. 对标账号（benchmark_accounts）

    Pre-conditions:
      - data_dir 存在
      - data_dir 未初始化（.cheat-state.json 不存在）
    Post-conditions:
      - .cheat-state.json 被创建
      - rubric_notes.md / rubric-memo.md / script_patterns.md 被创建
      - scripts/ predictions/ videos/ samples/ 目录被创建
      - candidates.md 被创建
    Side effects:
      - 写文件系统
    Error codes:
      - INIT_ALREADY_INITIALIZED: 项目已初始化
    """
    state_path = data_dir / ".cheat-state.json"

    if state_path.exists():
        logger.warning("init_already_exists", path=str(state_path))
        return {"status": "already_initialized", "message": "项目已初始化，如需重新初始化请先删除 .cheat-state.json"}

    # 创建目录
    for subdir in ["scripts", "predictions", "videos", "samples"]:
        (data_dir / subdir).mkdir(parents=True, exist_ok=True)

    # 构建 state
    platforms = answers.get("platforms", ["douyin"])
    content_form = answers.get("content_form", "opinion-video")
    cadence_days = answers.get("target_publish_cadence_days", 2)
    duration = answers.get("typical_duration_seconds", 240)

    state = CheatState(
        content_form=content_form,
        platforms=platforms if isinstance(platforms, list) else [platforms],
        target_publish_cadence_days=cadence_days,
        typical_duration_seconds=duration,
        hooks_installed=answers.get("install_hooks", False),
        initialized_at=datetime.now(),
    )

    # 写 .cheat-state.json
    safe_write(state_path, state.model_dump_json(indent=2))

    # 写 rubric_notes.md（blind 白名单 — 只含通用语言，禁真实数据）
    rubric_notes = _build_rubric_notes(state.rubric_weights, content_form)
    safe_write(data_dir / "rubric_notes.md", rubric_notes)

    # 写 rubric-memo.md（复盘备忘录 — 含实绩，blind scorer 硬禁读）
    rubric_memo = (
        "# Rubric Memo（复盘备忘录）\n\n"
        "> 此文件包含真实数据和实绩信息。blind scorer 硬禁读此文件。\n\n"
        "## 校准样本\n\n（暂无）\n"
    )
    safe_write(data_dir / "rubric-memo.md", rubric_memo)

    # 写 script_patterns.md
    script_patterns = "# 写作模式库\n\n> 记录从复盘中提炼的写作 pattern。\n\n（暂无）\n"
    safe_write(data_dir / "script_patterns.md", script_patterns)

    # 写 candidates.md
    candidates = "# 选题池\n\n## Tier 1（高 composite + 高信心）\n\n## Tier 2（中等）\n\n## Tier 3（实验性）\n"
    safe_write(data_dir / "candidates.md", candidates)

    logger.info("init_complete", platforms=platforms, content_form=content_form)
    return {"status": "initialized", "state": state.model_dump()}


def _build_rubric_notes(weights: RubricWeights, content_form: str) -> str:
    """构建 rubric_notes.md — blind 白名单

    只含：公式、维度定义、bucket 边界、抽象规则。
    禁含：真实视频名、播放数、评论内容、链接。
    """
    weight_lines = "\n".join(f"| {k} | {v} |" for k, v in weights.model_dump().items())

    return f"""# Rubric Notes（评分规则 — blind 白名单）

> 此文件是 blind scorer 唯一可读的评分规则文件。
> **禁止写入任何真实数据**（视频名、播放数、评论等）。这些内容写 rubric-memo.md。

## 内容形态
{content_form}

## 综合分公式
composite = Σ(dim × weight) / Σw × 2.0（0-5 分 → 0-10 composite）

## 维度权重
| 维度 | 权重 |
|---|---|
{weight_lines}

## 维度定义
| 维度 | 0 分 | 3 分 | 5 分 |
|---|---|---|---|
| ER 情感共鸣 | 纯信息 | 一般共鸣 | 锐利、具体、让人不愿承认的自我识别 |
| HP 钩子强度 | 通用开场 | 反直觉断言 | 无法停止处理的生动场景 |
| QL 金句密度 | 全是叙述 | 结尾一句令人记住 | 多句独立可用、分布在不同位置 |
| NA 叙事性 | 列表式 | 松散主线 | 紧凑三幕结构 |
| AB 受众广度 | 极小众 | 中等 | 普世 |
| SR 社会共振 | 纯个人/人际 | 触到公认现象但无新视角 | 命名了观众认识但没语言形容的结构模式 |
| SAT 讽刺深度 | 真诚直陈 | 一层反讽 | 嵌套/自指反讽 |
| TS 话题分享冲动 | 不值得分享 | "有点意思" | "这必须转给 XX" |
| MS 模因可传播 | 长文才能解释 | 关键句可引用 | "她不一样"级别的模因爆发 |
| CC 内容紧凑度 | 有冗余段落 | 节奏中等 | 无一句废话 |

## Bucket 方案
| 样本数 | 方案 | 说明 |
|---|---|---|
| 0-4 | ratio 桶 | 相对上一篇的倍数 |
| 5-9 | absolute 桶 | 校准池中位数 × {{0.3, 1, 3, 10, 30}} |
| ≥10 | percentile 桶 | 校准池实绩的 p30/p60/p85/p95 |

## 观察区
> 被数据推翻或被吸收为正式维度的观察要删除。git history 才是档案。

（暂无观察）
"""
