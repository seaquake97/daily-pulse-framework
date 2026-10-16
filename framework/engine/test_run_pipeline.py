#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_run_pipeline.py — 三步编排器回归（GAP-A3）

守护三类工程缺陷（均为 2026-10-16 实测踩过）：
  ① 路径推导错误（站点根算错层级 / 子脚本用相对路径随 cwd 失效）
  ② 参数校验缺失（日期格式、阶段名、未知任务）
  ③ 环境变量覆盖不生效（可迁移性前提）

另含预检用例：依赖缺失必须**提前失败并说清缺什么**，而不是运行中途崩。

运行：python3 test_run_pipeline.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIPELINE = HERE / "run_pipeline.py"
sys.path.insert(0, str(HERE))

import run_pipeline as RP  # noqa: E402


def run(args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, str(PIPELINE)] + args,
                          capture_output=True, text=True, env=e)


class TestPathDerivation(unittest.TestCase):
    """① 路径推导：站点根 = framework 的上一级（不是上两级）"""

    def test_site_root_points_to_real_site(self):
        self.assertTrue((RP.SITE_ROOT / "scripts" / "publish_to_github.py").exists(),
                        f"SITE_ROOT 推导错误: {RP.SITE_ROOT}")

    def test_submodule_scripts_exist(self):
        for p in (RP.NORMALIZE, RP.CHECK_MD_DATA, RP.CHECK_MD):
            self.assertTrue(p.exists(), f"子脚本路径错误: {p}")
            self.assertTrue(p.is_absolute(), f"必须是绝对路径: {p}")

    def test_framework_root_is_parent_of_engine(self):
        self.assertEqual(RP.FRAMEWORK, HERE.parent)


class TestTaskMapping(unittest.TestCase):
    def test_five_tasks_mapped(self):
        self.assertEqual(set(RP.TASK_DIR),
                         {"stock-assistant", "fund-market", "fund-guide",
                          "stock-review", "daily-review"})

    def test_task_dirs_are_absolute_or_relative_safe(self):
        for slug, d in RP.TASK_DIR.items():
            self.assertFalse(d.startswith("/"), f"{slug} 目录不应为绝对路径: {d}")


class TestArgValidation(unittest.TestCase):
    """② 参数校验"""

    def test_bad_date_rejected(self):
        r = run(["--date", "2026/10/16", "--stage", "collect"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("日期格式", r.stderr)

    def test_short_date_rejected(self):
        r = run(["--date", "20261016", "--stage", "collect"])
        self.assertEqual(r.returncode, 2)

    def test_dry_run_prints_command(self):
        r = run(["--date", "2026-10-16", "--stage", "all", "--dry-run"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("would run", r.stdout)
        self.assertIn("publish_to_github.py", r.stdout)

    def test_dry_run_does_not_push_by_default(self):
        r = run(["--date", "2026-10-16", "--stage", "publish", "--dry-run"])
        self.assertNotIn("--push", r.stdout)

    def test_push_flag_included_when_requested(self):
        r = run(["--date", "2026-10-16", "--stage", "publish",
                 "--dry-run", "--push"])
        self.assertIn("--push", r.stdout)


class TestPreflight(unittest.TestCase):
    """③ 预检：依赖缺失要提前说清，而不是中途崩"""

    def test_missing_site_root_reports_clearly(self):
        # 用「确实不存在」的路径——TemporaryDirectory 是已存在的空目录，
        # 缺 scripts 子目录时同样应报错（2026-10-16 实测修正）
        with tempfile.TemporaryDirectory() as td:
            r = run(["--date", "2026-10-16", "--stage", "collect"],
                    env={"PULSE_SITE_ROOT": td})
            self.assertEqual(r.returncode, 3)
            self.assertIn("发布脚本不存在", r.stderr)
            self.assertIn("PULSE_SITE_ROOT", r.stderr)

    def test_missing_engine_reports_clearly(self):
        with tempfile.TemporaryDirectory() as td:
            gone = str(Path(td) / "no-such-engine")
            r = run(["--date", "2026-10-16", "--stage", "score"],
                    env={"PULSE_ENGINE_SCRIPTS": gone})
            self.assertEqual(r.returncode, 3)
            self.assertIn("引擎脚本目录不存在", r.stderr)

    def test_preflight_returns_empty_when_satisfied(self):
        self.assertEqual(RP.preflight(), [])

    def test_env_var_overrides_defaults(self):
        """preflight 必须按**当前**环境变量判断，不能用导入时的模块常量。"""
        with tempfile.TemporaryDirectory() as td:
            gone = str(Path(td) / "no-such-root")
            old = os.environ.get("PULSE_WORKBUDDY_ROOT")
            try:
                os.environ["PULSE_WORKBUDDY_ROOT"] = gone
                miss = RP.preflight()
                self.assertTrue(any("工作区" in m for m in miss),
                                f"环境变量覆盖未生效: {miss}")
            finally:
                if old is None:
                    os.environ.pop("PULSE_WORKBUDDY_ROOT", None)
                else:
                    os.environ["PULSE_WORKBUDDY_ROOT"] = old


class TestStageSelection(unittest.TestCase):
    def test_all_expands_to_four_stages(self):
        r = run(["--date", "2026-10-16", "--stage", "all", "--dry-run"])
        for st in ("collect", "score", "report", "publish"):
            self.assertIn(st, r.stdout)

    def test_comma_separated_stages(self):
        r = run(["--date", "2026-10-16", "--stage", "collect,score", "--dry-run"])
        self.assertIn("collect", r.stdout)
        self.assertIn("score", r.stdout)

    def test_unknown_task_fails_loudly(self):
        """未知任务不该静默通过——静默通过等于没校验。"""
        r = run(["--date", "2026-10-16", "--stage", "collect",
                 "--task", "no-such-task"])
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
