"""脚本管理回归测试（"新建脚本后列表不显示" Bug 修复验证）。

运行方式（使用团队指定的 venv，不污染项目 data/）：
  PYTHONPATH=/Users/coubann/Documents/cheat-on-content-douyin-online \
  /Users/coubann/.workbuddy/binaries/python/envs/default/bin/python \
  backend/tests/test_scripts_regression.py

本文件仅依赖标准库 + structlog，对 scripts_service 的纯逻辑做回归，
覆盖：正常标题、标题含 /、标题含非法字符、空/纯非法字符、同名脚本重复创建。
（路由层 api/scripts.py 的 try/except 映射需 fastapi/pydantic，见报告说明。）
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# 将项目根目录加入 sys.path，使 `import backend.app...` 可用（backend 为隐式命名空间包）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services import scripts_service  # noqa: E402
from backend.app.errors import PREDICTION_EXISTS  # noqa: E402

# 文件名非法字符集合（路径分隔符是回归重点）
ILLEGAL_CHARS = set('/\\:*?"<>|')


def _is_path_safe(name: str) -> bool:
    """script_id 文件名段不能包含任何路径分隔符/非法字符。"""
    return not any(ch in ILLEGAL_CHARS for ch in name) and "\x00" not in name


class TestSanitizeFilenameSegment(unittest.TestCase):
    """_sanitize_filename_segment 单元测试（纯函数，同步）。"""

    def test_normal_title_unchanged(self):
        self.assertEqual(
            scripts_service._sanitize_filename_segment("夏日爆款引流脚本"),
            "夏日爆款引流脚本",
        )

    def test_slash_replaced(self):
        # 回归核心：标题含 / 必须被替换，否则会生成子目录导致 safe_write 抛 FileNotFoundError
        self.assertEqual(
            scripts_service._sanitize_filename_segment("教程/第1期"),
            "教程_第1期",
        )

    def test_various_illegal_chars_replaced(self):
        for raw, expected in [
            ("a\\b", "a_b"),
            ("a*b", "a_b"),
            ("a:b", "a_b"),
            ('a"b', "a_b"),
            ("a?b", "a_b"),
            ("a<b", "a_b"),
            ("a>b", "a_b"),
            ("a|b", "a_b"),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(scripts_service._sanitize_filename_segment(raw), expected)

    def test_empty_falls_back_to_untitled(self):
        self.assertEqual(scripts_service._sanitize_filename_segment(""), "untitled")

    def test_whitespace_and_dots_fall_back_to_untitled(self):
        # 仅空白/句点清洗后为空，应回退 untitled
        self.assertEqual(scripts_service._sanitize_filename_segment("   "), "untitled")
        self.assertEqual(scripts_service._sanitize_filename_segment("..."), "untitled")
        self.assertEqual(scripts_service._sanitize_filename_segment(" . "), "untitled")

    def test_leading_trailing_dot_stripped(self):
        # 避免文件名以 "." 结尾（macOS 隐藏文件）
        self.assertEqual(scripts_service._sanitize_filename_segment("标题."), "标题")
        self.assertEqual(scripts_service._sanitize_filename_segment(".标题"), "标题")


class TestScriptsServiceRegression(unittest.IsolatedAsyncioTestCase):
    """create_script / list_scripts 回归（使用临时目录，绝不触碰项目 data/）。"""

    async def asyncSetUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scripts_regression_"))
        self.user_id = 1

    async def asyncTearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def test_normal_title_create_and_list_real_title(self):
        """用例1：正常标题 → 创建成功，list 返回真实标题而非内部 id。"""
        result = await scripts_service.create_script(
            self.tmp, self.user_id, "夏日爆款引流脚本", "# 正文内容"
        )
        self.assertEqual(result["title"], "夏日爆款引流脚本")
        self.assertTrue(_is_path_safe(result["id"]))

        scripts = await scripts_service.list_scripts(self.tmp, user_id=self.user_id)
        self.assertEqual(len(scripts), 1)
        self.assertEqual(scripts[0]["id"], result["id"])
        # 关键：列表展示的是用户填写的真实标题，不是内部 id
        self.assertEqual(scripts[0]["title"], "夏日爆款引流脚本")
        self.assertNotEqual(scripts[0]["title"], result["id"])

    async def test_title_with_slash_no_crash_and_listable(self):
        """用例2：标题含 / → 不再 500，清洗后正常创建，list 能列出且 title 为真实标题。"""
        result = await scripts_service.create_script(
            self.tmp, self.user_id, "教程/第1期", "本期内容"
        )
        # 关键：script_id 绝不含路径分隔符（否则 safe_write 会 500）
        self.assertNotIn("/", result["id"])
        self.assertTrue(_is_path_safe(result["id"]))

        scripts = await scripts_service.list_scripts(self.tmp, user_id=self.user_id)
        self.assertEqual(len(scripts), 1)
        # 列表里的 title 是文件首行解析出的真实标题（含 / 也正常展示）
        self.assertEqual(scripts[0]["title"], "教程/第1期")

    async def test_title_with_illegal_chars_creates_safely(self):
        """用例3：标题含 \\ * : 等非法字符 → 清洗后正常创建。"""
        cases = [
            ("反斜杠\\标题", "反斜杠_标题"),
            ("星号*标题", "星号_标题"),
            ("冒号:标题", "冒号_标题"),
            ("引号\"标题", "引号_标题"),
            ("尖括号< >标题", "尖括号_ _标题"),
        ]
        for title, _expected_safe in cases:
            with self.subTest(title=title):
                result = await scripts_service.create_script(
                    self.tmp, self.user_id, title, f"content-{title}"
                )
                self.assertTrue(_is_path_safe(result["id"]))
                scripts = await scripts_service.list_scripts(self.tmp, user_id=self.user_id)
                titles = [s["title"] for s in scripts]
                self.assertIn(title, titles)  # 列表中显示真实标题

    async def test_empty_and_all_illegal_titles_no_error(self):
        """用例4：空标题 / 全为非法字符 → 清洗后不报错，能正常创建并被列出。

        注：实现上仅对「空/纯空白/纯句点」回退 'untitled'；全为非法字符时
        返回下划线占位串（如 '___'）。二者均安全、不崩溃、文件名合法。
        """
        # 空标题
        res_empty = await scripts_service.create_script(self.tmp, self.user_id, "", "空标题内容")
        self.assertIn("untitled", res_empty["id"])
        self.assertTrue(_is_path_safe(res_empty["id"]))

        # 全为非法字符
        res_illegal = await scripts_service.create_script(
            self.tmp, self.user_id, '/\\:*?"<>|', "全非法字符内容"
        )
        self.assertTrue(_is_path_safe(res_illegal["id"]))
        self.assertNotIn("/", res_illegal["id"])

        scripts = await scripts_service.list_scripts(self.tmp, user_id=self.user_id)
        # 两条都成功落盘并被列出
        self.assertEqual(len(scripts), 2)
        ids = [s["id"] for s in scripts]
        self.assertIn(res_empty["id"], ids)
        self.assertIn(res_illegal["id"], ids)

    async def test_duplicate_same_title_and_content_raises_fileexists(self):
        """用例5：同名脚本（相同 content）→ 触发 FileExistsError（路由据此返回 SCRIPT_EXISTS）。"""
        title, content = "重复脚本", "完全相同的内容"
        first = await scripts_service.create_script(self.tmp, self.user_id, title, content)
        self.assertIsNotNone(first)

        with self.assertRaises(FileExistsError) as ctx:
            await scripts_service.create_script(self.tmp, self.user_id, title, content)
        # 异常消息携带 PREDICTION_EXISTS 错误码，供路由映射为 SCRIPT_EXISTS
        self.assertIn(PREDICTION_EXISTS, str(ctx.exception))

    async def test_different_content_same_title_is_allowed(self):
        """回归：相同标题但不同 content 不应被误判为重复（hash 不同 → id 不同）。"""
        await scripts_service.create_script(self.tmp, self.user_id, "同标题", "内容A")
        second = await scripts_service.create_script(self.tmp, self.user_id, "同标题", "内容B")
        self.assertIsNotNone(second)
        scripts = await scripts_service.list_scripts(self.tmp, user_id=self.user_id)
        self.assertEqual(len(scripts), 2)

    async def test_list_parses_real_title_not_internal_id(self):
        """补充：list_scripts 必须从 '# {title}' 解析真实标题，而非用文件名(内部id)当标题。"""
        result = await scripts_service.create_script(
            self.tmp, self.user_id, "我的爆款脚本", "正文"
        )
        scripts = await scripts_service.list_scripts(self.tmp, user_id=self.user_id)
        self.assertEqual(scripts[0]["title"], "我的爆款脚本")
        # 内部 id 形如 日期_hash_标题，绝不等于友好标题
        self.assertNotEqual(scripts[0]["title"], scripts[0]["id"])


if __name__ == "__main__":
    print("=" * 70)
    print("脚本管理回归测试 — 修复: 新建脚本后列表不显示")
    print("venv: /Users/coubann/.workbuddy/binaries/python/envs/default/bin/python")
    print("=" * 70)
    unittest.main(verbosity=2)
