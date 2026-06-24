"""conftest — 测试配置和共享 fixtures"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

# 设置测试环境变量（在 import 之前）
os.environ["APP_ENV"] = "test"
os.environ["DEEPSEEK_API_KEY"] = "sk-test-placeholder"
os.environ["DEFAULT_LLM_PROVIDER"] = "deepseek"


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """创建临时数据目录（带脚手架文件）"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def initialized_data_dir(tmp_data_dir: Path) -> Path:
    """创建已初始化的数据目录"""
    from backend.app.models.state import CheatState
    from backend.app.services.file_io import safe_write

    data_dir = tmp_data_dir

    # 创建目录
    for subdir in ["scripts", "predictions", "videos", "samples"]:
        (data_dir / subdir).mkdir(parents=True, exist_ok=True)

    # 创建 state
    state = CheatState()
    safe_write(data_dir / ".cheat-state.json", state.model_dump_json(indent=2))

    # 创建 rubric_notes.md
    safe_write(data_dir / "rubric_notes.md", "# Rubric Notes\n\n测试用 rubric\n")

    # 创建 rubric-memo.md
    safe_write(data_dir / "rubric-memo.md", "# Rubric Memo\n\n测试用 memo\n")

    # 创建 candidates.md
    safe_write(data_dir / "candidates.md", "# 选题池\n")

    return data_dir
