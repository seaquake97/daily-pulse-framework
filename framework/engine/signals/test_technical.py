#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_technical.py — 纯标准库技术指标单元测试套件"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import technical as tech


class TestMovingAverage(unittest.TestCase):
    def test_empty_and_short_series(self):
        self.assertEqual(tech.calculate_ma([], 5), [])
        self.assertEqual(tech.calculate_ma([10.0, 11.0], 5), [None, None])

    def test_ma_exact_and_sliding(self):
        prices = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
        res = tech.calculate_ma(prices, 5)
        # 前4个为 None，第5个为 (10+20+30+40+50)/5 = 30.0，第6个为 (20+30+40+50+60)/5 = 40.0
        self.assertEqual(res[:4], [None, None, None, None])
        self.assertAlmostEqual(res[4], 30.0)
        self.assertAlmostEqual(res[5], 40.0)

    def test_invalid_window(self):
        with self.assertRaises(ValueError):
            tech.calculate_ma([10.0], 0)


class TestDynamicBias(unittest.TestCase):
    def test_pullback_below_ma(self):
        # 现价低于 MA，属于回踩支撑观察
        r = tech.calculate_bias(current_price=19.5, ma=20.0, strong_trend=False)
        self.assertEqual(r["status"], "pullback")
        self.assertLess(r["bias"], 0.0)
        self.assertFalse(r["strong_compensated"])

    def test_normal_within_threshold(self):
        # 现价 20.6，MA 20.0，乖离率 +3.0%，在基础 5% 阈值内
        r = tech.calculate_bias(current_price=20.6, ma=20.0, strong_trend=False)
        self.assertEqual(r["status"], "normal")
        self.assertAlmostEqual(r["bias"], 0.03)
        self.assertEqual(r["threshold"], 0.05)

    def test_chase_risk_without_strong_trend(self):
        # 现价 21.2，MA 20.0，乖离率 +6.0%，超过 5%，判定追高风险
        r = tech.calculate_bias(current_price=21.2, ma=20.0, strong_trend=False)
        self.assertEqual(r["status"], "chase_risk")
        self.assertEqual(r["threshold"], 0.05)

    def test_strong_trend_compensation_active(self):
        # 核心逻辑验证：强势趋势补偿触发！
        # 现价 21.2，MA 20.0，乖离率 +6.0%。
        # 当 strong_trend=True 时，有效阈值自动放宽 1.5 倍至 7.5%，允许顺势追踪！
        r = tech.calculate_bias(current_price=21.2, ma=20.0, strong_trend=True)
        self.assertEqual(r["status"], "strong_tracking")
        self.assertEqual(r["threshold"], 0.075)
        self.assertTrue(r["strong_compensated"])

    def test_extreme_bias_chase_risk_even_if_strong(self):
        # 现价 21.8，MA 20.0，乖离率 +9.0%，即使放宽到 7.5% 依然超标，严守追高红线
        r = tech.calculate_bias(current_price=21.8, ma=20.0, strong_trend=True)
        self.assertEqual(r["status"], "chase_risk")


class TestWilderRSI(unittest.TestCase):
    def test_short_series_returns_nones(self):
        res = tech.calculate_wilder_rsi([10.0, 11.0, 12.0], period=14)
        self.assertEqual(res, [None, None, None])

    def test_consecutive_gains_reaches_high_rsi(self):
        # 连续 20 天上涨，RSI 应该非常高（接近 100）
        prices = [10.0 + i * 1.0 for i in range(25)]
        res = tech.calculate_wilder_rsi(prices, period=14)
        self.assertIsNotNone(res[-1])
        self.assertGreater(res[-1], 95.0)

    def test_consecutive_losses_reaches_low_rsi(self):
        # 连续 20 天下跌，RSI 应该非常低（接近 0）
        prices = [50.0 - i * 1.0 for i in range(25)]
        res = tech.calculate_wilder_rsi(prices, period=14)
        self.assertIsNotNone(res[-1])
        self.assertLess(res[-1], 5.0)


class TestMACD(unittest.TestCase):
    def test_short_series_returns_nones(self):
        res = tech.calculate_macd([10.0] * 10)
        self.assertTrue(all(x is None for x in res))

    def test_macd_structure(self):
        # 构造 40 个价格点
        prices = [10.0 + (i % 5) * 0.5 for i in range(40)]
        res = tech.calculate_macd(prices, fast=12, slow=26, signal=9)
        # 前 25 个为 None，第 26 个开始产出 dict
        self.assertIsNone(res[24])
        self.assertIsNotNone(res[25])
        bar_dict = res[25]
        self.assertIn("dif", bar_dict)
        self.assertIn("dea", bar_dict)
        self.assertIn("bar", bar_dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
