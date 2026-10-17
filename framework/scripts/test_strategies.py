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
            "category: defensive\n"
            "description: 防守策略\n"
            "rules:\n"
            "  - 规则一\n"
        )
        y2 = (
            "name: s2\n"
            "display_name: 策略二\n"
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
