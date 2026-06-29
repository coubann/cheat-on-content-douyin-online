"""bump 服务 — cheat-bump 的 Python 实现

rubric 升级 5 步流程：
1. 收集校准池（所有已复盘的样本）
2. LLM 提议新权重 + rubric_notes 修订
3. blind sub-agent 全量重打分校准池
4. 排序一致性审计（≥ 0.8 才通过）
5. 写入新 rubric + 更新 state

跨模型审计：如果排序一致性 < 0.8（4/5 样本），升级被拒。

用户数据隔离：predictions 路径使用 data/{user_id}/predictions/
rubric_notes.md 和 rubric-memo.md 保留在根目录（系统级）。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.errors import BUMP_INSUFFICIENT_SAMPLES, RUBRIC_LEAK_DETECTED
from backend.app.models.state import CheatState, RubricWeights
from backend.app.services.blind_scorer import DIMENSIONS, score_script
from backend.app.services.file_io import read_file, safe_write
from backend.app.services.leak_guard import check_rubric_leak
from backend.app.services.llm import call_llm_json

logger = structlog.get_logger()

# 排序一致性阈值
_CONSISTENCY_THRESHOLD = 0.8


async def execute_bump(
    data_dir: Path,
    user_id: int = 0,
    force: bool = False,
) -> dict[str, Any]:
    """执行 rubric bump — 5 步升级流程

    Pre-conditions:
      - state.calibration_samples >= 5（或 force=True）
      - 至少有 3 篇已复盘的样本
    Post-conditions:
      - rubric_notes.md 被更新（通过 leak guard）
      - rubric-memo.md 追加 bump 记录
      - .cheat-state.json 的 rubric_weights 和 rubric_version 被更新
      - 返回 bump 结果（新旧权重对比 + 一致性分数）
    Side effects:
      - 多次 LLM 调用（提议 + 全量重打分）
      - 写文件系统
    Error codes:
      - BUMP_INSUFFICIENT_SAMPLES: 校准样本不足
      - RUBRIC_LEAK_DETECTED: 新 rubric 包含真实数据
      - LLM_CALL_FAILED
      - LLM_JSON_PARSE_FAILED
    """
    logger.info("bump_start", user_id=user_id)

    # 0. 加载 state
    state_path = data_dir / ".cheat-state.json"
    state = CheatState.model_validate_json(read_file(state_path))

    # 1. 收集校准池
    calibration_pool = _collect_calibration_pool(data_dir, user_id=user_id)
    if len(calibration_pool) < 3 and not force:
        raise BumpError(
            BUMP_INSUFFICIENT_SAMPLES,
            f"校准池仅 {len(calibration_pool)} 篇，至少需要 3 篇已复盘样本才能 bump",
        )

    if len(calibration_pool) == 0:
        raise BumpError(
            BUMP_INSUFFICIENT_SAMPLES,
            "校准池为空，无法执行 bump",
        )

    logger.info("bump_pool_collected", pool_size=len(calibration_pool), user_id=user_id)

    # 2. LLM 提议新权重 + rubric_notes 修订
    old_weights = state.rubric_weights
    proposal = await _propose_new_weights(data_dir, calibration_pool, old_weights)
    new_weights = _parse_weights(proposal.get("new_weights", {}))
    rubric_diff = proposal.get("rubric_diff", "")

    logger.info(
        "bump_proposal",
        new_weights=new_weights.model_dump(),
        rubric_diff_summary=rubric_diff[:100] if rubric_diff else "",
    )

    # 3. blind sub-agent 全量重打分校准池
    old_rankings = _compute_rankings(calibration_pool, "old_composite")
    new_scores = await _rescore_pool(data_dir, calibration_pool, new_weights)
    new_rankings = _compute_rankings(new_scores, "new_composite")

    # 4. 排序一致性审计
    consistency = _compute_ranking_consistency(old_rankings, new_rankings)
    passed = consistency >= _CONSISTENCY_THRESHOLD

    logger.info(
        "bump_audit",
        consistency=consistency,
        passed=passed,
        threshold=_CONSISTENCY_THRESHOLD,
    )

    if not passed:
        return {
            "status": "rejected",
            "reason": f"排序一致性 {consistency:.2f} < {_CONSISTENCY_THRESHOLD}，升级被拒",
            "consistency": consistency,
            "old_weights": old_weights.model_dump(),
            "proposed_weights": new_weights.model_dump(),
            "old_rankings": old_rankings,
            "new_rankings": new_rankings,
        }

    # 5. 写入新 rubric + 更新 state
    # 5a. 更新 rubric_notes.md（如果 LLM 提议了修订）
    if rubric_diff:
        rubric_path = data_dir / "rubric_notes.md"
        existing_rubric = read_file(rubric_path)
        new_rubric = existing_rubric + "\n\n" + rubric_diff

        # leak guard 检查
        try:
            check_rubric_leak(new_rubric)
        except Exception as e:
            raise BumpError(
                RUBRIC_LEAK_DETECTED,
                f"新 rubric 包含真实数据泄露，升级被拒: {e}",
            ) from e

        safe_write(rubric_path, new_rubric)

    # 5b. 更新 rubric-memo.md
    _append_bump_memo(data_dir, old_weights, new_weights, consistency, calibration_pool)

    # 5c. 更新 state
    old_version = state.rubric_version
    new_version = _bump_version(old_version)
    state.rubric_weights = new_weights
    state.rubric_version = new_version
    state.last_bump_at = datetime.now().isoformat()
    safe_write(state_path, state.model_dump_json(indent=2))

    logger.info("bump_complete", new_version=new_version, consistency=consistency, user_id=user_id)

    return {
        "status": "accepted",
        "old_version": old_version,
        "new_version": new_version,
        "consistency": consistency,
        "old_weights": old_weights.model_dump(),
        "new_weights": new_weights.model_dump(),
        "rubric_diff": rubric_diff,
        "pool_size": len(calibration_pool),
        "rescored": new_scores,
    }


def _collect_calibration_pool(data_dir: Path, user_id: int = 0) -> list[dict[str, Any]]:
    """收集校准池 — 所有已复盘的样本

    从 data/{user_id}/predictions/ 目录读取有 ## 复盘 段的预测文件。

    Pre-conditions:
      - data/{user_id}/predictions/ 目录存在
    Post-conditions:
      - 返回校准池列表，每项含 script_id + old_composite + 实际表现
    Side effects:
      - 无
    """
    preds_dir = data_dir / str(user_id) / "predictions"
    if not preds_dir.exists():
        return []

    pool: list[dict[str, Any]] = []
    for f in sorted(preds_dir.glob("*.md")):
        content = read_file(f)
        # 只收集已复盘的
        if "## 复盘" not in content:
            continue

        # 提取 script_id（从文件名）
        script_id = f.stem

        # 提取旧综合分（从预测文件中搜索 composite）
        composite_match = re.search(r"综合分[：:]\s*(\d+\.?\d*)", content)
        old_composite = float(composite_match.group(1)) if composite_match else 0.0

        # 提取实际播放量
        plays_match = re.search(r"播放量[：:]\s*(\d+)", content)
        actual_plays = int(plays_match.group(1)) if plays_match else 0

        pool.append({
            "script_id": script_id,
            "old_composite": old_composite,
            "actual_plays": actual_plays,
            "prediction_file": str(f),
        })

    return pool


async def _propose_new_weights(
    data_dir: Path,
    calibration_pool: list[dict[str, Any]],
    old_weights: RubricWeights,
) -> dict[str, Any]:
    """LLM 提议新权重 + rubric_notes 修订

    rubric_notes.md 和 rubric-memo.md 是系统级根目录文件。

    Pre-conditions:
      - calibration_pool 非空
    Post-conditions:
      - 返回提议的新权重和 rubric 修订
    Side effects:
      - LLM 调用 (tag="bump_propose")
    """
    rubric_content = read_file(data_dir / "rubric_notes.md")
    memo_content = read_file(data_dir / "rubric-memo.md")

    pool_summary = "\n".join(
        f"- {p['script_id']}: 旧综合分={p['old_composite']}, 实际播放={p['actual_plays']}"
        for p in calibration_pool
    )
    old_w_str = "\n".join(f"  {k}: {v}" for k, v in old_weights.model_dump().items())

    prompt = f"""基于校准池数据，提议新的 rubric 权重和评分规则修订。

## 当前 rubric_notes.md
{rubric_content[:3000]}

## rubric-memo.md（含复盘数据）
{memo_content[:3000]}

## 校准池
{pool_summary}

## 当前权重
{old_w_str}

## 维度列表
{', '.join(DIMENSIONS)}

## 任务
1. 分析哪些维度的得分与实际表现相关性高/低
2. 提议新权重（提高相关维度权重，降低无关维度权重）
3. 如有需要，提议 rubric_notes.md 的修订内容（新增观察规则、删除被推翻的规则）

## 输出 JSON
```json
{{
  "new_weights": {{
    "ER": 1.5,
    "HP": 2.0,
    ...
  }},
  "weight_reasoning": "HP权重提升因为...",
  "rubric_diff": "### v1 修订\\n- 新增：HP 5分的补充条件...\\n- 删除：SAT 维度中关于...的规则（已被数据推翻）",
  "observations": ["观察1", "观察2"]
}}
```

注意：
1. 权重范围 0.5-3.0，步长 0.5
2. rubric_diff 只能包含通用语言描述，不能包含任何真实数据（数字+单位）
3. 被数据推翻的规则要标记删除"""

    result = await call_llm_json(prompt, tag="bump_propose", temperature=0.3)
    return result


def _parse_weights(raw: dict[str, Any]) -> RubricWeights:
    """解析 LLM 返回的权重为 RubricWeights 模型

    无效值回退到 1.0。
    """
    defaults = RubricWeights()
    kwargs: dict[str, float] = {}
    for dim in DIMENSIONS:
        val = raw.get(dim, 1.0)
        try:
            val = float(val)
            # 限制范围 0.5-3.0
            val = max(0.5, min(3.0, val))
            # 步长对齐到 0.5
            val = round(val * 2) / 2
        except (ValueError, TypeError):
            val = getattr(defaults, dim, 1.0)
        kwargs[dim] = val
    return RubricWeights(**kwargs)


async def _rescore_pool(
    data_dir: Path,
    calibration_pool: list[dict[str, Any]],
    new_weights: RubricWeights,
) -> list[dict[str, Any]]:
    """blind sub-agent 全量重打分校准池

    Pre-conditions:
      - calibration_pool 非空
    Post-conditions:
      - 返回重打分结果列表
    Side effects:
      - 多次 LLM 调用（每个样本一次 blind_score）
    """
    results: list[dict[str, Any]] = []
    for item in calibration_pool:
        script_id = item["script_id"]
        try:
            score_result = await score_script(data_dir, script_id, new_weights)
            from backend.app.models.state import ScoreResult
            sr = ScoreResult(**score_result) if isinstance(score_result, dict) else score_result
            results.append({
                "script_id": script_id,
                "new_composite": sr.composite,
                "old_composite": item["old_composite"],
                "actual_plays": item["actual_plays"],
            })
        except Exception as e:
            logger.warning("bump_rescore_failed", script_id=script_id, error=str(e))
            results.append({
                "script_id": script_id,
                "new_composite": item["old_composite"],  # 回退到旧分
                "old_composite": item["old_composite"],
                "actual_plays": item["actual_plays"],
            })
    return results


def _compute_rankings(pool: list[dict[str, Any]], score_key: str) -> list[str]:
    """根据分数计算排序（从高到低），返回 script_id 排序列表"""
    sorted_pool = sorted(pool, key=lambda x: x.get(score_key, 0), reverse=True)
    return [item["script_id"] for item in sorted_pool]


def _compute_ranking_consistency(old_rankings: list[str], new_rankings: list[str]) -> float:
    """计算排序一致性 — 基于 Kendall tau 系数

    Pre-conditions:
      - 两个排序列表长度相同
    Post-conditions:
      - 返回 0-1 的一致性分数
    Side effects:
      - 无
    """
    n = len(old_rankings)
    if n <= 1:
        return 1.0

    # 构建 rank map
    old_rank_map = {sid: i for i, sid in enumerate(old_rankings)}
    new_rank_map = {sid: i for i, sid in enumerate(new_rankings)}

    # Kendall tau: 数一致对和不一致对
    concordant = 0
    discordant = 0
    items = list(old_rank_map.keys())

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            old_diff = old_rank_map[a] - old_rank_map[b]
            new_diff = new_rank_map.get(a, 0) - new_rank_map.get(b, 0)
            if old_diff * new_diff > 0:
                concordant += 1
            elif old_diff * new_diff < 0:
                discordant += 1

    total = concordant + discordant
    if total == 0:
        return 1.0

    return concordant / total


def _bump_version(version: str) -> str:
    """版本号递增：v0 → v1, v1 → v2, ..."""
    match = re.match(r"v(\d+)", version)
    if match:
        n = int(match.group(1))
        return f"v{n + 1}"
    return "v1"


def _append_bump_memo(
    data_dir: Path,
    old_weights: RubricWeights,
    new_weights: RubricWeights,
    consistency: float,
    calibration_pool: list[dict[str, Any]],
) -> None:
    """追加 bump 记录到 rubric-memo.md

    rubric-memo.md 是系统级根目录文件。

    Pre-conditions:
      - rubric-memo.md 存在
    Post-conditions:
      - rubric-memo.md 追加 bump 记录
    Side effects:
      - 写文件系统
    """
    memo_path = data_dir / "rubric-memo.md"
    if not memo_path.exists():
        return

    existing = read_file(memo_path)

    old_w = ", ".join(f"{k}={v}" for k, v in old_weights.model_dump().items())
    new_w = ", ".join(f"{k}={v}" for k, v in new_weights.model_dump().items())

    entry = f"""

### Bump 记录 ({datetime.now().strftime('%Y-%m-%d %H:%M')})

- 排序一致性: {consistency:.2f}
- 校准池大小: {len(calibration_pool)}
- 旧权重: {old_w}
- 新权重: {new_w}
- 样本: {', '.join(p['script_id'] for p in calibration_pool)}
"""
    safe_write(memo_path, existing + entry)


class BumpError(Exception):
    """bump 流程异常"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
