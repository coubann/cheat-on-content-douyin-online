"""rubric leak guard — rubric_notes.md 写操作必须过此检查"""

from __future__ import annotations

import re

from backend.app.errors import RUBRIC_LEAK_DETECTED

# 禁止模式：数字 + 中文单位（如 10w / 5000播放 / 800赞 / 3.2万）
_LEAK_PATTERNS = [
    r"\d+[\.\d]*\s*[万wW]\b",          # 10w, 3.2万
    r"\d+[\.\d]*\s*播放",
    r"\d+[\.\d]*\s*赞",
    r"\d+[\.\d]*\s*评论",
    r"\d+[\.\d]*\s*转发",
    r"\d+[\.\d]*\s*粉丝",
    r"\d+[\.\d]*\s*收藏",
    r"\d+[\.\d]*\s*分享",
]


def check_rubric_leak(content: str) -> None:
    """检查 rubric_notes.md 内容是否泄露真实数据

    Pre-conditions:
      - content 是待写入 rubric_notes.md 的文本
    Post-conditions:
      - 通过检查则正常返回
    Side effects:
      - 无
    Error codes:
      - RUBRIC_LEAK_DETECTED: 内容包含真实数据泄露
    """
    for pattern in _LEAK_PATTERNS:
        match = re.search(pattern, content)
        if match:
            raise RubricLeakError(
                RUBRIC_LEAK_DETECTED,
                f"rubric_notes.md 禁止包含真实数据：发现 '{match.group()}'",
            )


class RubricLeakError(Exception):
    """rubric 泄露异常"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
