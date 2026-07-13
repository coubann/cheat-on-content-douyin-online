"""草稿管理服务 — scripts CRUD"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.services.file_io import read_file, safe_write

logger = structlog.get_logger()


async def list_scripts(data_dir: Path, user_id: int = 0) -> list[dict[str, Any]]:
    """列出所有草稿

    Pre-conditions:
      - scripts/ 目录存在
    Post-conditions:
      - 返回草稿列表
    Side effects:
      - 无
    """
    scripts_dir = data_dir / str(user_id) / "scripts"
    if not scripts_dir.exists():
        return []

    scripts: list[dict[str, Any]] = []
    for f in sorted(scripts_dir.glob("*.md")):
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
        scripts.append({
            "id": f.stem,
            "title": title,
            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size_bytes": stat.st_size,
        })
    return scripts


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
    date_str = datetime.now().strftime("%Y-%m-%d")
    hash_prefix = hashlib.sha256(content.encode()).hexdigest()[:8]
    safe_title = _sanitize_filename_segment(title)
    script_id = f"{date_str}_{hash_prefix}_{safe_title[:20]}"

    script_path = scripts_dir / f"{script_id}.md"
    if script_path.exists():
        raise FileExistsError(f"{PREDICTION_EXISTS}: 脚本已存在 {script_id}")

    # 写入脚本（带 header）
    full_content = f"""# {title}

> 创建时间: {datetime.now().isoformat()}

---

{content}
"""
    safe_write(script_path, full_content)

    logger.info("script_created", script_id=script_id, user_id=user_id)
    return {"id": script_id, "title": title, "path": str(script_path)}


async def get_script(data_dir: Path, script_id: str, user_id: int = 0) -> dict[str, Any]:
    """获取草稿详情

    Pre-conditions:
      - scripts/<id>.md 存在
    Post-conditions:
      - 返回草稿内容
    Side effects:
      - 无
    Error codes:
      - SCRIPT_NOT_FOUND: 脚本不存在
    """
    script_path = data_dir / str(user_id) / "scripts" / f"{script_id}.md"
    content = read_file(script_path)
    stat = script_path.stat()

    return {
        "id": script_id,
        "content": content,
        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


async def update_script(data_dir: Path, script_id: str, content: str, user_id: int = 0) -> dict[str, Any]:
    """更新草稿

    Pre-conditions:
      - scripts/<id>.md 存在
    Post-conditions:
      - 脚本内容被更新（原子替换）
    Side effects:
      - 写文件系统
    Error codes:
      - SCRIPT_NOT_FOUND: 脚本不存在
    """
    script_path = data_dir / str(user_id) / "scripts" / f"{script_id}.md"
    # 验证文件存在
    read_file(script_path)
    safe_write(script_path, content)

    logger.info("script_updated", script_id=script_id, user_id=user_id)
    return {"id": script_id, "updated": True}


async def delete_script(data_dir: Path, script_id: str, user_id: int = 0) -> dict[str, Any]:
    """删除草稿

    Pre-conditions:
      - scripts/<id>.md 存在
    Post-conditions:
      - 脚本文件被删除
    Side effects:
      - 删除文件系统
    Error codes:
      - SCRIPT_NOT_FOUND: 脚本不存在
    """
    from backend.app.errors import SCRIPT_NOT_FOUND

    script_path = data_dir / str(user_id) / "scripts" / f"{script_id}.md"
    if not script_path.exists():
        raise FileNotFoundError(f"{SCRIPT_NOT_FOUND}: {script_id}")

    script_path.unlink()
    logger.info("script_deleted", script_id=script_id, user_id=user_id)
    return {"id": script_id, "deleted": True}
