"""新功能单元测试 — bump trigger / notification / calendar / pipeline / ab_experiment / auth / task_queue"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.models.state import CheatState
from backend.app.services.file_io import read_file, safe_write


# ---- Helpers ----


def _write_state(data_dir: Path, state: CheatState) -> None:
    safe_write(data_dir / ".cheat-state.json", state.model_dump_json(indent=2))


def _read_state(data_dir: Path) -> CheatState:
    return CheatState.model_validate_json(read_file(data_dir / ".cheat-state.json"))


# ---- Bump Trigger Conditions ----


class TestBumpTrigger:
    """status_service._check_bump_trigger 测试"""

    def test_consecutive_deviation_trigger(self, initialized_data_dir: Path) -> None:
        """连续 3+ 同向偏差触发 bump"""
        from backend.app.services.status_service import _check_bump_trigger

        data_dir = initialized_data_dir
        state = _read_state(data_dir)
        state.calibration_samples = 5
        _write_state(data_dir, state)

        # 创建 3 个预测文件，全部 overestimated
        preds_dir = data_dir / "predictions"
        for i in range(3):
            content = f"""# 预测: script_{i}

## 预测

综合分：5.0

Bucket: ratio → 1K-5K

## 复盘

> 复盘时间: 2025-01-0{i+1}T12:00:00（T+3d）

### 实际表现
- 播放量: 500
- 点赞: 20
- 评论: 5

### 偏差分析
- 预测准确性: overestimated
- 主要偏差: 测试偏差 {i}
"""
            safe_write(preds_dir / f"script_{i}.md", content)

        state = _read_state(data_dir)
        result = _check_bump_trigger(data_dir, state)
        assert result["triggered"] is True
        assert result["trigger_type"] == "consecutive_deviation"
        assert "3 次同向偏差" in result["reason"]

    def test_10x_deviation_trigger(self, initialized_data_dir: Path) -> None:
        """10x 偏差触发 bump"""
        from backend.app.services.status_service import _check_bump_trigger

        data_dir = initialized_data_dir
        state = _read_state(data_dir)
        state.calibration_samples = 5
        _write_state(data_dir, state)

        # 创建 1 个预测文件，实际播放 >= 10x 预测
        preds_dir = data_dir / "predictions"
        content = """# 预测: script_big

## 预测

综合分：5.0

Bucket: ratio → 500-1K

## 复盘

> 复盘时间: 2025-01-10T12:00:00（T+3d）

### 实际表现
- 播放量: 50000
- 点赞: 2000
- 评论: 500

### 偏差分析
- 预测准确性: underestimated
- 主要偏差: 爆款
"""
        safe_write(preds_dir / "script_big.md", content)

        state = _read_state(data_dir)
        result = _check_bump_trigger(data_dir, state)
        assert result["triggered"] is True
        assert result["trigger_type"] == "10x_deviation"
        assert "10x" in result["reason"]

    def test_no_trigger_when_conditions_not_met(self, initialized_data_dir: Path) -> None:
        """条件不满足时不触发"""
        from backend.app.services.status_service import _check_bump_trigger

        data_dir = initialized_data_dir
        state = _read_state(data_dir)
        state.calibration_samples = 5
        _write_state(data_dir, state)

        # 创建 2 个预测文件，偏差方向不同
        preds_dir = data_dir / "predictions"
        for i, direction in enumerate(["overestimated", "underestimated"]):
            content = f"""# 预测: script_{i}

## 预测

综合分：5.0

Bucket: ratio → 1K-5K

## 复盘

> 复盘时间: 2025-01-0{i+1}T12:00:00（T+3d）

### 实际表现
- 播放量: 3000
- 点赞: 100
- 评论: 20

### 偏差分析
- 预测准确性: {direction}
- 主要偏差: 测试偏差 {i}
"""
            safe_write(preds_dir / f"script_{i}.md", content)

        state = _read_state(data_dir)
        result = _check_bump_trigger(data_dir, state)
        assert result["triggered"] is False

    def test_no_trigger_insufficient_calibration(self, initialized_data_dir: Path) -> None:
        """校准样本不足时不触发"""
        from backend.app.services.status_service import _check_bump_trigger

        data_dir = initialized_data_dir
        state = _read_state(data_dir)
        # calibration_samples = 0 (default)
        _write_state(data_dir, state)

        result = _check_bump_trigger(data_dir, state)
        assert result["triggered"] is False


# ---- Notification Service ----


class TestNotificationService:
    """notification_service 测试"""

    def test_check_pending_retros(self, initialized_data_dir: Path) -> None:
        """check_pending_retros 返回待复盘通知"""
        from backend.app.services.notification_service import check_pending_retros

        data_dir = initialized_data_dir
        state = _read_state(data_dir)
        state.pending_retros = ["script_1|douyin|2025-01-01T10:00:00"]
        _write_state(data_dir, state)

        result = check_pending_retros(data_dir)
        assert len(result) == 1
        assert result[0]["type"] == "pending_retro"
        assert result[0]["script_id"] == "script_1"

    def test_check_pending_retros_empty(self, initialized_data_dir: Path) -> None:
        """无待复盘时返回空列表"""
        from backend.app.services.notification_service import check_pending_retros

        result = check_pending_retros(initialized_data_dir)
        assert result == []

    def test_check_pending_retros_already_retroed(self, initialized_data_dir: Path) -> None:
        """已完成复盘的不出现在待复盘列表"""
        from backend.app.services.notification_service import check_pending_retros

        data_dir = initialized_data_dir
        state = _read_state(data_dir)
        state.pending_retros = ["script_1|douyin|2025-01-01T10:00:00"]
        _write_state(data_dir, state)

        # 创建已复盘的预测文件
        preds_dir = data_dir / "predictions"
        content = """# 预测: script_1

## 预测

综合分：5.0

## 复盘

> 复盘时间: 2025-01-05T12:00:00（T+3d）

### 实际表现
- 播放量: 3000

### 偏差分析
- 预测准确性: accurate
"""
        safe_write(preds_dir / "script_1.md", content)

        result = check_pending_retros(data_dir)
        assert len(result) == 0

    def test_get_notification_summary_counts(self, initialized_data_dir: Path) -> None:
        """get_notification_summary 返回各类计数"""
        from backend.app.services.notification_service import get_notification_summary

        data_dir = initialized_data_dir
        state = _read_state(data_dir)
        state.pending_retros = ["script_1|douyin|2025-01-01T10:00:00"]
        _write_state(data_dir, state)

        result = get_notification_summary(data_dir)
        assert result["pending_retros"] == 1
        assert "bump_suggestions" in result
        assert "low_buffer_warnings" in result
        assert "total_unread" in result

    def test_get_notification_summary_uninitialized(self, tmp_data_dir: Path) -> None:
        """未初始化时返回零计数"""
        from backend.app.services.notification_service import get_notification_summary

        result = get_notification_summary(tmp_data_dir)
        assert result["pending_retros"] == 0
        assert result["total_unread"] == 0

    def test_mark_notification_read(self, initialized_data_dir: Path) -> None:
        """mark_notification_read 持久化已读状态"""
        from backend.app.services.notification_service import (
            get_notification_summary,
            mark_notification_read,
        )

        data_dir = initialized_data_dir
        state = _read_state(data_dir)
        state.pending_retros = ["script_1|douyin|2025-01-01T10:00:00"]
        _write_state(data_dir, state)

        # 标记已读
        result = mark_notification_read(data_dir, "retro-script_1|douyin|2025-01-01T10:00:00")
        assert result["read"] is True

        # 验证持久化
        notif_path = data_dir / "notifications.json"
        assert notif_path.exists()
        data = json.loads(read_file(notif_path))
        assert "retro-script_1|douyin|2025-01-01T10:00:00" in data["read_ids"]

        # 验证 retro 通知不再算 unread
        summary = get_notification_summary(data_dir)
        retro_notifications = [n for n in summary["notifications"] if n["type"] == "pending_retro"]
        assert all(n["id"] in data["read_ids"] for n in retro_notifications)

    def test_mark_notification_read_not_found(self, initialized_data_dir: Path) -> None:
        """标记不存在通知时抛出 ValueError"""
        from backend.app.services.notification_service import mark_notification_read

        with pytest.raises(ValueError):
            mark_notification_read(initialized_data_dir, "nonexistent-id")


# ---- Calendar Service ----


class TestCalendarService:
    """calendar_service 测试"""

    def test_get_calendar_returns_14_days(self, initialized_data_dir: Path) -> None:
        """get_calendar 默认返回 14 天"""
        from backend.app.services.calendar_service import get_calendar

        result = get_calendar(initialized_data_dir)
        assert len(result["days"]) == 14
        # 第一天应该是今天
        assert result["days"][0]["is_today"] is True

    def test_get_calendar_custom_days(self, initialized_data_dir: Path) -> None:
        """get_calendar 支持自定义天数"""
        from backend.app.services.calendar_service import get_calendar

        result = get_calendar(initialized_data_dir, days=7)
        assert len(result["days"]) == 7

    def test_add_schedule(self, initialized_data_dir: Path) -> None:
        """add_schedule 创建排期"""
        from backend.app.services.calendar_service import add_schedule

        # 先创建一个脚本
        safe_write(initialized_data_dir / "scripts" / "test_script.md", "# 测试脚本\n\n内容")

        from datetime import date
        tomorrow = (date.today()).isoformat()
        result = add_schedule(initialized_data_dir, tomorrow, "test_script")
        assert result["script_id"] == "test_script"
        assert result["status"] == "planned"
        assert result["id"].startswith("sch_")

    def test_remove_schedule(self, initialized_data_dir: Path) -> None:
        """remove_schedule 删除排期"""
        from backend.app.services.calendar_service import add_schedule, remove_schedule, _load_schedules

        safe_write(initialized_data_dir / "scripts" / "test_script.md", "# 测试脚本\n\n内容")

        from datetime import date
        tomorrow = (date.today()).isoformat()
        schedule = add_schedule(initialized_data_dir, tomorrow, "test_script")
        schedule_id = schedule["id"]

        # 验证排期已添加
        schedules = _load_schedules(initialized_data_dir)
        assert len(schedules) == 1

        # 删除排期
        remove_schedule(initialized_data_dir, schedule_id)

        # 验证排期已删除
        schedules = _load_schedules(initialized_data_dir)
        assert len(schedules) == 0


# ---- Pipeline Service ----


class TestPipelineService:
    """pipeline_service 测试"""

    def test_get_pipeline_returns_data(self, initialized_data_dir: Path) -> None:
        """get_pipeline 返回管道数据"""
        from backend.app.services.pipeline_service import get_pipeline

        result = get_pipeline(initialized_data_dir)
        assert "pipelines" in result
        assert "stats" in result
        assert "total" in result["stats"]

    def test_pipeline_status_draft(self, initialized_data_dir: Path) -> None:
        """只有脚本时状态为 draft"""
        from backend.app.services.pipeline_service import _compute_pipeline_status

        script = {"id": "test1"}
        result = _compute_pipeline_status(script, [], [], [])
        assert result == "draft"

    def test_pipeline_status_predicted(self, initialized_data_dir: Path) -> None:
        """有预测时状态为 predicted"""
        from backend.app.services.pipeline_service import _compute_pipeline_status

        script = {"id": "test1"}
        predictions = [{"id": "test1", "script_id": "test1"}]
        result = _compute_pipeline_status(script, predictions, [], [])
        assert result == "predicted"

    def test_pipeline_status_published(self, initialized_data_dir: Path) -> None:
        """有发布时状态为 published"""
        from backend.app.services.pipeline_service import _compute_pipeline_status

        script = {"id": "test1"}
        predictions = [{"id": "test1", "script_id": "test1"}]
        publishes = [{"script_id": "test1", "published_at": "2025-01-01"}]
        result = _compute_pipeline_status(script, predictions, publishes, [])
        assert result == "published"

    def test_pipeline_status_completed(self, initialized_data_dir: Path) -> None:
        """有复盘时状态为 completed"""
        from backend.app.services.pipeline_service import _compute_pipeline_status

        script = {"id": "test1"}
        predictions = [{"id": "test1", "script_id": "test1"}]
        publishes = [{"script_id": "test1", "published_at": "2025-01-01"}]
        retros = [{"prediction_id": "test1", "script_id": "test1"}]
        result = _compute_pipeline_status(script, predictions, publishes, retros)
        assert result == "completed"


# ---- A/B Experiment Service ----


class TestABExperimentService:
    """ab_experiment_service 测试"""

    @pytest.mark.asyncio
    async def test_create_experiment(self, initialized_data_dir: Path) -> None:
        """create_experiment 创建实验文件"""
        from backend.app.services.ab_experiment_service import create_experiment

        data_dir = initialized_data_dir
        # 创建两个脚本
        safe_write(data_dir / "scripts" / "script_a.md", "# 脚本 A\n\n内容 A")
        safe_write(data_dir / "scripts" / "script_b.md", "# 脚本 B\n\n内容 B")

        result = await create_experiment(
            data_dir, "测试选题", "script_a", "script_b", "A 比 B 更好"
        )
        assert result["topic"] == "测试选题"
        assert result["status"] == "created"
        assert result["script_a_id"] == "script_a"
        assert result["script_b_id"] == "script_b"

        # 验证文件已创建
        exp_dir = data_dir / "experiments"
        assert exp_dir.exists()
        json_files = list(exp_dir.glob("*.json"))
        assert len(json_files) == 1

    @pytest.mark.asyncio
    async def test_create_experiment_same_script_fails(self, initialized_data_dir: Path) -> None:
        """script_a_id == script_b_id 时抛出 ValueError"""
        from backend.app.services.ab_experiment_service import create_experiment

        with pytest.raises(ValueError, match="不能相同"):
            await create_experiment(
                initialized_data_dir, "测试", "same_id", "same_id", "假设"
            )

    @pytest.mark.asyncio
    async def test_create_experiment_script_not_found(self, initialized_data_dir: Path) -> None:
        """脚本不存在时抛出 FileNotFoundError"""
        from backend.app.services.ab_experiment_service import create_experiment

        safe_write(initialized_data_dir / "scripts" / "script_a.md", "# A")

        with pytest.raises(FileNotFoundError):
            await create_experiment(
                initialized_data_dir, "测试", "script_a", "nonexistent", "假设"
            )

    @pytest.mark.asyncio
    async def test_list_experiments(self, initialized_data_dir: Path) -> None:
        """list_experiments 返回实验列表"""
        from backend.app.services.ab_experiment_service import create_experiment, list_experiments

        data_dir = initialized_data_dir
        safe_write(data_dir / "scripts" / "script_a.md", "# A")
        safe_write(data_dir / "scripts" / "script_b.md", "# B")

        await create_experiment(data_dir, "选题1", "script_a", "script_b", "假设1")
        await create_experiment(data_dir, "选题2", "script_a", "script_b", "假设2")

        result = await list_experiments(data_dir)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_experiments_empty(self, initialized_data_dir: Path) -> None:
        """无实验时返回空列表"""
        from backend.app.services.ab_experiment_service import list_experiments

        result = await list_experiments(initialized_data_dir)
        assert result == []

    @pytest.mark.asyncio
    async def test_complete_experiment(self, initialized_data_dir: Path) -> None:
        """complete_experiment 完成实验"""
        from backend.app.services.ab_experiment_service import (
            complete_experiment,
            create_experiment,
            get_experiment,
        )

        data_dir = initialized_data_dir
        safe_write(data_dir / "scripts" / "script_a.md", "# A")
        safe_write(data_dir / "scripts" / "script_b.md", "# B")

        exp = await create_experiment(data_dir, "选题", "script_a", "script_b", "假设")

        # 手动将状态设为 predicted（跳过 LLM 调用）
        exp["status"] = "predicted"
        exp["prediction_a"] = {"virality": {"virality_score": 70}}
        exp["prediction_b"] = {"virality": {"virality_score": 50}}
        exp_path = data_dir / "experiments" / f"{exp['id']}.json"
        safe_write(exp_path, json.dumps(exp, ensure_ascii=False, indent=2))

        result = await complete_experiment(data_dir, exp["id"], 10000, 5000)
        assert result["status"] == "completed"
        assert result["result"]["actual_winner"] == "A"
        assert result["result"]["predicted_winner"] == "A"
        assert result["result"]["prediction_correct"] is True
        assert result["actual_plays_a"] == 10000
        assert result["actual_plays_b"] == 5000


# ---- Auth Service ----


class TestAuthService:
    """auth_service 测试"""

    def test_verify_password_correct(self) -> None:
        """正确密码验证通过"""
        from backend.app.services.auth_service import verify_password

        with patch("backend.app.config.APP_PASSWORD", "test_pass"):
            assert verify_password("test_pass") is True

    def test_verify_password_incorrect(self) -> None:
        """错误密码验证失败"""
        from backend.app.services.auth_service import verify_password

        with patch("backend.app.config.APP_PASSWORD", "test_pass"):
            assert verify_password("wrong_pass") is False

    def test_verify_password_not_configured(self) -> None:
        """未配置密码时验证失败"""
        from backend.app.services.auth_service import verify_password

        with patch("backend.app.config.APP_PASSWORD", None):
            assert verify_password("any_pass") is False

    def test_create_session(self) -> None:
        """create_session 返回 token 和过期时间"""
        from backend.app.services.auth_service import create_session

        session = create_session()
        assert "token" in session
        assert len(session["token"]) == 64  # 32 bytes hex = 64 chars
        assert "expires_at" in session
        assert session["expires_at"] > int(time.time())

    def test_validate_token_valid(self, tmp_path: Path) -> None:
        """validate_token 验证有效 token"""
        from backend.app.services.auth_service import create_session, save_session, validate_token

        session = create_session()
        save_session(tmp_path, session)
        assert validate_token(tmp_path, session["token"]) is True

    def test_validate_token_invalid(self, tmp_path: Path) -> None:
        """validate_token 验证无效 token"""
        from backend.app.services.auth_service import validate_token

        assert validate_token(tmp_path, "invalid_token") is False

    def test_validate_token_expired(self, tmp_path: Path) -> None:
        """validate_token 验证过期 token"""
        from backend.app.services.auth_service import validate_token

        # 手动写入一个过期 session（绕过 save_session 的清理逻辑）
        import json as _json
        expired_session = {
            "token": "expired_token_123",
            "expires_at": int(time.time()) - 100,  # 已过期
            "created_at": int(time.time()) - 100000,
        }
        sessions_path = tmp_path / "sessions.json"
        safe_write(sessions_path, _json.dumps([expired_session], indent=2))

        assert validate_token(tmp_path, "expired_token_123") is False

    def test_is_auth_configured_true(self) -> None:
        """配置了密码时返回 True"""
        from backend.app.services.auth_service import is_auth_configured

        with patch("backend.app.config.APP_PASSWORD", "test_pass"):
            assert is_auth_configured() is True

    def test_is_auth_configured_false(self) -> None:
        """未配置密码时返回 False"""
        from backend.app.services.auth_service import is_auth_configured

        with patch("backend.app.config.APP_PASSWORD", None):
            assert is_auth_configured() is False


# ---- Task Queue ----


class TestTaskQueue:
    """task_queue 测试"""

    def test_submit_creates_task(self) -> None:
        """submit 创建任务并返回 task_id"""
        from backend.app.services.task_queue import TaskQueue

        q = TaskQueue()
        task_id = q.submit("predict", {"script_id": "test1"})
        assert task_id  # 非空
        assert len(task_id) == 8

        info = q.get_task(task_id)
        assert info is not None
        assert info.task_type == "predict"
        assert info.status.value == "pending"

    def test_get_task_not_found(self) -> None:
        """get_task 返回 None 对于不存在的 task_id"""
        from backend.app.services.task_queue import TaskQueue

        q = TaskQueue()
        assert q.get_task("nonexistent") is None

    def test_list_tasks(self) -> None:
        """list_tasks 返回任务列表"""
        from backend.app.services.task_queue import TaskQueue

        q = TaskQueue()
        q.submit("predict", {"script_id": "test1"})
        q.submit("bump", {"force": False})

        tasks = q.list_tasks()
        assert len(tasks) == 2
        # 应包含必要字段
        for t in tasks:
            assert "task_id" in t
            assert "task_type" in t
            assert "status" in t

    def test_list_tasks_filter_by_type(self) -> None:
        """list_tasks 按 task_type 过滤"""
        from backend.app.services.task_queue import TaskQueue

        q = TaskQueue()
        q.submit("predict", {"script_id": "test1"})
        q.submit("bump", {"force": False})
        q.submit("predict", {"script_id": "test2"})

        predict_tasks = q.list_tasks(task_type="predict")
        assert len(predict_tasks) == 2
        assert all(t["task_type"] == "predict" for t in predict_tasks)

    def test_cancel_pending_task(self) -> None:
        """取消待执行的任务"""
        from backend.app.services.task_queue import TaskQueue

        q = TaskQueue()
        task_id = q.submit("predict", {"script_id": "test1"})
        assert q.cancel_task(task_id) is True

        info = q.get_task(task_id)
        assert info.status.value == "failed"
        assert info.error == "cancelled"

    def test_cancel_non_pending_task(self) -> None:
        """取消非待执行任务返回 False"""
        from backend.app.services.task_queue import TaskQueue, TaskStatus

        q = TaskQueue()
        task_id = q.submit("predict", {"script_id": "test1"})
        info = q.get_task(task_id)
        info.status = TaskStatus.RUNNING  # 模拟运行中
        assert q.cancel_task(task_id) is False
