"""爆款预测引擎 — Phase 1 + Phase 2

Phase 1 (0-4 样本): 规则 + LLM 双判
  virality_score = 0.6 * rubric_normalized + 0.15 * topic_heat + 0.1 * platform_fit + 0.15 * benchmark_similarity

Phase 2 (5+ 样本): LightGBM + time-based split + 每 3 样本 retrain
  特征: 10 维度分 + composite + topic_heat + platform_fit + benchmark_sim + 内容长度 + 发布时间特征
  标签: log(实际播放量)

Phase 3 (20+ 样本): 多任务学习 + transfer learning（预留接口）
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.models.state import CheatState, ScoreResult
from backend.app.services.file_io import read_file, safe_write
from backend.app.services.llm import call_llm_json

logger = structlog.get_logger()

# Phase 1 权重
_RUBRIC_W = 0.6
_TOPIC_HEAT_W = 0.15
_PLATFORM_FIT_W = 0.1
_BENCHMARK_W = 0.15

# Phase 2 配置
_PHASE2_MIN_SAMPLES = 5
_RETRAIN_EVERY_N = 3
_MODEL_DIR_NAME = "model"
_FEATURE_NAMES = [
    "ER", "HP", "QL", "NA", "AB", "SR", "SAT", "TS", "MS", "CC",
    "composite", "topic_heat", "platform_fit", "benchmark_sim",
    "content_length", "publish_hour", "publish_dayofweek",
]


async def predict_virality(
    data_dir: Path,
    script_id: str,
    score_result: ScoreResult,
    state: CheatState,
) -> dict[str, Any]:
    """爆款预测 — 自动选择 Phase 1 或 Phase 2

    Pre-conditions:
      - score_result 已由 blind_scorer 产出
      - state 已从 .cheat-state.json 加载
    Post-conditions:
      - 返回 virality_score (0-100) + 各子分 + 诊断 + 改稿建议
    Side effects:
      - LLM 调用（tag="virality_predict"）
      - Phase 2 时可能 retrain 模型
    Error codes:
      - LLM_CALL_FAILED
      - LLM_JSON_PARSE_FAILED
    """
    logger.info("virality_predict_start", script_id=script_id)

    # 1. rubric 归一化 (composite 0-10 → 0-1)
    rubric_norm = score_result.composite / 10.0

    # 2. topic_heat (LLM 判断)
    script_content = read_file(data_dir / "scripts" / f"{script_id}.md")
    topic_heat = await _assess_topic_heat(script_content, state.platforms)

    # 3. platform_fit (规则 + LLM)
    platform_fit = await _assess_platform_fit(script_content, state.platforms, state.content_form)

    # 4. benchmark_similarity
    benchmark_sim = await _assess_benchmark_similarity(script_content, state.content_form)

    # 5. 判断 Phase
    calibration_pool = _load_calibration_pool(data_dir)
    n_samples = len(calibration_pool)

    if n_samples >= _PHASE2_MIN_SAMPLES:
        # Phase 2: LightGBM
        result = await _predict_phase2(
            data_dir, script_id, score_result, state,
            rubric_norm, topic_heat, platform_fit, benchmark_sim,
            script_content, calibration_pool,
        )
    else:
        # Phase 1: 规则 + LLM
        result = await _predict_phase1(
            script_id, score_result, state,
            rubric_norm, topic_heat, platform_fit, benchmark_sim,
            script_content,
        )

    logger.info(
        "virality_predict_complete",
        script_id=script_id,
        virality_score=result["virality_score"],
        phase=result["phase"],
    )
    return result


async def _predict_phase1(
    script_id: str,
    score_result: ScoreResult,
    state: CheatState,
    rubric_norm: float,
    topic_heat: float,
    platform_fit: float,
    benchmark_sim: float,
    script_content: str,
) -> dict[str, Any]:
    """Phase 1: 规则 + LLM 双判"""
    virality_raw = (
        _RUBRIC_W * rubric_norm
        + _TOPIC_HEAT_W * topic_heat
        + _PLATFORM_FIT_W * platform_fit
        + _BENCHMARK_W * benchmark_sim
    )
    virality_score = round(virality_raw * 100, 1)

    diagnosis = _generate_diagnosis(score_result, topic_heat, platform_fit, benchmark_sim)
    suggestions = await _generate_suggestions(script_content, score_result, diagnosis)
    bucket = _predict_bucket(state, virality_score)

    return {
        "virality_score": virality_score,
        "breakdown": {
            "rubric_contribution": round(_RUBRIC_W * rubric_norm * 100, 1),
            "topic_heat_contribution": round(_TOPIC_HEAT_W * topic_heat * 100, 1),
            "platform_fit_contribution": round(_PLATFORM_FIT_W * platform_fit * 100, 1),
            "benchmark_similarity_contribution": round(_BENCHMARK_W * benchmark_sim * 100, 1),
        },
        "sub_scores": {
            "rubric_normalized": round(rubric_norm, 3),
            "topic_heat": round(topic_heat, 3),
            "platform_fit": round(platform_fit, 3),
            "benchmark_similarity": round(benchmark_sim, 3),
        },
        "diagnosis": diagnosis,
        "suggestions": suggestions,
        "bucket": bucket,
        "phase": "phase1",
        "calibration_samples": state.calibration_samples,
        "timestamp": datetime.now().isoformat(),
    }


async def _predict_phase2(
    data_dir: Path,
    script_id: str,
    score_result: ScoreResult,
    state: CheatState,
    rubric_norm: float,
    topic_heat: float,
    platform_fit: float,
    benchmark_sim: float,
    script_content: str,
    calibration_pool: list[dict[str, Any]],
) -> dict[str, Any]:
    """Phase 2: LightGBM + time-based split

    Pre-conditions:
      - calibration_pool >= 5 样本
    Post-conditions:
      - 返回 Phase 2 预测结果
    Side effects:
      - 可能 retrain 模型（每 3 样本）
      - 写模型文件
    """
    import numpy as np

    # 构建当前样本特征
    dims = {d.dimension: d.score for d in score_result.dimensions}
    now = datetime.now()
    current_features = _build_features(
        dims, score_result.composite,
        topic_heat, platform_fit, benchmark_sim,
        len(script_content), now,
    )

    # 检查是否需要 retrain
    model_dir = data_dir / _MODEL_DIR_NAME
    model_meta_path = model_dir / "meta.json"
    should_retrain = _should_retrain(model_meta_path, len(calibration_pool))

    model = None
    if should_retrain:
        model = _train_model(calibration_pool, data_dir)
        logger.info("phase2_model_retrained", samples=len(calibration_pool))
    else:
        model = _load_model(model_dir)

    # 预测
    if model is not None:
        feature_array = np.array([current_features])
        log_pred = model.predict(feature_array)[0]
        # log(plays) → virality_score (0-100)
        # 用校准池的播放量范围做归一化
        plays_list = [p["actual_plays"] for p in calibration_pool if p["actual_plays"] > 0]
        if plays_list:
            import math
            max_log = math.log(max(plays_list) + 1)
            virality_score = round(min(100, max(0, (log_pred / max_log) * 100)), 1)
        else:
            virality_score = round(min(100, max(0, log_pred * 10)), 1)

        phase = "phase2"
        model_info = {
            "model_type": "LightGBM",
            "trained_samples": len(calibration_pool),
            "retrained": should_retrain,
        }
    else:
        # 模型加载/训练失败，回退到 Phase 1
        virality_raw = (
            _RUBRIC_W * rubric_norm
            + _TOPIC_HEAT_W * topic_heat
            + _PLATFORM_FIT_W * platform_fit
            + _BENCHMARK_W * benchmark_sim
        )
        virality_score = round(virality_raw * 100, 1)
        phase = "phase1_fallback"
        model_info = {"model_type": "fallback", "reason": "model_load_failed"}

    # Phase 1 权重作为 baseline
    phase1_raw = (
        _RUBRIC_W * rubric_norm
        + _TOPIC_HEAT_W * topic_heat
        + _PLATFORM_FIT_W * platform_fit
        + _BENCHMARK_W * benchmark_sim
    )
    phase1_score = round(phase1_raw * 100, 1)

    diagnosis = _generate_diagnosis(score_result, topic_heat, platform_fit, benchmark_sim)
    suggestions = await _generate_suggestions(script_content, score_result, diagnosis)
    bucket = _predict_bucket(state, virality_score)

    # Phase 2 额外的特征重要性
    feature_importance = {}
    if model is not None:
        try:
            importances = model.feature_importance(importance_type="gain")
            for fname, imp in zip(_FEATURE_NAMES, importances, strict=False):
                feature_importance[fname] = round(float(imp), 4)
        except Exception:
            pass

    return {
        "virality_score": virality_score,
        "breakdown": {
            "rubric_contribution": round(_RUBRIC_W * rubric_norm * 100, 1),
            "topic_heat_contribution": round(_TOPIC_HEAT_W * topic_heat * 100, 1),
            "platform_fit_contribution": round(_PLATFORM_FIT_W * platform_fit * 100, 1),
            "benchmark_similarity_contribution": round(_BENCHMARK_W * benchmark_sim * 100, 1),
        },
        "sub_scores": {
            "rubric_normalized": round(rubric_norm, 3),
            "topic_heat": round(topic_heat, 3),
            "platform_fit": round(platform_fit, 3),
            "benchmark_similarity": round(benchmark_sim, 3),
        },
        "diagnosis": diagnosis,
        "suggestions": suggestions,
        "bucket": bucket,
        "phase": phase,
        "phase1_baseline_score": phase1_score,
        "model_info": model_info,
        "feature_importance": feature_importance,
        "calibration_samples": state.calibration_samples,
        "timestamp": datetime.now().isoformat(),
    }


def _build_features(
    dims: dict[str, float],
    composite: float,
    topic_heat: float,
    platform_fit: float,
    benchmark_sim: float,
    content_length: int,
    dt: datetime,
) -> list[float]:
    """构建 LightGBM 特征向量

    特征顺序与 _FEATURE_NAMES 对应。
    """
    return [
        dims.get("ER", 0), dims.get("HP", 0), dims.get("QL", 0),
        dims.get("NA", 0), dims.get("AB", 0), dims.get("SR", 0),
        dims.get("SAT", 0), dims.get("TS", 0), dims.get("MS", 0),
        dims.get("CC", 0),
        composite,
        topic_heat, platform_fit, benchmark_sim,
        float(content_length),
        float(dt.hour),
        float(dt.weekday()),
    ]


def _load_calibration_pool(data_dir: Path) -> list[dict[str, Any]]:
    """从 predictions/ 加载校准池（已复盘的样本）

    Pre-conditions:
      - predictions/ 目录存在
    Post-conditions:
      - 返回校准池列表
    Side effects:
      - 无
    """
    preds_dir = data_dir / "predictions"
    if not preds_dir.exists():
        return []

    pool: list[dict[str, Any]] = []
    for f in sorted(preds_dir.glob("*.md")):
        content = read_file(f)
        if "## 复盘" not in content:
            continue

        script_id = f.stem

        # 提取维度分
        dims: dict[str, float] = {}
        for dim in ["ER", "HP", "QL", "NA", "AB", "SR", "SAT", "TS", "MS", "CC"]:
            match = re.search(rf"{dim}[：:]\s*(\d+\.?\d*)", content)
            if match:
                dims[dim] = float(match.group(1))

        # 提取 composite
        composite_match = re.search(r"综合分[：:]\s*(\d+\.?\d*)", content)
        composite = float(composite_match.group(1)) if composite_match else 0.0

        # 提取实际播放量
        plays_match = re.search(r"播放量[：:]\s*(\d+)", content)
        actual_plays = int(plays_match.group(1)) if plays_match else 0

        # 提取子分
        topic_match = re.search(r"topic_heat[：:]\s*(\d+\.?\d*)", content)
        platform_match = re.search(r"platform_fit[：:]\s*(\d+\.?\d*)", content)
        bench_match = re.search(r"benchmark_sim[：:]\s*(\d+\.?\d*)", content)

        pool.append({
            "script_id": script_id,
            "dimensions": dims,
            "composite": composite,
            "topic_heat": float(topic_match.group(1)) if topic_match else 0.5,
            "platform_fit": float(platform_match.group(1)) if platform_match else 0.5,
            "benchmark_sim": float(bench_match.group(1)) if bench_match else 0.5,
            "actual_plays": actual_plays,
            "content_length": len(content),
        })

    return pool


def _should_retrain(model_meta_path: Path, current_samples: int) -> bool:
    """判断是否需要 retrain

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回是否需要 retrain
    Side effects:
      - 无
    """
    if not model_meta_path.exists():
        return True

    try:
        meta = json.loads(read_file(model_meta_path))
        trained_samples = meta.get("trained_samples", 0)
        return (current_samples - trained_samples) >= _RETRAIN_EVERY_N
    except Exception:
        return True


def _train_model(calibration_pool: list[dict[str, Any]], data_dir: Path) -> Any:
    """训练 LightGBM 模型

    Pre-conditions:
      - calibration_pool >= 5 样本
    Post-conditions:
      - 模型被训练并保存到 data_dir/model/
      - 返回训练好的模型
    Side effects:
      - 写文件系统
    """
    import math

    import numpy as np

    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("lightgbm_not_installed", msg="Phase 2 需要 lightgbm，回退到 Phase 1")
        return None

    # 构建训练数据
    x_list: list[list[float]] = []
    y_list: list[float] = []

    for item in calibration_pool:
        if item["actual_plays"] <= 0:
            continue
        features = _build_features(
            item["dimensions"], item["composite"],
            item["topic_heat"], item["platform_fit"], item["benchmark_sim"],
            item["content_length"], datetime.now(),  # 发布时间特征用当前值近似
        )
        x_list.append(features)
        y_list.append(math.log(item["actual_plays"] + 1))

    if len(x_list) < 3:
        logger.warning("phase2_insufficient_valid_samples", valid=len(x_list))
        return None

    x_arr = np.array(x_list)
    y_arr = np.array(y_list)

    # time-based split: 前 80% 训练，后 20% 验证
    split_idx = max(1, int(len(x_arr) * 0.8))
    x_train, x_val = x_arr[:split_idx], x_arr[split_idx:]
    y_train, y_val = y_arr[:split_idx], y_arr[split_idx:]

    # LightGBM 参数（小数据集友好）
    params = {
        "objective": "regression",
        "metric": "mae",
        "num_leaves": 8,
        "learning_rate": 0.1,
        "min_child_samples": 2,
        "verbose": -1,
        "seed": 42,
    }

    train_data = lgb.Dataset(x_train, label=y_train, feature_name=_FEATURE_NAMES)
    valid_data = lgb.Dataset(x_val, label=y_val, feature_name=_FEATURE_NAMES) if len(x_val) > 0 else None

    callbacks = [lgb.log_evaluation(period=0)]  # 静默训练
    model = lgb.train(
        params,
        train_data,
        num_boost_round=50,
        valid_sets=[valid_data] if valid_data is not None else None,
        callbacks=callbacks,
    )

    # 保存模型
    model_dir = data_dir / _MODEL_DIR_NAME
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "virality_model.txt"
    model.save_model(str(model_path))

    # 保存 meta
    meta = {
        "trained_samples": len(calibration_pool),
        "trained_at": datetime.now().isoformat(),
        "feature_names": _FEATURE_NAMES,
        "num_boost_round": 50,
    }
    safe_write(model_dir / "meta.json", json.dumps(meta, indent=2))

    logger.info("phase2_model_trained", samples=len(x_list), train_size=split_idx)
    return model


def _load_model(model_dir: Path) -> Any:
    """加载已训练的 LightGBM 模型

    Pre-conditions:
      - model/virality_model.txt 存在
    Post-conditions:
      - 返回加载的模型
    Side effects:
      - 无
    """
    try:
        import lightgbm as lgb
    except ImportError:
        return None

    model_path = model_dir / "virality_model.txt"
    if not model_path.exists():
        return None

    try:
        model = lgb.Booster(model_file=str(model_path))
        return model
    except Exception as e:
        logger.warning("phase2_model_load_failed", error=str(e))
        return None


async def _assess_topic_heat(script_content: str, platforms: list[str]) -> float:
    """评估话题热度 (0-1)

    Pre-conditions:
      - script_content 非空
    Post-conditions:
      - 返回 0-1 的话题热度分
    Side effects:
      - LLM 调用 (tag="topic_heat")
    """
    prompt = f"""评估以下脚本内容的话题热度。

目标平台: {', '.join(platforms)}

脚本内容:
{script_content[:2000]}

请评估这个话题在目标平台上的当前热度，返回 JSON：
```json
{{
  "topic_heat": 0.7,
  "reasoning": "该话题与当前XX热点相关，但视角较为常见",
  "trending_keywords": ["关键词1", "关键词2"]
}}
```

topic_heat 范围 0-1：
- 0-0.3: 冷门话题，无热点关联
- 0.3-0.6: 中等热度，有一定受众
- 0.6-0.8: 热门话题，正在流行
- 0.8-1.0: 超级热点，全民关注"""

    result = await call_llm_json(prompt, tag="topic_heat", temperature=0.2)
    return float(result.get("topic_heat", 0.5))


async def _assess_platform_fit(script_content: str, platforms: list[str], content_form: str) -> float:
    """评估平台契合度 (0-1)

    Pre-conditions:
      - script_content 非空
    Post-conditions:
      - 返回 0-1 的平台契合度
    Side effects:
      - LLM 调用 (tag="platform_fit")
    """
    # 规则层：快速判断
    rule_score = 0.5  # 基线

    # 内容长度适配
    content_len = len(script_content)
    if content_form == "opinion-video":
        if 200 <= content_len <= 800:
            rule_score += 0.15
        elif content_len > 1500:
            rule_score -= 0.1

    # 平台特定规则
    if "douyin" in platforms:
        rule_score += 0.05  # 短视频天然适配
    if "xiaohongshu" in platforms and any(kw in script_content for kw in ["分享", "推荐", "实测", "避坑"]):
        rule_score += 0.1

    rule_score = min(1.0, max(0.0, rule_score))

    # LLM 层：精细判断
    prompt = f"""评估以下内容在平台 {', '.join(platforms)} 上的契合度。

内容形态: {content_form}
脚本内容:
{script_content[:2000]}

返回 JSON：
```json
{{
  "platform_fit": 0.7,
  "reasoning": "...",
  "platform_specific_notes": {{"douyin": "前3秒钩子足够强", "xiaohongshu": "需要更多视觉描述"}}
}}
```

platform_fit 范围 0-1。"""

    result = await call_llm_json(prompt, tag="platform_fit", temperature=0.2)
    llm_score = float(result.get("platform_fit", 0.5))

    # 规则 + LLM 各半
    return round((rule_score + llm_score) / 2, 3)


async def _assess_benchmark_similarity(script_content: str, content_form: str) -> float:
    """评估与爆款标杆的相似度 (0-1)

    Pre-conditions:
      - script_content 非空
    Post-conditions:
      - 返回 0-1 的标杆相似度
    Side effects:
      - LLM 调用 (tag="benchmark_sim")
    """
    prompt = f"""评估以下内容与该领域爆款标杆的相似度。

内容形态: {content_form}
脚本内容:
{script_content[:2000]}

请基于你对{content_form}领域爆款内容的理解，评估这段内容与"爆款模式"的契合程度。

返回 JSON：
```json
{{
  "benchmark_similarity": 0.6,
  "reasoning": "有钩子但展开不够紧凑",
  "missing_elements": ["缺少反差/转折", "结尾没有call-to-action"]
}}
```

benchmark_similarity 范围 0-1：
- 0-0.3: 与爆款模式差距大
- 0.3-0.6: 有部分爆款元素
- 0.6-0.8: 较为接近爆款模式
- 0.8-1.0: 高度契合爆款模式"""

    result = await call_llm_json(prompt, tag="benchmark_sim", temperature=0.2)
    return float(result.get("benchmark_similarity", 0.5))


def _generate_diagnosis(
    score_result: ScoreResult,
    topic_heat: float,
    platform_fit: float,
    benchmark_sim: float,
) -> dict[str, Any]:
    """生成诊断报告（纯规则，不调 LLM）"""
    dims = {d.dimension: d.score for d in score_result.dimensions}

    # 找最强和最弱维度
    strongest = max(dims.items(), key=lambda x: x[1])
    weakest = min(dims.items(), key=lambda x: x[1])

    # 风险信号
    risks: list[str] = []
    if dims.get("HP", 0) <= 1:
        risks.append("钩子强度不足 — 前3秒可能留不住观众")
    if dims.get("TS", 0) <= 1:
        risks.append("分享冲动低 — 观众不太可能转发")
    if dims.get("CC", 0) <= 1:
        risks.append("内容不够紧凑 — 有冗余段落")
    if topic_heat < 0.3:
        risks.append("话题热度低 — 非当前热点")
    if platform_fit < 0.4:
        risks.append("平台契合度低 — 内容形态与平台不匹配")

    # 亮点
    highlights: list[str] = []
    if dims.get("ER", 0) >= 4:
        highlights.append("情感共鸣强 — 观众容易产生代入感")
    if dims.get("HP", 0) >= 4:
        highlights.append("钩子极强 — 开头能抓住注意力")
    if dims.get("QL", 0) >= 4:
        highlights.append("金句密度高 — 有多句可截图传播")
    if benchmark_sim >= 0.7:
        highlights.append("接近爆款模式 — 结构和节奏与标杆相似")

    return {
        "strongest_dimension": {"dimension": strongest[0], "score": strongest[1]},
        "weakest_dimension": {"dimension": weakest[0], "score": weakest[1]},
        "risks": risks,
        "highlights": highlights,
        "composite": score_result.composite,
    }


async def _generate_suggestions(
    script_content: str,
    score_result: ScoreResult,
    diagnosis: dict[str, Any],
) -> list[dict[str, str]]:
    """生成改稿建议

    Pre-conditions:
      - score_result 和 diagnosis 已生成
    Post-conditions:
      - 返回改稿建议列表
    Side effects:
      - LLM 调用 (tag="suggest_edits")
    """
    dims_summary = ", ".join(f"{d.dimension}={d.score}" for d in score_result.dimensions)
    risks_text = "; ".join(diagnosis.get("risks", []))

    prompt = f"""基于以下分析，给出3条具体的改稿建议。

当前维度得分: {dims_summary}
综合分: {score_result.composite}/10
风险: {risks_text}
最弱维度: {diagnosis['weakest_dimension']['dimension']}={diagnosis['weakest_dimension']['score']}

脚本内容:
{script_content[:2000]}

返回 JSON：
```json
{{
  "suggestions": [
    {{"priority": "high", "target_dimension": "HP",
      "action": "将开头改为...", "expected_impact": "钩子从0→3，综合分预计+1.2"}},
    {{"priority": "medium", "target_dimension": "CC",
      "action": "删除第3段的...", "expected_impact": "紧凑度从3→5，综合分预计+0.8"}},
    {{"priority": "low", "target_dimension": "QL",
      "action": "在结尾添加...", "expected_impact": "金句密度从3→5，综合分预计+0.6"}}
  ]
}}
```"""

    result = await call_llm_json(prompt, tag="suggest_edits", temperature=0.3)
    return result.get("suggestions", [])


def _predict_bucket(state: CheatState, virality_score: float) -> dict[str, Any]:
    """预测 bucket（ratio/absolute/percentile）

    Pre-conditions:
      - state 已加载
    Post-conditions:
      - 返回 bucket 预测
    Side effects:
      - 无
    """
    n = state.calibration_samples

    if n <= 4:
        # ratio 桶：相对上一篇的倍数
        if virality_score >= 70:
            ratio = "3x+"
        elif virality_score >= 50:
            ratio = "1.5-3x"
        elif virality_score >= 30:
            ratio = "0.5-1.5x"
        else:
            ratio = "<0.5x"
        return {"scheme": "ratio", "prediction": ratio, "samples": n}

    elif n <= 9:
        # absolute 桶
        if virality_score >= 80:
            tier = "爆款（校准池中位数×30）"
        elif virality_score >= 60:
            tier = "优秀（校准池中位数×10）"
        elif virality_score >= 40:
            tier = "中等（校准池中位数×3）"
        elif virality_score >= 20:
            tier = "一般（校准池中位数×1）"
        else:
            tier = "低迷（校准池中位数×0.3）"
        return {"scheme": "absolute", "prediction": tier, "samples": n}

    else:
        # percentile 桶
        if virality_score >= 85:
            pct = "p95+"
        elif virality_score >= 65:
            pct = "p85-p95"
        elif virality_score >= 40:
            pct = "p60-p85"
        else:
            pct = "<p60"
        return {"scheme": "percentile", "prediction": pct, "samples": n}
