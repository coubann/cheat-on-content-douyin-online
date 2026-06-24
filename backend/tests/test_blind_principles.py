"""blind 原则攻击测试 — 验证盲预测不可变性和 rubric 泄露防护"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.file_io import (
    get_prediction_hash,
    verify_prediction_immutability,
)
from backend.app.services.leak_guard import RubricLeakError, check_rubric_leak


class TestPredictionImmutability:
    """测试预测段不可变性"""

    def test_prediction_hash_extracted(self) -> None:
        """能正确提取 `## 预测` 段的 hash"""
        content = """# Test

## 预测

这是预测内容，不可修改。

## 复盘

这是复盘内容。
"""
        h = get_prediction_hash(content)
        assert h != "", "应该能提取到预测段的 hash"

    def test_prediction_hash_empty_when_no_section(self) -> None:
        """没有 `## 预测` 段时返回空字符串"""
        content = "# Test\n\n没有预测段\n"
        h = get_prediction_hash(content)
        assert h == ""

    def test_immutability_pass_when_same(self) -> None:
        """预测段不变时验证通过"""
        content = """## 预测

原始预测内容。

## 复盘

追加的复盘。
"""
        original_hash = get_prediction_hash(content)
        assert verify_prediction_immutability(original_hash, content) is True

    def test_immutability_fail_when_modified(self) -> None:
        """预测段被修改时验证失败"""
        original = """## 预测

原始预测内容。

## 复盘

复盘。
"""
        modified = """## 预测

被篡改的预测内容！

## 复盘

复盘。
"""
        original_hash = get_prediction_hash(original)
        assert verify_prediction_immutability(original_hash, modified) is False

    def test_append_retro_does_not_change_prediction_hash(self) -> None:
        """追加复盘段不改变预测段 hash"""
        original = """## 预测

原始预测内容。
"""
        original_hash = get_prediction_hash(original)

        appended = """## 预测

原始预测内容。

## 复盘

T+3d 复盘：实际播放 5000，预测 3000。
"""
        assert verify_prediction_immutability(original_hash, appended) is True


class TestRubricLeakGuard:
    """测试 rubric 泄露防护"""

    def test_clean_content_passes(self) -> None:
        """干净内容通过检查"""
        content = "# Rubric Notes\n\nER 维度：情感共鸣评分\n"
        check_rubric_leak(content)  # 不应抛异常

    def test_detects_play_count(self) -> None:
        """检测到播放数 → RUBRIC_LEAK_DETECTED"""
        content = "该视频获得了 5000播放"
        with pytest.raises(RubricLeakError) as exc_info:
            check_rubric_leak(content)
        assert exc_info.value.code == "RUBRIC_LEAK_DETECTED"

    def test_detects_wan_unit(self) -> None:
        """检测到万/w 单位 → RUBRIC_LEAK_DETECTED"""
        for bad in ["10w", "3.2万", "100W"]:
            with pytest.raises(RubricLeakError):
                check_rubric_leak(f"播放量 {bad}")

    def test_detects_likes(self) -> None:
        """检测到赞数 → RUBRIC_LEAK_DETECTED"""
        content = "获得了 800赞"
        with pytest.raises(RubricLeakError):
            check_rubric_leak(content)

    def test_detects_comments(self) -> None:
        """检测到评论数 → RUBRIC_LEAK_DETECTED"""
        content = "有 200评论"
        with pytest.raises(RubricLeakError):
            check_rubric_leak(content)

    def test_detects_shares(self) -> None:
        """检测到分享数 → RUBRIC_LEAK_DETECTED"""
        content = "被 50分享"
        with pytest.raises(RubricLeakError):
            check_rubric_leak(content)

    def test_detects_followers(self) -> None:
        """检测到粉丝数 → RUBRIC_LEAK_DETECTED"""
        content = "涨了 5000粉丝"
        with pytest.raises(RubricLeakError):
            check_rubric_leak(content)

    def test_generic_numbers_allowed(self) -> None:
        """通用数字（不带单位）允许通过"""
        content = "维度评分 3 分，权重 1.0"
        check_rubric_leak(content)  # 不应抛异常
