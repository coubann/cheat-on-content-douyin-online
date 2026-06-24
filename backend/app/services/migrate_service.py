"""Schema 迁移服务 — cheat-migrate 的 Python 实现

当数据合约（.cheat-state.json、rubric_notes.md 等）的 schema 发生变更时，
此服务负责将旧版数据迁移到新版。

迁移原则：
1. 迁移前自动备份
2. 迁移是幂等的（重复执行不会出错）
3. 每个版本迁移有独立的迁移函数
4. 迁移失败时回滚到备份
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.services.file_io import read_file, safe_write

logger = structlog.get_logger()

# 当前 schema 版本
CURRENT_SCHEMA_VERSION = "1.4-ext"

# 迁移函数注册表：key = 从版本, value = 迁移函数
_MIGRATIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def register_migration(from_version: str):
    """迁移函数注册装饰器"""
    def decorator(fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
        _MIGRATIONS[from_version] = fn
        return fn
    return decorator


@register_migration("1.0")
def _migrate_1_0_to_1_1(state: dict[str, Any]) -> dict[str, Any]:
    """1.0 → 1.1: 添加 TS/MS/CC 维度权重"""
    weights = state.get("rubric_weights", {})
    for dim in ["TS", "MS", "CC"]:
        if dim not in weights:
            weights[dim] = 1.0
    state["rubric_weights"] = weights
    state["schema_version"] = "1.1"
    return state


@register_migration("1.1")
def _migrate_1_1_to_1_2(state: dict[str, Any]) -> dict[str, Any]:
    """1.1 → 1.2: 添加 enabled_trend_sources"""
    if "enabled_trend_sources" not in state:
        state["enabled_trend_sources"] = ["douyin-hot", "xhs-explore"]
    state["schema_version"] = "1.2"
    return state


@register_migration("1.2")
def _migrate_1_2_to_1_3(state: dict[str, Any]) -> dict[str, Any]:
    """1.2 → 1.3: 添加 your_project_version"""
    if "your_project_version" not in state:
        state["your_project_version"] = "0.1.0"
    state["schema_version"] = "1.3"
    return state


@register_migration("1.3")
def _migrate_1_3_to_1_4_ext(state: dict[str, Any]) -> dict[str, Any]:
    """1.3 → 1.4-ext: 添加 hooks_installed"""
    if "hooks_installed" not in state:
        state["hooks_installed"] = False
    state["schema_version"] = "1.4-ext"
    return state


def migrate(data_dir: Path, target_version: str | None = None) -> dict[str, Any]:
    """执行 schema 迁移

    Pre-conditions:
      - .cheat-state.json 存在
    Post-conditions:
      - .cheat-state.json 被迁移到目标版本
      - 备份文件被创建在 data_dir/backups/
      - 返回迁移结果
    Side effects:
      - 写文件系统
      - 创建备份
    Error codes:
      - 无（迁移失败时回滚）
    """
    logger.info("migrate_start", target_version=target_version)

    state_path = data_dir / ".cheat-state.json"
    if not state_path.exists():
        return {"status": "no_state", "message": ".cheat-state.json 不存在"}

    # 读取当前 state
    state = json.loads(read_file(state_path))
    current_version = state.get("schema_version", "1.0")
    target = target_version or CURRENT_SCHEMA_VERSION

    if current_version == target:
        return {"status": "already_current", "current_version": current_version}

    # 备份
    backup_dir = data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"cheat-state_{timestamp}_v{current_version}.json"
    shutil.copy2(state_path, backup_path)
    logger.info("migrate_backup_created", path=str(backup_path))

    # 执行迁移链
    migrated_state = state
    migrations_applied: list[str] = []
    original_version = current_version

    try:
        while migrated_state.get("schema_version", "1.0") != target:
            version = migrated_state.get("schema_version", "1.0")
            if version not in _MIGRATIONS:
                logger.warning("migrate_no_path", from_version=version, target=target)
                break

            migrated_state = _MIGRATIONS[version](migrated_state)
            migrations_applied.append(f"{version} → {migrated_state['schema_version']}")

        # 写入迁移后的 state
        safe_write(state_path, json.dumps(migrated_state, indent=2, ensure_ascii=False))

        logger.info(
            "migrate_complete",
            original_version=original_version,
            new_version=migrated_state.get("schema_version"),
            migrations=migrations_applied,
        )

        return {
            "status": "ok",
            "original_version": original_version,
            "new_version": migrated_state.get("schema_version"),
            "migrations_applied": migrations_applied,
            "backup_path": str(backup_path),
        }

    except Exception as e:
        # 回滚
        shutil.copy2(backup_path, state_path)
        logger.error("migrate_failed_rollback", error=str(e))
        return {
            "status": "failed",
            "error": str(e),
            "rollback": True,
            "backup_path": str(backup_path),
        }


def get_migration_status(data_dir: Path) -> dict[str, Any]:
    """获取迁移状态

    Pre-conditions:
      - .cheat-state.json 存在
    Post-conditions:
      - 返回当前版本和可用迁移
    Side effects:
      - 无
    """
    state_path = data_dir / ".cheat-state.json"
    if not state_path.exists():
        return {"status": "no_state"}

    state = json.loads(read_file(state_path))
    current_version = state.get("schema_version", "1.0")

    # 计算待执行的迁移
    pending: list[str] = []
    v = current_version
    while v in _MIGRATIONS:
        v = _MIGRATIONS[v]({"schema_version": v}).get("schema_version", v)
        pending.append(v)

    return {
        "current_version": current_version,
        "target_version": CURRENT_SCHEMA_VERSION,
        "needs_migration": current_version != CURRENT_SCHEMA_VERSION,
        "pending_migrations": pending,
        "available_migrations": list(_MIGRATIONS.keys()),
    }
