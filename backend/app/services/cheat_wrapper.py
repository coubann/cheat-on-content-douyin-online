"""cheat-on-content CLI 封装 — 通过子进程调用原生子 skill

cheat-on-content/ 目录是 submodule（只读），本模块通过 CLI 调用它，
不直接修改其内部文件。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import structlog

from backend.app.config import CHEAT_CONTENT_DIR, DATA_DIR

logger = structlog.get_logger()


class CheatWrapper:
    """封装 cheat-on-content CLI 调用

    Pre-conditions:
      - cheat-on-content/ 目录存在且包含 skills/
      - DATA_DIR 已初始化（.cheat-state.json 存在）
    Post-conditions:
      - CLI 输出被解析为结构化数据返回
    Side effects:
      - 可能写文件系统（通过 CLI）
    Error codes:
      - CHEAT_CLI_NOT_FOUND: cheat-on-content 目录不存在
      - CHEAT_CLI_FAILED: CLI 执行失败
    """

    def __init__(self, cheat_dir: Path | None = None, data_dir: Path | None = None) -> None:
        self.cheat_dir = cheat_dir or CHEAT_CONTENT_DIR
        self.data_dir = data_dir or DATA_DIR

    def _ensure_dirs(self) -> None:
        """确保必要目录存在"""
        if not self.cheat_dir.exists():
            raise CheatCLIError(
                "CHEAT_CLI_NOT_FOUND",
                f"cheat-on-content 目录不存在: {self.cheat_dir}",
            )
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def _run_skill(self, skill_name: str, args: list[str] | None = None) -> str:
        """调用 cheat-on-content 的 skill CLI

        cheat-on-content 的 skill 是 Claude Code 的 SKILL.md 文件，
        不是传统 CLI。这里预留 CLI 接口，当上游提供 CLI 入口时可直接对接。
        目前返回提示信息。

        Pre-conditions:
          - cheat_dir 存在
        Post-conditions:
          - 返回 CLI stdout
        Side effects:
          - 子进程执行
        Error codes:
          - CHEAT_CLI_FAILED: 执行失败
        """
        self._ensure_dirs()
        args = args or []

        # 检查是否有 CLI 入口脚本
        cli_script = self.cheat_dir / "cli.py"
        if not cli_script.exists():
            logger.warning(
                "cheat_cli_not_available",
                skill=skill_name,
                msg="cheat-on-content CLI not available, using Python fallback",
            )
            return json.dumps({"status": "fallback", "skill": skill_name})

        try:
            cmd = ["python3", str(cli_script), skill_name, *args]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.data_dir),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                error_msg = stderr.decode().strip()
                logger.error("cheat_cli_failed", skill=skill_name, error=error_msg)
                raise CheatCLIError("CHEAT_CLI_FAILED", f"Skill {skill_name} 执行失败: {error_msg}")

            return stdout.decode().strip()

        except TimeoutError:
            raise CheatCLIError("CHEAT_CLI_FAILED", f"Skill {skill_name} 执行超时（120s）") from None

    async def init(self, answers: dict[str, Any]) -> dict[str, Any]:
        """调用 cheat-init

        Pre-conditions:
          - DATA_DIR 为空或未初始化
        Post-conditions:
          - .cheat-state.json 被创建
          - rubric_notes.md / rubric-memo.md / script_patterns.md 被创建
          - scripts/ predictions/ videos/ samples/ 目录被创建
        Side effects:
          - 写文件系统
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info("cheat_init_start", answers=answers)

        # 直接用 Python 实现初始化逻辑（不依赖 CLI）
        from backend.app.services.init_service import initialize_project

        result = await initialize_project(self.data_dir, answers)
        logger.info("cheat_init_complete")
        return result

    async def score(self, script_id: str) -> dict[str, Any]:
        """调用 cheat-score — 委托 blind_scorer"""
        from backend.app.services.blind_scorer import score_script

        return await score_script(self.data_dir, script_id)

    async def status(self) -> dict[str, Any]:
        """调用 cheat-status — 读取状态看板"""
        from backend.app.services.status_service import get_status

        return await get_status(self.data_dir)


class CheatCLIError(Exception):
    """cheat-on-content CLI 异常"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
