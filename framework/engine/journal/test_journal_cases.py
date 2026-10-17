#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_journal_cases.py — 16 条断言的负例套件（纯标准库，零依赖）

一条断言如果只有正例，就没人知道它会不会真炸。本文件对 A-01..A-16
各构造至少一个**必然失败**的条目，断言错误码落在预期值上。

每个用例的构造方式：取合法骨架 -> 只改坏一处。改多处会让失败原因
指向错误的规则，测的就不是这条断言了。

「必然失败」由 journal_fixtures.assert_rejected 保证：它先验证同一构造器的
未改版本能通过校验，再验证改坏的版本被拒且错误码匹配。

运行：python3 test_journal_cases.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from contracts import (  # noqa: E402
    ASSERTION_CODES, E_A01_REQUESTED_POSITION, E_A02_OBSERVATION_FIELDS,
    E_A03_AMOUNT_UNIT, E_A04_GRID_BASE_PRICE, E_A05_EXIT_AVAILABLE,
    E_A06_ORPHAN_INSTRUMENT, E_A07_RISK_FIELDS, E_A08_GRID_REBALANCE_EXCLUSIVE,
    E_A09_DEGRADED_MARKING, E_A10_REASONING_BASIS, E_A11_DERIVATION_REF,
    E_A12_MISSING_MUST_BE_NULL, E_A13_ACTION_COUNT_CAP,
    E_A14_UNVERIFIED_WITH_ACTION, E_A15_TRACK_INDEPENDENCE,
    E_A16_COVERS_PATHS,
)
from journal_fixtures import (  # noqa: E402
    ORPHAN_CODE, assert_rejected, example_index, new_entry, run_entry, run_log,
)


class TestPositionAndObservation(unittest.TestCase):
    """A-01 / A-02 / A-03：数量、观察点四字段、金额口径。"""

    def test_a01_missing_requested_position(self):
        """A-01：给方向不给数量即拒（用户指令原文的落点）。"""
        ent = new_entry(requested_position=None)
        rep = assert_rejected(self, ent, E_A01_REQUESTED_POSITION)
        self.assertTrue(any("requested_position" in e["message"]
                            for e in rep.errors))

    def test_a02_each_observation_field_required(self):
        """A-02：四个字段逐个抽掉，每个都必须炸。"""
        for field in ("trigger", "condition", "invalidation",
                      "monitoring_window"):
            with self.subTest(field=field):
                base = new_entry()
                broken = {**base, "observation_point": {
                    **base["observation_point"], field: None}}
                assert_rejected(self, broken, E_A02_OBSERVATION_FIELDS)

    def test_a03_unit_required_and_no_dual_amount(self):
        """A-03：口径必填 + 禁 money/shares 同时给（禁换算执行）。"""
        base = new_entry()
        no_unit = {**base, "action": {**base["action"],
                                      "amount_unit": None}}
        assert_rejected(self, no_unit, E_A03_AMOUNT_UNIT)
        req = {**base["requested_position"], "converted_amount": 2400.0}
        assert_rejected(self, {**base, "requested_position": req},
                        E_A03_AMOUNT_UNIT)
        bad_unit = {**base, "action": {**base["action"],
                                       "amount_unit": "yuan"}}
        assert_rejected(self, bad_unit, E_A03_AMOUNT_UNIT)


class TestActionRules(unittest.TestCase):
    """A-04 / A-05 / A-06 / A-15：网格锚点、可平仓、孤儿标的、跨轨独立。"""

    def test_a04_grid_requires_base_price(self):
        """A-04：网格动作缺 base_price 即拒（不得从配置静默代填）。"""
        base = new_entry()
        assert_rejected(self, {**base, "action": {
            **base["action"], "kind": "grid", "base_price": None}},
            E_A04_GRID_BASE_PRICE)

    def test_a05_exit_requires_available(self):
        """A-05：卖出 900 股 > available 400 股即拒。

        数值取自 portfolio.example.yaml 的 600312（shares 500 / available 400，
        故意留了 T+1 冻结），不是随手写的整数——夹具变了这个断言要跟着变，
        这正是它该有的耦合。
        """
        base = new_entry()
        over = {**base, "action": {**base["action"], "kind": "sell",
                                   "amount": 900, "amount_unit": "shares"}}
        assert_rejected(self, over, E_A05_EXIT_AVAILABLE)
        in_money = {**base, "action": {**base["action"], "kind": "sell",
                                       "amount": 2100.0,
                                       "amount_unit": "money"}}
        assert_rejected(self, in_money, E_A05_EXIT_AVAILABLE)

    def test_a06_orphan_instrument(self):
        """A-06：数据仓里没有的代码即拒（孤儿标的）。"""
        base = new_entry()
        orphan = {**base, "action": {**base["action"],
                                     "instrument_code": ORPHAN_CODE}}
        assert_rejected(self, orphan, E_A06_ORPHAN_INSTRUMENT)

    def test_a15_fund_track_rejects_on_track_only_keys(self):
        """A-15：场外基金动作不得引用网格/委托/持仓类场内机制。"""
        base = new_entry()
        act = {**base["action"], "instrument_code": "000979", "kind": "buy",
               "amount": 500.0, "amount_unit": "money", "base_price": 2.1,
               "available": 500}
        assert_rejected(self, {**base, "action": act},
                        E_A15_TRACK_INDEPENDENCE)
        wrong_track = {**base, "action": {**base["action"],
                                          "instrument_code": "000979",
                                          "kind": "buy", "track": "stock"}}
        assert_rejected(self, wrong_track, E_A15_TRACK_INDEPENDENCE)


class TestRiskAndCrossEntry(unittest.TestCase):
    """A-07 / A-08 / A-14 / A-16：风控四字段、互斥、UNVERIFIED、覆盖声明。"""

    def test_a07_each_risk_field_required(self):
        """A-07：stop_loss / method_semantics / confidence / limit_conditions
        逐个抽掉，每个都必须炸。"""
        base = new_entry()
        for field in ("stop_loss", "method_semantics", "confidence",
                      "limit_conditions"):
            with self.subTest(field=field):
                empty = [] if isinstance(base["risk"][field], list) else None
                broken = {**base, "risk": {**base["risk"], field: empty}}
                assert_rejected(self, broken, E_A07_RISK_FIELDS)

    def test_a08_grid_and_full_rebalance_exclusive(self):
        """A-08：同一 observation_point 下 grid 与 full_rebalance 互斥。"""
        repo = example_index()
        base = new_entry()
        second = new_entry(action={**base["action"], "code": "ACT-2",
                                   "kind": "full_rebalance",
                                   "base_price": None})
        third = new_entry(action={**base["action"], "code": "ACT-3",
                                  "kind": "grid"})
        rep = run_log([base, second, third], repo)
        self.assertFalse(rep.ok)
        self.assertIn(E_A08_GRID_REBALANCE_EXCLUSIVE, {e["code"]
                                                       for e in rep.errors})

    def test_a14_unverified_cannot_carry_action(self):
        """A-14：UNVERIFIED 条目只能作为 observation。"""
        base = new_entry()
        assert_rejected(self, {**base, "classification_verified": "UNVERIFIED"},
                        E_A14_UNVERIFIED_WITH_ACTION)

    def test_a16_covers_paths_required(self):
        """A-16：covers_paths 必填非空。"""
        for bad in (None, [], "not-a-list"):
            with self.subTest(covers=bad):
                assert_rejected(self, new_entry(covers_paths=bad),
                                E_A16_COVERS_PATHS)


class TestIntegrityRules(unittest.TestCase):
    """A-09 / A-10 / A-11 / A-12：降级标注、推理来源、推导引用、缺失登记。"""

    def test_a09_threshold_degradation_must_be_marked(self):
        """A-09：阈值降级成哨兵值（0 / 阈值带）必须标 degraded。"""
        base = new_entry()
        for sentinel in (0, "阈值带", "TBD"):
            with self.subTest(sentinel=sentinel):
                broken = {**base, "observation_point": {
                    **base["observation_point"], "threshold": sentinel}}
                assert_rejected(self, broken, E_A09_DEGRADED_MARKING)
        # 标了 degraded 但没写理由，同样拒（光标不解释等于把问题转交）
        silent = {**base, "observation_point": {
            **base["observation_point"], "threshold": 0,
            "degraded": True, "degraded_reason": None}}
        assert_rejected(self, silent, E_A09_DEGRADED_MARKING)
        # 标全了才放行
        good = {**base, "observation_point": {
            **base["observation_point"], "threshold": 0,
            "degraded": True, "degraded_reason": "分时价未取到"}}
        self.assertTrue(run_entry(good, example_index()).ok)

    def test_a10_generated_reasoning_rejected(self):
        """A-10：reasoning_basis=GENERATED 即拒。"""
        assert_rejected(self, new_entry(reasoning_basis="GENERATED"),
                        E_A10_REASONING_BASIS)

    def test_a11_derivation_refs_must_exist(self):
        """A-11：input_ref/output_ref 必须真实存在，且禁 reference_format。"""
        base = new_entry()
        dangling = {**base, "derivation": [{
            "step": "凭印象", "input_ref": "portfolio.999998.base_price",
            "output_ref": "action.price"}]}
        assert_rejected(self, dangling, E_A11_DERIVATION_REF)
        with_format = {**base, "derivation": [{
            "step": "按格式写", "input_ref": "entry.observation_point.trigger",
            "output_ref": "action.price", "reference_format": "v2"}]}
        assert_rejected(self, with_format, E_A11_DERIVATION_REF)
        assert_rejected(self, {**base, "derivation": []},
                        E_A11_DERIVATION_REF)

    def test_a12_missing_fields_must_be_null(self):
        """A-12：登记 missing 的字段必须真为 None（不可用优于默认值）。"""
        base = new_entry()
        with_default = {**base, "action": {**base["action"], "price": 21.0},
                        "missing": ["action.price"]}
        assert_rejected(self, with_default, E_A12_MISSING_MUST_BE_NULL)
        ghost = {**base, "missing": ["action.no_such_field"]}
        assert_rejected(self, ghost, E_A12_MISSING_MUST_BE_NULL)
        # 真为 None 时登记合法。但推导链不能引用它——引用不可得的量会被
        # A-11 拦下（这正是「登记缺失」与「把它当依据」必须分开的理由）。
        nulled = {**base, "action": {**base["action"], "price": None},
                  "missing": ["action.price"],
                  "derivation": [{"step": "按网格锚点挂买",
                                  "input_ref": "portfolio.600312.base_price",
                                  "output_ref": "action.base_price"}]}
        self.assertTrue(run_entry(nulled, example_index()).ok)


class TestLogLevelCap(unittest.TestCase):
    """A-13：同观察点动作数上限（可配置）。"""

    def test_a13_action_count_cap(self):
        """A-13：同一 observation_point 下 5 条动作超上限（默认 3）。"""
        repo = example_index()
        base = new_entry()
        entries = [new_entry(action={**base["action"], "code": f"ACT-{i}"})
                   for i in range(5)]
        rep = run_log(entries, repo, max_actions=3)
        self.assertFalse(rep.ok)
        self.assertIn(E_A13_ACTION_COUNT_CAP, {e["code"] for e in rep.errors})
        # 上限可配置：放宽到 5 后放行
        self.assertTrue(run_log(entries, repo, max_actions=5).ok)
        # 非法上限直接拒绝，不静默套用默认
        with self.assertRaises(ValueError):
            run_log(entries, repo, max_actions=0)


class TestAssertionCoverage(unittest.TestCase):
    """元断言：16 条断言的错误码与用例一一对应，且都不曾消失。"""

    def test_all_sixteen_codes_are_reachable(self):
        """每个 A-码都必须至少被一个 check_* 产出——忘了挂进调度表就永不触发。"""
        from validate import assertion_coverage
        cov = assertion_coverage()
        self.assertEqual(len(cov), 16)
        for code, produced in sorted(cov.items()):
            with self.subTest(code=code):
                self.assertTrue(produced, f"{code} 没有被任何断言产出")
        self.assertEqual(set(cov), set(ASSERTION_CODES))


if __name__ == "__main__":
    unittest.main(verbosity=2)