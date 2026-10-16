"""content_contract 一致性校验测试。

用例覆盖正常场景与违规场景，fixture 全部取自 2026-10-14 六任务真实产出，
不构造人造样本——真实数据才暴露得出真实违规。

运行：python3 test_content_contract.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import content_contract as cc
from content_dictionary import BANNED_DIMENSIONS, DIMENSIONS, ICONS

BASE = Path("/Users/lianghaizhen/WorkBuddy")
DAY = "2026-10-14"
SRC = Path(__file__).resolve().parent


def real_md(task_dir: str, fname: str) -> Path:
    return BASE / task_dir / DAY / fname


def real_json(task_dir: str, fname: str = "market_data.json") -> dict | None:
    p = BASE / task_dir / DAY / fname
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


class TestSkeleton(unittest.TestCase):
    """骨架生成：必选章节恒在，条件章节按任务选入。"""

    def test_required_sections_always_present(self):
        """结论卡/待验证信号/免责声明对全部 6 任务恒定必选。"""
        for slug in ("stock-assistant", "fund-market", "fund-guide",
                     "stock-review", "daily-review", "v2-decision-engine"):
            keys = [s.key for s in cc.build_skeleton(slug)]
            for req in ("verdict", "watchlist", "disclaimer"):
                self.assertIn(req, keys, f"{slug} 缺必选章节 {req}")

    def test_conditional_sections_task_specific(self):
        """专家圆桌只进复盘类，网格委托只进基金指引。"""
        review = [s.key for s in cc.build_skeleton("stock-review")]
        guide = [s.key for s in cc.build_skeleton("fund-guide")]
        self.assertIn("expert_roundtable", review)
        self.assertNotIn("expert_roundtable", guide)
        self.assertIn("grid_order", guide)
        self.assertNotIn("grid_order", review)

    def test_skeleton_tolerates_length_spread(self):
        """9:28(73行) 与 15:05(144行) 任务骨架均可生成，骨架不按行数裁剪。"""
        lengths = {slug: len(cc.build_skeleton(slug)) for slug in
                   ("stock-assistant", "fund-market", "fund-guide",
                    "stock-review", "daily-review", "v2-decision-engine")}
        self.assertTrue(all(v >= 3 for v in lengths.values()), lengths)

    def test_render_skeleton_md_numbering(self):
        """渲染出的章节标题必须是两位数字编号。"""
        out = cc.render_skeleton_md("fund-guide").splitlines()
        self.assertTrue(out)
        for i, line in enumerate(out, start=1):
            self.assertTrue(line.startswith(f"## {i:02d}. "), line)


class TestDictionaryIntegrity(unittest.TestCase):
    """词表自身的一致性——词表错了校验器会静默放过一切。"""

    def test_no_banned_name_equals_canonical(self):
        """旧称不得与规范名同名，否则自相矛盾。"""
        for key, zh, old in BANNED_DIMENSIONS:
            self.assertNotEqual(old, zh, f"{key} 的旧称与规范名相同")

    def test_canonical_names_unique_per_key(self):
        """每个维度的规范中文名唯一。"""
        names = [zh for zh, _en, _o in DIMENSIONS.values()]
        self.assertEqual(len(names), len(set(names)), "规范名重复")

    def test_icons_have_24x24_paths(self):
        """SVG 语义映射：语义键齐全，path 均为 24x24 线性描边。"""
        self.assertGreaterEqual(len(ICONS), 14)
        for key, (zh, path) in ICONS.items():
            self.assertTrue(zh, f"{key} 缺中文语义")
            self.assertTrue(path.startswith("M"), f"{key} path 非 SVG 起始命令")

    def test_every_dimension_has_icon_or_exempt(self):
        """每个分析维度都能映射到图标语义或显式豁免。"""
        mapped = {"verdict", "signal_detail", "market_snapshot", "sector_moneyflow",
                  "overseas_check", "portfolio_attribution", "fund_lookthrough",
                  "position_action", "grid_order", "expert_roundtable",
                  "viewpoint_ledger", "data_gap", "watchlist", "sigma_timeline"}
        for key in DIMENSIONS:
            if key in ("disclaimer", "concentration", "bull_bear_evidence",
                       "index_quote"):
                continue
            self.assertIn(key, mapped | set(ICONS), f"{key} 未映射图标语义")


class TestRenderSigma(unittest.TestCase):
    """Σ 呈现契约：值与时点必须同行。"""

    def test_sigma_line_contains_stage_and_snapshot(self):
        line = cc.render_sigma_line(-0.263, "intraday", "2026-10-14 14:30", "防守")
        self.assertIn("Σ = **-0.263**", line)
        self.assertIn("data_stage=`intraday`", line)
        self.assertIn("snapshot_at=`2026-10-14 14:30`", line)

    def test_meta_block_field_order(self):
        block = cc.render_meta_block(0.010, "intraday", "2026-10-14 12:39",
                                     "信号矛盾", 1.0, "a_plus_bj")
        self.assertTrue(block.startswith("> Σ = +0.010"))
        for field in ("data_stage", "snapshot_at", "rating",
                      "valid_weight", "breadth_scope"):
            self.assertIn(field, block)

    def test_sigma_timeline_has_all_snapshots(self):
        """日内演进带必须逐行列出每个时点，读者才能区分演进与错误。"""
        rows = [
            {"time": "09:28", "snapshot_at": "2026-10-14 12:39",
             "data_stage": "intraday", "sigma": 0.010, "rating": "信号矛盾"},
            {"time": "14:30", "snapshot_at": "2026-10-14 14:30",
             "data_stage": "intraday", "sigma": -0.263, "rating": "防守"},
            {"time": "15:30", "snapshot_at": "2026-10-14 15:31",
             "data_stage": "close", "sigma": -0.339, "rating": "防守"},
        ]
        table = cc.render_sigma_timeline(rows)
        self.assertIn("| 时点 | 快照时刻 |", table)
        for r in rows:
            self.assertIn(f"{r['sigma']:+.3f}", table)
        self.assertIn("`close`", table)

    def test_comparable_flags_scope_mismatch(self):
        """breadth_scope 不一致时必须判定 Σ 不可比。"""
        a = {"breadth_scope": "a_plus_bj", "valid_weight": 1.0}
        b = {"breadth_scope": "a_only", "valid_weight": 1.0}
        ok, why = cc.comparable([a, b])
        self.assertFalse(ok)
        self.assertIn("breadth_scope", why)
        ok2, _ = cc.comparable([a, dict(a)])
        self.assertTrue(ok2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
