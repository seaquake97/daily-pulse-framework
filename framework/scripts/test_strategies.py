#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_strategies.py — 声明式策略库解析与校验测试套件（纯标准库）"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import strategies as st


class TestStrategyValidation(unittest.TestCase):
    def test_valid_strategy_passes(self):
        valid = {
            "name": "test_strat",
            "display_name": "测试策略",
            "track": "stock",
            "category": "strategic",
            "description": "这是测试策略说明",
            "rules": ["规则1：低吸", "规则2：高抛"],
        }
        errs = st.validate_strategy_dict(valid)
        self.assertEqual(errs, [])

    def test_missing_required_field_fails(self):
        invalid = {
            "name": "test_strat",
            "display_name": "测试策略",
            "track": "stock",
            "category": "strategic",
            # missing description & rules
        }
        errs = st.validate_strategy_dict(invalid)
        self.assertTrue(any("description" in e for e in errs))
        self.assertTrue(any("rules" in e for e in errs))

    def test_emoji_violation_triggers_p0(self):
        # 团队 P0-1 铁律测试：严禁在策略中包含 emoji
        invalid = {
            "name": "emoji_strat",
            "display_name": "火箭策略",
            "track": "stock",
            "category": "trend",
            "description": "顺势做多",
            "rules": ["规则1：买入🚀"],
        }
        errs = st.validate_strategy_dict(invalid)
        self.assertTrue(any("P0-1" in e or "emoji" in e for e in errs))

    def test_invalid_category_fails(self):
        invalid = {
            "name": "cat_strat",
            "display_name": "分类测试",
            "track": "stock",
            "category": "unknown_category",
            "description": "分类错误测试",
            "rules": ["规则1"],
        }
        errs = st.validate_strategy_dict(invalid)
        self.assertTrue(any("category" in e for e in errs))

    def test_load_from_yaml_file(self):
        yaml_content = (
            "name: file_strat\n"
            "display_name: 文件测试策略\n"
            "track: stock\n"
            "category: execution\n"
            "description: 从受限 YAML 正常加载\n"
            "rules:\n"
            "  - 规则A：价格触及下沿买入\n"
            "  - 规则B：冲高触及上沿分批高抛\n"
        )
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "strat.yaml"
            f.write_text(yaml_content, encoding="utf-8")

            res = st.load_strategy(f)
            self.assertEqual(res["name"], "file_strat")
            self.assertEqual(res["category"], "execution")
            self.assertEqual(len(res["rules"]), 2)

    def test_load_all_strategies_dir(self):
        y1 = (
            "name: s1\n"
            "display_name: 策略一\n"
            "track: stock\n"
            "category: defensive\n"
            "description: 防守策略\n"
            "rules:\n"
            "  - 规则一\n"
        )
        y2 = (
            "name: s2\n"
            "display_name: 策略二\n"
            "track: stock\n"
            "category: strategic\n"
            "description: 战略配置\n"
            "rules:\n"
            "  - 规则二\n"
        )
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "s1.yaml").write_text(y1, encoding="utf-8")
            (Path(td) / "s2.yaml").write_text(y2, encoding="utf-8")

            all_s = st.load_all_strategies(Path(td))
            self.assertEqual(len(all_s), 2)
            self.assertIn("s1", all_s)
            self.assertIn("s2", all_s)


class TestTrackIsolation(unittest.TestCase):
    """ADR-007 §2.2：基金轨与股票轨隔离（收割 H-1/H-2/H-3）。"""

    def test_missing_track_fails(self):
        """未声明轨道 → 拒。轨道归属必须显式，不得靠默认值兜底（收割 M-2）。"""
        s = {"name": "t1", "display_name": "T", "category": "strategic",
             "description": "d", "rules": ["r"]}
        errs = st.validate_strategy_dict(s)
        self.assertTrue(any("track" in e for e in errs))

    def test_invalid_track_fails(self):
        s = {"name": "t2", "display_name": "T", "track": "future_track",
             "category": "strategic", "description": "d", "rules": ["r"]}
        errs = st.validate_strategy_dict(s)
        self.assertTrue(any("track" in e for e in errs))

    def test_fund_track_rejects_grid_mechanism(self):
        """场外基金轨出现网格机制 → 拒（场外基金无中间态）。"""
        s = {"name": "t3", "display_name": "T", "track": "fund",
             "category": "execution", "description": "d",
             "rules": ["网格步长设为2.5%，逢低分档买入"]}
        errs = st.validate_strategy_dict(s)
        self.assertTrue(any("中间态机制词" in e for e in errs))

    def test_fund_track_allows_negated_mechanism_mention(self):
        """否定语境（禁止网格）不算违规——纪律文本必须能说出被禁机制。"""
        s = {"name": "t4", "display_name": "T", "track": "fund",
             "category": "execution", "description": "d",
             "rules": ["场外基金禁止使用网格做T", "本轨无挂单条件单机制"]}
        errs = st.validate_strategy_dict(s)
        self.assertEqual(errs, [])

    def test_stock_track_allows_grid(self):
        """股票轨保留网格与做T（收割 H-3：场内 ETF 属股票轨）。"""
        s = {"name": "t5", "display_name": "T", "track": "stock",
             "category": "execution", "description": "d",
             "rules": ["网格步长2.5%", "依托条件单执行"]}
        errs = st.validate_strategy_dict(s)
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
