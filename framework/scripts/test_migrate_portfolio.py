#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_migrate_portfolio.py — 迁移脚本自测（纯标准库，零依赖）

迁移脚本是一次性工具，但**必须可复跑且幂等**（ADR-007 §4：MEMORY.md → yaml
一次性迁移，此后 yaml 为准）。一份悄悄迁错的数据 yaml 比没有迁移更危险——它看起来
是对的。与 test_validate_config.py 分文件且同用表格驱动，两者合计守住 300 行上限；
该文件会加载本模块，故 CI 只需登记一个入口。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from memory_plan_amounts import parse_plan_amounts  # noqa: E402
from migrate_memory_to_portfolio import build_portfolio, main, parse_tables  # noqa: E402
from validate_config import Report, validate  # noqa: E402
from yaml_emit import dump_yaml  # noqa: E402
from yaml_min import parse_yaml_subset  # noqa: E402

# 散文段：每期定投额只存在于这里（基金表只有「在途」列），迁移必须能解析它。
PROSE = ("- 基金风格：定投：标普500/纳指100 各100元/天、汇添富全球移动互联 70元/天；"
         "智慧定投：景顺沪港深 60-210 元/天；合计约 518 元/天\n")
# 夹具保留 MEMORY.md 的全部行形态（场内个股 / 场内 ETF / 场外基金 / 黄金 /
# 网格启用行 / 网格占位行）：每种形态对应迁移脚本里的一条分支。
MEM = (Path(__file__).resolve().parent / "fixtures" / "memory_sample.md").read_text(
    encoding="utf-8")

class TestTableParsing(unittest.TestCase):
    def test_row_counts_and_title_lookup(self):
        t = parse_tables(MEM)
        self.assertEqual([len(t["stocks"]), len(t["grid"]), len(t["funds"])],
                         [3, 3, 4])
        self.assertEqual(len(parse_tables("# 段\n\n" + MEM)["stocks"]), 3)

    def test_plan_amounts_parsed_from_prose(self):
        """定投额必须来自 MEMORY.md 原文，不得硬编码在代码里。
        「A/B 各N元」要拆成两条，否则只有一只拿得到金额。"""
        got = {n: (lo, hi) for n, lo, hi in parse_plan_amounts(PROSE)}
        want = {"标普500": (100, 100), "纳指100": (100, 100),
                "汇添富全球移动互联": (70, 70), "景顺沪港深": (60, 210)}
        self.assertEqual({k: got.get(k) for k in want}, want)
        self.assertNotIn("合计约", got)   # 合计不是标的

class TestDualTrackMigration(unittest.TestCase):
    """迁移的核心断言：双轨归属由数据决定，黄金不进基金段。"""
    def setUp(self):
        self.h = build_portfolio(MEM)["holdings"]
        self.pos = {p["code"]: p for p in self.h["stock"]["positions"]}
        self.grid = {g["code"]: g for g in self.h["stock"]["grid"]}
        self.fund = {p["code"]: p for p in self.h["fund"]["positions"]}

    def test_counts_split_by_track(self):
        """三轨各自计数，黄金单列不计入基金轨。"""
        h = self.h
        n = [len(h[s]["positions"]) for s in ("stock", "fund")] + [len(h["gold"])]
        self.assertEqual(n, [3, 3, 1])
        self.assertEqual(h["gold"][0]["amount"], 3907.41)

    def test_listing_assigned_by_segment(self):
        """归属由数据字段决定，不由代码硬编码（ADR-007 §2.2）。
        场内 ETF 归股票轨——它可挂单，不是场外基金，故不能出现在基金段。"""
        for seg, want in (("stock", "exchange"), ("fund", "otc")):
            got = {p["listing"] for p in self.h[seg]["positions"]}
            self.assertEqual(got, {want}, seg)
        self.assertEqual({g["listing"] for g in self.h["stock"]["grid"]},
                         {"exchange"})
        self.assertIn("563230", self.pos)       # 场内 ETF 有挂单，归股票轨
        self.assertNotIn("563230", self.fund)

    def test_dash_row_becomes_disabled_grid(self):
        """区间/步长均为 '-' 的行 → enabled:false，但底仓上下限仍留档。"""
        g = self.grid
        self.assertTrue(g["600312"]["enabled"])
        self.assertFalse(g["600919"]["enabled"])
        self.assertEqual(g["600919"]["min_position"], 100)
        self.assertNotIn("range_low", g["600919"])   # 不给无效区间

    def test_split_columns_and_prefix_stripped(self):
        """「500 / 400」拆两列；网格表前缀剥离只存 6 位，避免两处不一致。"""
        p = self.pos["600312"]
        self.assertEqual((p["shares"], p["available"], p["note"]),
                         (500, 400, "加仓至500股"))
        self.assertEqual(self.pos["600919"]["cost"], 1.696)
        self.assertEqual(list(self.grid), ["600312", "563230", "600919"])

    def test_daily_columns_dropped_and_plans_covered(self):
        """现价/市值/盈亏等每日变量不进配置（必然过期）；plans 要含普通定投
        ——标普500 每日 100 元是定投日历里频率最高的一笔。"""
        drop = ("price", "market_value", "profit", "profit_pct")
        fund_drop = ("holding_profit", "yesterday_profit", "weight_pct")
        self.assertFalse([k for k in drop if k in self.pos["600312"]])
        self.assertFalse([k for k in fund_drop if k in self.fund["000979"]])
        plans = {p["code"]: p["type"] for p in self.h["fund"]["plans"]}
        self.assertEqual([plans["017641"], plans["000979"]], ["regular", "smart"])

class TestOutputIntegrity(unittest.TestCase):
    def test_output_valid_idempotent_and_reparsable(self):
        """生成物必须能通过自家校验器（否则迁移等于产出坏数据），且同一输入
        两次生成必得同一字节——幂等是可复跑迁移的前提。"""
        cfg = build_portfolio(MEM)
        rep = Report()
        validate(parse_yaml_subset(dump_yaml(cfg)), rep)
        self.assertTrue(rep.ok, [e["message"] for e in rep.errors])
        self.assertEqual(dump_yaml(cfg), dump_yaml(cfg))
        self.assertEqual(parse_yaml_subset(dump_yaml(cfg)), cfg)

    def test_missing_memory_is_error_not_silent_default(self):
        """无隐式默认路径：文件不存在必须报错退出 2。"""
        self.assertEqual(main(["--memory", "/nonexistent/MEMORY.md"]), 2)

    def test_cli_writes_valid_file_and_refuses_overwrite(self):
        """默认不覆盖：迁移单向，误覆盖会毁掉已手工校准的数据。"""
        with tempfile.TemporaryDirectory() as td:
            mem, out = Path(td) / "MEMORY.md", Path(td) / "p.yaml"
            mem.write_text(MEM, encoding="utf-8")
            args = ["--memory", str(mem), "--out", str(out)]
            self.assertEqual(main(args), 0)
            self.assertEqual(main(args), 1)
            self.assertEqual(main([*args, "--force"]), 0)
            self.assertEqual(parse_yaml_subset(out.read_text(encoding="utf-8")),
                             build_portfolio(MEM))

if __name__ == "__main__":
    unittest.main(verbosity=2)
