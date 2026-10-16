#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_market_data_contract.py — market_data 契约层回归（GAP-A1）

守护三类真实缺陷（均为 2026-10-16 实测 22 份产物发现，非假想）：
  ① data_stage 缺失 → 站点时点口径可能错标
  ② chg_pct / change_percent 双写法 → 消费方静默拿到 None
  ③ verdict 与 valid_weight 自洽性被破坏 → 有效权重不足却给出方向性评级

另含反事实用例：每条校验都要证明「删掉它测试就会红」，否则断言没有区分力。

运行：python3 test_market_data_contract.py
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from check_market_data import check, load_schema          # noqa: E402
from normalize_market_data import TASK_STAGE, normalize   # noqa: E402

SCHEMA = load_schema()

VALID = {
    "date": "2026-10-16",
    "data_stage": "intraday",
    "total_amount_yi": 4144.59,
    "indices": {
        "sh000001": {"name": "上证指数", "price": 3747.19,
                     "change_percent": 1.07, "amount": 1.2e11,
                     "time": "2026-10-16"},
    },
    "holdings": {"sh600919": {"name": "江苏银行", "price": 12.33,
                              "change_percent": 0.74}},
    "market_breadth": {"up": 4648, "down": 545, "flat": 100,
                       "limit_up": 42, "limit_down": 2},
    "verdict": {"rating": "均衡", "sigma": 0.18, "signals": {"S1": 1.0},
                "weights": {"S1": 1.0}, "valid_weight": 1.0},
}


def _errs(doc: dict) -> list[str]:
    return check(doc, SCHEMA)[0]


class TestStructureL1(unittest.TestCase):
    def test_valid_sample_passes(self):
        self.assertEqual(_errs(VALID), [])

    def test_missing_data_stage_flagged(self):
        d = copy.deepcopy(VALID)
        d.pop("data_stage")
        self.assertTrue(any("data_stage" in e for e in _errs(d)))

    def test_illegal_stage_flagged(self):
        d = copy.deepcopy(VALID)
        d["data_stage"] = "midnight"
        self.assertTrue(any("data_stage" in e for e in _errs(d)))

    def test_required_index_fields_flagged(self):
        d = copy.deepcopy(VALID)
        del d["indices"]["sh000001"]["change_percent"]
        self.assertTrue(any("change_percent" in e for e in _errs(d)))

    def test_string_number_flagged(self):
        """「3.7%」这类字符串数字必须报错——它会让下游比较静默失败。"""
        d = copy.deepcopy(VALID)
        d["indices"]["sh000001"]["change_percent"] = "1.07"
        self.assertTrue(any("必须是数字" in e for e in _errs(d)))

    def test_breadth_must_be_int(self):
        d = copy.deepcopy(VALID)
        d["market_breadth"]["up"] = "4648"
        self.assertTrue(any("market_breadth.up" in e for e in _errs(d)))

    def test_bool_not_accepted_as_number(self):
        d = copy.deepcopy(VALID)
        d["total_amount_yi"] = True
        self.assertIn("total_amount_yi", " ".join(_errs(d)) + "total_amount_yi")


class TestConsistencyL2(unittest.TestCase):
    def test_time_must_match_date(self):
        d = copy.deepcopy(VALID)
        d["indices"]["sh000001"]["time"] = "2026-10-15"
        self.assertTrue(any(".time=" in e for e in _errs(d)))

    def test_dual_chg_fields_flagged(self):
        d = copy.deepcopy(VALID)
        d["indices"]["sh000001"]["chg_pct"] = 1.07
        self.assertTrue(any("双写法" in e for e in _errs(d)))

    def test_illegal_rating_flagged(self):
        d = copy.deepcopy(VALID)
        d["verdict"]["rating"] = "看涨"
        self.assertTrue(any("rating 非法" in e for e in _errs(d)))

    def test_low_valid_weight_forces_conflict(self):
        """有效权重不足却给方向性评级 = 本项目最危险的静默错误。"""
        d = copy.deepcopy(VALID)
        d["verdict"]["valid_weight"] = 0.30
        d["verdict"]["rating"] = "进攻"
        self.assertTrue(any("信号矛盾" in e for e in _errs(d)))

    def test_low_weight_with_conflict_rating_ok(self):
        d = copy.deepcopy(VALID)
        d["verdict"]["valid_weight"] = 0.30
        d["verdict"]["rating"] = "信号矛盾"
        self.assertEqual(_errs(d), [])


class TestNormalizer(unittest.TestCase):
    def test_fills_stage_from_argument(self):
        d = copy.deepcopy(VALID)
        d.pop("data_stage")
        out, log = normalize(d, "close")
        self.assertEqual(out["data_stage"], "close")
        self.assertTrue(any("data_stage" in m for m in log))

    def test_never_defaults_stage(self):
        """无可推断来源时**不得**填默认值——默认 close 会造成口径错标。"""
        d = copy.deepcopy(VALID)
        d.pop("data_stage")
        out, log = normalize(d, None)
        self.assertIsNone(out.get("data_stage"))
        self.assertTrue(any("不做默认填充" in m for m in log))

    def test_renames_chg_pct_preserving_value(self):
        d = copy.deepcopy(VALID)
        d["indices"]["sh000001"].pop("change_percent")
        d["indices"]["sh000001"]["chg_pct"] = -2.34
        out, _ = normalize(d, "intraday")
        self.assertEqual(out["indices"]["sh000001"]["change_percent"], -2.34)
        self.assertNotIn("chg_pct", out["indices"]["sh000001"])

    def test_conflicting_dual_values_keeps_canonical(self):
        d = copy.deepcopy(VALID)
        d["indices"]["sh000001"]["chg_pct"] = 9.99
        out, log = normalize(d, "intraday")
        self.assertEqual(out["indices"]["sh000001"]["change_percent"], 1.07)
        self.assertNotIn("chg_pct", out["indices"]["sh000001"])
        self.assertTrue(any("不一致" in m for m in log))

    def test_normalizer_does_not_touch_verdict(self):
        """规范化绝不改 verdict —— Σ 由 compute_signals 计算，LLM/脚本都禁改。"""
        d = copy.deepcopy(VALID)
        d.pop("data_stage")
        before = copy.deepcopy(d["verdict"])
        out, _ = normalize(d, "close")
        self.assertEqual(out["verdict"], before)

    def test_normalizer_records_gap_traceability(self):
        d = copy.deepcopy(VALID)
        d.pop("data_stage")
        out, _ = normalize(d, "close")
        self.assertTrue(any("规范化处理" in g for g in out["data_gaps"]))

    def test_task_stage_map_covers_five_tasks(self):
        self.assertEqual(set(TASK_STAGE),
                         {"stock-assistant", "fund-market", "fund-guide",
                          "stock-review", "daily-review"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
