"""默认/共享脚本空间回归测试（历史脚本隔离可见性修复）。

背景：隔离机制启用前，所有脚本都创建在 user_id=0（系统默认/游客空间）
data/0/scripts/ 下；启用后真实用户为 user_id=1~9，按 data/<本用户id>/scripts
读取自然为空。本测试验证：已登录用户能重新看到 user_id=0 下的历史脚本，
同时新建脚本仍写入各自 user_id 目录（隔离语义不变）。

运行方式：
  PYTHONPATH=/Users/coubann/Documents/cheat-on-content-douyin-online \
  /Users/coubann/.workbuddy/binaries/python/envs/default/bin/python \
  backend/tests/test_scripts_default_space.py

全程使用临时目录，绝不污染项目 data/。
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services import scripts_service  # noqa: E402


class TestDefaultSpaceMerge(unittest.IsolatedAsyncioTestCase):
    """验证 list/get/create 对默认空间(user_id=0)历史脚本的合并与回退。"""

    async def asyncSetUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scripts_default_space_"))
        # 预置：系统默认空间(user_id=0)下一历史脚本
        default_dir = self.tmp / "0" / "scripts"
        default_dir.mkdir(parents=True, exist_ok=True)
        (default_dir / "历史脚本.md").write_text("# 历史脚本\n\n历史正文\n", encoding="utf-8")
        # 预置：用户 3 自己空间下一脚本
        user_dir = self.tmp / "3" / "scripts"
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "我的脚本.md").write_text("# 我的脚本\n\n我的正文\n", encoding="utf-8")

    async def asyncTearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def test_list_merge_user_and_default_space_no_dup(self):
        """user_id=3 应能同时看到 历史脚本(0空间) 与 我的脚本(3空间)，且不重复。"""
        scripts = await scripts_service.list_scripts(self.tmp, user_id=3)
        ids = [s["id"] for s in scripts]
        titles = [s["title"] for s in scripts]

        self.assertIn("历史脚本", ids, "历史脚本(默认空间)应被合并进列表")
        self.assertIn("我的脚本", ids, "用户自己的脚本应仍在列表")
        self.assertEqual(len(ids), len(set(ids)), "不应出现重复 id")
        self.assertIn("历史脚本", titles)
        self.assertIn("我的脚本", titles)

    async def test_get_script_falls_back_to_default_space(self):
        """get_script 对历史脚本(0空间)应能回退取到，且 title 解析正确。"""
        detail = await scripts_service.get_script(self.tmp, "历史脚本", user_id=3)
        self.assertEqual(detail["id"], "历史脚本")
        self.assertEqual(detail["content"].lstrip().startswith("# 历史脚本"), True)
        # 文件头首行解析出的真实标题应出现在内容中，确认取到了正确文件
        self.assertIn("历史脚本", detail["content"])
        # created_at 应为东八区
        self.assertTrue(detail["created_at"].endswith("+08:00"))

    async def test_list_user_zero_only_own_space_no_self_merge(self):
        """user_id=0 时只返回 0 空间内容，不重复合并自己。"""
        scripts = await scripts_service.list_scripts(self.tmp, user_id=0)
        ids = [s["id"] for s in scripts]
        self.assertEqual(ids, ["历史脚本"], "user_id=0 应只看到默认空间脚本")
        self.assertEqual(len(ids), 1, "不应重复合并自己的空间")

    async def test_create_script_writes_to_own_space(self):
        """新建脚本必须写入 data/{user_id}/scripts（隔离语义不变）。"""
        result = await scripts_service.create_script(
            self.tmp, 3, "新建脚本", "新建正文"
        )
        script_id = result["id"]
        own_path = self.tmp / "3" / "scripts" / f"{script_id}.md"
        default_path = self.tmp / "0" / "scripts" / f"{script_id}.md"

        self.assertTrue(own_path.exists(), "新脚本应写入用户自己的空间")
        self.assertFalse(default_path.exists(), "新脚本不应写入默认空间")
        self.assertIn(str(own_path), result["path"])

    async def test_user_own_script_priority_over_default(self):
        """同 id 在两空间都存在时，用户自己的优先（去重不重复、取用户版）。"""
        # 在默认空间也放一个与用户空间同名的脚本
        dup_content = "# 重复脚本\n\n默认空间版本\n"
        (self.tmp / "0" / "scripts" / "重复脚本.md").write_text(dup_content, encoding="utf-8")
        (self.tmp / "3" / "scripts" / "重复脚本.md").write_text("# 重复脚本\n\n用户空间版本\n", encoding="utf-8")

        scripts = await scripts_service.list_scripts(self.tmp, user_id=3)
        ids = [s["id"] for s in scripts]
        self.assertEqual(ids.count("重复脚本"), 1, "同名脚本应去重为 1 条")

        detail = await scripts_service.get_script(self.tmp, "重复脚本", user_id=3)
        self.assertIn("用户空间版本", detail["content"], "应优先返回用户自己空间的版本")


if __name__ == "__main__":
    print("=" * 70)
    print("默认/共享脚本空间回归测试 — 修复: 历史脚本隔离可见性")
    print("venv: /Users/coubann/.workbuddy/binaries/python/envs/default/bin/python")
    print("=" * 70)
    unittest.main(verbosity=2)
