"""时区修复回归验证（东八区 UTC+8）。

针对 Bug：脚本创建/显示时间未按东八区 UTC+8 处理。
独立可运行脚本（不依赖 pytest），覆盖 team-lead 指定的 4 个用例 + get_script。

运行方式：
  PYTHONPATH=/Users/coubann/Documents/cheat-on-content-douyin-online \
  /Users/coubann/.workbuddy/binaries/python/envs/default/bin/python \
  backend/tests/test_timezone_fix.py

全程使用临时目录，绝不污染项目 data/。
"""

from __future__ import annotations

import asyncio
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services import scripts_service  # noqa: E402

# 与源码一致：东八区固定偏移
CST = timezone(timedelta(hours=8))
UTC = timezone.utc


class TestTimezoneFix(unittest.IsolatedAsyncioTestCase):
    """验证 create_script / list_scripts / get_script 的时区处理为 UTC+8。"""

    async def asyncSetUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tz_fix_"))
        self.user_id = 1

    async def asyncTearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def test_case1_created_updated_end_with_plus08(self):
        """用例1：list 返回的 created_at / updated_at 以 `+08:00` 结尾（时区感知）。"""
        await scripts_service.create_script(
            self.tmp, self.user_id, "时区用例1", "正文内容"
        )
        scripts = await scripts_service.list_scripts(self.tmp, user_id=self.user_id)

        self.assertEqual(len(scripts), 1)
        created_at = scripts[0]["created_at"]
        updated_at = scripts[0]["updated_at"]

        self.assertTrue(
            created_at.endswith("+08:00"),
            f"created_at 未以 +08:00 结尾: {created_at!r}",
        )
        self.assertTrue(
            updated_at.endswith("+08:00"),
            f"updated_at 未以 +08:00 结尾: {updated_at!r}",
        )
        # 解析回带时区的 datetime，确认 offset 恰好是 +8 小时
        dt_created = datetime.fromisoformat(created_at)
        dt_updated = datetime.fromisoformat(updated_at)
        self.assertEqual(dt_created.utcoffset(), timedelta(hours=8))
        self.assertEqual(dt_updated.utcoffset(), timedelta(hours=8))

    async def test_case2_created_at_matches_cst_now_within_1min(self):
        """用例2：created_at 的北京时间(时:分)与 datetime.now(CST) 在 1 分钟内一致（即不是 UTC）。"""
        before = datetime.now(CST)
        result = await scripts_service.create_script(
            self.tmp, self.user_id, "时区用例2", "正文内容"
        )
        after = datetime.now(CST)

        scripts = await scripts_service.list_scripts(self.tmp, user_id=self.user_id)
        created_at = scripts[0]["created_at"]
        dt_created = datetime.fromisoformat(created_at)

        # 时区必须是东八区
        self.assertEqual(dt_created.utcoffset(), timedelta(hours=8))

        # 在 [before, after] 窗口内（容差 1 分钟，覆盖文件创建耗时）
        self.assertGreaterEqual(dt_created, before - timedelta(minutes=1))
        self.assertLessEqual(dt_created, after + timedelta(minutes=1))

        # 关键：若当初误用 UTC，则 HH:MM 会与 now(CST) 相差约 8 小时。
        # 这里直接断言 created_at 的本地时:分与 now(CST) 一致（差值 < 1 分钟）。
        now_cst = datetime.now(CST)
        delta_minutes = abs((dt_created - now_cst).total_seconds()) / 60.0
        self.assertLess(
            delta_minutes, 1.0,
            f"created_at({dt_created}) 与 now(CST)({now_cst}) 相差 {delta_minutes:.2f} 分钟，不像东八区",
        )

        # 反证：与 now(UTC) 的时:分不应相等（排除“其实是 UTC 但字符串被改”的假修复）
        now_utc = datetime.now(UTC)
        self.assertNotEqual(
            (dt_created.hour, dt_created.minute),
            (now_utc.hour, now_utc.minute),
            "created_at 的时:分与 UTC 当前时:分相同，说明并未真正转为东八区",
        )
        _ = result  # 抑制未使用告警

    async def test_case3_script_id_date_str_is_cst_date(self):
        """用例3：script_id 中的 date_str 等于 datetime.now(CST).strftime('%Y-%m-%d')。"""
        expected_date = datetime.now(CST).strftime("%Y-%m-%d")
        result = await scripts_service.create_script(
            self.tmp, self.user_id, "时区用例3", "正文内容"
        )
        script_id = result["id"]
        # script_id 形如 {date_str}_{hash8}_{title}
        date_str = script_id.split("_", 1)[0]
        self.assertEqual(
            date_str, expected_date,
            f"script_id 日期段 {date_str!r} 不等于东八区日期 {expected_date!r}",
        )
        # 进一步确认该日期段是合法 YYYY-MM-DD 且落在 now(CST) 当天
        self.assertRegex(date_str, r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(date_str, datetime.now(CST).strftime("%Y-%m-%d"))

    async def test_case4_file_header_creation_time_is_cst(self):
        """用例4：文件头 `> 创建时间:` 行解析出的时间也为 UTC+8。"""
        result = await scripts_service.create_script(
            self.tmp, self.user_id, "时区用例4", "正文内容"
        )
        script_path = Path(result["path"])
        text = script_path.read_text(encoding="utf-8")

        match = re.search(r"^>\s*创建时间:\s*(.+)$", text, re.MULTILINE)
        self.assertIsNotNone(match, "未在文件头找到 `> 创建时间:` 行")
        header_ts = match.group(1).strip()

        self.assertTrue(
            header_ts.endswith("+08:00"),
            f"文件头创建时间未以 +08:00 结尾: {header_ts!r}",
        )
        dt_header = datetime.fromisoformat(header_ts)
        self.assertEqual(dt_header.utcoffset(), timedelta(hours=8))

        # 与 now(CST) 在 1 分钟内一致
        now_cst = datetime.now(CST)
        delta_minutes = abs((dt_header - now_cst).total_seconds()) / 60.0
        self.assertLess(
            delta_minutes, 1.0,
            f"文件头创建时间({dt_header}) 与 now(CST)({now_cst}) 相差 {delta_minutes:.2f} 分钟",
        )

    async def test_get_script_also_returns_cst_timestamps(self):
        """补充：get_script 返回的 created_at / updated_at 同样为 UTC+8。"""
        result = await scripts_service.create_script(
            self.tmp, self.user_id, "时区用例_get", "正文内容"
        )
        detail = await scripts_service.get_script(
            self.tmp, result["id"], user_id=self.user_id
        )
        created_at = detail["created_at"]
        updated_at = detail["updated_at"]
        self.assertTrue(created_at.endswith("+08:00"), f"get_script created_at: {created_at!r}")
        self.assertTrue(updated_at.endswith("+08:00"), f"get_script updated_at: {updated_at!r}")
        self.assertEqual(datetime.fromisoformat(created_at).utcoffset(), timedelta(hours=8))
        self.assertEqual(datetime.fromisoformat(updated_at).utcoffset(), timedelta(hours=8))


if __name__ == "__main__":
    print("=" * 70)
    print("时区修复验证 — 东八区 UTC+8 (Bug: 脚本时间未按 UTC+8 处理)")
    print("venv: /Users/coubann/.workbuddy/binaries/python/envs/default/bin/python")
    print("=" * 70)
    unittest.main(verbosity=2)
