#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_report_contract.py — 报告章节契约回归（GAP-A2）

守护五类真实缺陷（2026-10-16 扫真实产物发现 23 项违规，择其要者）：
  R-1 必需章节缺失（章节命名各写各的 → 渲染层无法稳定映射区块）
  R-2 结论章节不在首位（读者首屏看不到结论）
  R-3 标题含 emoji / 版本号副标题 / 空章节 / 层级跳跃
  R-4 评级或 Σ 与 market_data.json 不符（最危险：按错方向操作）
  R-5 降级轮给出可执行动作（金融场景 P0）

**误报回归**同样入测：「昨日观点：6.75 元挂买」是回顾而非动作，
误报会让契约变成噪音，噪音等于没有契约。

运行：python3 test_report_contract.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from check_report import check_report, load_contract, parse_yaml_subset  # noqa: E402

CONTRACT = load_contract()

MD_OK = """# 标题

## 一、结论卡

今日评级【均衡】，Σ+0.180。

## 二、六信号明细

S1 量能 1.00。

## 三、观点台账兑现结算

四态结算完成。

## 四、持仓诊断与网格动作执行卡

无动作。
"""

MDATA_OK = {"verdict": {"rating": "均衡", "sigma": 0.18}, "data_gaps": []}


def _check(md: str, task="stock-assistant", mdata=None):
    return check_report(md, task, mdata if mdata is not None else MDATA_OK)


class TestContractParsing(unittest.TestCase):
    def test_yaml_subset_parser_handles_nesting(self):
        d = parse_yaml_subset("a:\n  b: 1\n  c: two\n")
        self.assertEqual(d, {"a": {"b": 1, "c": "two"}})

    def test_yaml_subset_parser_handles_list_of_maps(self):
        d = parse_yaml_subset("items:\n  - k: v\n    j: 2\n  - k: w\n")
        self.assertEqual(d["items"][0]["k"], "v")
        self.assertEqual(d["items"][1]["k"], "w")

    def test_inline_list_parsed_as_list_not_chars(self):
        """回归：内联列表曾被逐字符拆分，规则静默失效却看不出异常。"""
        d = parse_yaml_subset('kw: ["结论卡", "核心决策"]  # 说明\n')
        self.assertEqual(d["kw"], ["结论卡", "核心决策"])

    def test_inline_comment_stripped(self):
        """回归：行尾注释不剥会让内联列表带上说明文字，匹配随之失效。"""
        d = parse_yaml_subset("v: abc   # 这是说明\n")
        self.assertEqual(d["v"], "abc")

    def test_hash_inside_quotes_not_comment(self):
        d = parse_yaml_subset('v: "a#b"  # 注释\n')
        self.assertEqual(d["v"], "a#b")

    def test_contract_keywords_clean(self):
        """契约里的 verdict_keywords 必须解析为干净字符串（无尾注释）。"""
        kws = CONTRACT["rules"]["verdict_keywords"]
        for k in kws:
            self.assertNotIn("#", k, f"关键词带注释残留: {k!r}")
            self.assertNotIn(" ", k.strip()[:1], f"关键词首尾含空格: {k!r}")

    def test_contract_has_five_tasks(self):
        self.assertEqual(set(CONTRACT["tasks"]),
                         {"stock-assistant", "fund-market", "fund-guide",
                          "stock-review", "daily-review"})

    def test_every_required_section_has_semantic_and_pattern(self):
        for task, spec in CONTRACT["tasks"].items():
            for sec in spec["required"]:
                self.assertIn("semantic", sec, f"{task} 缺 semantic")
                self.assertIn("title_pattern", sec, f"{task} 缺 title_pattern")


class TestStructureR1R2(unittest.TestCase):
    def test_valid_report_passes(self):
        e, _ = _check(MD_OK)
        self.assertEqual(e, [])

    def test_missing_required_section_flagged(self):
        md = MD_OK.replace("## 四、持仓诊断与网格动作执行卡", "## 四、其他")
        e, _ = _check(md)
        self.assertTrue(any("缺必需章节" in x for x in e))

    def test_verdict_section_must_be_first(self):
        # 章节必须齐全，否则 R-1 先报错、R-2 会跳过，测的就不是顺序了
        md = ("# 标题\n\n## 一、持仓诊断与网格动作执行卡\n\n无。\n\n"
              "## 二、六信号明细\n\nx\n\n"
              "## 三、观点台账兑现结算\n\nx\n\n"
              "## 四、结论卡\n\n今日评级【均衡】，Σ+0.180。\n")
        e, _ = _check(md)
        self.assertTrue(any("应在首位" in x for x in e),
                        f"结论章节不在首位却未报错: {e}")

    def test_degraded_notice_may_precede_verdict(self):
        """降级提示可置于结论之前——读者须先知道数据不可信，再看结论。

        这是契约服从产品的一例（2026-10-16 修正：契约一度要求结论绝对首位，
        与「⚠️ 连接器未连接提示」排第一的真实产物冲突）。
        """
        md = ("# 标题\n\n## 一、连接器未连接提示\n\n本轮数据降级。\n\n"
              "## 二、结论卡\n\n今日评级【均衡】，Σ+0.180。\n\n"
              "## 三、六信号明细\n\nx\n\n"
              "## 四、观点台账兑现结算\n\nx\n\n"
              "## 五、持仓诊断与网格动作\n\nx\n")
        e, _ = _check(md)
        self.assertEqual([x for x in e if "首位" in x or "紧随" in x], [],
                         f"降级提示在前不该报顺序错: {e}")

    def test_degraded_notice_still_requires_verdict_after(self):
        """降级提示在前时，结论仍必须紧随其后（提示不能连续占两位）。"""
        md = ("# 标题\n\n## 一、连接器未连接提示\n\n降级。\n\n"
              "## 二、持仓诊断与网格动作\n\n无。\n\n"
              "## 三、结论卡\n\n评级【均衡】Σ+0.180。\n\n"
              "## 四、六信号明细\n\nx\n\n"
              "## 五、观点台账兑现结算\n\nx\n")
        e, _ = _check(md)
        self.assertTrue(any("紧随" in x for x in e),
                        f"提示后又插别的章节却未报错: {e}")

    def test_unknown_task_flagged(self):
        e, _ = check_report(MD_OK, "no-such-task", MDATA_OK)
        self.assertTrue(any("未知任务" in x for x in e))


class TestHeadingHygieneR3(unittest.TestCase):
    def test_emoji_in_heading_flagged(self):
        md = MD_OK.replace("## 一、结论卡", "## 🚦 一、结论卡")
        e, _ = _check(md)
        self.assertTrue(any("emoji" in x for x in e))

    def test_version_suffix_flagged(self):
        md = MD_OK.replace("## 一、结论卡", "## 一、结论卡 — daily-decision-engine v1.3")
        e, _ = _check(md)
        self.assertTrue(any("版本号副标题" in x for x in e))

    def test_empty_section_flagged(self):
        md = MD_OK + "\n## 五、空章节\n\n## 六、结尾\n\n结束。\n"
        e, _ = _check(md)
        self.assertTrue(any("空章节" in x for x in e))

    def test_level_jump_flagged(self):
        md = MD_OK + "\n#### 跳级\n\n内容\n"
        e, _ = _check(md)
        self.assertTrue(any("层级跳跃" in x for x in e))


class TestDataConsistencyR4(unittest.TestCase):
    def test_conflicting_rating_flagged(self):
        md = MD_OK.replace("今日评级【均衡】", "今日评级【进攻】")
        e, _ = _check(md, mdata={"verdict": {"rating": "均衡", "sigma": 0.18}})
        self.assertTrue(any("评级" in x for x in e))

    def test_conflicting_sigma_flagged(self):
        md = MD_OK.replace("Σ+0.180", "Σ+0.510")
        e, _ = _check(md)
        self.assertTrue(any("Σ 值" in x for x in e))

    def test_matching_sigma_tolerates_rounding(self):
        md = MD_OK.replace("Σ+0.180", "Σ+0.1801")   # 四舍五入尾差
        e, _ = _check(md)
        self.assertEqual([x for x in e if "Σ 值" in x], [])

    def test_no_market_data_skips_r4(self):
        e, _ = check_report(MD_OK, "stock-assistant", None)
        self.assertEqual([x for x in e if "Σ 值" in x or "评级" in x], [])


class TestDegradedDisciplineR5(unittest.TestCase):
    GAP = {"verdict": {"rating": "信号矛盾", "sigma": -0.011},
           "data_gaps": ["westock-mcp 连接器未连接"]}

    def test_actionable_advice_in_degraded_round_flagged(self):
        md = MD_OK.replace("无动作。", "**操作指引**：盘中冲高 7.15 元挂单卖出 500 股。")
        e, _ = _check(md, mdata=self.GAP)
        self.assertTrue(any("降级轮不得给出可执行动作" in x for x in e))

    def test_action_hidden_in_table_row_still_flagged(self):
        """回归：动作写在表格行里也算违规（实测网格卡表格内藏指令）。"""
        md = MD_OK.replace(
            "无动作。",
            "| **网格做T卡** | 现价 6.85。**操作指引**：冲高 7.15 元挂单卖出 500 股 |\n")
        e, _ = _check(md, mdata=self.GAP)
        self.assertTrue(any("降级轮不得给出可执行动作" in x for x in e))

    def test_review_context_not_flagged(self):
        """误报回归：「昨日观点：6.75 元挂买」是回顾，不是本轮动作。"""
        md = MD_OK.replace(
            "无动作。",
            "- **V2（甘肃能源 6.75 元挂买）**：`NOT_TRIGGERED`（未触及下限）。")
        e, _ = _check(md, mdata=self.GAP)
        self.assertEqual([x for x in e if "降级轮" in x], [])

    def test_normal_round_action_allowed(self):
        """非降级轮给出动作是正常的——不能一刀切禁掉。"""
        md = MD_OK.replace("无动作。", "挂单卖出 500 股做T。")
        e, _ = _check(md, mdata=MDATA_OK)
        self.assertEqual([x for x in e if "降级轮" in x], [])

    def test_degraded_round_without_action_warns_only(self):
        e, w = _check(MD_OK, mdata=self.GAP)
        self.assertEqual([x for x in e if "降级轮" in x], [])
        self.assertTrue(any("数据源降级" in x for x in w))


if __name__ == "__main__":
    unittest.main(verbosity=2)
