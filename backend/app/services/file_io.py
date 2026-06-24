"""原子文件 I/O 工具 — 所有写操作必须走此模块"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import structlog

logger = structlog.get_logger()


def safe_write(path: Path, content: str) -> None:
    """原子替换写文件：write to *.tmp → os.replace

    Pre-conditions:
      - 父目录必须存在
    Post-conditions:
      - 文件被完整写入，不会出现半写状态
    Side effects:
      - 写文件系统
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
    logger.info("safe_write", path=str(path))


def read_file(path: Path) -> str:
    """读文件，返回内容

    Error codes:
      - FILE_NOT_FOUND: 文件不存在
    """
    if not path.exists():
        from backend.app.errors import FILE_NOT_FOUND
        raise FileNotFoundError(f"{FILE_NOT_FOUND}: {path}")
    return path.read_text(encoding="utf-8")


def get_prediction_hash(content: str) -> str:
    """提取 `## 预测` 段的 hash，用于 immutability 校验"""
    match = re.search(r"^## 预测\s*\n(.*?)(?=^## |\Z)", content, re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    # 去掉尾部空白，确保 hash 只基于内容本身
    body = match.group(1).rstrip()
    return hashlib.sha256(body.encode()).hexdigest()[:12]


def verify_prediction_immutability(original_hash: str, new_content: str) -> bool:
    """验证新内容中 `## 预测` 段是否与原 hash 一致

    Returns:
      True = 一致（安全），False = 被篡改（拒绝写入）
    """
    new_hash = get_prediction_hash(new_content)
    if not original_hash and not new_hash:
        return True
    return original_hash == new_hash
