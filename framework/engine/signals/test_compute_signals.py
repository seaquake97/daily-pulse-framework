#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_compute_signals.py — S4 动量/技术信号升级的单测套件（全离线，零网络）

覆盖三层契约：
  1. 向后兼容：不传 --rsi/--bias/--strong-trend 时，S4 与升级前 v1.2 实现逐字节一致
     （与 legacy_s4 黄金副本比对，含函数级返回值与 CLI 级 stdout）
  2. 动量确认：--rsi/--bias/--strong-trend 正确介入，复合公式 0.6*分化 + 0.4*动量成立，
     结果恒在 [-1, 1] clamp 内
  3. 降级不变：指数数据缺失时无论是否提供技术面入参，一律返回 None + 「数据缺口」

运行：python3 _git_engine/scripts/test_compute_signals.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import compute_signals as cs  # noqa: E402

PY = sys.executable
SCRIPT = HERE / "compute_signals.py"


# ---------------------------------------------------------------------------
# 黄金副本：升级前 v1.2 的 s4_divergence 实现，仅用于回归比对，禁止改动
# ---------------------------------------------------------------------------
def legacy_s4(idx):
    """v1.2 纯分化实现的黄金副本（compute_signals.py:105 升级前原文）。"""
    def _num(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    cy = _num((idx.get("sz399006") or {}).get("change_percent"))
    kc = _num((idx.get("sh000688") or {}).get("change_percent"))
    hs = _num((idx.get("sh000300") or {}).get("change_percent"))
    if None in (cy, kc, hs):
        return None, "数据缺口：成长/蓝筹指数缺失"
    spread = (cy + kc) / 2 - hs
    s = max(-1.0, min(1.0, spread / 2.0))
    return round(s, 3), f"成长均值 {(cy+kc)/2:+.2f}% vs 沪深300 {hs:+.2f}%，价差 {spread:+.2f}pct"


def make_idx(cy=0.67, kc=0.65, hs=0.37):
    """构造 mock indices：创业板 + 科创50 + 沪深300 + 上证 + 深证 均带 change_percent。"""
    return {
        "sh000001": {"name": "上证指数", "price": 3726.11, "change_percent": 0.5,
                     "amount": 1.2e11, "volume_ratio": 3.58, "chg_20d": -5.29},
        "sz399001": {"name": "深证成指", "change_percent": 0.74},
        "sz399006": {"name": "创业板指", "change_percent": cy},
        "sh000688": {"name": "科创50", "change_percent": kc},
        "sh000300": {"name": "沪深300", "change_percent": hs,
                     "pe_ratio": 13.02, "chg_60d": -11.01},
    }


def make_market_data(cy=0.67, kc=0.65, hs=0.37):
    return {
        "date": "2026-10-16",
        "total_amount_yi": 4145.0,
        "indices": make_idx(cy, kc, hs),
        "market_breadth": {"up": 4648, "down": 545, "limit_up": 42, "limit_down": 2},
        "sector_flows": {"top_inflow": 17.1, "top_outflow": 4.22,
                         "inflow_name": "电子", "outflow_name": "有色金属"},
    }


def run_cli(md: dict, extra_args=()):
    """在临时目录跑一次 CLI，返回 (returncode, stdout, 合入后的 market_data)。"""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "market_data.json"
        p.write_text(json.dumps(md, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([PY, str(SCRIPT), str(p), *extra_args],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr, json.loads(p.read_text(encoding="utf-8"))


def redact_paths(stdout: str) -> str:
    """抹掉临时目录绝对路径，使同一输入的两次运行输出可比。"""
    return re.sub(r"\S*/market_data\.json", "<MARKET_DATA>", stdout)


def s4_line(stdout: str) -> str:
    """抽取 stdout 中的 S4 行（形如 `  S4 [0.15] +0.143  ...`）。"""
    for line in stdout.splitlines():
        if line.strip().startswith("S4 "):
            return line.strip()
    raise AssertionError(f"未找到 S4 行:\n{stdout}")


def s4_score_from_stdout(stdout: str) -> float | None:
    line = s4_line(stdout)
    m = re.match(r"S4 \[0\.15\]\s+(\S+)", line)
    val = m.group(1)
    return None if val == "缺失" else float(val)


class TestModuleWiring(unittest.TestCase):
    """A-04 路径推导：compute_signals 必须能从 _git_engine/scripts 定位到 framework 指标库。"""

    def test_momentum_module_loaded(self):
        self.assertIsNotNone(cs._momentum, "signal_momentum 模块未载入")

    def test_technical_library_importable(self):
        self.assertIsNone(cs.momentum_unavailable_reason(),
                          "technical 指标库不可用，检查 framework/engine/signals 路径推导")


class TestS4BackwardCompat(unittest.TestCase):
    """不传技术面入参时，S4 必须与 v1.2 逐字节一致。"""

    def test_value_and_note_match_legacy(self):
        for cy, kc, hs in [(0.67, 0.65, 0.37), (1.8, 2.2, -0.4), (-2.5, -3.0, 0.8),
                           (0.0, 0.0, 0.0), (5.0, 5.0, -5.0)]:
            idx = make_idx(cy, kc, hs)
            with self.subTest(cy=cy, kc=kc, hs=hs):
                self.assertEqual(cs.s4_divergence(idx), legacy_s4(idx))

    def test_legacy_note_text_unchanged(self):
        idx = make_idx()
        _, note = cs.s4_divergence(idx)
        self.assertEqual(note, "成长均值 +0.66% vs 沪深300 +0.37%，价差 +0.29pct")
        self.assertNotIn("动量", note)

    def test_explicit_none_args_equal_legacy(self):
        idx = make_idx(1.2, 0.8, -0.5)
        self.assertEqual(cs.s4_divergence(idx, rsi=None, bias=None, strong_trend=False),
                         legacy_s4(idx))

    def test_strong_trend_alone_keeps_pure_divergence(self):
        """--strong-trend 单独提供时不启用动量（无 BIAS 无法判定 status）。"""
        idx = make_idx()
        self.assertEqual(cs.s4_divergence(idx, strong_trend=True), legacy_s4(idx))

    def test_cli_without_momentum_matches_legacy(self):
        md = make_market_data()
        rc, out, merged = run_cli(md)
        self.assertEqual(rc, 0, out)
        self.assertAlmostEqual(s4_score_from_stdout(out), legacy_s4(md["indices"])[0], places=3)
        self.assertNotIn("动量", out)
        self.assertEqual(merged["verdict"]["signals"]["S4"], legacy_s4(md["indices"])[0])
        self.assertNotIn("s4_technical", merged["verdict"])

    def test_cli_default_output_is_deterministic(self):
        md = make_market_data()
        _, out1, d1 = run_cli(md)
        _, out2, d2 = run_cli(md)
        self.assertEqual(redact_paths(out1), redact_paths(out2))
        self.assertEqual(d1["verdict"], d2["verdict"])


class TestS4MomentumMapping(unittest.TestCase):
    """动量分项映射：BIAS status 与 RSI 超买超卖。"""

    def test_bias_status_mapping(self):
        cases = [
            (-0.02, False, "pullback", 0.3),      # 回踩支撑 → +0.3
            (0.03, False, "normal", 0.0),        # 正常区间 → 0.0
            (0.06, False, "chase_risk", -0.5),   # 乖离 +6% 超 5% 阈值 → 追高 -0.5
            (0.06, True, "strong_tracking", 0.5)  # 强势趋势放宽至 7.5% → 强势追踪 +0.5
        ]
        for bias, strong, status, score in cases:
            with self.subTest(bias=bias, strong=strong):
                mr = cs._momentum.evaluate(bias=bias, strong_trend=strong)
                self.assertEqual(mr.bias_status, status)
                self.assertAlmostEqual(mr.score, score, places=4)

    def test_rsi_term_mapping(self):
        self.assertAlmostEqual(cs._momentum.rsi_score_of(75.0), -0.3)
        self.assertAlmostEqual(cs._momentum.rsi_score_of(25.0), 0.3)
        self.assertAlmostEqual(cs._momentum.rsi_score_of(50.0), 0.0)
        self.assertAlmostEqual(cs._momentum.rsi_score_of(70.0), 0.0)   # 边界：>70 才记超买
        self.assertAlmostEqual(cs._momentum.rsi_score_of(30.0), 0.0)   # 边界：<30 才记超卖

    def test_no_input_returns_none(self):
        self.assertIsNone(cs._momentum.evaluate())
        self.assertIsNone(cs._momentum.evaluate(rsi=None, bias=None, strong_trend=True))

    def test_momentum_is_mean_of_terms(self):
        mr = cs._momentum.evaluate(rsi=75.0, bias=0.06, strong_trend=True)
        self.assertAlmostEqual(mr.score, (0.5 + -0.3) / 2, places=4)

    def test_bias_alone_not_diluted(self):
        """只给 BIAS 时不与 RSI 取均值（分项未提供的不参与平均）。"""
        mr = cs._momentum.evaluate(bias=0.06, strong_trend=True)
        self.assertAlmostEqual(mr.score, 0.5, places=4)


class TestS4Composite(unittest.TestCase):
    """复合公式与 clamp 边界。"""

    def test_composite_formula(self):
        idx = make_idx(1.8, 2.2, -0.4)
        div = legacy_s4(idx)[0]
        for rsi, bias, strong in [(None, 0.03, False), (75.0, None, False),
                                  (25.0, 0.06, True), (75.0, 0.06, True),
                                  (None, -0.02, False), (50.0, 0.0, False)]:
            with self.subTest(rsi=rsi, bias=bias, strong=strong):
                mr = cs._momentum.evaluate(rsi=rsi, bias=bias, strong_trend=strong)
                got, note = cs.s4_divergence(idx, rsi=rsi, bias=bias, strong_trend=strong)
                self.assertAlmostEqual(got, round(0.6 * div + 0.4 * mr.score, 3), places=3)
                self.assertIn("动量确认", note)

    def test_result_within_clamp(self):
        for cy, kc, hs in [(5.0, 5.0, -5.0), (-5.0, -5.0, 5.0), (0.0, 0.0, 0.0), (3.0, 1.0, -1.0)]:
            for rsi in (None, 0.0, 15.0, 50.0, 90.0, 100.0):
                for bias in (None, -0.9, -0.02, 0.0, 0.05, 0.5, 3.0):
                    for strong in (False, True):
                        s, _ = cs.s4_divergence(make_idx(cy, kc, hs), rsi=rsi, bias=bias,
                                                strong_trend=strong)
                        self.assertGreaterEqual(s, -1.0)
                        self.assertLessEqual(s, 1.0)

    def test_rounded_to_three_decimals(self):
        s, _ = cs.s4_divergence(make_idx(1.11, 0.93, -0.17), rsi=68.0, bias=0.041)
        self.assertEqual(s, round(s, 3))

    def test_momentum_moves_score_vs_pure_divergence(self):
        idx = make_idx()
        pure = legacy_s4(idx)[0]
        up, _ = cs.s4_divergence(idx, bias=0.06, strong_trend=True)     # 强势追踪 +0.5
        down, _ = cs.s4_divergence(idx, bias=0.06, strong_trend=False)  # 追高风险 -0.5
        self.assertGreater(up, pure)
        self.assertLess(down, pure)

    def test_cli_momentum_active(self):
        md = make_market_data()
        rc, out, merged = run_cli(md, ["--rsi", "75", "--bias", "0.06", "--strong-trend"])
        self.assertEqual(rc, 0, out)
        self.assertIn("动量确认", out)
        pure = legacy_s4(md["indices"])[0]
        self.assertNotAlmostEqual(s4_score_from_stdout(out), pure, places=3)
        tech = merged["verdict"]["s4_technical"]
        self.assertEqual(tech["bias_status"], "strong_tracking")
        self.assertAlmostEqual(tech["momentum"], 0.1, places=4)
        self.assertAlmostEqual(merged["verdict"]["signals"]["S4"],
                               round(0.6 * pure + 0.4 * 0.1, 3), places=3)

    def test_cli_invalid_rsi_rejected(self):
        rc, out, _ = run_cli(make_market_data(), ["--rsi", "150"])
        self.assertEqual(rc, 2)
        self.assertIn("--rsi 非法", out)

    def test_cli_invalid_bias_rejected(self):
        rc, out, _ = run_cli(make_market_data(), ["--bias", "-1.5"])
        self.assertEqual(rc, 2)
        self.assertIn("--bias 非法", out)

    def test_cli_strong_trend_without_bias_warns(self):
        rc, out, merged = run_cli(make_market_data(), ["--strong-trend"])
        self.assertEqual(rc, 0, out)
        self.assertIn("需配合 --bias 生效", out)
        self.assertEqual(merged["verdict"]["signals"]["S4"], legacy_s4(make_market_data()["indices"])[0])


class TestS4DataGap(unittest.TestCase):
    """数据缺口：降级行为不因动量增强而改变。"""

    def test_missing_indices_return_none(self):
        for broken in [{}, {"sz399006": {"change_percent": 1.0}},
                       {"sz399006": {"change_percent": 1.0}, "sh000688": {"change_percent": 1.0}},
                       make_idx(hs=None)]:
            with self.subTest(broken=str(broken)[:40]):
                self.assertEqual(cs.s4_divergence(broken), (None, "数据缺口：成长/蓝筹指数缺失"))

    def test_momentum_does_not_resurrect_missing_data(self):
        """提供技术面入参也不能把缺口补成分数 —— 缺口优先于动量。"""
        for broken in [{}, make_idx(cy=None), make_idx(kc=None), make_idx(hs=None)]:
            with self.subTest(broken=str(broken)[:40]):
                s, note = cs.s4_divergence(broken, rsi=25.0, bias=0.06, strong_trend=True)
                self.assertIsNone(s)
                self.assertEqual(note, "数据缺口：成长/蓝筹指数缺失")

    def test_cli_gap_marks_degraded(self):
        rc, out, merged = run_cli(make_market_data(hs=None), ["--rsi", "25"])
        self.assertEqual(rc, 0, out)
        self.assertIn("缺失", s4_line(out))
        self.assertIn("S4", merged["verdict"]["degraded"])
        self.assertIsNone(merged["verdict"]["signals"]["S4"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
