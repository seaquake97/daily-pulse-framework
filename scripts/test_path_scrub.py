#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_path_scrub.py — 本机绝对路径脱敏回归（安全 P0）

## 背景（2026-10-16 实测）

上游 15:05 复盘正文写着
「数据源：/Users/<用户名>/WorkBuddy/股票复盘/2026-10-15/settlement.json」，
渲染后直接出现在公开 GitHub Pages 上——泄漏本机用户名与目录结构，且对读者零价值。

## 两层实现（缺一不可）

  ① `md_render/inline.py`  渲染入口——覆盖经 render_md 的产物
  ② `sanitizer/path_pass.py` 消毒链——**上游直传 html 不过 inline()**，
     消毒是所有 html 的最后一道闸

## 关键回归（真实踩过的坑）

初版正则 `(?:/[^\\s"'<>]*)*?` 贪婪度不足，`settlement.json` 被截成 `t.json`
——"setlemen" 被前一段吞掉。**脱敏不能吃掉文件名**（读者要的是"用了哪个文件"）。
本套件逐条锁定文件名完整性。

运行：python3 scripts/test_path_scrub.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent          # <site>/scripts/
ROOT = HERE.parent                             # <site>/
sys.path.insert(0, str(HERE))                  # sanitizer 与 md_render 都在 scripts/ 下
sys.path.insert(0, str(ROOT / "framework" / "scripts"))   # A-04: 集中路径
import paths

from sanitizer import path_pass as P            # noqa: E402
# ⚠ 必须用 importlib 拿**模块**，不能用 `from md_render import inline`——
# 包的 __init__ 把同名函数 inline() re-export 了，`from ... import inline`
# 拿到的是函数而不是模块，访问其私有成员会 AttributeError（实测踩过）。
import importlib                                   # noqa: E402
I = importlib.import_module("md_render.inline")


class TestPathPass(unittest.TestCase):
    def test_file_path_keeps_full_filename(self):
        """文件名必须完整——初版把 settlement.json 截成 t.json。

        注意断言写法：`t.json` 是 `settlement.json` 的**子串**，直接用
        `assertNotIn` 会假失败（我自己踩过）。正确做法是比较剥离前后的
        文件名是否相等。
        """
        import re
        src = f"数据源：{paths.WORKBUDDY_ROOT}/股票复盘/2026-10-15/settlement.json"
        out = P._scrub(src)
        got = re.search(r"([^\s/]+\.json)", out)
        self.assertIsNotNone(got, f"文件名丢失: {out}")
        self.assertEqual(got.group(1), "settlement.json", "文件名被截断")
        self.assertNotIn("/Users/", out)
        self.assertIn("数据源：", out, "前后文本不得受损")

    def test_home_only_masked(self):
        out = P._scrub(f"归档于 {paths.WORKBUDDY_ROOT.parent} 目录")
        self.assertNotIn("lianghaizhen", out)
        self.assertIn("归档于", out)

    def test_multiple_paths(self):
        out = P._scrub("/Users/a/W/b/c.json 和 /Users/d/e/f.md")
        self.assertIn("c.json", out)
        self.assertIn("f.md", out)
        self.assertNotIn("/Users/", out)

    def test_no_path_untouched(self):
        src = "今日评级【均衡】，Σ+0.180，市场有风险。"
        self.assertEqual(P._scrub(src), src)

    def test_idempotent(self):
        once = P._scrub(f"{paths.WORKBUDDY_ROOT}/x/y.json")
        self.assertEqual(P._scrub(once), once)

    def test_various_extensions(self):
        for ext in ("json", "md", "html", "csv", "py", "sh", "yaml", "txt"):
            src = f"/Users/u/WorkBuddy/task/data.{ext}"
            self.assertIn(f"data.{ext}", P._scrub(src), f".{ext} 未保留")


class TestInlineLayerMatches(unittest.TestCase):
    def test_inline_scrub_same_behavior(self):
        """渲染层与消毒层行为须一致——两层都在链路上，不一致会留下绕过路径。"""
        src = f"{paths.WORKBUDDY_ROOT}/股票复盘/2026-10-15/settlement.json"
        self.assertEqual(I._scrub_home_path(src), P._scrub(src))

    def test_inline_keeps_filename(self):
        out = I._scrub_home_path("/Users/u/W/t/settlement.json")
        self.assertIn("settlement.json", out)


class TestPublishedSiteClean(unittest.TestCase):
    """真实产物层：站点不得含本机路径（与 test_site_links.py 的 S-1 互补，
    那个从 HTML 全量扫，这个从 md 源扫——md 泄漏同样不该存在）。"""

    def test_no_leak_in_stage_html(self):
        import re
        docs = ROOT / "_stage" / "docs"
        if not docs.is_dir():
            self.skipTest(f"真实产出缺失：{docs}")
        pat = re.compile(r"/Users/[^/\s\"'<>]+")
        bad = []
        for f in docs.rglob("*.html"):
            if pat.search(f.read_text(encoding="utf-8", errors="replace")):
                bad.append(str(f.relative_to(docs)))
        self.assertEqual(bad, [], f"站点泄漏本机绝对路径：{bad[:5]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
