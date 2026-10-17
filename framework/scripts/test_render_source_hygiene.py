#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_render_source_hygiene.py — 渲染层源码卫生门禁

从 test_render_strategies.py 拆出（2026-10-17）：双轨隔离新增用例后该文件
触及 313 行，超过团队单文件 300 行硬上限。拆分而非压缩断言——门禁本身不该
为了塞进行数而降低强度。
"""
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
P0_EMOJI_RE = re.compile("[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]")

class SourceHygieneTest(unittest.TestCase):
    """本轮新增源码自身也要过团队 P0 门禁（扫 hosts 之前先扫自己）。"""

    FILES = ("render_strategies.py", "inject_strategies.py", "test_render_strategies.py")
    # 拼接构造而非写字面量：否则「禁止写死路径」这条断言自身就是一条写死路径
    LOCAL_MARK = "/" + "Users" + "/" + "lianghaizhen"

    def test_source_no_emoji_no_hardcoded_path(self):
        for name in self.FILES:
            src = (HERE / name).read_text(encoding="utf-8")
            self.assertEqual(P0_EMOJI_RE.findall(src), [], f"{name} 含 emoji（P0-1）")
            self.assertNotIn(self.LOCAL_MARK, src, f"{name} 写死本机路径")
    def test_source_within_line_budget(self):
        for name in self.FILES:
            lines = (HERE / name).read_text(encoding="utf-8").splitlines()
            self.assertLessEqual(len(lines), 300, f"{name} 超过 300 行上限")


if __name__ == "__main__":
    unittest.main(verbosity=2)
