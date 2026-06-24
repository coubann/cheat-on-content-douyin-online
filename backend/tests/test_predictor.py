"""predictor 单元测试 + 预测流程集成测试"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.models.state import CheatState, DimensionScore, RubricWeights, ScoreResult
from backend.app.services.predictor import _generate_diagnosis, _predict_bucket


class TestPredictorDiagnosis:
    """诊断报告生成测试"""

    def test_diagnosis_identifies_risks(self) -> None:
        """低分维度被识别为风险"""
        dims = [
            DimensionScore(dimension="ER", score=5, confidence=0.9, reason="", self_check=""),
            DimensionScore(dimension="HP", score=0, confidence=0.8, reason="", self_check=""),
            DimensionScore(dimension="TS", score=0, confidence=0.7, reason="", self_check=""),
            DimensionScore(dimension="CC", score=3, confidence=0.6, reason="", self_check=""),
        ]
        score_result = ScoreResult(dimensions=dims, composite=4.0, rubric_version="v0")
        diagnosis = _generate_diagnosis(score_result, topic_heat=0.2, platform_fit=0.5, benchmark_sim=0.5)

        assert len(diagnosis["risks"]) >= 2
        assert any("钩子" in r for r in diagnosis["risks"])
        assert any("分享" in r for r in diagnosis["risks"])

    def test_diagnosis_identifies_highlights(self) -> None:
        """高分维度被识别为亮点"""
        dims = [
            DimensionScore(dimension="ER", score=5, confidence=0.9, reason="", self_check=""),
            DimensionScore(dimension="HP", score=5, confidence=0.9, reason="", self_check=""),
            DimensionScore(dimension="QL", score=5, confidence=0.9, reason="", self_check=""),
        ]
        score_result = ScoreResult(dimensions=dims, composite=9.0, rubric_version="v0")
        diagnosis = _generate_diagnosis(score_result, topic_heat=0.8, platform_fit=0.8, benchmark_sim=0.8)

        assert len(diagnosis["highlights"]) >= 2
        assert any("情感共鸣" in h for h in diagnosis["highlights"])

    def test_strongest_weakest(self) -> None:
        """正确识别最强和最弱维度"""
        dims = [
            DimensionScore(dimension="ER", score=5, confidence=0.9, reason="", self_check=""),
            DimensionScore(dimension="HP", score=0, confidence=0.8, reason="", self_check=""),
        ]
        score_result = ScoreResult(dimensions=dims, composite=5.0, rubric_version="v0")
        diagnosis = _generate_diagnosis(score_result, topic_heat=0.5, platform_fit=0.5, benchmark_sim=0.5)

        assert diagnosis["strongest_dimension"]["dimension"] == "ER"
        assert diagnosis["weakest_dimension"]["dimension"] == "HP"


class TestBucketPrediction:
    """Bucket 预测测试"""

    def test_ratio_bucket_few_samples(self) -> None:
        state = CheatState(calibration_samples=2)
        bucket = _predict_bucket(state, 65.0)
        assert bucket["scheme"] == "ratio"
        assert bucket["samples"] == 2

    def test_ratio_bucket_high_score(self) -> None:
        state = CheatState(calibration_samples=0)
        bucket = _predict_bucket(state, 80.0)
        assert "3x" in bucket["prediction"]

    def test_ratio_bucket_low_score(self) -> None:
        state = CheatState(calibration_samples=0)
        bucket = _predict_bucket(state, 20.0)
        assert "<0.5x" in bucket["prediction"]

    def test_absolute_bucket(self) -> None:
        state = CheatState(calibration_samples=7)
        bucket = _predict_bucket(state, 65.0)
        assert bucket["scheme"] == "absolute"

    def test_percentile_bucket(self) -> None:
        state = CheatState(calibration_samples=15)
        bucket = _predict_bucket(state, 90.0)
        assert bucket["scheme"] == "percentile"
        assert "p95" in bucket["prediction"]


class TestPredictService:
    """预测流程集成测试（mock LLM）"""

    @pytest.mark.asyncio
    async def test_full_predict_creates_file(self, initialized_data_dir: Path) -> None:
        """完整预测流程创建预测文件"""
        from backend.app.services.scripts_service import create_script
        from backend.app.services.file_io import read_file
        from backend.app.services.blind_scorer import DIMENSIONS

        # 创建脚本
        created = await create_script(initialized_data_dir, "测试", "测试内容")

        mock_score_result = ScoreResult(
            dimensions=[
                DimensionScore(dimension=d, score=3, confidence=0.8, reason="test", self_check="test")
                for d in DIMENSIONS
            ],
            composite=6.0,
            rubric_version="v0",
        )

        mock_virality_result = {
            "virality_score": 60.0,
            "breakdown": {"rubric_contribution": 36.0, "topic_heat_contribution": 9.0,
                          "platform_fit_contribution": 6.0, "benchmark_similarity_contribution": 9.0},
            "sub_scores": {"rubric_normalized": 0.6, "topic_heat": 0.6,
                           "platform_fit": 0.6, "benchmark_similarity": 0.6},
            "diagnosis": {
                "strongest_dimension": {"dimension": "ER", "score": 3},
                "weakest_dimension": {"dimension": "HP", "score": 3},
                "risks": ["测试风险"],
                "highlights": ["测试亮点"],
                "composite": 6.0,
            },
            "suggestions": [{"priority": "high", "target_dimension": "HP", "action": "改钩子", "expected_impact": "+1.2"}],
            "bucket": {"scheme": "ratio", "prediction": "1.5-3x", "samples": 0},
            "phase": "phase1",
        }

        with patch("backend.app.services.predict_service.blind_score", new_callable=AsyncMock) as mock_score, \
             patch("backend.app.services.predict_service.predict_virality", new_callable=AsyncMock) as mock_viral:
            mock_score.return_value = mock_score_result.model_dump()
            mock_viral.return_value = mock_virality_result

            from backend.app.services.predict_service import full_predict

            result = await full_predict(initialized_data_dir, created["id"])

            assert result["prediction_id"] == created["id"]
            assert result["virality"]["virality_score"] == 60.0

            # 验证预测文件存在
            pred_path = initialized_data_dir / "predictions" / f"{created['id']}.md"
            assert pred_path.exists()

            # 验证预测文件包含 ## 预测 段
            content = read_file(pred_path)
            assert "## 预测" in content
            assert "IMMUTABLE" in content
            assert "## 复盘" in content
