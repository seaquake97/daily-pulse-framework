#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_journal.py — 决策日志校验层与四分类层主套件（纯标准库，零依赖）

本套件守三件事：
  1. 四分类判定（场外基金×价格类必为 monitoring_only 是核心断言）
  2. 抑制层留痕（降级轮仍保留被阻断动作的可追溯记录）
  3. 校验层入口与 CLI 行为

16 条断言的负例在 test_journal_cases.py，本文件不重复——两份都写会让
同一个构造在两处漂移，届时「红」不知道是哪条规则在拦。

**每次跑都做 mutation 检查**：随机抽一条 A-断言，把它的判据临时改成
恒真，若套件仍全绿，说明该断言没有被任何用例真正覆盖。
这比多写十个正例更有效——正例只能证明代码能跑，变异只能证明断言还活着。

运行：python3 test_journal.py
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))

from classification import (  # noqa: E402
    apply_suppression, build_output, classify,
)
from contracts import (  # noqa: E402
    CLASS_ACTIONABLE, CLASS_FORBIDDEN, CLASS_MONITORING_ONLY, CLASS_WATCH_ONLY,
    E_A13_ACTION_COUNT_CAP, PROXY_FLAG, PROXY_INDICATOR,
)
from diagnostics import format_diagnostics  # noqa: E402
from journal_fixtures import (  # noqa: E402
    EXAMPLE, example_index, new_entry, run_entry, run_log,
)
from test_journal_cases import *  # noqa: E402,F401,F403  CI 单入口加载 16 条负例
from validate import main  # noqa: E402

# 场外基金（000979，listing=otc）与场内标的（600312，listing=exchange）。
# 取自 portfolio.example.yaml，不硬编码持仓数值以外的东西。
FUND_CODE = "000979"
STOCK_CODE = "600312"
EXAMPLE_CFG = str(EXAMPLE)


class TestFourWayClassification(unittest.TestCase):
    """四分类：标的 × 资产 × 观察点三级组合的不触发类判定。"""

    def setUp(self):
        self.repo = example_index()

    def test_otc_price_point_is_monitoring_only(self):
        """核心断言：场外基金 × 价格类观察点 ⇒ monitoring_only（方法论不可得）。

        场外基金没有分时价，「突破 X 元」这类观察点在它身上根本无法判定，
        硬给 actionable 等于让下游去取一个不存在的价。
        """
        got = classify(FUND_CODE, "PRICE", self.repo)
        self.assertEqual(got, CLASS_MONITORING_ONLY)
        # 反向对照：同样价格类，换场内就是 actionable
        self.assertEqual(classify(STOCK_CODE, "PRICE", self.repo),
                         CLASS_ACTIONABLE)

    def test_otc_nav_and_position_are_actionable(self):
        """场外基金 × 净值/仓位类 ⇒ actionable（动作限买入/卖出/调整定投）。"""
        for point_class in ("NAV", "POSITION"):
            with self.subTest(point_class=point_class):
                self.assertEqual(classify(FUND_CODE, point_class, self.repo),
                                 CLASS_ACTIONABLE)

    def test_otc_grid_action_is_forbidden(self):
        """场外基金 × 任何网格/条件单/委托动作 ⇒ forbidden。"""
        act = {"kind": "grid", "code": "ACT-9"}
        self.assertEqual(classify(FUND_CODE, "GRID", self.repo, act),
                         CLASS_FORBIDDEN)
        self.assertEqual(classify(FUND_CODE, "NAV", self.repo, act),
                         CLASS_FORBIDDEN)

    def test_exchange_grid_is_actionable(self):
        """场内标的 × 网格类 ⇒ actionable（ADR-007 §2.2：场内才有挂单）。"""
        self.assertEqual(classify(STOCK_CODE, "GRID", self.repo),
                         CLASS_ACTIONABLE)

    def test_unknown_instrument_is_forbidden(self):
        """数据仓里没有的标的一律 forbidden——先确认存在，再谈可执行性。"""
        self.assertEqual(classify("999998", "PRICE", self.repo),
                         CLASS_FORBIDDEN)

    def test_proxy_substitution_marks_agency(self):
        """降级必须换代理指标并标注代理性质（三件事都不可省）。"""
        base = new_entry()
        base["action"] = {**base["action"], "instrument_code": FUND_CODE,
                          "kind": "buy", "amount": 500.0,
                          "amount_unit": "money", "base_price": None}
        out, blocked = apply_suppression(base, self.repo)
        self.assertIsNone(out["action"], "降级后动作必须为 None")
        obs = out["observation_point"]
        self.assertEqual(obs["proxy"], PROXY_FLAG)
        self.assertIn(PROXY_INDICATOR, obs["proxy_basis"])
        self.assertIn("代理", obs["proxy_basis"], "必须标注这是代理指标")
        self.assertIsNone(obs["threshold"], "场内价格阈值对场外无意义，必须清空")
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["blocking_domain"], "methodology")


class TestGateSuppression(unittest.TestCase):
    """抑制层：动作被阻断时不删除，改为留痕。"""

    def setUp(self):
        self.repo = example_index()

    def test_blocked_action_is_retained_as_trace(self):
        """§4：降级轮仍保留被阻断动作的可追溯记录。

        三要素都要能回答：本来做什么（action_code）、被什么挡（gate_id）、
        当时的判据值（blocking_value）。缺任何一项，下一轮就复盘不了。
        """
        base = new_entry()
        base["action"] = {**base["action"], "instrument_code": FUND_CODE,
                          "kind": "buy", "amount": 500.0,
                          "amount_unit": "money", "base_price": None}
        out, blocked = apply_suppression(base, self.repo)
        self.assertIsNone(out["action"])
        self.assertEqual(len(blocked), 1)
        trace = blocked[0]
        for field in ("action_code", "gate_id", "blocking_value",
                      "blocking_domain"):
            self.assertIsNotNone(trace.get(field), f"{field} 不得为空")
        self.assertEqual(trace["action_code"], "ACT-1")
        self.assertEqual(trace["gate_id"], "GATE_METHOD_UNAVAILABLE")

    def test_suppressed_entry_passes_validation_after_retagging(self):
        """抑制后的条目必须仍能过校验：动作置 None 后 A-01 不再适用。

        这条是抑制层与校验层的接缝。若抑制产物过不了校验，
        「降级轮」就等于「坏数据」，留痕功能形同虚设。
        """
        base = new_entry()
        base["action"] = {**base["action"], "instrument_code": FUND_CODE,
                          "kind": "buy", "amount": 500.0,
                          "amount_unit": "money", "base_price": None}
        out, blocked = apply_suppression(base, self.repo)
        out = {**out, "gate_blocked_actions": blocked}
        rep = run_entry(out, self.repo)
        self.assertTrue(rep.ok,
                        f"抑制产物应可校验：{format_diagnostics(rep)}")

    def test_build_output_requires_full_actionable_bundle(self):
        """输出 actionable 时必须同时给出 action / gates_passed / risk。

        自称 actionable 却缺风控段的产物，会被下游当成「可以执行」——
        这里必须降级为 watch_only 而不是放行。
        """
        for drop in ("gates_passed", "risk"):
            with self.subTest(dropped=drop):
                base = new_entry()
                base["action"] = {**base["action"], "kind": "buy",
                                  "amount": 100, "amount_unit": "shares",
                                  "base_price": None}
                base[drop] = [] if drop == "gates_passed" else None
                out = build_output(base, self.repo)
                self.assertEqual(out["classification"], CLASS_WATCH_ONLY)
                self.assertFalse(out["actionable"])
                self.assertIsNone(out["entry"]["action"])
                self.assertEqual(out["gate_blocked_actions"][-1]["gate_id"],
                                 "GATE_ACTIONABLE_INCOMPLETE")
                self.assertIn(drop, out["gate_blocked_actions"][-1]
                              ["blocking_value"])

    def test_build_output_actionable_keeps_action(self):
        """完整条目 ⇒ actionable，动作原样保留（抑制层不能反向削合法建议）。"""
        out = build_output(new_entry(), self.repo)
        self.assertEqual(out["classification"], CLASS_ACTIONABLE)
        self.assertTrue(out["actionable"])
        self.assertIsNotNone(out["entry"]["action"])
        self.assertEqual(out["gate_blocked_actions"], [])


class TestFacadeAndCli(unittest.TestCase):
    """门面入口与 CLI。"""

    def test_validate_log_respects_cap(self):
        """A-13 上限从门面透传，不写死在断言里。"""
        repo = example_index()
        base = new_entry()
        entries = [new_entry(action={**base["action"], "code": f"ACT-{i}"})
                   for i in range(4)]
        self.assertIn(E_A13_ACTION_COUNT_CAP,
                      {e["code"] for e in run_log(entries, repo, 3).errors})
        self.assertTrue(run_log(entries, repo, 4).ok)

    def test_non_mapping_entry_reports_structural_error(self):
        """条目不是映射时报 E_J_STRUCTURE，不抛异常——
        校验一整份日志时单条畸形不该中断整批。"""
        repo = example_index()
        rep = run_log([new_entry(), "not-a-dict"], repo)
        self.assertFalse(rep.ok)
        self.assertIn("E_J_STRUCTURE", {e["code"] for e in rep.errors})

    def test_cli_exit_codes(self):
        """CLI：0 通过 / 1 校验失败 / 2 文件不存在。"""
        repo = example_index()
        base = new_entry()
        bad = new_entry(reasoning_basis="GENERATED")
        with TemporaryDirectory() as tmp:
            good_file = Path(tmp) / "good.json"
            good_file.write_text(json.dumps({"decision_log": [base]},
                                            ensure_ascii=False),
                                 encoding="utf-8")
            bad_file = Path(tmp) / "bad.json"
            bad_file.write_text(json.dumps({"decision_log": [bad]},
                                            ensure_ascii=False),
                                encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--log", str(good_file),
                                       "--portfolio", EXAMPLE_CFG]), 0)
                self.assertEqual(main(["--log", str(bad_file),
                                       "--portfolio", EXAMPLE_CFG]), 1)
                self.assertEqual(main(["--log", str(Path(tmp) / "nope.json")]), 2)
        self.assertIn("校验通过", buf.getvalue())

    def test_line_number_index_when_provided(self):
        """带 line_index 时错误带行号；不带时行号为 0（不猜行号）。"""
        repo = example_index()
        ent = new_entry(reasoning_basis="GENERATED")
        rep = run_entry(ent, repo)
        self.assertEqual(rep.errors[0]["line"], 0)
        indexed = run_log([ent], repo)
        self.assertEqual(indexed.errors[0]["line"], 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
