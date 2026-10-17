#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_primary_health.py — 主源降级判定单测（全离线）

核心反例：主源完整时**不得**判降级 —— 误判会无谓触发备用源抓取，成本与风险都实打实。

运行：python3 framework/engine/collect/test_primary_health.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import merge_fallback as mf  # noqa: E402
import primary_health as ph  # noqa: E402


def healthy_doc() -> dict:
    """主源完整：核心指数齐、price/change_percent 均有值、无连接器缺口。"""
    return {
        "date": "2026-10-16",
        "indices": {
            "sh000001": {"name": "上证指数", "price": 3726.11, "change_percent": 0.5,
                         "amount": 1.2e11, "time": "2026-10-16"},
            "sz399001": {"name": "深证成指", "price": 11903.73, "change_percent": 0.74,
                         "amount": 1.4e11, "time": "2026-10-16"},
            "sh000300": {"name": "沪深300", "price": 4181.22, "change_percent": 0.37,
                         "amount": 3.1e10, "time": "2026-10-16"},
            "sz399006": {"name": "创业板指", "price": 2801.87, "change_percent": 0.67,
                         "amount": 7.2e10, "time": "2026-10-16"},
            "sh000688": {"name": "科创50", "price": 1368.28, "change_percent": 1.1,
                         "amount": 9.0e10, "time": "2026-10-16"},
        },
        "market_breadth": {"up": 4648, "down": 545, "flat": 0, "limit_up": 42,
                           "limit_down": 2},
        "sector_flows": {"top_inflow": 17.1, "top_outflow": 4.22},
    }


class TestConstants(unittest.TestCase):
    """核心指数必须是备用源覆盖范围的子集，否则判了降级备用源也补不了。"""

    def test_core_codes_within_fallback_coverage(self):
        self.assertTrue(set(ph.CORE_INDEX_CODES).issubset(set(mf.FALLBACK_INDEX_CODES)))

    def test_essential_fields_are_mergeable(self):
        self.assertTrue(set(ph.ESSENTIAL_FIELDS).issubset(set(mf.MERGEABLE_FIELDS)))


class TestNotDegraded(unittest.TestCase):
    """反例优先：完整主源不得判降级（误判会无谓触发抓取）。"""

    def test_healthy_doc_not_degraded(self):
        self.assertFalse(ph.is_primary_degraded(healthy_doc()))
        self.assertEqual(ph.degradation_reasons(healthy_doc()), [])

    def test_zero_change_percent_is_not_a_gap(self):
        doc = healthy_doc()
        doc["indices"]["sh000001"]["change_percent"] = 0.0
        self.assertFalse(ph.is_primary_degraded(doc))

    def test_non_connector_gap_does_not_trigger(self):
        """普通字段缺口（非连接器类）不构成启用备用源的理由。"""
        doc = healthy_doc()
        doc["data_gaps"] = ["sz563230 已自动规范化映射为 sh563230",
                            "外盘数据本轮未采集"]
        self.assertFalse(ph.is_primary_degraded(doc))

    def test_unfillable_sections_missing_does_not_trigger(self):
        """板块资金流/涨跌家数备用源补不了，缺了也不该触发抓取。"""
        doc = healthy_doc()
        doc.pop("sector_flows")
        doc.pop("market_breadth")
        self.assertFalse(ph.is_primary_degraded(doc))

    def test_non_core_index_missing_does_not_trigger(self):
        """非核心指数（bj899050）缺了不触发：备用源覆盖不到，抓也白抓。"""
        doc = healthy_doc()
        self.assertFalse(ph.is_primary_degraded(doc))   # 本就不含 bj899050


class TestDegraded(unittest.TestCase):
    def test_not_a_dict(self):
        for bad in (None, [], "x", 42):
            with self.subTest(bad=bad):
                self.assertTrue(ph.is_primary_degraded(bad))
                self.assertTrue(ph.degradation_reasons(bad))

    def test_indices_missing_or_empty(self):
        for bad in ({}, {"indices": None}, {"indices": {}}, {"indices": []}):
            with self.subTest(bad=bad):
                self.assertTrue(ph.is_primary_degraded(bad))

    def test_core_index_absent(self):
        for code in ph.CORE_INDEX_CODES:
            doc = healthy_doc()
            doc["indices"].pop(code)
            with self.subTest(code=code):
                self.assertTrue(ph.is_primary_degraded(doc))
                self.assertTrue(any(code in r for r in ph.degradation_reasons(doc)))

    def test_price_missing_or_non_positive(self):
        for price in (None, 0, -1.0, "abc"):
            doc = healthy_doc()
            doc["indices"]["sh000001"]["price"] = price
            with self.subTest(price=price):
                self.assertTrue(ph.is_primary_degraded(doc))

    def test_change_percent_missing(self):
        for pct in (None, "abc"):
            doc = healthy_doc()
            doc["indices"]["sh000300"]["change_percent"] = pct
            with self.subTest(pct=pct):
                self.assertTrue(ph.is_primary_degraded(doc))

    def test_entry_not_a_dict(self):
        doc = healthy_doc()
        doc["indices"]["sh000001"] = ["坏数据"]
        self.assertTrue(ph.is_primary_degraded(doc))

    def test_connector_gap_triggers(self):
        for gap in ("westock-mcp 连接器未连接", "连接器不可用，本轮降级采集",
                    "MCP 不可达：超时"):
            doc = healthy_doc()
            doc["data_gaps"] = [gap]
            with self.subTest(gap=gap):
                self.assertTrue(ph.is_primary_degraded(doc))

    def test_connector_gap_triggers_even_when_indices_complete(self):
        """刻意保留的行为：通道不可用即判降级，与 indices 是否完整无关。"""
        doc = healthy_doc()
        doc["data_gaps"] = ["westock-mcp 连接器未连接：降级采用公开合规行情数据源采集"]
        self.assertTrue(ph.is_primary_degraded(doc))


class TestConnectorGapSwitch(unittest.TestCase):
    """真实样本：indices 完整但 data_gaps 留了连接器痕迹（当时已改走公开源采集成功）。"""

    def doc(self):
        doc = healthy_doc()
        doc["data_gaps"] = ["westock-mcp 连接器未连接：降级采用公开合规行情数据源采集，"
                            "字段契约 100% 对齐。"]
        return doc

    def test_default_counts_connector_gap(self):
        self.assertTrue(ph.is_primary_degraded(self.doc()))

    def test_switch_off_looks_at_data_only(self):
        """集成口径「数据完整就不启用备用源」时用此开关，避免为完整快照多跑一次抓取。"""
        self.assertFalse(ph.is_primary_degraded(self.doc(), include_connector_gaps=False))

    def test_switch_off_still_catches_real_missing_data(self):
        doc = self.doc()
        doc["indices"]["sh000300"]["price"] = None
        self.assertTrue(ph.is_primary_degraded(doc, include_connector_gaps=False))

    def test_multiple_reasons_all_reported(self):
        doc = healthy_doc()
        doc["indices"].pop("sh000001")
        doc["indices"]["sh000300"]["price"] = None
        doc["data_gaps"] = ["westock-mcp 连接器未连接"]
        reasons = ph.degradation_reasons(doc)
        self.assertTrue(any("sh000001" in r for r in reasons))
        self.assertTrue(any("sh000300.price" in r for r in reasons))
        self.assertTrue(any("连接器" in r for r in reasons))


class TestDeterminism(unittest.TestCase):
    def test_repeated_calls_stable(self):
        doc = healthy_doc()
        self.assertEqual(ph.degradation_reasons(doc), ph.degradation_reasons(doc))
        self.assertFalse(ph.is_primary_degraded(doc))

    def test_input_not_mutated(self):
        doc = healthy_doc()
        snapshot = {"indices": dict(doc["indices"])}
        ph.degradation_reasons(doc)
        self.assertEqual(set(doc["indices"]), set(snapshot["indices"]))

    def test_boolean_type_strict(self):
        self.assertIs(ph.is_primary_degraded(healthy_doc()), False)
        self.assertIs(ph.is_primary_degraded({}), True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
