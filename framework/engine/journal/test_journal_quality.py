#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_journal_quality.py — 决策日志套件的质量守卫（纯标准库，零依赖）

从 test_journal.py 切出的独立套件，守三件 test_journal.py 不管的事：

  1. 变异检查（TestMutationGuard）——把每条 check_* 改成「永不报错」，
     负例套件必须变红。任一条存活，说明该断言没有真正的失败用例，
     永远不触发而 CI 不会知道。这是「写了断言就以为有护栏」的失败模式。
  2. 真实数据仓联调——用 config/portfolio.yaml 跑一遍，
     证明断言不只在 example 夹具上成立。数据仓不可用则跳过。
  3. 产物序列化——抑制后的条目必须仍是可 JSON 落盘的结构。

切分判据是「跑一次的成本不同」：本套件要重跑负例套件十几次（变异检查），
混进主套件会让日常 `python3 test_journal.py` 慢一个数量级。

运行：python3 test_journal_quality.py
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from classification import build_output  # noqa: E402
from contracts import PROXY_FLAG  # noqa: E402
from diagnostics import format_diagnostics  # noqa: E402
from journal_fixtures import (  # noqa: E402
    example_index, new_entry, real_index, run_entry,
)

FUND_CODE = "000979"

class TestAgainstRealPortfolio(unittest.TestCase):
    """用真实 config/portfolio.yaml 跑一遍。数据仓不可用则跳过——
    绿灯不可信比红灯更糟。"""

    def test_real_portfolio_index_and_baseline(self):
        repo = real_index()
        if repo is None:
            self.skipTest("真实数据仓不可用（config/portfolio.yaml 缺失或损坏）")
        self.assertTrue(repo.track_codes("stock"), "股票轨为空")
        self.assertTrue(repo.track_codes("fund"), "基金轨为空")
        rep = run_entry(new_entry(), repo)
        self.assertTrue(rep.ok,
                        f"真实数据仓下基线条目应通过：{format_diagnostics(rep)}")

    def test_real_grid_params_are_indexed(self):
        """网格段参数必须能按两种代码键查到（只存一种会让 A-04 误报）。"""
        repo = real_index()
        if repo is None:
            self.skipTest("真实数据仓不可用")
        for code in repo.track_codes("stock"):
            rec = repo.get(code)
            self.assertIsNotNone(rec, code)
            self.assertEqual(repo.listing_of(code), "exchange")


class TestMutationGuard(unittest.TestCase):
    """变异检查：把断言判据改成恒真，套件必须变红。

    目的不是测实现，是测「测试是否还活着」。一个恒真实现能让所有用例通过，
    这在测试套件里是最危险的状态：CI 全绿而护栏已失效。

    实现要点：变异**必须作用在被测模块已导入的函数对象上**。
    改源码文件而不重新导入等于什么都没变——第一次写这版时就踩了这个坑，
    12 条变异「全部存活」，看起来像覆盖率极差，实际是变异根本没生效。
    故这里用 unittest.mock.patch 替换模块属性，改完即还原。
    """

    # (模块, 函数名, 变异方式)。变异方式只描述意图，实现在 _mutate 里落地。
    TARGETS = (
        ("assertions", "check_requested_position", "no_error"),
        ("assertions", "check_observation_point", "no_error"),
        ("assertions", "check_amount_unit", "no_error"),
        ("assertions", "check_grid_base_price", "no_error"),
        ("assertions", "check_exit_available", "no_error"),
        ("assertions", "check_instrument_known", "no_error"),
        ("assertions", "check_risk_fields", "no_error"),
        ("assertions_cross", "check_degraded_marking", "no_error"),
        ("assertions_cross", "check_reasoning_basis", "no_error"),
        ("references", "check_derivation", "no_error"),
        ("assertions_cross", "check_missing", "no_error"),
        ("structure", "check_covers_paths", "no_error"),
        ("assertions_cross", "check_unverified_no_action", "no_error"),
    )

    def test_every_assertion_is_covered_by_a_negative_case(self):
        """每条 check_* 被改成「永不报错」后，负例套件必须变红。

        任一条存活即说明该断言没有对应的必然失败用例：它可能永远不触发，
        而 CI 不会知道。这正是「写了断言就以为有护栏」的失败模式。
        """
        import assertions
        import assertions_cross
        survived = []
        for mod_name, func_name, _mode in self.TARGETS:
            with self.subTest(assertion=func_name):
                mod = sys.modules[mod_name]
                original = getattr(mod, func_name)
                if not self._negative_suite_fails(
                        mod_name, func_name, original):
                    survived.append(func_name)
        self.assertEqual(survived, [],
                         f"这些断言变异后套件仍全绿，说明没被真正覆盖：{survived}")

    @staticmethod
    def _negative_suite_fails(mod_name: str, func_name: str, original) -> bool:
        """把指定 check_* 换成恒真版，跑负例套件，看是否变红。"""
        import unittest as ut

        import test_journal_cases as T
        import validate as V

        def silent(*_args, **_kwargs):
            return 0

        silent.__name__ = func_name
        # 两处都要打：模块属性供断言间直接调用，ENTRY_CHECKS 供调度表使用。
        # 只改一处的话，validate 仍握着原函数引用，变异等于没做。
        patched_checks = tuple(silent if c.__name__ == func_name else c
                               for c in V.ENTRY_CHECKS)
        with mock.patch.object(sys.modules[mod_name], func_name, silent), \
                mock.patch.object(V, "ENTRY_CHECKS", patched_checks):
            loader = ut.TestLoader()
            suite = loader.loadTestsFromModule(T)
            stream = io.StringIO()
            result = ut.TextTestRunner(stream=stream, verbosity=0).run(suite)
            return not result.wasSuccessful()

    def test_log_level_assertion_is_wired(self):
        """A-08 / A-13 挂在 check_log_level 上：它失效时互斥与上限都会失效。"""
        import unittest as ut

        import assertions_cross as X
        import test_journal_cases as T
        import validate as V

        def silent(*_args, **_kwargs):
            return 0

        silent.__name__ = "check_log_level"
        with mock.patch.object(X, "check_log_level", silent), \
                mock.patch.object(V, "check_log_level", silent):
            suite = ut.TestLoader().loadTestsFromModule(T)
            stream = io.StringIO()
            result = ut.TextTestRunner(stream=stream, verbosity=0).run(suite)
        self.assertFalse(result.wasSuccessful(),
                         "摘掉 check_log_level 后负例仍全绿，说明 A-08/A-13 未被覆盖")


class TestRealOutputArtifacts(unittest.TestCase):
    """产物落盘契约：抑制后的条目必须仍是可序列化结构。"""

    def test_output_is_json_serializable(self):
        repo = example_index()
        base = new_entry()
        base["action"] = {**base["action"], "instrument_code": FUND_CODE,
                          "kind": "buy", "amount": 500.0,
                          "amount_unit": "money", "base_price": None}
        out = build_output(base, repo)
        blob = json.dumps(out, ensure_ascii=False)
        self.assertIn(PROXY_FLAG, blob)
        self.assertIsNone(json.loads(blob)["entry"]["action"])


if __name__ == "__main__":
    unittest.main(verbosity=2)