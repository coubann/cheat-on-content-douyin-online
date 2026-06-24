"""M4 测试 — 发布 + 复盘 + immutable 攻击"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.models.state import CheatState
from backend.app.services.file_io import get_prediction_hash, read_file, safe_write
from backend.app.services.publish_service import register_publish, register_shoot
from backend.app.services.retro_service import retro_predict


class TestPublishService:
    """发布服务测试"""

    @pytest.mark.asyncio
    async def test_register_shoot(self, initialized_data_dir: Path) -> None:
        """登记拍摄"""
        from backend.app.services.scripts_service import create_script

        created = await create_script(initialized_data_dir, "拍摄测试", "原始脚本内容")
        result = await register_shoot(initialized_data_dir, created["id"], "拍摄稿内容，和脚本不同")

        assert result["diff_ratio"] > 0
        assert result["needs_v2"] is True or result["needs_v2"] is False
        assert (initialized_data_dir / "videos" / f"{created['id']}.md").exists()

    @pytest.mark.asyncio
    async def test_register_publish(self, initialized_data_dir: Path) -> None:
        """发布登记"""
        from backend.app.services.scripts_service import create_script

        created = await create_script(initialized_data_dir, "发布测试", "内容")
        await register_shoot(initialized_data_dir, created["id"], "拍摄稿")

        result = await register_publish(
            initialized_data_dir, created["id"], "douyin", "https://example.com"
        )

        assert result["platform"] == "douyin"
        assert result["calibration_samples"] >= 1

    @pytest.mark.asyncio
    async def test_publish_updates_state(self, initialized_data_dir: Path) -> None:
        """发布后 state 正确更新"""
        from backend.app.services.scripts_service import create_script

        created = await create_script(initialized_data_dir, "state测试", "内容")
        await register_shoot(initialized_data_dir, created["id"], "拍摄稿")
        await register_publish(initialized_data_dir, created["id"], "douyin")

        state = CheatState.model_validate_json(read_file(initialized_data_dir / ".cheat-state.json"))
        assert created["id"] not in state.shoots
        assert state.calibration_samples >= 1
        assert len(state.pending_retros) >= 1


class TestRetroService:
    """复盘服务测试"""

    @pytest.mark.asyncio
    async def test_retro_appends_to_prediction(self, initialized_data_dir: Path) -> None:
        """复盘追加到预测文件，不修改 ## 预测 段"""
        # 创建一个带预测段的文件
        pred_dir = initialized_data_dir / "predictions"
        pred_dir.mkdir(parents=True, exist_ok=True)

        pred_id = "test_retro_001"
        pred_content = """# Prediction: test

## 预测

这是预测内容，不可修改。

## 复盘

> 在 T+3d 后追加此段。记录实际表现与预测的偏差。
> （尚未复盘）
"""
        safe_write(pred_dir / f"{pred_id}.md", pred_content)
        original_hash = get_prediction_hash(pred_content)

        mock_deviation = {
            "prediction_accuracy": "underestimated",
            "key_deviation": "实际播放远超预测",
            "lessons": ["钩子比预期强"],
            "rubric_observation": "HP 权重可能需要提高",
            "bump_trigger": False,
        }

        with patch("backend.app.services.retro_service.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_deviation
            result = await retro_predict(
                initialized_data_dir, pred_id, actual_plays=5000, actual_likes=200
            )

        assert result["retro_written"] is True

        # 验证 ## 预测 段未被修改
        new_content = read_file(pred_dir / f"{pred_id}.md")
        new_hash = get_prediction_hash(new_content)
        assert original_hash == new_hash, "复盘写入导致预测段被修改！"

        # 验证 ## 复盘 段存在
        assert "实际播放" in new_content
        assert "5000" in new_content

    @pytest.mark.asyncio
    async def test_retro_removes_from_pending(self, initialized_data_dir: Path) -> None:
        """复盘后从 pending_retros 移除"""
        # 设置 state 有 pending_retros
        state_path = initialized_data_dir / ".cheat-state.json"
        state = CheatState.model_validate_json(read_file(state_path))
        state.pending_retros = ["test_retro_002|douyin|2024-01-01"]
        safe_write(state_path, state.model_dump_json(indent=2))

        # 创建预测文件
        pred_dir = initialized_data_dir / "predictions"
        pred_dir.mkdir(parents=True, exist_ok=True)
        safe_write(pred_dir / "test_retro_002.md", "## 预测\n\n预测内容\n\n## 复盘\n\n> 占位\n")

        with patch("backend.app.services.retro_service.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "prediction_accuracy": "accurate",
                "key_deviation": "无",
                "lessons": [],
                "rubric_observation": "",
                "bump_trigger": False,
            }
            await retro_predict(initialized_data_dir, "test_retro_002", actual_plays=1000)

        state = CheatState.model_validate_json(read_file(state_path))
        assert "test_retro_002|douyin|2024-01-01" not in state.pending_retros

    @pytest.mark.asyncio
    async def test_retro_updates_rubric_memo(self, initialized_data_dir: Path) -> None:
        """复盘更新 rubric-memo.md"""
        pred_dir = initialized_data_dir / "predictions"
        pred_dir.mkdir(parents=True, exist_ok=True)
        safe_write(pred_dir / "test_memo.md", "## 预测\n\n预测\n\n## 复盘\n\n> 占位\n")

        with patch("backend.app.services.retro_service.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "prediction_accuracy": "underestimated",
                "key_deviation": "偏差大",
                "lessons": ["教训1"],
                "rubric_observation": "HP 权重低",
                "bump_trigger": False,
            }
            await retro_predict(initialized_data_dir, "test_memo", actual_plays=8000)

        memo = read_file(initialized_data_dir / "rubric-memo.md")
        assert "8000" in memo  # rubric-memo 允许包含真实数据
