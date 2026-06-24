"""M3 服务单元测试 — style_mimic / comment_miner / trends"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.services.style_mimic import import_benchmark, list_benchmarks, mimic_style
from backend.app.services.comment_miner import analyze_comments, recommend_candidates
from backend.app.services.trends_service import fetch_trends, match_trends_to_niche


class TestStyleMimic:
    """风格模仿服务测试"""

    @pytest.mark.asyncio
    async def test_list_benchmarks_empty(self, initialized_data_dir: Path) -> None:
        """空对标列表"""
        result = await list_benchmarks(initialized_data_dir)
        assert result == []

    @pytest.mark.asyncio
    async def test_import_benchmark(self, initialized_data_dir: Path) -> None:
        """导入对标账号"""
        mock_fingerprint = {
            "fingerprint_text": "犀利观点型博主",
            "traits": {"tone": "犀利", "opening_style": "反问开头"},
            "patterns": ["你知道吗？", "问题在于"],
        }

        with patch("backend.app.services.style_mimic.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_fingerprint
            result = await import_benchmark(
                initialized_data_dir, "测试博主", "douyin", ["样本1", "样本2"]
            )

        assert result["account"] == "测试博主"
        assert result["platform"] == "douyin"
        assert (initialized_data_dir / "benchmarks").exists()

    @pytest.mark.asyncio
    async def test_mimic_not_found(self, initialized_data_dir: Path) -> None:
        """模仿未导入的账号"""
        result = await mimic_style(initialized_data_dir, "不存在", "焦虑话题")
        assert "error" in result


class TestCommentMiner:
    """评论挖掘服务测试"""

    @pytest.mark.asyncio
    async def test_analyze_comments(self, initialized_data_dir: Path) -> None:
        """分析评论"""
        mock_result = {
            "clusters": [
                {
                    "theme": "职场焦虑",
                    "representative_comments": ["太焦虑了"],
                    "topic_suggestion": "如何应对职场焦虑",
                    "potential": "high",
                    "reasoning": "高频话题",
                }
            ],
            "audience_insight": "受众以职场新人为主",
            "content_gap": "缺少实操建议",
        }

        with patch("backend.app.services.comment_miner.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_result
            result = await analyze_comments(
                initialized_data_dir, "video_001", ["太焦虑了", "我也是", "怎么办"]
            )

        assert result["video_id"] == "video_001"
        assert len(result["clusters"]) == 1

    @pytest.mark.asyncio
    async def test_recommend_candidates_empty(self, initialized_data_dir: Path) -> None:
        """空选题池推荐"""
        with patch("backend.app.services.comment_miner.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"recommendations": []}
            result = await recommend_candidates(initialized_data_dir)
        assert "candidates" in result


class TestTrendsService:
    """热点服务测试"""

    @pytest.mark.asyncio
    async def test_fetch_trends(self, initialized_data_dir: Path) -> None:
        """抓取热点"""
        mock_result = {
            "trends": [
                {
                    "platform": "douyin",
                    "topic": "AI焦虑",
                    "heat_level": "hot",
                    "description": "AI替代工作引发焦虑",
                    "related_keywords": ["AI", "焦虑"],
                    "content_angle": "从焦虑到行动",
                    "competition_level": "medium",
                }
            ]
        }

        with patch("backend.app.services.trends_service.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_result
            result = await fetch_trends(initialized_data_dir, ["douyin-hot"], "泛知识")

        assert len(result["trends"]) == 1
        assert result["trends"][0]["topic"] == "AI焦虑"

    @pytest.mark.asyncio
    async def test_match_trends_empty(self, initialized_data_dir: Path) -> None:
        """空热点列表匹配"""
        result = await match_trends_to_niche(initialized_data_dir, [], "泛知识")
        assert result == []
