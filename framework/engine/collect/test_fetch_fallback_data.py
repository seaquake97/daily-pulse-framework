#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_fetch_fallback_data.py — 备用源自动抓取与合并编排器单测（全离线 Mock）"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import fallback_fetcher as FF
import fetch_fallback_data as FFD


def _mock_healthy_market_data():
    return {
        "date": "2026-10-16",
        "data_stage": "pre_open",
        "indices": {
            "sh000001": {"name": "上证指数", "price": 3716.28, "change_percent": 0.24, "amount": 7.3e11},
            "sz399001": {"name": "深证成指", "price": 11802.46, "change_percent": -0.12, "amount": 8.2e11},
            "sh000300": {"name": "沪深300", "price": 4170.61, "change_percent": 0.11, "amount": 4.1e11},
            "sz399006": {"name": "创业板指", "price": 2772.38, "change_percent": -0.39, "amount": 3.9e11},
            "sh000688": {"name": "科创50", "price": 1358.65, "change_percent": -0.06, "amount": 7.1e10},
        },
        "holdings": {
            "sh600312": {"name": "平高电气", "price": 20.74, "amount": 500},
        },
        "data_source": "primary_westock",
        "data_gaps": [],
    }


class TestFetchFallbackData(unittest.TestCase):
    def test_healthy_primary_does_not_fetch(self):
        """主源数据完整时，不调用 fetch_fn，不执行多余抓取。"""
        doc = _mock_healthy_market_data()
        called = False

        def mock_fetch(codes):
            nonlocal called
            called = True
            return FF.FetchResult(data={}, sources=[], warnings=[], missing=[])

        out, gaps = FFD.ensure_market_data(doc, fetch_fn=mock_fetch)
        self.assertFalse(called, "主源完整时不应调用 fetch 接口")
        self.assertEqual(gaps, [])
        self.assertEqual(out["data_source"], "primary_westock")

    def test_missing_indices_triggers_fetch_and_merge(self):
        """核心指数缺失时触发抓取，并成功合并。"""
        doc = _mock_healthy_market_data()
        del doc["indices"]["sz399001"]  # 人为制造缺失

        mock_fallback_data = {
            "sz399001": {
                "name": "深证成指", "price": 11800.0, "change_percent": -0.15,
                "amount": 8.0e11, "volume": 5.0e8, "time": "2026-10-16", "source": "tencent"
            }
        }

        def mock_fetch(codes):
            return FF.FetchResult(data=mock_fallback_data, sources=["tencent"], warnings=[], missing=[])

        out, gaps = FFD.ensure_market_data(doc, fetch_fn=mock_fetch)
        self.assertIn("sz399001", out["indices"])
        self.assertEqual(out["indices"]["sz399001"]["price"], 11800.0)
        self.assertEqual(out["data_source"], "fallback_public")
        self.assertIn("indices.sz399001.price", out.get("fallback_fields", []))

    def test_primary_precedence_preserved(self):
        """主源已有字段优先，备用源不会覆盖主源已有数值。"""
        doc = _mock_healthy_market_data()
        doc["indices"]["sh000001"]["price"] = 3716.28
        doc["indices"]["sz399001"]["price"] = None  # 仅这个缺失

        mock_fallback_data = {
            "sh000001": {"name": "上证指数备用", "price": 9999.99, "change_percent": 1.0, "source": "tencent"},
            "sz399001": {"name": "深成指备用", "price": 11800.0, "change_percent": -0.15, "source": "tencent"},
        }

        def mock_fetch(codes):
            return FF.FetchResult(data=mock_fallback_data, sources=["tencent"], warnings=[], missing=[])

        out, gaps = FFD.ensure_market_data(doc, force=True, fetch_fn=mock_fetch)
        # sh000001 的 price 保持 3716.28，不被覆盖为 9999.99
        self.assertEqual(out["indices"]["sh000001"]["price"], 3716.28)
        # sz399001 原为 None，被成功补上
        self.assertEqual(out["indices"]["sz399001"]["price"], 11800.0)

    def test_missing_codes_recorded_in_data_gaps(self):
        """备用源也未能取到的代码必须贯通进 data_gaps。"""
        doc = _mock_healthy_market_data()
        del doc["indices"]["sh000001"]

        def mock_fetch(codes):
            return FF.FetchResult(data={}, sources=[], warnings=[], missing=["sh000001"])

        out, gaps = FFD.ensure_market_data(doc, fetch_fn=mock_fetch)
        self.assertTrue(any("sh000001" in g for g in out["data_gaps"]))
        self.assertEqual(out["data_source"], "degraded")

    def test_idempotence(self):
        """连续两次 ensure 结果幂等。"""
        doc = _mock_healthy_market_data()
        doc["indices"]["sz399001"]["price"] = None

        mock_fallback_data = {
            "sz399001": {"name": "深成指", "price": 11800.0, "change_percent": -0.15, "source": "tencent"}
        }

        def mock_fetch(codes):
            return FF.FetchResult(data=mock_fallback_data, sources=["tencent"], warnings=[], missing=[])

        first, _ = FFD.ensure_market_data(doc, force=True, fetch_fn=mock_fetch)
        second, _ = FFD.ensure_market_data(first, force=True, fetch_fn=mock_fetch)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
