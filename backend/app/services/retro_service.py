"""复盘服务 — cheat-retro 的 Python 实现

T+N 复盘流程：
1. 读取预测文件
2. 收集实际表现数据
3. 对比预测 vs 实际
4. 追加 ## 复盘 段（## 预测 段 immutable）
5. 更新 rubric-memo.md
6. 检查是否触发 bump

用户数据隔离：predictions 路径使用 data/{user_id}/predictions/
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.errors import PREDICTION_NOT_FOUND
from backend.app.models.state import CheatState
from backend.app.services.file_io import (
    get_prediction_hash,
    read_file,
    safe_write,
    verify_prediction_immutability,
)
from backend.app.services.llm import call_llm_json

logger = structlog.get_logger()


async def retro_predict(
    data_dir: Path,
    user_id: int = 0,
    prediction_id: str = "",
    actual_plays: int = 0,
    actual_likes: int | None = None,
    actual_comments: int | None = None,
    actual_shares: int | None = None,
    retro_notes: str | None = None,
    days_since_publish: int = 3,
) -> dict[str, Any]:
    """复盘 — T+N 复盘流程

    Pre-conditions:
      - data/{user_id}/predictions/<id>.md 存在
      - actual_plays > 0
    Post-conditions:
      - data/{user_id}/predictions/<id>.md 追加 ## 复盘 段（## 预测 段不变）
      - rubric-memo.md 追加复盘数据（系统级根目录）
      - state.pending_retros 移除该条
      - 返回预测 vs 实际偏差分析
    Side effects:
      - LLM 调用 (tag="retro_analysis")
      - 写文件系统
    Error codes:
      - PREDICTION_NOT_FOUND
      - BLIND_VIOLATION_SEEN_DATA: 预测段被篡改
    """
    logger.info("retro_start", prediction_id=prediction_id, user_id=user_id)

    user_pred_dir = data_dir / str(user_id) / "predictions"

    # 1. 读取预测文件
    pred_path = user_pred_dir / f"{prediction_id}.md"
    if not pred_path.exists():
        candidates = list(user_pred_dir.glob(f"*{prediction_id}*.md"))
        if not candidates:
            raise FileNotFoundError(f"{PREDICTION_NOT_FOUND}: {prediction_id}")
        pred_path = candidates[0]

    original_content = read_file(pred_path)
    original_hash = get_prediction_hash(original_content)

    # 2. LLM 分析偏差
    deviation_analysis = await _analyze_deviation(
        original_content, actual_plays, actual_likes, actual_comments, actual_shares, retro_notes
    )

    # 3. 构建 ## 复盘 段
    retro_section = _build_retro_section(
        actual_plays=actual_plays,
        actual_likes=actual_likes,
        actual_comments=actual_comments,
        actual_shares=actual_shares,
        retro_notes=retro_notes,
        days_since_publish=days_since_publish,
        deviation_analysis=deviation_analysis,
    )

    # 4. 追加到预测文件（替换占位复盘段或追加新复盘段）
    if "## 复盘\n\n> 在 T+3d 后追加此段" in original_content:
        new_content = original_content.replace(
            "## 复盘\n\n> 在 T+3d 后追加此段。记录实际表现与预测的偏差。\n> （尚未复盘）",
            retro_section,
        )
    elif "## 复盘" in original_content:
        # 已有复盘段，追加
        new_content = original_content + "\n\n" + retro_section
    else:
        new_content = original_content + "\n\n" + retro_section

    # 5. 验证 ## 预测 段未被修改
    if not verify_prediction_immutability(original_hash, new_content):
        from backend.app.errors import BLIND_VIOLATION_SEEN_DATA
        raise RuntimeError(
            f"{BLIND_VIOLATION_SEEN_DATA}: 复盘写入导致预测段被修改，操作被拒绝"
        )

    # 6. 写入
    safe_write(pred_path, new_content)

    # 7. 更新 rubric-memo.md（系统级根目录，与 user_id 无关）
    _update_rubric_memo(data_dir, prediction_id, actual_plays, actual_likes, deviation_analysis)

    # 8. 更新 state（根目录下的 .cheat-state.json 是系统级）
    state_path = data_dir / ".cheat-state.json"
    state = CheatState.model_validate_json(read_file(state_path))
    # 移除 pending_retros 中匹配的条目
    state.pending_retros = [
        r for r in state.pending_retros if not r.startswith(prediction_id)
    ]
    safe_write(state_path, state.model_dump_json(indent=2))

    logger.info("retro_complete", prediction_id=prediction_id, actual_plays=actual_plays, user_id=user_id)

    return {
        "prediction_id": prediction_id,
        "actual_plays": actual_plays,
        "deviation_analysis": deviation_analysis,
        "retro_written": True,
    }


async def _analyze_deviation(
    prediction_content: str,
    actual_plays: int,
    actual_likes: int | None,
    actual_comments: int | None,
    actual_shares: int | None,
    retro_notes: str | None,
) -> dict[str, Any]:
    """LLM 分析预测 vs 实际偏差

    Pre-conditions:
      - prediction_content 非空
    Post-conditions:
      - 返回偏差分析
    Side effects:
      - LLM 调用 (tag="retro_analysis")
    """
    prompt = f"""分析以下预测与实际表现的偏差。

预测内容:
{prediction_content[:2000]}

实际表现:
- 播放量: {actual_plays}
- 点赞: {actual_likes or '未提供'}
- 评论: {actual_comments or '未提供'}
- 分享: {actual_shares or '未提供'}
- 复盘备注: {retro_notes or '无'}

返回 JSON：
```json
{{
  "prediction_accuracy": "overestimated/accurate/underestimated",
  "key_deviation": "主要偏差描述",
  "lessons": ["教训1", "教训2"],
  "rubric_observation": "rubric 需要调整的观察（如有）",
  "bump_trigger": false
}}
```

bump_trigger 为 true 的条件：
- 连续 ≥3 同向偏差
- 1 次 ≥10x 偏差
- 2 次同向偏差 + 评论反向证据"""

    result = await call_llm_json(prompt, tag="retro_analysis", temperature=0.2)
    return result


def _build_retro_section(
    actual_plays: int,
    actual_likes: int | None,
    actual_comments: int | None,
    actual_shares: int | None,
    retro_notes: str | None,
    days_since_publish: int,
    deviation_analysis: dict[str, Any],
) -> str:
    """构建复盘段内容"""
    now = datetime.now().isoformat()
    return f"""## 复盘

> 复盘时间: {now}（T+{days_since_publish}d）

### 实际表现
- 播放量: {actual_plays}
- 点赞: {actual_likes or '未提供'}
- 评论: {actual_comments or '未提供'}
- 分享: {actual_shares or '未提供'}

### 偏差分析
- 预测准确性: {deviation_analysis.get('prediction_accuracy', 'N/A')}
- 主要偏差: {deviation_analysis.get('key_deviation', 'N/A')}

### 教训
{chr(10).join(f'- {lesson}' for lesson in deviation_analysis.get('lessons', []))}

### Rubric 观察
{deviation_analysis.get('rubric_observation', '无')}

### 复盘备注
{retro_notes or '无'}

### Bump 触发
{'是 — 建议执行 cheat-bump' if deviation_analysis.get('bump_trigger') else '否'}
"""


def _update_rubric_memo(
    data_dir: Path,
    prediction_id: str,
    actual_plays: int,
    actual_likes: int | None,
    deviation_analysis: dict[str, Any],
) -> None:
    """更新 rubric-memo.md — 追加复盘数据

    rubric-memo.md 包含真实数据，blind scorer 硬禁读。
    该系统文件保持在 data/ 根目录，与用户数据隔离无关。

    Pre-conditions:
      - rubric-memo.md 存在
    Post-conditions:
      - rubric-memo.md 追加复盘条目
    Side effects:
      - 写文件系统
    """
    memo_path = data_dir / "rubric-memo.md"
    if not memo_path.exists():
        return

    existing = read_file(memo_path)
    entry = f"""

### 复盘: {prediction_id} ({datetime.now().strftime('%Y-%m-%d')})

- 实际播放: {actual_plays}
- 实际点赞: {actual_likes or 'N/A'}
- 预测准确性: {deviation_analysis.get('prediction_accuracy', 'N/A')}
- 主要偏差: {deviation_analysis.get('key_deviation', 'N/A')}
- 教训: {'; '.join(deviation_analysis.get('lessons', []))}
"""
    safe_write(memo_path, existing + entry)
