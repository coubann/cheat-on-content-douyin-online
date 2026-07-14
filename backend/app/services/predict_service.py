"""完整预测流程 — cheat-predict 7 Phase 实现

对应 cheat-on-content 的 cheat-predict skill：
Phase 1: 读取脚本 + rubric
Phase 2: 盲打分（委托 blind_scorer）
Phase 3: 爆款预测（委托 predictor）
Phase 4: 生成预测文件（7 组件）
Phase 5: 落盘（predictions/<id>.md）
Phase 6: 更新 state
Phase 7: 返回结果

预测文件 7 组件：
1. Header（脚本 ID + 时间戳）
2. Input Snapshot（脚本 hash + rubric 版本）
3. Prediction（bucket + 置信度）
4. Reasoning Factors（各维度得分 + 爆款子分）
5. Anchor Comparison（与校准池锚点对比）
6. Counterfactual Scenarios（反事实场景）
7. Critical Calibration Hypothesis（关键校准假设）
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.models.state import CheatState, ScoreResult
from backend.app.services.blind_scorer import score_script as blind_score
from backend.app.services.file_io import get_prediction_hash, read_file, safe_write
from backend.app.services.llm import call_llm_json
from backend.app.services.predictor import predict_virality
from backend.app.services.scripts_service import _resolve_script_path

logger = structlog.get_logger()


async def full_predict(data_dir: Path, script_id: str, user_id: int = 0) -> dict[str, Any]:
    """完整预测流程 — 7 Phase

    Pre-conditions:
      - scripts/<id>.md 存在
      - .cheat-state.json 存在
      - rubric_notes.md 存在
    Post-conditions:
      - predictions/<id>.md 被创建（## 预测 段 immutable）
      - .cheat-state.json 被更新（in_progress_session）
    Side effects:
      - LLM 调用（blind_score + predictor）
      - 写文件系统
    Error codes:
      - SCRIPT_NOT_FOUND
      - PREDICTION_EXISTS: 预测文件已存在
    """
    from backend.app.errors import PREDICTION_EXISTS, SCRIPT_NOT_FOUND

    logger.info("predict_start", script_id=script_id, user_id=user_id)

    # 用户隔离路径
    user_data_dir = data_dir / str(user_id)
    predictions_dir = user_data_dir / "predictions"

    # Phase 1: 读取脚本 + state
    # 复用 scripts_service 的路径解析：先查本用户空间，回退默认共享空间(data/0)
    script_path = _resolve_script_path(data_dir, script_id, user_id)
    if not script_path.exists():
        raise FileNotFoundError(f"{SCRIPT_NOT_FOUND}: {script_id}")

    # 脚本实际所在的数据目录（user_data_dir 级别）。
    # 当脚本回退到共享空间(data/0)时，blind_score / predict_virality 也需要
    # 从该目录读取脚本，否则会再次因路径找不到而失败。
    # script_path 形如 data_dir/{uid}/scripts/{id}.md，向上两级即用户数据目录。
    script_data_dir = script_path.parent.parent

    state_path = data_dir / ".cheat-state.json"
    state = CheatState.model_validate_json(read_file(state_path))
    script_content = read_file(script_path)
    script_hash = hashlib.sha256(script_content.encode()).hexdigest()[:12]

    logger.info("predict_phase1_complete", script_hash=script_hash, user_id=user_id)

    # Phase 2: 盲打分（传入 script_data_dir 以读取脚本实际所在目录的脚本）
    score_data = await blind_score(script_data_dir, script_id)
    score_result = ScoreResult(**score_data)

    logger.info("predict_score_returned", composite=score_result.composite, user_id=user_id)

    # Phase 3: 爆款预测（传入 script_data_dir 以读取脚本实际所在目录的校准池）
    virality = await predict_virality(script_data_dir, script_id, score_result, state)

    logger.info("predict_virality_returned", virality_score=virality["virality_score"], user_id=user_id)

    # Phase 4: 生成预测文件
    prediction_id = f"{script_id}"
    prediction_path = predictions_dir / f"{prediction_id}.md"

    if prediction_path.exists():
        raise FileExistsError(f"{PREDICTION_EXISTS}: 预测已存在 {prediction_id}")

    prediction_content = _build_prediction_file(
        script_id=script_id,
        script_hash=script_hash,
        score_result=score_result,
        virality=virality,
        state=state,
    )

    # Phase 5: 落盘
    predictions_dir.mkdir(parents=True, exist_ok=True)
    safe_write(prediction_path, prediction_content)

    logger.info("predict_written", prediction_id=prediction_id, user_id=user_id)

    # Phase 6: 更新 state（共享的 .cheat-state.json）
    state.in_progress_session = prediction_id
    safe_write(state_path, state.model_dump_json(indent=2))

    # Phase 7: 返回
    result = {
        "prediction_id": prediction_id,
        "script_id": script_id,
        "script_hash": script_hash,
        "score": score_data,
        "virality": virality,
        "prediction_path": str(prediction_path),
    }

    logger.info("predict_complete", prediction_id=prediction_id, user_id=user_id)
    return result


async def list_predictions(data_dir: Path, user_id: int = 0) -> list[dict[str, Any]]:
    """列出所有已预测的脚本

    Pre-conditions:
      - predictions/ 目录存在（可选）
    Post-conditions:
      - 返回预测列表（按修改时间倒序）
    Side effects:
      - 无
    """
    preds_dir = data_dir / str(user_id) / "predictions"
    if not preds_dir.exists():
        return []

    results = []
    for path in sorted(preds_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        content = read_file(path)
        # 从 markdown 内容中提取关键信息
        prediction_id = path.stem
        has_retro = "## 复盘" in content

        # 提取脚本 ID
        script_id = prediction_id
        for line in content.split("\n"):
            if line.startswith("- 脚本 ID:"):
                script_id = line.split(":", 1)[1].strip()
                break

        # 提取预测时间
        pred_time = ""
        for line in content.split("\n"):
            if line.startswith("- 预测时间:"):
                pred_time = line.split(":", 1)[1].strip()
                break

        # 提取爆款分 — 格式: "- 爆款分: **64.7/100**" 或 "- 爆款分: 64.7/100"
        virality_score = None
        for line in content.split("\n"):
            if "爆款分" in line:
                m = re.search(r"\*{0,2}(\d+\.?\d*)\s*/\s*100\*{0,2}", line)
                if m:
                    virality_score = float(m.group(1))
                break

        # 提取 bucket
        bucket_info = ""
        for line in content.split("\n"):
            if "Bucket:" in line or "bucket:" in line.lower():
                bucket_info = line.strip()
                break

        results.append({
            "prediction_id": prediction_id,
            "script_id": script_id,
            "pred_time": pred_time,
            "has_retro": has_retro,
            "virality_score": virality_score,
            "bucket": bucket_info,
            "file_mtime": path.stat().st_mtime,
        })

    return results


async def get_prediction_detail(data_dir: Path, prediction_id: str, user_id: int = 0) -> dict[str, Any]:
    """获取预测详情

    Pre-conditions:
      - predictions/<id>.md 存在
    Post-conditions:
      - 返回预测详情
    Side effects:
      - 无
    Error codes:
      - PREDICTION_NOT_FOUND
    """
    from backend.app.errors import PREDICTION_NOT_FOUND

    preds_dir = data_dir / str(user_id) / "predictions"
    path = preds_dir / f"{prediction_id}.md"
    if not path.exists():
        # 尝试带 script_id 前缀
        candidates = list(preds_dir.glob(f"*{prediction_id}*.md"))
        if not candidates:
            raise FileNotFoundError(f"{PREDICTION_NOT_FOUND}: {prediction_id}")
        path = candidates[0]

    content = read_file(path)
    prediction_hash = get_prediction_hash(content)

    return {
        "prediction_id": path.stem,
        "content": content,
        "prediction_hash": prediction_hash,
        "has_retro": "## 复盘" in content,
    }


async def generate_optimized_script(data_dir: Path, prediction_id: str, user_id: int = 0) -> dict[str, Any]:
    """基于预测结果生成最优文案/脚本

    读取原始脚本 + 预测维度评分 + 改稿建议，
    让 LLM 重写一份符合打分标准的最优版本。

    Pre-conditions:
      - predictions/<id>.md 存在
      - scripts/<id>.md 存在
    Post-conditions:
      - 返回最优文案（纯文本，非 markdown）
    Side effects:
      - LLM 调用
    """
    user_data_dir = data_dir / str(user_id)
    preds_dir = user_data_dir / "predictions"
    scripts_dir = user_data_dir / "scripts"

    # 1. 读取预测文件
    pred_path = preds_dir / f"{prediction_id}.md"
    if not pred_path.exists():
        candidates = list(preds_dir.glob(f"*{prediction_id}*.md"))
        if not candidates:
            raise FileNotFoundError(f"预测不存在: {prediction_id}")
        pred_path = candidates[0]
    pred_content = read_file(pred_path)

    # 2. 读取原始脚本
    script_path = scripts_dir / f"{prediction_id}.md"
    if not script_path.exists():
        candidates = list(scripts_dir.glob(f"*{prediction_id}*.md"))
        if not candidates:
            raise FileNotFoundError(f"脚本不存在: {prediction_id}")
        script_path = candidates[0]
    script_content = read_file(script_path)

    # 3. 提取维度评分和改稿建议
    dim_scores = []
    for m in re.finditer(r"\|\s*(\w{2,3})\s*\|\s*(\d+\.?\d*)\s*\|\s*(\d+)%?\s*\|\s*(.+?)\s*\|", pred_content):
        key, score, conf, reason = m.group(1), float(m.group(2)), int(m.group(3)), m.group(4)
        if key in ("ER", "HP", "QL", "NA", "AB", "SR", "SAT", "TS", "MS", "CC"):
            dim_scores.append(f"  {key}: {score}/5 (置信度{conf}%) - {reason}")

    suggestions = []
    _suggestion_pattern = (
        r"- \[(HIGH|MEDIUM|LOW)\]\s*(\w+):\s*(.+?)(?:\s*\(预期影响:\s*(.+?)\))?$"
    )
    for m in re.finditer(_suggestion_pattern, pred_content, re.MULTILINE):
        suggestions.append(f"  [{m.group(1)}] {m.group(2)}: {m.group(3)} (预期: {m.group(4) or '未知'})")

    # 4. LLM 生成最优文案
    prompt = f"""你是一位顶级短视频文案策划。请根据以下预测评分和改稿建议，将原始脚本重写为最优版本。

## 原始脚本
{script_content[:3000]}

## 各维度评分
{chr(10).join(dim_scores)}

## 改稿建议
{chr(10).join(suggestions) if suggestions else "无具体建议"}

## 要求
1. 严格按照改稿建议逐条修改，确保每个低分维度都得到提升
2. 输出纯文本格式，不要使用 markdown 语法（不要 #、**、| 等）
3. 直接输出可以复制粘贴使用的最终文案
4. 保持原始脚本的核心信息和价值主张
5. 语言自然流畅，像真人在说话

返回 JSON：
```json
{{
  "optimized_script": "重写后的最优文案（纯文本，可直接使用）",
  "improvements": ["改进点1", "改进点2", "改进点3"],
  "estimated_score_boost": "+15"
}}
```"""

    result = await call_llm_json(prompt, tag="optimize_script", temperature=0.3)

    return {
        "prediction_id": prediction_id,
        "optimized_script": result.get("optimized_script", ""),
        "improvements": result.get("improvements", []),
        "estimated_score_boost": result.get("estimated_score_boost", ""),
    }


def _build_prediction_file(
    script_id: str,
    script_hash: str,
    score_result: ScoreResult,
    virality: dict[str, Any],
    state: CheatState,
) -> str:
    """构建预测文件 — 7 组件 + 复盘占位

    ## 预测 段一旦写入不可修改，只能追加 ## 复盘 段。
    """
    now = datetime.now().isoformat()
    dims_text = "\n".join(
        f"| {d.dimension} | {d.score} | {d.confidence:.0%} | {d.reason} |"
        for d in score_result.dimensions
    )

    breakdown = virality.get("breakdown", {})
    sub_scores = virality.get("sub_scores", {})
    diagnosis = virality.get("diagnosis", {})
    suggestions = virality.get("suggestions", [])
    bucket = virality.get("bucket", {})

    risks_text = "\n".join(f"- {r}" for r in diagnosis.get("risks", []))
    highlights_text = "\n".join(f"- {h}" for h in diagnosis.get("highlights", []))
    suggestions_text = "\n".join(
        f"- [{s.get('priority', 'medium').upper()}] "
        f"{s.get('target_dimension', '?')}: {s.get('action', '')} "
        f"(预期影响: {s.get('expected_impact', '')})"
        for s in suggestions
    )

    _prediction_hash_input = '## 预测\n\nplaceholder'

    # Pre-extract values for long lines
    _strongest = diagnosis.get('strongest_dimension', {})
    _weakest = diagnosis.get('weakest_dimension', {})
    _bm_sim = sub_scores.get('benchmark_similarity', 0)
    _bm_sim_contrib = breakdown.get('benchmark_similarity_contribution', 0)

    return f"""# Prediction: {script_id}

## 预测

> **IMMUTABLE** — 此段写完后不可修改，只能追加 `## 复盘` 段。
> 预测 hash: {get_prediction_hash(_prediction_hash_input)[:8]}（落盘后自动计算）

### 1. Header
- 脚本 ID: {script_id}
- 预测时间: {now}
- Rubric 版本: {state.rubric_version}
- 预测引擎: Phase 1 (规则 + LLM 双判)
- 校准样本数: {state.calibration_samples}

### 2. Input Snapshot
- Script Hash: {script_hash}
- 内容形态: {state.content_form}
- 目标平台: {', '.join(state.platforms)}

### 3. Prediction
- 爆款分: **{virality.get('virality_score', 0)}/100**
- Bucket: {bucket.get('scheme', 'ratio')} → {bucket.get('prediction', 'N/A')}
- 综合分: {score_result.composite}/10

### 4. Reasoning Factors

**维度得分:**
| 维度 | 分数 | 置信度 | 原因 |
|---|---|---|---|
{dims_text}

**爆款子分:**
| 子分 | 值 | 贡献 |
|---|---|---|
| rubric_normalized | {sub_scores.get('rubric_normalized', 0)} | {breakdown.get('rubric_contribution', 0)} |
| topic_heat | {sub_scores.get('topic_heat', 0)} | {breakdown.get('topic_heat_contribution', 0)} |
| platform_fit | {sub_scores.get('platform_fit', 0)} | {breakdown.get('platform_fit_contribution', 0)} |
| benchmark_similarity | {_bm_sim} | {_bm_sim_contrib} |

### 5. Anchor Comparison
- 校准样本数: {state.calibration_samples}
- 最强维度: {_strongest.get('dimension', 'N/A')} = {_strongest.get('score', 'N/A')}
- 最弱维度: {_weakest.get('dimension', 'N/A')} = {_weakest.get('score', 'N/A')}

### 6. Counterfactual Scenarios
- 如果最弱维度提升到 5 分，综合分预计 +{round(diagnosis.get('weakest_dimension', {}).get('score', 0) * -1 + 5, 1)}
- 如果钩子(HP)从 0 提升到 5，爆款分预计 +15-25

### 7. Critical Calibration Hypothesis
- 当前预测基于 Phase 1（规则 + LLM），置信度有限
- 需要 5+ 校准样本后进入 Phase 2（LightGBM）
- 关键假设：rubric 维度权重等权是否合理？首次 bump 后重新评估

**风险信号:**
{risks_text or '（无）'}

**亮点:**
{highlights_text or '（无）'}

**改稿建议:**
{suggestions_text or '（无）'}

## 复盘

> 在 T+3d 后追加此段。记录实际表现与预测的偏差。
> （尚未复盘）
"""
