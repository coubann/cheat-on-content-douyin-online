"""基础服务单元测试"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.file_io import read_file, safe_write
from backend.app.services.init_service import initialize_project
from backend.app.services.scripts_service import (
    create_script,
    get_script,
    list_scripts,
    update_script,
)
from backend.app.services.status_service import get_status, get_today


class TestFileIO:
    """文件 I/O 测试"""

    def test_safe_write_creates_file(self, tmp_path: Path) -> None:
        """safe_write 正确创建文件"""
        f = tmp_path / "test.md"
        safe_write(f, "hello")
        assert f.read_text() == "hello"

    def test_safe_write_atomic_replace(self, tmp_path: Path) -> None:
        """safe_write 原子替换已存在的文件"""
        f = tmp_path / "test.md"
        safe_write(f, "old")
        safe_write(f, "new")
        assert f.read_text() == "new"
        # 不应有 .tmp 残留
        assert not (tmp_path / "test.md.tmp").exists()

    def test_read_file_not_found(self, tmp_path: Path) -> None:
        """读取不存在的文件抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            read_file(tmp_path / "nonexistent.md")


class TestInitService:
    """初始化服务测试"""

    @pytest.mark.asyncio
    async def test_initialize_creates_all_files(self, tmp_data_dir: Path) -> None:
        """初始化创建所有脚手架文件"""
        result = await initialize_project(tmp_data_dir, {
            "content_form": "opinion-video",
            "platforms": ["douyin"],
        })

        assert result["status"] == "initialized"
        assert (tmp_data_dir / ".cheat-state.json").exists()
        assert (tmp_data_dir / "rubric_notes.md").exists()
        assert (tmp_data_dir / "rubric-memo.md").exists()
        assert (tmp_data_dir / "scripts").is_dir()
        assert (tmp_data_dir / "predictions").is_dir()
        assert (tmp_data_dir / "videos").is_dir()
        assert (tmp_data_dir / "samples").is_dir()

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, tmp_data_dir: Path) -> None:
        """重复初始化返回 already_initialized"""
        await initialize_project(tmp_data_dir, {"platforms": ["douyin"]})
        result = await initialize_project(tmp_data_dir, {"platforms": ["douyin"]})
        assert result["status"] == "already_initialized"


class TestScriptsService:
    """草稿服务测试"""

    @pytest.mark.asyncio
    async def test_create_and_list_scripts(self, initialized_data_dir: Path) -> None:
        """创建草稿后能列出"""
        await create_script(initialized_data_dir, "测试标题", "测试内容")
        scripts = await list_scripts(initialized_data_dir)
        assert len(scripts) == 1
        assert "测试标题" in scripts[0]["id"]

    @pytest.mark.asyncio
    async def test_get_script(self, initialized_data_dir: Path) -> None:
        """获取草稿详情"""
        created = await create_script(initialized_data_dir, "详情测试", "详情内容")
        result = await get_script(initialized_data_dir, created["id"])
        assert "详情内容" in result["content"]

    @pytest.mark.asyncio
    async def test_update_script(self, initialized_data_dir: Path) -> None:
        """更新草稿"""
        created = await create_script(initialized_data_dir, "更新测试", "旧内容")
        await update_script(initialized_data_dir, created["id"], "新内容")
        result = await get_script(initialized_data_dir, created["id"])
        assert "新内容" in result["content"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_script(self, initialized_data_dir: Path) -> None:
        """获取不存在的草稿抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            await get_script(initialized_data_dir, "nonexistent")


class TestStatusService:
    """状态看板服务测试"""

    @pytest.mark.asyncio
    async def test_status_uninitialized(self, tmp_data_dir: Path) -> None:
        """未初始化时返回 initialized=False"""
        result = await get_status(tmp_data_dir)
        assert result["initialized"] is False

    @pytest.mark.asyncio
    async def test_status_initialized(self, initialized_data_dir: Path) -> None:
        """已初始化时返回完整状态"""
        result = await get_status(initialized_data_dir)
        assert result["initialized"] is True
        assert result["buffer_color"] == "red"  # 0 shoots
        assert result["confidence_level"] == "none"  # 0 samples

    @pytest.mark.asyncio
    async def test_today_todos(self, initialized_data_dir: Path) -> None:
        """今日 todo 返回任务列表"""
        result = await get_today(initialized_data_dir)
        assert "todos" in result
        assert len(result["todos"]) > 0
