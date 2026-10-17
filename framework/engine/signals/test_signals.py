#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_signals.py — 引擎四脚本迁入 framework/engine/signals/ 后的回归套件（A-09）

覆盖四份框架侧 canonical 脚本（A-09 自 _engine_stage/scripts/ 迁入，关系声明见同目录 README.md）：
  compute_signals  评级四档/权重封顶/信号降级/CLI 两次运行逐字节一致（路径脱敏）
  validate_market_data  全过/缺 verdict/日期不符/占位符/退出码 0·1·2 契约
  settle_viewpoints  指标前缀提取/四态结算/eval_at 防误触发/MISSED_NEUTRAL/CLI 落盘
  parse_holdings  A-05 来源纪律/三表解析/full_code 与 codes.normalize_code 前缀一致性（A-10）
全离线：外部输入一律 tempfile + HERE 相对推导，无硬编码路径、无网络、无真实产物依赖。
运行：python3 framework/engine/signals/test_signals.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(_HERE), str(_HERE.parent.parent / "scripts")]
HERE = _HERE

import codes  # noqa: E402
import compute_signals as cs  # noqa: E402
import parse_holdings as ph  # noqa: E402
import settle_viewpoints as sv  # noqa: E402
import validate_market_data as vmd  # noqa: E402

PY = sys.executable

# 合成 MEMORY.md：字段位置与真实三表一致，覆盖 sh/sz/bj/坏代码/黄金三类行
MEMORY_MD = """| 标的 | 证券代码 | 持仓/可用 | 成本 | 现价 | 市值 | 盈亏额 | 盈亏率 | 状态 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| 示例银行 | 600919 | 100/100 | 20.00 | 21.00 | 2100 | 100 | 5% | 底仓 | note-a |
| 深市示例 | sz003816 | 50/50 | 30.00 | 31.00 | 1550 | 50 | 3% | 底仓 | note-b |
| 北交所示例 | 430047 | 10/10 | 10.00 | 11.00 | 110 | 10 | 10% | 底仓 | note-c |
| 坏代码行 | abcde | 1/1 | 1 | 1 | 1 | 0 | 0% | x | y |
# 网格表
| 标的 | 证券代码 | 基准价 | 区间 | 网格步长 | 单笔 | 最小底仓 | 最大顶仓 | 指引 |
|---|---|---|---|---|---|---|---|---|
| 网格A | 600312 | 20.40 | 18.50 - 24.50 | 2.5 | 100 | 300 | 1000 | guide-a |
# 基金表
| 标的 | 证券代码 | 金额 | 持有收益 | 昨日收益 | 占纯基金比 | 定投 | 备注 |
|---|---|---|---|---|---|---|---|
| 基金A | 000979 | 15080 | 100 | 1 | 60% | 是 | note-f |
| 黄金 | - | 3907 | 20 | 0 | - | 否 | note-g |
"""

IDX_CODES = ["sh000001", "sz399001", "sz399006", "sh000300", "sh000688", "bj899050"]


def valid_doc() -> dict:
    """可通过全部硬断言（[1]-[6]）的最小市场数据。"""
    return {
        "date": "2026-10-16", "data_stage": "close", "total_amount_yi": 15692.32,
        "indices": {c: {"time": "2026-10-16", "price": 100.0 + i,
                        "change_percent": 0.5, "amount": 1e10}
                    for i, c in enumerate(IDX_CODES)},
        "market_breadth": {"up": 3111, "down": 2038, "flat": 144, "limit_up": 55,
                           "limit_down": 9, "total_amount": 1569232000000},
        "verdict": {"rating": "均衡", "sigma": 0.18},
    }


def run_cli(script: Path, argv, drop_env=()):
    """跑一次 CLI，返回 (returncode, stdout+stderr)。可剥离指定环境变量。"""
    env = {k: v for k, v in os.environ.items() if k not in drop_env}
    p = subprocess.run([PY, str(script), *argv], capture_output=True,
                       text=True, env=env, timeout=60)
    return p.returncode, p.stdout + p.stderr


def redact_paths(text: str) -> str:
    return re.sub(r"\S*market_data\.json", "<MD>", text)


class TestPrefixConvergence(unittest.TestCase):
    """A-10：full_code 与 codes.normalize_code 共用一张前缀表，禁止再漂移。"""

    VALID = ["600919", "003816", "300750", "688981", "000001", "430047", "830799",
             "920002", "159001", "512480", "588000", "sh600919", "sz003816",
             "bj430047", "bj899050", "900901"]

    def test_valid_codes_agree_with_normalize_code(self):
        for c in self.VALID:
            with self.subTest(code=c):
                self.assertEqual(ph.full_code(c), codes.normalize_code(c))

    def test_prefix_table_lives_only_in_codes(self):
        self.assertTrue(hasattr(codes, "SH_PREFIX"), "codes.py 必须持有规则表")
        self.assertFalse(hasattr(ph, "SH_PREFIX"), "parse_holdings 不得再持有前缀表（A-10 单一事实源）")

    def test_unparseable_returns_none(self):
        for c in ["", "abc", "60091", "6009199", "1234567", None, 600919.0]:
            with self.subTest(code=c):
                self.assertIsNone(ph.full_code(c))

    def test_market_hint_is_inert(self):
        self.assertEqual(ph.full_code("600919", market_hint="sz"), "sh600919")

    def test_uppercase_prefix_keeps_legacy_digit_inference(self):
        # 迁入前 full_code 对大写显式前缀按数字段重推断（SH003816 → sz003816），
        # 适配器必须保持该行为，否则就是静默改逻辑
        self.assertEqual(ph.full_code("SH003816"), "sz003816")


class TestParseHoldings(unittest.TestCase):
    """A-05 来源纪律 + 三表解析 + CLI 契约。"""

    def test_resolve_memory_path_priority(self):
        self.assertEqual(ph._resolve_memory_path("cli.md"), "cli.md")
        os.environ["DECISION_ENGINE_MEMORY"] = "env.md"
        try:
            self.assertEqual(ph._resolve_memory_path(None), "env.md")
            self.assertEqual(ph._resolve_memory_path("cli.md"), "cli.md")
        finally:
            os.environ.pop("DECISION_ENGINE_MEMORY", None)
        self.assertIsNone(ph._resolve_memory_path(None))

    def test_cli_requires_explicit_source(self):
        rc, out = run_cli(HERE / "parse_holdings.py", [], drop_env=("DECISION_ENGINE_MEMORY",))
        self.assertEqual(rc, 2)
        self.assertIn("未指定持仓记忆文件", out)
        self.assertIn("A-05", out)

    def test_parse_tables_and_classify(self):
        by_kind = {}
        for t in ph.parse_tables(MEMORY_MD):
            by_kind.setdefault(ph.classify_table(t[0]), []).append(t)
        self.assertEqual(sorted(by_kind), ["funds", "grid", "stocks"])
        stocks = ph.parse_stocks(by_kind["stocks"][0])
        self.assertEqual([s["code"] for s in stocks], ["sh600919", "sz003816", "bj430047"])
        funds = ph.parse_funds(by_kind["funds"][0])
        self.assertEqual([f["code"] for f in funds], ["000979", "GOLD"])
        grid = ph.parse_grid(by_kind["grid"][0])
        self.assertEqual((grid[0]["code"], grid[0]["range_low"]), ("sh600312", 18.50))

    def test_cli_writes_holdings_json(self):
        with tempfile.TemporaryDirectory() as td:
            mem = Path(td) / "MEMORY.md"
            mem.write_text(MEMORY_MD, encoding="utf-8")
            out_path = Path(td) / "holdings.json"
            rc, out = run_cli(HERE / "parse_holdings.py",
                              ["--memory", str(mem), "-o", str(out_path)])
            self.assertEqual(rc, 0, out)
            data = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(data["summary"], {"stock_count": 3, "stock_market_value": 3760.0,
                                               "fund_count": 1, "fund_amount": 15080.0,
                                               "gold_amount": 3907.0})


class TestComputeSignals(unittest.TestCase):
    """评级口径 / 权重封顶 / 信号降级 / CLI 确定性。"""

    def test_rating_thresholds(self):
        for sigma, expect in [(0.50, "进攻"), (0.15, "均衡"), (0.0, "信号矛盾"),
                              (-0.14, "信号矛盾"), (-0.15, "防守"), (-0.50, "回避")]:
            with self.subTest(sigma=sigma):
                self.assertEqual(cs.rating_of(sigma), expect)

    def test_insufficient_weight_caps_rating(self):
        # 有效权重 < 0.50（过半信号缺失）时禁止方向性评级
        self.assertEqual(cs.rating_of(0.9, 0.45), "信号矛盾")
        self.assertEqual(cs.rating_of(-0.9, 0.45), "信号矛盾")

    def test_signal_gap_degrades(self):
        s, note = cs.s1_volume({"sh000001": {"price": 100.0}}, None)  # 缺 volume_ratio
        self.assertIsNone(s)
        self.assertIn("数据缺口", note)
        self.assertIsNone(cs.s4_divergence({})[0])

    def test_s2_breadth_value(self):
        s, note = cs.s2_breadth({"up": 3111, "down": 2038,
                                 "limit_up": 55, "limit_down": 9})
        self.assertAlmostEqual(s, 0.819, places=3)
        self.assertIn("上涨占比", note)

    def test_cli_deterministic_and_merges_verdict(self):
        with tempfile.TemporaryDirectory() as td:
            md = Path(td) / "market_data.json"
            payload = valid_doc()
            payload.pop("verdict")
            fresh = json.dumps(payload, ensure_ascii=False)
            md.write_text(fresh, encoding="utf-8")
            rc1, out1 = run_cli(HERE / "compute_signals.py", [str(md)])
            self.assertEqual(rc1, 0, out1)
            first = json.loads(md.read_text(encoding="utf-8"))
            self.assertEqual(set(first["verdict"]["signals"]),
                             {"S1", "S2", "S3", "S4", "S5", "S6"})
            md.write_text(fresh, encoding="utf-8")
            rc2, out2 = run_cli(HERE / "compute_signals.py", [str(md)])
            self.assertEqual(rc2, 0, out2)
            self.assertEqual(redact_paths(out1), redact_paths(out2))
            self.assertEqual(first["verdict"], json.loads(md.read_text(encoding="utf-8"))["verdict"])


class TestValidateMarketData(unittest.TestCase):
    """硬断言与退出码契约（先 compute 后 validate 的顺序铁律在此守护）。"""

    def test_full_pass(self):
        self.assertEqual(vmd.validate(valid_doc(), "2026-10-16"), [])

    def test_missing_verdict_fails(self):
        doc = valid_doc()
        doc.pop("verdict")
        self.assertTrue(any("verdict" in e for e in vmd.validate(doc, "2026-10-16")))

    def test_date_mismatch_fails(self):
        self.assertTrue(any("不一致" in e for e in vmd.validate(valid_doc(), "2026-10-15")))

    def test_placeholder_fails(self):
        doc = valid_doc()
        doc["note"] = "待填"
        self.assertTrue(any("占位符" in e for e in vmd.validate(doc, "2026-10-16")))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as td:
            good, bad = Path(td) / "good.json", Path(td) / "bad.json"
            good.write_text(json.dumps(valid_doc(), ensure_ascii=False), encoding="utf-8")
            doc = valid_doc()
            doc.pop("verdict")
            bad.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            script = HERE / "validate_market_data.py"
            rcs = [run_cli(script, a)[0] for a in
                   ([str(good), "--expect-date", "2026-10-16"],
                    [str(bad), "--expect-date", "2026-10-16"],
                    [str(Path(td) / "nope.json")])]
        self.assertEqual(rcs, [0, 1, 2])


class TestSettleViewpoints(unittest.TestCase):
    """指标前缀提取 / 四态结算 / 漏报判定 / CLI 落盘。"""

    MARKET = {"data_stage": "close", "total_amount_yi": 16000,
              "indices": {"sh000001": {"change_percent": 0.8},
                          "sh000300": {"change_percent": 0.6}},
              "market_breadth": {"up": 3000},
              "holdings": {"sh600919": {"price": 20.0}}}

    def test_get_metric_variants(self):
        m = self.MARKET
        self.assertAlmostEqual(sv.get_metric(m, "total_amount_yi"), 16000)
        self.assertAlmostEqual(sv.get_metric(m, "idx:sh000001.change_percent"), 0.8)
        self.assertAlmostEqual(sv.get_metric(m, "mb:up"), 3000)
        # hd: 分支按整键查找（"sh600919.price" 当作一个 key）——预存行为原样保留，
        # 本任务只做迁移不改逻辑；该缺陷已在回传报告中登记，不在本任务修
        for bad in ("idx:malformed", "idx:sh000001", "unknown_metric", "hd:sh600919.price"):
            self.assertIsNone(sv.get_metric(m, bad))

    def test_evaluate_four_states(self):
        vp = {"type": "conditional",
              "condition": {"metric": "total_amount_yi", "op": ">=", "value": 15000}}
        self.assertEqual(sv.evaluate(vp, self.MARKET)[0], "TRIGGERED")
        vp2 = {"condition": {"metric": "total_amount_yi", "op": ">=", "value": 18000}}
        self.assertEqual(sv.evaluate(vp2, self.MARKET)[0], "NOT_TRIGGERED")
        vp3 = {"condition": {"metric": "idx:sz399001.change_percent", "op": "<", "value": 1}}
        self.assertEqual(sv.evaluate(vp3, self.MARKET)[0], "UNEVALUABLE")
        vp4 = {"condition": {"metric": "total_amount_yi", "op": "!=", "value": 1}}
        self.assertEqual(sv.evaluate(vp4, self.MARKET)[0], "UNEVALUABLE")

    def test_eval_at_close_blocks_intraday_data(self):
        vp = {"eval_at": "close", "condition": {"metric": "total_amount_yi", "op": ">=", "value": 15000}}
        status, detail = sv.evaluate(vp, {"data_stage": "intraday", "total_amount_yi": 16000})
        self.assertEqual(status, "UNEVALUABLE")
        self.assertIn("防盘中数据误触发", detail)

    def test_cli_no_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = run_cli(HERE / "settle_viewpoints.py",
                              ["--archive", td, "--today", "2026-10-16"])
        self.assertEqual(rc, 0, out)
        self.assertIn("no_ledger", out)

    def test_cli_settles_and_flags_missed_neutral(self):
        prev = {"date": "2026-10-15",
                "viewpoints": [{"id": "V0", "type": "neutral", "claim": "观望"}]}
        with tempfile.TemporaryDirectory() as td:
            arch = Path(td)
            for day, name, obj in (("2026-10-15", "viewpoint.json", prev),
                                   ("2026-10-16", "market_data.json", self.MARKET)):
                (arch / day).mkdir()
                (arch / day / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
            rc, out = run_cli(HERE / "settle_viewpoints.py",
                              ["--archive", str(arch), "--today", "2026-10-16"])
            self.assertEqual(rc, 0, out)
            result = json.loads((arch / "2026-10-16" / "settlement.json")
                                .read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "settled")
        self.assertEqual(result["counts"]["MISSED_NEUTRAL"], 1)
        self.assertEqual(result["ledger_date"], "2026-10-15")


if __name__ == "__main__":
    unittest.main(verbosity=2)
