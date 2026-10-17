#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_validate_config.py — 校验器自测（纯标准库，零依赖）

一个从不拒绝任何配置的校验器等于没有校验器。本文件用真实 MEMORY.md 的
历史踩坑构造反例，确保每条规则真的会炸。v2 重点（ADR-007 §2.2 双轨隔离）：
三条负例对应「otc 出现在 grid 段」「基金段出现网格键」「前缀与代码段冲突」。
纪律：规则用例直接构造 dict 喂 validate()，不走 YAML——YAML 往返由
TestYamlParser 与 test_migrate_portfolio.py 覆盖；断言一律表格 + subTest。
两套件合计守住 300 行上限，基座见 fixtures_support.py。运行：python3 test_validate_config.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures_support import (  # noqa: E402
    BAD_YAML, FUND, GRID, MINIMAL, assert_rejected, cfg, codes_of, fund_cfg,
    run,
)
from test_migrate_portfolio import *  # noqa: E402,F401,F403  CI 单入口加载迁移套件
from validate_config import (  # noqa: E402
    ConfigError, Report, build_export, code_mismatch, market_of,
    normalize_code, parse_yaml_subset, parse_yaml_subset_indexed,
)

class TestYamlParser(unittest.TestCase):
    def test_block_map_seq_and_scalars(self):
        got = parse_yaml_subset("a:\n  b: 1\n  c:\n    - d: 2\n      e: 3\n")
        self.assertEqual(got["a"], {"b": 1, "c": [{"d": 2, "e": 3}]})
        sc = parse_yaml_subset("a: null\nb: ~\nc: true\nd: 1.5\ne: -3\nf: []\n")
        self.assertEqual([sc[k] for k in "abcdef"], [None, None, True, 1.5, -3, []])
        q = parse_yaml_subset('# 头\nversion: 2  # 尾\nprofile:\n  owner: "a#b"\n')
        self.assertEqual((q["version"], q["profile"]["owner"]), (2, "a#b"))

    def test_line_index_points_at_key(self):
        """行号索引：报错必须能定位到文件具体行。"""
        text = "holdings:\n  stock:\n    positions:\n      - code: \"600919\"\n"
        _, idx = parse_yaml_subset_indexed(text)
        self.assertEqual(idx["holdings.stock.positions[0].code"], 4)
        rep = Report({"holdings.stock.positions[0].shares": 42})
        rep.err("holdings.stock.positions[0].shares", "x")
        self.assertEqual(rep.errors[0]["line"], 42)

    def test_bad_syntax_rejected(self):
        """重复键 / Tab / 动态语法 / 块标量 / 流式集合——一律显式报错带行号。"""
        for label, bad in BAD_YAML.items():
            with self.subTest(case=label):
                with self.assertRaises(ConfigError) as cm:
                    parse_yaml_subset(bad)
            self.assertIn("行", str(cm.exception))

class TestCodeNormalization(unittest.TestCase):
    def test_market_rules_match_parser(self):
        """与 parse_holdings.py full_code() 逐条对齐（含 ETF 与北交所）。"""
        for digits, want in (("600919", "sh"), ("688111", "sh"), ("003816", "sz"),
                             ("300750", "sz"), ("563230", "sz"), ("159611", "sz"),
                             ("899050", "bj")):
            self.assertEqual(market_of(digits), want, digits)
        for raw, want in (("600919", "sh600919"), ("003816", "sz003816")):
            self.assertEqual(normalize_code(raw), want)

    def test_mismatch_detection(self):
        self.assertEqual(code_mismatch("sz600919"),
                         "代码 600919 按段应属 sh，却写成 sz")
        for ok in ("sh600919", "600919"):
            self.assertFalse(code_mismatch(ok), ok)

class TestDualTrackBoundary(unittest.TestCase):
    """v2 核心：双轨隔离。三条负例 + 正例 + 反向边界。"""

    def test_otc_in_grid_segment_rejected(self):
        """负例 1：场外标的不得进股票轨 grid 段（场外基金没有挂单）。"""
        otc = {"code": "000979", "name": "场外基金", "listing": "otc",
               "enabled": False}
        assert_rejected(self, {"otc进grid": (
            cfg(**{"holdings.stock.grid": [otc]}), "E_TRACK_OTC_IN_GRID")})

    def test_grid_key_in_fund_position_rejected(self):
        """负例 2：基金段出现网格键即违规（遍历网格键全集，不靠键名猜测）。"""
        keys = (("base_price", 1.0), ("range_low", 1.0), ("range_high", 2.0),
                ("step_pct", 2.5), ("per_trade", 100), ("min_position", 0),
                ("max_position", 100))
        assert_rejected(self, {f"基金含{k}": (fund_cfg({**FUND, k: v}),
                              "E_TRACK_GRID_KEY_IN_FUND") for k, v in keys})

    def test_market_prefix_conflict_rejected(self):
        """负例 3：市场前缀与代码段冲突（sz600919 按段应属 sh）。"""
        bad = cfg(**{"holdings.stock.positions.0.code": "sz600919"})
        assert_rejected(self, {"前缀冲突": (bad, "E_CODE_PREFIX")})

    def test_reverse_boundary_and_order_concept(self):
        """反向边界：场内 ETF 进基金轨、基金带 available（挂单概念）同样违规。
        同时守住正例——场内 ETF 留在股票轨必须放行，边界规则不能只拒不认。"""
        assert_rejected(self, {
            "场内ETF进基金轨": (fund_cfg({**FUND, "code": "563230",
                                         "listing": "exchange"}), "E_TRACK_OTC_IN_GRID"),
            "基金带available": (fund_cfg({**FUND, "available": 50}),
                                "E_TRACK_GRID_KEY_IN_FUND")})
        ok = run(cfg(**{"holdings.stock.positions.0.code": "563230"}))
        self.assertTrue(ok.ok, [e["message"] for e in ok.errors])

class TestValidationRules(unittest.TestCase):
    def test_minimal_config_passes(self):
        """最小配置零错误零警告；清仓类问题只警告不阻断（--strict 下才失败）。"""
        rep = run(MINIMAL)
        self.assertTrue(rep.ok, [e["message"] for e in rep.errors])
        self.assertEqual(rep.warnings, [])
        zero = run(cfg(**{"holdings.stock.positions.0.shares": 0}))
        self.assertTrue(zero.ok)
        self.assertTrue(any("持仓为 0" in w["message"] for w in zero.warnings))

    def test_v1_rejected_with_migration_hint(self):
        """v1 不保留读取能力，但必须给出可执行的迁移提示。"""
        rep = run(cfg(version=1))
        self.assertFalse(rep.ok)
        self.assertIn("E_VERSION", codes_of(rep))
        self.assertIn("双轨", " ".join(e["message"] + e["hint"] for e in rep.errors))

    def test_missing_and_unknown_segments(self):
        """缺段（cash 改名 / gold 空值）、未知键、缺必填字段都必须报错。"""
        p = "holdings.stock.positions.0."
        assert_rejected(self, {
            "cash改名": (cfg(**{"cash": None}), "E_CASH"),
            "gold空值": (cfg(**{"holdings.gold": None}), "E_STRUCTURE"),
            "未知顶层键": ({**MINIMAL, "holdings_extra": 1}, "E_UNKNOWN_KEY"),
            "缺version": (cfg(version=None), "E_VERSION"),
            "缺listing": (cfg(**{p + "listing": None}), "E_LISTING"),
            "缺code": (cfg(**{p + "code": None}), "E_REQUIRED")})

    def test_track_field_rules(self):
        """两轨字段级规则：重复、可用量越界、缺区间、区间反、底仓>顶仓、
        必填 code、plan 枚举、扣款日上界、定投标的必须持有。"""
        base = MINIMAL["holdings"]["stock"]["positions"][0]
        no_range = [{"code": "600312", "name": "G", "listing": "exchange",
                     "enabled": True, "step_pct": 2.5}]
        plan = {"code": "000979", "type": "regular"}
        assert_rejected(self, {
            "重复持仓": (cfg(**{"holdings.stock.positions":
                                [base, {**base, "shares": 10}]}), "E_DUPLICATE"),
            "available超shares": (
                cfg(**{"holdings.stock.positions.0.available": 200}), None),
            "负数持仓": (cfg(**{"holdings.stock.positions.0.shares": -1}), "E_RANGE"),
            "缺区间": (cfg(**{"holdings.stock.grid": no_range}), None),
            "区间反了": (cfg(**{"holdings.stock.grid": [
                {**GRID, "range_low": 20}]}), None),
            "底仓大于顶仓": (cfg(**{"holdings.stock.grid": [
                {**GRID, "min_position": 900}]}), None),
            "基金缺code": (fund_cfg({"name": "X", "listing": "otc"}), None),
            "plan非法": (fund_cfg({**FUND, "plan": "bogus"}), None),
            "扣款日31": (fund_cfg(FUND, {**plan, "day_of_month": 31}), None),
            "定投标的未持有": (cfg(**{"holdings.fund.plans": [plan]}), None),
            "浮动区间倒挂": (fund_cfg(FUND, {"code": "000979", "type": "smart",
                                            "amount_per_period": 210,
                                            "amount_per_period_max": 60}), None)})

    def test_export_marks_track(self):
        gold = [{"name": "积存金", "amount": 3.0}]
        out = build_export(cfg(**{"holdings.fund.positions": [FUND],
                                  "holdings.gold": gold}))
        self.assertEqual({i["track"] for i in out["positions"]},
                         {"stock", "fund", "gold"})
        self.assertIs([i for i in out["positions"]
                       if i["track"] == "fund"][0]["grid_enabled"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)