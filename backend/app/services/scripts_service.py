"""草稿管理服务 — scripts CRUD"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import structlog

from backend.app.services.file_io import read_file, safe_write

# 中国标准时间（UTC+8）。中国无夏令时，使用固定偏移即可，
# 同时可避免 Docker 镜像缺少 tzdata / 系统时区数据导致的问题。
CST = timezone(timedelta(hours=8))

# 系统默认/共享脚本空间：历史脚本在隔离机制启用前创建于此（user_id=0），
# 所有已登录用户都应能查看；新建脚本仍写入各自 user_id 目录。
DEFAULT_USER_ID = 0

logger = structlog.get_logger()


def _read_script_meta(f: Path) -> dict[str, Any]:
    """读取单个脚本文件的元信息（id/title/created_at/updated_at/size_bytes）。

    Pre-conditions:
      - f 为已存在的 .md 文件
    Post-conditions:
      - 返回脚本元信息字典
    Side effects:
      - 无
    """
    stat = f.stat()
    # 默认用文件名（脚本 id）作为标题，再从 Markdown 首行 "# {title}" 解析真实标题，
    # 保证列表展示的是用户填写的标题，而非内部 id。
    title = f.stem
    try:
        with open(f, "r", encoding="utf-8") as fh:
            first_line = fh.readline()
        if first_line.startswith("# "):
            title = first_line[2:].strip()
    except (OSError, UnicodeDecodeError):
        pass
    return {
        "id": f.stem,
        "title": title,
        "created_at": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).astimezone(CST).isoformat(),
        "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone(CST).isoformat(),
        "size_bytes": stat.st_size,
    }


def _resolve_script_path(data_dir: Path, script_id: str, user_id: int) -> Path:
    """解析脚本文件路径：优先当前用户空间，若不存在则回退系统默认空间（user_id=0）。

    历史脚本创建于隔离机制启用前（位于 DEFAULT_USER_ID 空间），已登录用户（user_id>=1）
    需要能查看/编辑/删除这些脚本；自己的脚本则始终优先本用户目录。

    Pre-conditions:
      - data_dir 存在
    Post-conditions:
      - 返回脚本的绝对路径（可能不存在，交由调用方的 read_file 判定）
    Side effects:
      - 无
    """
    user_path = data_dir / str(user_id) / "scripts" / f"{script_id}.md"
    if user_path.exists():
        return user_path
    return data_dir / str(DEFAULT_USER_ID) / "scripts" / f"{script_id}.md"


async def list_scripts(data_dir: Path, user_id: int = 0) -> list[dict[str, Any]]:
    """列出所有草稿（合并当前用户空间与系统默认/共享空间）。

    合并「当前用户空间」（data/{user_id}/scripts）与「系统默认/共享空间」
    （data/{DEFAULT_USER_ID}/scripts）下的脚本；当 user_id 本身等于 DEFAULT_USER_ID
    时不重复合并自己。按 script_id 去重（用户自己的优先），最后统一按 created_at 倒序返回。

    Pre-conditions:
      - data_dir 存在
    Post-conditions:
      - 返回草稿列表（含历史共享脚本）
    Side effects:
      - 无
    """
    seen_ids: set[str] = set()
    merged: list[dict[str, Any]] = []

    # 1) 先放当前用户自己的空间（优先）
    user_dir = data_dir / str(user_id) / "scripts"
    if user_dir.exists():
        for f in sorted(user_dir.glob("*.md")):
            meta = _read_script_meta(f)
            if meta["id"] in seen_ids:
                continue
            seen_ids.add(meta["id"])
            merged.append(meta)

    # 2) 再合并系统默认/共享空间（仅补充当前用户没有的脚本，避免重复）
    if user_id != DEFAULT_USER_ID:
        default_dir = data_dir / str(DEFAULT_USER_ID) / "scripts"
        if default_dir.exists():
            for f in sorted(default_dir.glob("*.md")):
                meta = _read_script_meta(f)
                if meta["id"] in seen_ids:
                    continue
                seen_ids.add(meta["id"])
                merged.append(meta)

    # 3) 统一按 created_at 倒序（ISO 字符串同 +08:00 偏移下字典序即时间序）
    merged.sort(key=lambda s: s["created_at"], reverse=True)
    return merged


def _sanitize_filename_segment(title: str) -> str:
    """清洗用于文件名的标题片段，确保绝不含任何文件系统路径分隔符

    仅影响 script_id 的文件名段，不改变写入文件的 content 内容。

    Pre-conditions:
      - title 为任意字符串
    Post-conditions:
      - 返回不含路径分隔符 / 非法字符的字符串
    Side effects:
      - 无
    """
    # 替换 Unix/Windows 路径分隔符、非法字符以及控制字符为下划线
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', "_", title)
    # 去除首尾空白与句点，避免以 "." 结尾或清洗后为空名
    cleaned = cleaned.strip().strip(".")
    return cleaned or "untitled"


async def create_script(data_dir: Path, user_id: int, title: str, content: str) -> dict[str, Any]:
    """新建草稿

    Pre-conditions:
      - scripts/ 目录存在
      - 同名脚本不存在
    Post-conditions:
      - scripts/<id>.md 被创建
    Side effects:
      - 写文件系统
    Error codes:
      - SCRIPT_NOT_FOUND: 目录不存在
      - PREDICTION_EXISTS: 同名脚本已存在
    """
    from backend.app.errors import PREDICTION_EXISTS

    scripts_dir = data_dir / str(user_id) / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    # 生成 ID：日期 + hash 前8位
    # 注意：title 必须先做路径安全清洗，否则含 "/" 等字符时会生成非法文件名，
    # 导致 safe_write 因父目录不存在抛 FileNotFoundError 而 500（见 Bug A）。
    date_str = datetime.now(CST).strftime("%Y-%m-%d")
    hash_prefix = hashlib.sha256(content.encode()).hexdigest()[:8]
    safe_title = _sanitize_filename_segment(title)
    script_id = f"{date_str}_{hash_prefix}_{safe_title[:20]}"

    script_path = scripts_dir / f"{script_id}.md"
    if script_path.exists():
        raise FileExistsError(f"{PREDICTION_EXISTS}: 脚本已存在 {script_id}")

    # 写入脚本（带 header）
    full_content = f"""# {title}

> 创建时间: {datetime.now(CST).isoformat()}

---

{content}
"""
    safe_write(script_path, full_content)

    logger.info("script_created", script_id=script_id, user_id=user_id)
    return {"id": script_id, "title": title, "path": str(script_path)}


async def get_script(data_dir: Path, script_id: str, user_id: int = 0) -> dict[str, Any]:
    """获取草稿详情

    路径查找先查当前用户空间，若不存在则回退系统默认空间（历史脚本）。

    Pre-conditions:
      - scripts/<id>.md 存在（本用户空间或默认空间）
    Post-conditions:
      - 返回草稿内容
    Side effects:
      - 无
    Error codes:
      - SCRIPT_NOT_FOUND: 脚本不存在
    """
    script_path = _resolve_script_path(data_dir, script_id, user_id)
    content = read_file(script_path)
    stat = script_path.stat()

    return {
        "id": script_id,
        "content": content,
        "created_at": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).astimezone(CST).isoformat(),
        "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone(CST).isoformat(),
    }


async def update_script(data_dir: Path, script_id: str, content: str, user_id: int = 0) -> dict[str, Any]:
    """更新草稿

    路径查找先查当前用户空间，若不存在则回退系统默认空间（历史脚本）。

    Pre-conditions:
      - scripts/<id>.md 存在（本用户空间或默认空间）
    Post-conditions:
      - 脚本内容被更新（原子替换）
    Side effects:
      - 写文件系统
    Error codes:
      - SCRIPT_NOT_FOUND: 脚本不存在
    """
    script_path = _resolve_script_path(data_dir, script_id, user_id)
    # 验证文件存在
    read_file(script_path)
    safe_write(script_path, content)

    logger.info("script_updated", script_id=script_id, user_id=user_id)
    return {"id": script_id, "updated": True}


async def delete_script(data_dir: Path, script_id: str, user_id: int = 0) -> dict[str, Any]:
    """删除草稿

    路径查找先查当前用户空间，若不存在则回退系统默认空间（历史脚本）。

    Pre-conditions:
      - scripts/<id>.md 存在（本用户空间或默认空间）
    Post-conditions:
      - 脚本文件被删除
    Side effects:
      - 删除文件系统
    Error codes:
      - SCRIPT_NOT_FOUND: 脚本不存在
    """
    from backend.app.errors import SCRIPT_NOT_FOUND

    script_path = _resolve_script_path(data_dir, script_id, user_id)
    if not script_path.exists():
        raise FileNotFoundError(f"{SCRIPT_NOT_FOUND}: {script_id}")

    script_path.unlink()
    logger.info("script_deleted", script_id=script_id, user_id=user_id)
    return {"id": script_id, "deleted": True}
