"""M5 测试 — bump + LightGBM Phase 2 + 复盘报告"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.models.state import CheatState, RubricWeights
from backend.app.services.file_io import read_file, safe_write


@pytest.fixture
def calibrated_data_dir(initialized_data_dir: Path) -> Path:
    """创建带校准池的数据目录（5 篇已复盘样本）"""
    data_dir = initialized_data_dir

    # 更新 state 为 5 个校准样本
    state = CheatState.model_validate_json(read_file(data_dir / ".cheat-state.json"))
    state.calibration_samples = 5
    safe_write(data_dir / ".cheat-state.json", state.model_dump_json(indent=2))

    # 创建 5 个已复盘的预测文件
    preds_dir = data_dir / "predictions"
    for i in range(5):
        pred_content = f"""# 预测: script_{i}

## 输入快照

脚本: script_{i}

## 预测

综合分：{3.0 + i * 0.5}

维度得分:
- ER: {3 if i % 2 == 0 else 5}
- HP: {5 if i % 2 == 0 else 3}
- QL: 3
- NA: 3
- AB: 3
- SR: 3
- SAT: 0
- TS: {5 if i > 2 else 3}
- MS: 3
- CC: 3

sub_scores:
- topic_heat: 0.6
- platform_fit: 0.5
- benchmark_sim: 0.4

## 复盘

> 复盘时间: 2025-01-0{i+1}T12:00:00（T+3d）

### 实际表现
- 播放量: {1000 + i * 2000}
- 点赞: {50 + i * 100}
- 评论: {10 + i * 20}

### 偏差分析
- 预测准确性: {'accurate' if i == 2 else 'underestimated' if i > 2 else 'overestimated'}
- 主要偏差: 测试偏差 {i}
"""
        safe_write(preds_dir / f"script_{i}.md", pred_content)

    # 创建对应的脚本文件
    scripts_dir = data_dir / "scripts"
    for i in range(5):
        safe_write(scripts_dir / f"script_{i}.md", f"# 脚本 {i}\n\n这是测试脚本 {i} 的内容。")

    return data_dir


# ---- Bump Service Tests ----


class TestBumpService:
    """bump_service 测试"""

    def test_collect_calibration_pool(self, calibrated_data_dir: Path) -> None:
        from backend.app.services.bump_service import _collect_calibration_pool

        pool = _collect_calibration_pool(calibrated_data_dir)
        assert len(pool) == 5
        # 应该包含 script_id 和 actual_plays
        for item in pool:
            assert "script_id" in item
            assert "actual_plays" in item
            assert item["actual_plays"] > 0

    def test_compute_rankings(self) -> None:
        from backend.app.services.bump_service import _compute_rankings

        pool = [
            {"script_id": "a", "old_composite": 5.0},
            {"script_id": "b", "old_composite": 3.0},
            {"script_id": "c", "old_composite": 7.0},
        ]
        rankings = _compute_rankings(pool, "old_composite")
        assert rankings == ["c", "a", "b"]

    def test_ranking_consistency_perfect(self) -> None:
        from backend.app.services.bump_service import _compute_ranking_consistency

        old = ["a", "b", "c", "d"]
        new = ["a", "b", "c", "d"]
        assert _compute_ranking_consistency(old, new) == 1.0

    def test_ranking_consistency_reversed(self) -> None:
        from backend.app.services.bump_service import _compute_ranking_consistency

        old = ["a", "b", "c", "d"]
        new = ["d", "c", "b", "a"]
        assert _compute_ranking_consistency(old, new) == 0.0

    def test_ranking_consistency_partial(self) -> None:
        from backend.app.services.bump_service import _compute_ranking_consistency

        old = ["a", "b", "c", "d", "e"]
        new = ["a", "c", "b", "d", "e"]  # b 和 c 交换
        consistency = _compute_ranking_consistency(old, new)
        assert 0.5 < consistency < 1.0  # 大部分一致

    def test_bump_version(self) -> None:
        from backend.app.services.bump_service import _bump_version

        assert _bump_version("v0") == "v1"
        assert _bump_version("v1") == "v2"
        assert _bump_version("v5") == "v6"
        assert _bump_version("custom") == "v1"

    def test_parse_weights(self) -> None:
        from backend.app.services.bump_service import _parse_weights

        raw = {"ER": 1.5, "HP": 2.0, "QL": 0.3, "NA": "invalid"}
        weights = _parse_weights(raw)
        assert weights.ER == 1.5
        assert weights.HP == 2.0
        assert weights.QL == 0.5  # clamped to min 0.5
        assert weights.NA == 1.0  # fallback to default

    @pytest.mark.asyncio
    async def test_bump_insufficient_samples(self, initialized_data_dir: Path) -> None:
        from backend.app.services.bump_service import BumpError, execute_bump

        with pytest.raises(BumpError) as exc_info:
            await execute_bump(initialized_data_dir)
        assert exc_info.value.code == "BUMP_INSUFFICIENT_SAMPLES"

    @pytest.mark.asyncio
    async def test_bump_rejected_low_consistency(self, calibrated_data_dir: Path) -> None:
        """测试 bump 被拒（排序一致性低）"""
        from backend.app.services.bump_service import execute_bump

        # Mock LLM 提议（正常返回）
        mock_propose = AsyncMock(return_value={
            "new_weights": {"ER": 2.0, "HP": 2.5, "QL": 1.0, "NA": 1.0, "AB": 1.0, "SR": 1.0, "SAT": 0.5, "TS": 2.0, "MS": 1.0, "CC": 1.5},
            "weight_reasoning": "test",
            "rubric_diff": "",
            "observations": [],
        })

        # Mock blind_scorer（返回完全不同的分数，导致排序不一致）
        mock_score = AsyncMock(return_value={
            "dimensions": [
                {"dimension": d, "score": 0, "confidence": 0.5, "reason": "test", "self_check": "test"}
                for d in ["ER", "HP", "QL", "NA", "AB", "SR", "SAT", "TS", "MS", "CC"]
            ],
            "composite": 0.0,
            "rubric_version": "v0",
        })

        with patch("backend.app.services.bump_service.call_llm_json", mock_propose), \
             patch("backend.app.services.bump_service.score_script", mock_score):
            result = await execute_bump(calibrated_data_dir)
            assert result["status"] == "rejected"
            assert result["consistency"] < 0.8

    @pytest.mark.asyncio
    async def test_bump_accepted(self, calibrated_data_dir: Path) -> None:
        """测试 bump 通过（排序一致）"""
        from backend.app.services.bump_service import execute_bump

        mock_propose = AsyncMock(return_value={
            "new_weights": {"ER": 1.5, "HP": 1.5, "QL": 1.0, "NA": 1.0, "AB": 1.0, "SR": 1.0, "SAT": 1.0, "TS": 1.5, "MS": 1.0, "CC": 1.0},
            "weight_reasoning": "test",
            "rubric_diff": "### v1 修订\n- 新增测试规则",
            "observations": [],
        })

        # Mock blind_scorer 返回与旧分排序一致的分数
        async def mock_score_fn(data_dir, script_id, weights=None):
            # 保持与旧分排序一致
            idx = int(script_id.split("_")[1])
            composite = 3.0 + idx * 0.5
            return {
                "dimensions": [
                    {"dimension": d, "score": 3, "confidence": 0.5, "reason": "test", "self_check": "test"}
                    for d in ["ER", "HP", "QL", "NA", "AB", "SR", "SAT", "TS", "MS", "CC"]
                ],
                "composite": composite,
                "rubric_version": "v1",
            }

        with patch("backend.app.services.bump_service.call_llm_json", mock_propose), \
             patch("backend.app.services.bump_service.score_script", mock_score_fn):
            result = await execute_bump(calibrated_data_dir)
            assert result["status"] == "accepted"
            assert result["new_version"] == "v1"
            assert result["consistency"] >= 0.8

            # 验证 state 被更新
            state = CheatState.model_validate_json(read_file(calibrated_data_dir / ".cheat-state.json"))
            assert state.rubric_version == "v1"

    @pytest.mark.asyncio
    async def test_bump_rubric_leak_rejected(self, calibrated_data_dir: Path) -> None:
        """测试 bump 因 rubric 泄露被拒 — 需要一致性通过后触发 leak guard"""
        from backend.app.services.bump_service import BumpError, execute_bump

        mock_propose = AsyncMock(return_value={
            "new_weights": {"ER": 1.5, "HP": 1.5, "QL": 1.0, "NA": 1.0, "AB": 1.0, "SR": 1.0, "SAT": 1.0, "TS": 1.5, "MS": 1.0, "CC": 1.0},
            "weight_reasoning": "test",
            "rubric_diff": "这条规则来自 10w 播放的经验",  # 泄露真实数据
            "observations": [],
        })

        # Mock blind_scorer 返回与旧分排序一致的分数（让一致性通过）
        async def mock_score_fn(data_dir, script_id, weights=None):
            idx = int(script_id.split("_")[1])
            composite = 3.0 + idx * 0.5
            return {
                "dimensions": [
                    {"dimension": d, "score": 3, "confidence": 0.5, "reason": "test", "self_check": "test"}
                    for d in ["ER", "HP", "QL", "NA", "AB", "SR", "SAT", "TS", "MS", "CC"]
                ],
                "composite": composite,
                "rubric_version": "v1",
            }

        with patch("backend.app.services.bump_service.call_llm_json", mock_propose), \
             patch("backend.app.services.bump_service.score_script", mock_score_fn):
            with pytest.raises(BumpError) as exc_info:
                await execute_bump(calibrated_data_dir)
            assert exc_info.value.code == "RUBRIC_LEAK_DETECTED"


# ---- LightGBM Phase 2 Tests ----


class TestPhase2:
    """LightGBM Phase 2 预测引擎测试"""

    def test_build_features(self) -> None:
        from backend.app.services.predictor import _build_features
        from datetime import datetime

        dims = {"ER": 3, "HP": 5, "QL": 0, "NA": 3, "AB": 3, "SR": 3, "SAT": 0, "TS": 5, "MS": 3, "CC": 3}
        features = _build_features(dims, 5.0, 0.7, 0.5, 0.6, 500, datetime(2025, 1, 15, 14, 0))

        assert len(features) == 17
        assert features[0] == 3  # ER
        assert features[1] == 5  # HP
        assert features[10] == 5.0  # composite
        assert features[11] == 0.7  # topic_heat
        assert features[14] == 500  # content_length
        assert features[15] == 14  # hour
        assert features[16] == 2  # weekday (Wed)

    def test_should_retrain_no_meta(self, tmp_path: Path) -> None:
        from backend.app.services.predictor import _should_retrain

        meta_path = tmp_path / "meta.json"
        assert _should_retrain(meta_path, 5) is True

    def test_should_retrain_enough_new_samples(self, tmp_path: Path) -> None:
        from backend.app.services.predictor import _should_retrain

        meta_path = tmp_path / "meta.json"
        meta_path.write_text(json.dumps({"trained_samples": 5}))
        assert _should_retrain(meta_path, 8) is True  # 8-5=3 >= 3
        assert _should_retrain(meta_path, 7) is False  # 7-5=2 < 3

    def test_load_calibration_pool_empty(self, initialized_data_dir: Path) -> None:
        from backend.app.services.predictor import _load_calibration_pool

        pool = _load_calibration_pool(initialized_data_dir)
        assert pool == []

    def test_load_calibration_pool_with_retros(self, calibrated_data_dir: Path) -> None:
        from backend.app.services.predictor import _load_calibration_pool

        pool = _load_calibration_pool(calibrated_data_dir)
        assert len(pool) == 5
        # 所有项都应有 actual_plays
        for item in pool:
            assert item["actual_plays"] > 0

    @pytest.mark.asyncio
    async def test_phase1_fallback_when_no_samples(self, initialized_data_dir: Path) -> None:
        """无校准样本时走 Phase 1"""
        from backend.app.models.state import DimensionScore, ScoreResult
        from backend.app.services.predictor import predict_virality

        score_result = ScoreResult(
            dimensions=[
                DimensionScore(dimension=d, score=3, confidence=0.8, reason="test", self_check="test")
                for d in ["ER", "HP", "QL", "NA", "AB", "SR", "SAT", "TS", "MS", "CC"]
            ],
            composite=6.0,
            rubric_version="v0",
        )
        state = CheatState.model_validate_json(read_file(initialized_data_dir / ".cheat-state.json"))

        # 创建脚本
        safe_write(initialized_data_dir / "scripts" / "test1.md", "# 测试脚本\n\n测试内容")

        mock_topic = AsyncMock(return_value={"topic_heat": 0.6})
        mock_platform = AsyncMock(return_value={"platform_fit": 0.5})
        mock_bench = AsyncMock(return_value={"benchmark_similarity": 0.4})
        mock_suggest = AsyncMock(return_value={"suggestions": []})

        with patch("backend.app.services.predictor.call_llm_json") as mock_llm:
            mock_llm.side_effect = [mock_topic.return_value, mock_platform.return_value, mock_bench.return_value, mock_suggest.return_value]
            result = await predict_virality(initialized_data_dir, "test1", score_result, state)
            assert result["phase"] == "phase1"
            assert 0 <= result["virality_score"] <= 100


# ---- Retro Report Tests ----


class TestRetroReport:
    """自动化复盘报告测试"""

    def test_collect_retros(self, calibrated_data_dir: Path) -> None:
        from backend.app.services.retro_report_service import _collect_retros

        retros = _collect_retros(calibrated_data_dir)
        assert len(retros) == 5
        for r in retros:
            assert "script_id" in r
            assert "actual_plays" in r
            assert "prediction_accuracy" in r

    def test_compute_stats(self) -> None:
        from backend.app.services.retro_report_service import _compute_stats

        retros = [
            {"script_id": "a", "prediction_accuracy": "accurate", "actual_plays": 1000, "actual_likes": 50, "composite": 5.0, "dimensions": {}},
            {"script_id": "b", "prediction_accuracy": "overestimated", "actual_plays": 500, "actual_likes": 20, "composite": 7.0, "dimensions": {}},
            {"script_id": "c", "prediction_accuracy": "underestimated", "actual_plays": 5000, "actual_likes": 200, "composite": 3.0, "dimensions": {}},
        ]
        stats = _compute_stats(retros)
        assert stats["total"] == 3
        assert abs(stats["accuracy_rate"] - 1/3) < 0.01
        assert stats["accuracy_distribution"]["overestimated"] == 1
        assert stats["plays"]["max"] == 5000

    def test_rank(self) -> None:
        from backend.app.services.retro_report_service import _rank

        values = [3.0, 1.0, 2.0, 5.0, 4.0]
        ranks = _rank(values)
        # 1.0→1, 2.0→2, 3.0→3, 4.0→4, 5.0→5
        assert ranks == [3.0, 1.0, 2.0, 5.0, 4.0]

    def test_rank_with_ties(self) -> None:
        from backend.app.services.retro_report_service import _rank

        values = [3.0, 3.0, 1.0]
        ranks = _rank(values)
        # ascending: 1.0→rank1, 3.0→rank2.5 (tied)
        assert ranks[0] == ranks[1]  # tied values get same rank
        assert ranks[2] == 1.0  # smallest value gets lowest rank number

    @pytest.mark.asyncio
    async def test_generate_report_no_data(self, initialized_data_dir: Path) -> None:
        from backend.app.services.retro_report_service import generate_retro_report

        result = await generate_retro_report(initialized_data_dir)
        assert result["status"] == "no_data"

    @pytest.mark.asyncio
    async def test_generate_report_with_data(self, calibrated_data_dir: Path) -> None:
        from backend.app.services.retro_report_service import generate_retro_report

        mock_insights = AsyncMock(return_value={
            "overall_assessment": "测试评估",
            "key_findings": ["发现1"],
            "rubric_recommendation": "建议",
            "content_strategy": "策略",
            "next_bump_trigger": "5篇后",
            "risk_warnings": [],
        })

        with patch("backend.app.services.retro_report_service.call_llm_json", mock_insights):
            result = await generate_retro_report(calibrated_data_dir)
            assert result["status"] == "ok"
            assert result["summary"]["total_retros"] == 5
            assert "accuracy" in result
            assert "dimension_analysis" in result
            assert "llm_insights" in result

            # 验证报告文件被创建
            reports_dir = calibrated_data_dir / "reports"
            assert reports_dir.exists()
            # 应该有 .md 和 .json 两个文件
            md_files = list(reports_dir.glob("retro_*.md"))
            json_files = list(reports_dir.glob("retro_*.json"))
            assert len(md_files) == 1
            assert len(json_files) == 1
