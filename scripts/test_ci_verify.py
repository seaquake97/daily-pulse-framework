#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_ci_verify.py — 统一 CI 总调度器 ci_verify.py 的自检套件（全离线）

只验证调度器自身：过滤、跳过、超时、假绿灯识别、护栏解析、退出码、JSON 契约。
被调度套件的业务断言由各自 test_*.py 负责，此处不重复。
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ci_verify

P0_EMOJI_RE = re.compile('[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]')
HOME_MARK = "/".join(["", "Users", ""])

COMPLIANT_TEXT = (
    "   emoji 数（P0 口径）:        0\n"
    "   紫粉渐变/靛蓝:            0\n"
    "   弹跳缓动:                0\n"
    "   emoji(P0): 基线 98 → 当前 0（-98）\n"
)
FAILING_SUITE = 'import sys\nsys.stderr.write("boom: 模拟断言失败\\n")\nsys.exit(3)'


def _run_main(argv, items=None):
    """执行 main()（可注入自定义清单），返回 (退出码, stdout, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ci_verify.main(argv, items=items)
    return code, out.getvalue(), err.getvalue()


def _synthetic(tmp: Path, name: str, body: str = "", **kw) -> dict:
    path = tmp / name
    if body is not None:
        path.write_text(body, encoding="utf-8")
    return {"name": name, "kind": kw.get("kind", "test"), "path": path,
            "args": list(kw.get("args", [])), "network": kw.get("network", False),
            "reserved": kw.get("reserved", False)}


def _result(name: str, status: str, code=None) -> dict:
    return {"name": name, "status": status, "duration_ms": 1, "exit_code": code,
            "timed_out": False, "kind": "test", "path": f"/{name}", "detail": ""}


class ManifestTest(unittest.TestCase):
    """清单本身的可信度：写错路径等于静默漏测，必须先钉死。"""

    def test_manifest_contains_all_expected_items(self):
        names = [it["name"] for it in ci_verify.build_manifest()]
        for rel in ci_verify.TEST_SUITES + ci_verify.RESERVED_SUITES:
            self.assertIn(rel, names)
        self.assertTrue(all(r in names for r, _a, _k in ci_verify.VALIDATORS))
        self.assertNotIn("{ROOT}", " ".join(
            a for it in ci_verify.build_manifest() for a in it["args"]))

    def test_every_item_exists_or_is_reserved(self):
        missing = [it["name"] for it in ci_verify.build_manifest()
                   if not it["reserved"] and not it["path"].is_file()]
        self.assertEqual(missing, [], "非预留项文件缺失（漏测风险）")

    def test_reserved_items_are_flagged(self):
        reserved = {it["name"] for it in ci_verify.build_manifest() if it["reserved"]}
        self.assertEqual(reserved, {"framework/engine/collect/test_fallback_fetcher.py",
                                    "_git_engine/scripts/test_compute_signals.py"})

    def test_source_is_clean_and_within_budget(self):
        for name in ("ci_verify.py", "test_ci_verify.py"):
            src = (HERE / name).read_text(encoding="utf-8")
            self.assertNotIn(HOME_MARK, src, f"{name} 含硬编码本机路径")
            self.assertEqual(P0_EMOJI_RE.findall(src), [], f"{name} 含 emoji（P0）")
            self.assertLessEqual(len(src.splitlines()), 300, f"{name} 超过 300 行上限")


class SelectTest(unittest.TestCase):
    def test_only_is_case_insensitive_and_multi_hit(self):
        items = ci_verify.build_manifest()
        picked_one = ci_verify.select_items(items, only=["path_scrub"])
        self.assertEqual([it["name"] for it, _ in picked_one],
                         ["scripts/test_path_scrub.py"])
        self.assertEqual(len(ci_verify.select_items(items, only=["SANITIZE_gate"])), 2)
        self.assertEqual(len(ci_verify.select_items(items, only=["test_"])),
                         len(ci_verify.TEST_SUITES) + len(ci_verify.RESERVED_SUITES))
        picked = ci_verify.select_items(items, only=["dark_mode", "strategies"])
        self.assertEqual(sorted(it["name"] for it, _ in picked),
                         ["framework/scripts/render_strategies.py",
                          "framework/scripts/strategies.py",
                          "framework/scripts/test_render_strategies.py",
                          "framework/scripts/test_strategies.py",
                          "scripts/test_dark_mode.py"])

    def test_only_no_match_returns_empty(self):
        self.assertEqual(ci_verify.select_items(ci_verify.build_manifest(),
                                                only=["__no_such_suite__"]), [])

    def test_skip_network_marks_flagged_item(self):
        item = {"name": "net_suite", "kind": "test", "path": Path("/nonexistent/net.py"),
                "args": [], "network": True, "reserved": False}
        self.assertEqual(ci_verify.select_items([item], skip_network=True)[0][1],
                         "按 --skip-network 跳过")
        self.assertEqual(ci_verify.select_items([item], skip_network=False)[0][1], "")
        offline = ci_verify.select_items(ci_verify.build_manifest(), skip_network=True)
        self.assertTrue(all(reason == "" for _it, reason in offline), "离线项不得被跳过")


class RunItemTest(unittest.TestCase):
    def test_missing_file_is_skip_only_when_reserved(self):
        with tempfile.TemporaryDirectory() as td:
            reserved = ci_verify.run_item(
                _synthetic(Path(td), "future_suite.py", body=None, reserved=True))
            vanished = ci_verify.run_item(
                _synthetic(Path(td), "vanished_suite.py", body=None, reserved=False))
        self.assertEqual(reserved["status"], "SKIP")
        self.assertIsNone(reserved["exit_code"])
        self.assertEqual(vanished["status"], "FAIL", "测试文件不该凭空消失")

    def test_failing_child_is_fail_with_exit_code(self):
        with tempfile.TemporaryDirectory() as td:
            res = ci_verify.run_item(_synthetic(Path(td), "bad.py", FAILING_SUITE))
        self.assertEqual((res["status"], res["exit_code"]), ("FAIL", 3))
        self.assertIn("退出码 3", res["detail"])
        self.assertIn("boom", res["output"], "失败项应保留子进程输出供诊断")

    def test_skip_reason_short_circuits_execution(self):
        with tempfile.TemporaryDirectory() as td:
            item = _synthetic(Path(td), "never_run.py", "raise SystemExit(9)")
            res = ci_verify.run_item(item, skip_reason="按 --skip-network 跳过")
        self.assertEqual((res["status"], res["duration_ms"]), ("SKIP", 0))
        self.assertEqual(res["exit_code"], None, "被跳过的项不应真的执行")

    def test_timeout_marks_fail_and_kills_child(self):
        with tempfile.TemporaryDirectory() as td:
            item = _synthetic(Path(td), "slow.py", "import time\ntime.sleep(30)")
            t0 = ci_verify.time.monotonic()
            res = ci_verify.run_item(item, timeout=1)
            elapsed = ci_verify.time.monotonic() - t0
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(res["timed_out"], "超时项必须打 timeout 标记")
        self.assertIn("已杀掉子进程", res["detail"])
        self.assertLess(elapsed, 20, "超时未生效，子进程仍在跑")

    def test_compliance_gate_passes_on_clean_output(self):
        with tempfile.TemporaryDirectory() as td:
            item = _synthetic(Path(td), "scan_ok.py", f"print({COMPLIANT_TEXT!r})",
                              kind="compliance")
            res = ci_verify.run_item(item)
        self.assertEqual((res["status"], res["exit_code"]), ("PASS", 0))
        self.assertIsNone(res.get("child_ran"), "校验器不走用例计数")

    def test_compliance_gate_fails_even_when_exit_code_zero(self):
        """合规脚本退出码恒为 0，护栏必须自己看数字，不能只看退出码。"""
        dirty = COMPLIANT_TEXT.replace("弹跳缓动:                0", "弹跳缓动:                2")
        with tempfile.TemporaryDirectory() as td:
            item = _synthetic(Path(td), "scan_dirty.py", f"print({dirty!r})",
                              kind="compliance")
            res = ci_verify.run_item(item)
        self.assertEqual(res["exit_code"], 0, "子进程本身是成功的")
        self.assertEqual(res["status"], "FAIL")
        self.assertIn("弹跳缓动", res["detail"])


class SkipDetectionTest(unittest.TestCase):
    """退出码 0 不等于真的测过：套内用例可能全部 skipTest，绿灯是假的。"""

    def _run(self, body):
        with tempfile.TemporaryDirectory() as td:
            return ci_verify.run_item(_synthetic(Path(td), "suite.py", body))

    def test_all_skipped_suite_becomes_skip(self):
        res = self._run('import sys\nsys.stderr.write("Ran 3 tests in 0.01s\\n\\n'
                        'OK (skipped=3)\\n")')
        self.assertEqual(res["status"], "SKIP")
        self.assertEqual((res["child_ran"], res["child_skipped"]), (3, 3))
        self.assertIn("绿灯不可信", res["detail"])

    def test_zero_cases_is_fail(self):
        res = self._run('import sys\nsys.stderr.write("Ran 0 tests in 0.00s\\n\\nOK\\n")')
        self.assertEqual(res["status"], "FAIL")
        self.assertIn("未执行任何用例", res["detail"])

    def test_partial_skip_stays_pass(self):
        res = self._run('import sys\nsys.stderr.write("Ran 17 tests in 0.01s\\n\\n'
                        'OK (skipped=1)\\n")')
        self.assertEqual(res["status"], "PASS")
        self.assertEqual((res["child_ran"], res["child_skipped"]), (17, 1))

    def test_failure_is_not_masked_by_skip_count(self):
        res = self._run('import sys\nsys.stderr.write("Ran 2 tests\\n\\n'
                        'FAILED (failures=2, skipped=2)\\n")\nsys.exit(1)')
        self.assertEqual(res["status"], "FAIL", "失败优先，不得被 skip 计数覆盖")


class ComplianceGateTest(unittest.TestCase):
    def test_all_zero_is_clean(self):
        self.assertEqual(ci_verify.check_compliance(COMPLIANT_TEXT), [])

    def test_missing_metric_line_is_violation(self):
        bad = ci_verify.check_compliance("扫描输出格式已变，没有任何指标行")
        self.assertEqual(len(bad), len(ci_verify.COMPLIANCE_GATES))
        self.assertTrue(any("护栏失守" in b for b in bad))

    def test_positive_count_is_violation(self):
        bad = ci_verify.check_compliance(COMPLIANT_TEXT.replace(
            "紫粉渐变/靛蓝:            0", "紫粉渐变/靛蓝:            7"))
        self.assertEqual(len(bad), 1)
        self.assertIn("紫粉渐变", bad[0])
        self.assertIn("7", bad[0])


class MainTest(unittest.TestCase):
    def test_only_no_match_exits_zero(self):
        code, out, _err = _run_main(["--only", "__no_such_suite__"])
        self.assertEqual(code, 0, "无匹配不算失败")
        self.assertIn("总计 0 项", out)
        self.assertIn("| 跳过 0", out)

    def test_only_runs_target_and_exits_zero(self):
        code, out, _err = _run_main(["--only", "path_scrub"])
        self.assertEqual(code, 0)
        self.assertIn("[PASS] scripts/test_path_scrub.py", out)

    def test_json_output_is_parseable_with_required_fields(self):
        code, out, _err = _run_main(["--only", "path_scrub", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertEqual((payload["total"], payload["passed"]), (1, 1))
        for item in payload["items"]:
            for key in ("name", "status", "duration_ms", "exit_code"):
                self.assertIn(key, item, f"JSON 项缺少必需字段 {key}")
            self.assertEqual(item["name"], "scripts/test_path_scrub.py")
            self.assertEqual((item["status"], item["exit_code"]), ("PASS", 0))
            self.assertIsInstance(item["duration_ms"], int)
        empty = json.loads(_run_main(["--only", "__no_such_suite__", "--json"])[1])
        self.assertEqual((empty["items"], empty["total"]), ([], 0))

    def test_bad_arguments_exit_two(self):
        for argv in (["--only", "   "], ["--not-a-flag"]):
            with self.assertRaises(SystemExit) as ctx:
                _run_main(argv)
            self.assertEqual(ctx.exception.code, 2, f"参数错误应退出 2: {argv}")

    def test_main_returns_one_when_any_item_fails(self):
        """注入失败项跑通整条链路：退出码 1 + 汇总行 + stderr 诊断。"""
        with tempfile.TemporaryDirectory() as td:
            injected = [_synthetic(Path(td), "ok_suite.py", "print('ok')"),
                        _synthetic(Path(td), "bad_suite.py", FAILING_SUITE),
                        _synthetic(Path(td), "future_suite.py", body=None, reserved=True)]
            code, out, err = _run_main([], items=injected)
        self.assertEqual(code, 1, "有失败项必须退出 1")
        self.assertIn("[PASS] ok_suite.py", out)
        self.assertIn("[FAIL] bad_suite.py", out)
        self.assertIn("总计 3 项 | 通过 1 | 失败 1 | 跳过 1", out)
        self.assertIn("bad_suite.py", err, "失败诊断落 stderr，不污染 stdout")
        self.assertIn("boom", err)

    def test_main_json_returns_one_and_keeps_stdout_parseable(self):
        with tempfile.TemporaryDirectory() as td:
            injected = [_synthetic(Path(td), "bad_suite.py", FAILING_SUITE)]
            code, out, _err = _run_main(["--json"], items=injected)
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["items"][0]["status"], "FAIL")
        self.assertEqual(payload["items"][0]["exit_code"], 3)

    def test_summarize_counts(self):
        cases = [([_result("a", "PASS", 0), _result("b", "FAIL", 1),
                   _result("c", "SKIP")], (3, 1, 1, 1), 1),
                 ([_result("a", "PASS", 0), _result("b", "SKIP"),
                   _result("c", "SKIP")], (3, 1, 0, 2), 0)]
        for results, expect, exit_code in cases:
            counts = ci_verify.summarize(results)
            self.assertEqual((counts["total"], counts["passed"],
                              counts["failed"], counts["skipped"]), expect)
            self.assertEqual(1 if counts["failed"] else 0, exit_code,
                             "跳过不算失败，有失败项才退出 1")

    def test_list_prints_manifest_without_running(self):
        code, out, _err = _run_main(["--list"])
        self.assertEqual(code, 0)
        self.assertIn("scripts/test_path_scrub.py", out)
        self.assertIn("framework/engine/collect/test_fallback_fetcher.py", out)
        self.assertNotIn("[PASS]", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
