#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_validate_config.py — 校验器自测（纯标准库，零依赖）

一个从不拒绝任何配置的校验器等于没有校验器。本文件用真实 MEMORY.md 的
历史踩坑构造反例，确保每条规则真的会炸。

运行：python3 test_validate_config.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_config import (  # noqa: E402
    ConfigError, Report, code_mismatch, market_of, normalize_code,
    parse_yaml_subset, validate,
)

MINIMAL = """
version: 1
profile:
  owner: "t"
  base_currency: CNY
holdings:
  stocks:
    - code: "600919"
      name: "示例"
      shares: 100
      cost: 1.696
  grid: []
  funds: []
"""


def run(cfg_text: str) -> Report:
    rep = Report()
    validate(parse_yaml_subset(cfg_text), rep)
    return rep


class TestYamlParser(unittest.TestCase):
    def test_block_map_and_seq(self):
        got = parse_yaml_subset(MINIMAL)
        self.assertEqual(got["version"], 1)
        self.assertEqual(got["holdings"]["stocks"][0]["code"], "600919")
        self.assertEqual(got["holdings"]["stocks"][0]["shares"], 100)

    def test_comments_and_blank_lines(self):
        got = parse_yaml_subset("# 头部注释\n\nversion: 1  # 行尾\nprofile:\n  owner: a\n")
        self.assertEqual(got["version"], 1)
        self.assertEqual(got["profile"]["owner"], "a")

    def test_hash_inside_quotes_is_kept(self):
        got = parse_yaml_subset('profile:\n  owner: "a#b"\n')
        self.assertEqual(got["profile"]["owner"], "a#b")

    def test_scalar_types(self):
        got = parse_yaml_subset("a: null\nb: ~\nc: true\nd: false\ne: 1.5\nf: -3\n")
        self.assertIsNone(got["a"])
        self.assertIsNone(got["b"])
        self.assertIs(got["c"], True)
        self.assertIs(got["d"], False)
        self.assertEqual(got["e"], 1.5)
        self.assertEqual(got["f"], -3)

    def test_nested_seq_of_maps(self):
        got = parse_yaml_subset(
            "holdings:\n  funds:\n"
            "    - code: \"000979\"\n      name: A\n      amount: 1.5\n"
            "    - code: \"017641\"\n      name: B\n      amount: 2\n"
        )
        self.assertEqual(len(got["holdings"]["funds"]), 2)
        self.assertEqual(got["holdings"]["funds"][1]["code"], "017641")
        self.assertEqual(got["holdings"]["funds"][1]["amount"], 2)

    def test_empty_list_inline(self):
        got = parse_yaml_subset("holdings:\n  stocks: []\n  grid: []\n  funds: []\n")
        self.assertEqual(got["holdings"]["stocks"], [])

    def test_duplicate_key_rejected(self):
        with self.assertRaises(ConfigError):
            parse_yaml_subset("a: 1\na: 2\n")

    def test_tab_indent_rejected(self):
        with self.assertRaises(ConfigError):
            parse_yaml_subset("a:\n\tb: 1\n")

    def test_unsupported_syntax_reports_location(self):
        cases = [
            "a: 1\nb: &anc 2\n",          # 锚点
            "a: 1\nb: *anc\n",            # 别名
            "a: !!str 1\n",                # 标签
            "a: 1\n---\nb: 2\n",          # 多文档
        ]
        for bad in cases:
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigError) as cm:
                    parse_yaml_subset(bad)
                self.assertIn("行", str(cm.exception))

    def test_block_scalar_rejected(self):
        with self.assertRaises(ConfigError):
            parse_yaml_subset("a: |\n  text\n")

    def test_nonempty_flow_seq_rejected(self):
        with self.assertRaises(ConfigError):
            parse_yaml_subset("a: [1, 2]\n")


class TestCodeNormalization(unittest.TestCase):
    def test_market_rules_match_parser(self):
        # 规则与 parse_holdings.py full_code() 逐条对齐（含 ETF/北交所），
        # 56 开头（563230）在 MEMORY.md 中即记为 sz563230，故期望 sz。
        self.assertEqual(market_of("600919"), "sh")
        self.assertEqual(market_of("688111"), "sh")
        self.assertEqual(market_of("003816"), "sz")
        self.assertEqual(market_of("300750"), "sz")
        self.assertEqual(market_of("563230"), "sz")
        self.assertEqual(market_of("159611"), "sz")
        self.assertEqual(market_of("899050"), "bj")

    def test_normalize_adds_prefix(self):
        self.assertEqual(normalize_code("600919"), "sh600919")
        self.assertEqual(normalize_code("003816"), "sz003816")
        self.assertEqual(normalize_code("sh600312"), "sh600312")

    def test_mismatch_detection(self):
        self.assertTrue(code_mismatch("sz600919"))
        self.assertFalse(code_mismatch("sh600919"))
        self.assertFalse(code_mismatch("600919"))


class TestValidationRules(unittest.TestCase):
    def test_minimal_config_passes(self):
        self.assertTrue(run(MINIMAL).ok)

    def test_missing_version_rejected(self):
        rep = run(MINIMAL.replace("version: 1\n", ""))
        self.assertFalse(rep.ok)
        self.assertTrue(any("version" in e["location"] for e in rep.errors))

    def test_unknown_top_level_key_rejected(self):
        rep = run(MINIMAL + "\nholdings_extra: 1\n")
        self.assertFalse(rep.ok)
        self.assertTrue(any("未知顶层键" in e["message"] for e in rep.errors))

    def test_wrong_version_rejected(self):
        rep = run(MINIMAL.replace("version: 1", "version: 99"))
        self.assertFalse(rep.ok)

    def test_market_prefix_conflict_is_error(self):
        rep = run(MINIMAL.replace('"600919"', '"sz600919"'))
        self.assertFalse(rep.ok)

    def test_duplicate_stock_rejected(self):
        cfg = MINIMAL.replace("  grid: []", """    - code: "600919"
      name: "重复"
      shares: 10
      cost: 1.0
  grid: []""")
        rep = run(cfg)
        self.assertFalse(rep.ok)
        self.assertTrue(any("重复持仓" in e["message"] for e in rep.errors))

    def test_available_exceeds_shares_rejected(self):
        rep = run(MINIMAL.replace("shares: 100", "shares: 100\n      available: 200"))
        self.assertFalse(rep.ok)

    def test_grid_enabled_requires_range(self):
        cfg = MINIMAL.replace("  grid: []", """  grid:
    - code: "600312"
      name: G
      enabled: true
      step_pct: 2.5""")
        rep = run(cfg)
        self.assertFalse(rep.ok)
        self.assertTrue(any("range_low" in e["location"] for e in rep.errors))

    def test_grid_inverted_range_rejected(self):
        cfg = MINIMAL.replace("  grid: []", """  grid:
    - code: "600312"
      name: G
      enabled: true
      base_price: 10
      range_low: 20
      range_high: 10
      step_pct: 2.5""")
        rep = run(cfg)
        self.assertFalse(rep.ok)

    def test_min_position_above_max_rejected(self):
        cfg = MINIMAL.replace("  grid: []", """  grid:
    - code: "600312"
      name: G
      enabled: false
      min_position: 900
      max_position: 100""")
        rep = run(cfg)
        self.assertFalse(rep.ok)

    def test_gold_does_not_require_code(self):
        cfg = MINIMAL.replace("  funds: []", """  funds:
    - name: "黄金（实物/积存金）"
      asset_class: gold
      amount: 3907.41""")
        rep = run(cfg)
        self.assertTrue(rep.ok, [e["message"] for e in rep.errors])

    def test_fund_requires_code(self):
        cfg = MINIMAL.replace("  funds: []", """  funds:
    - name: 某基金
      asset_class: fund
      amount: 100""")
        rep = run(cfg)
        self.assertFalse(rep.ok)

    def test_bad_asset_class_rejected(self):
        cfg = MINIMAL.replace("  funds: []", """  funds:
    - code: "000979"
      name: X
      asset_class: crypto""")
        rep = run(cfg)
        self.assertFalse(rep.ok)

    def test_non_westock_source_rejected(self):
        cfg = MINIMAL.replace("profile:", "market_data:\n  source: sina\nprofile:")
        rep = run(cfg)
        self.assertFalse(rep.ok)

    def test_zero_shares_is_warning_not_error(self):
        rep = run(MINIMAL.replace("shares: 100", "shares: 0"))
        self.assertTrue(rep.ok)
        self.assertTrue(any("持仓为 0" in w["message"] for w in rep.warnings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
