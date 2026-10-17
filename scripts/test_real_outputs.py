"""content_contract 对真实 2026-10-14 产出的契约回归测试。

与 test_content_contract.py 分文件：本文件只管「真实数据 + 跨任务一致性」，
fixture 全部指向工作区根（paths.WORKBUDDY_ROOT）下的当日实际产出。
真实数据缺失时用例 skip 而非伪造样本。

运行：python3 test_real_outputs.py
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "framework" / "scripts"))   # A-04
import paths

import content_contract as cc

BASE = paths.WORKBUDDY_ROOT
DAY = os.environ.get("PULSE_TEST_DAY", "2026-10-14")
SRC = Path(__file__).resolve().parent


def real_md(task_dir: str, fname: str) -> Path:
    p = BASE / task_dir / DAY / fname
    if not p.exists():
        raise unittest.SkipTest(f"真实产出缺失：{p}")
    return p


def real_json(task_dir: str, fname: str = "market_data.json") -> dict:
    """取真实 market_data.json；缺失即 SkipTest。

    ⚠ 原实现返回 None 而不 skip，导致依赖它的用例在**他人机器上必然失败**
    （2026-10-16 架构师实测 failures=1，本轮实锤复现）。这是「clone 完就能跑」
    承诺的破口：别人没有你的真实产物，测试就不该红——它该 skip。
    """
    p = BASE / task_dir / DAY / fname
    if not p.exists():
        raise unittest.SkipTest(f"真实产出缺失：{p}")
    return json.loads(p.read_text(encoding="utf-8"))


class TestValidateAgainstRealOutput(unittest.TestCase):
    """用 2026-10-14 真实产出验证违规能被检出。"""

    CASES = [
        ("股票助手", "stock_assistant.md"),
        ("基金每日盘面分析（11:00）", "fund_market_analysis.md"),
        ("基金每日操作指引（14:30）", "fund_operation_guide.md"),
        ("股票复盘", "stock_review.md"),
    ]

    def test_real_outputs_are_flagged(self):
        """真实产出全部违反新契约——证明校验器不是空转。"""
        for task_dir, fname in self.CASES:
            with self.subTest(task=task_dir):
                v = cc.validate_contract(real_md(task_dir, fname))
                self.assertTrue(v, f"{task_dir} 未检出任何违规，校验器可能失效")

    def test_fund_guide_emoji_detected(self):
        """14:30 指引有 13 处 emoji（码点见 ADR-003 证据表），须全部命中。"""
        v = cc.validate_contract(real_md("基金每日操作指引（14:30）",
                                         "fund_operation_guide.md"))
        emoji = [x for x in v if x.rule == "EMOJI"]
        self.assertGreaterEqual(len(emoji), 10)

    def test_stock_review_banned_dimension_detected(self):
        """15:05 复盘的「子专家观点」为废弃维度名。"""
        v = cc.validate_contract(real_md("股票复盘", "stock_review.md"))
        dims = [x for x in v if x.rule == "DIMENSION"]
        self.assertTrue(any("子专家观点" in x.message for x in dims))

    def test_chinese_numbering_rejected(self):
        """「一、」「01」混用编号体系必须被判违规。"""
        v = cc.validate_contract(real_md("股票助手", "stock_assistant.md"))
        self.assertTrue([x for x in v if x.rule == "NUMBERING"])

    def test_illegal_data_stage_rejected(self):
        """非法 data_stage 枚举须拦下——真实产出暂无此样本，用构造样本覆盖。"""
        text = ("# 报告\n\n> Σ = +0.010 ｜ data_stage=`morning`"
                " ｜ snapshot_at=`2026-10-14 09:28`\n\nΣ = +0.010\n")
        p = SRC / "_tmp_bad_stage.md"
        p.write_text(text, encoding="utf-8")
        try:
            v = cc.validate_contract(p)
            self.assertTrue([x for x in v if x.rule == "STAGE_ENUM"])
        finally:
            p.unlink(missing_ok=True)

    def test_illegal_breadth_scope_rejected(self):
        """非法 breadth_scope 须拦下。"""
        text = ("# 报告\n\n> Σ = +0.010 ｜ data_stage=`intraday`"
                " ｜ snapshot_at=`2026-10-14 09:28` ｜ breadth_scope=`all`\n\nΣ = +0.010\n")
        p = SRC / "_tmp_bad_scope.md"
        p.write_text(text, encoding="utf-8")
        try:
            v = cc.validate_contract(p)
            self.assertTrue([x for x in v if x.rule == "BREADTH_SCOPE"
                             and x.severity == "error"])
        finally:
            p.unlink(missing_ok=True)

    def test_section_name_outside_skeleton_rejected(self):
        """章节名不在骨架内须拦下（如自造「资金面观察」章节）。"""
        text = ("# 报告\n\n> Σ = +0.010 ｜ data_stage=`intraday`"
                " ｜ snapshot_at=`2026-10-14 09:28`\n\n"
                "## 01. 结论卡\n\nΣ = +0.010\n\n## 02. 资金面观察\n")
        p = SRC / "_tmp_bad_section.md"
        p.write_text(text, encoding="utf-8")
        try:
            v = cc.validate_contract(p)
            self.assertTrue([x for x in v if x.rule == "SECTION_NAME"])
        finally:
            p.unlink(missing_ok=True)

    def test_sigma_without_stage_stamp_rejected(self):
        """Σ 出现但缺 data_stage/snapshot_at 标注须拦下（两条独立规则）。"""
        v = cc.validate_contract(real_md("股票复盘", "stock_review.md"))
        self.assertTrue([x for x in v if x.rule == "SIGMA_SNAPSHOT_STAMP"])
        self.assertTrue([x for x in v if x.rule == "SIGMA_STAGE_STAMP"])

    def test_sigma_with_stage_but_no_snapshot_is_still_flagged(self):
        """只补 data_stage 不补 snapshot_at 仍须报——防止用 stage 顶替时刻。"""
        text = ("# 报告\n\n> Σ = +0.010 ｜ data_stage=`intraday`\n\n"
                "- Σ = **+0.010** ｜ data_stage=`intraday` ｜ rating=**信号矛盾**\n")
        p = SRC / "_tmp_stage_only.md"
        p.write_text(text, encoding="utf-8")
        try:
            v = cc.validate_contract(p)
            self.assertTrue([x for x in v if x.rule == "SIGMA_SNAPSHOT_STAMP"])
            self.assertFalse([x for x in v if x.rule == "SIGMA_STAGE_STAMP"])
        finally:
            p.unlink(missing_ok=True)

    def test_bare_sigma_without_any_stamp_flagged(self):
        """裸 Σ（无任何时点标注）两条规则同时触发。"""
        text = "# 报告\n\n今日评级为信号矛盾，Σ = -0.339。\n"
        p = SRC / "_tmp_bare_sigma.md"
        p.write_text(text, encoding="utf-8")
        try:
            v = cc.validate_contract(p)
            self.assertTrue([x for x in v if x.rule == "SIGMA_SNAPSHOT_STAMP"])
            self.assertTrue([x for x in v if x.rule == "SIGMA_STAGE_STAMP"])
        finally:
            p.unlink(missing_ok=True)


class TestCleanFixturePasses(unittest.TestCase):
    """合规产出必须零 error——否则校验器过严会逼所有人绕开它。"""

    def test_compliant_report_has_no_error(self):
        good = "\n".join([
            "# 基金每日操作指引 · 2026-10-14",
            "",
            "> Σ = -0.263 ｜ data_stage=`intraday` ｜ snapshot_at=`2026-10-14 14:30`"
            " ｜ rating=防守 ｜ valid_weight=1.00 ｜ breadth_scope=`a_plus_bj`",
            "",
            "## 01. 结论卡",
            "",
            "- Σ = **-0.263** ｜ data_stage=`intraday`"
            " ｜ snapshot_at=`2026-10-14 14:30` ｜ rating=**防守**",
            "",
            "## 02. 确定性信号明细",
            "",
            "## 03. 板块资金流向",
            "",
            "## 04. 持仓动作卡",
            "",
            "## 05. 观点台账",
            "",
            "## 06. 待验证信号",
            "",
            "## 07. 免责声明",
            "",
        ])
        p = SRC / "_tmp_compliant.md"
        p.write_text(good, encoding="utf-8")
        try:
            v = cc.validate_contract(p)
            self.assertEqual([x for x in v if x.severity == "error"], [],
                             [x.message for x in v if x.severity == "error"])
        finally:
            p.unlink(missing_ok=True)

    def test_sigma_mismatch_against_own_json_detected(self):
        """报告 Σ 与本任务 market_data.json 不一致须报 SIGMA_VALUE。"""
        text = ("> Σ = +0.500 ｜ data_stage=`intraday`"
                " ｜ snapshot_at=`2026-10-14 14:30`\n\nΣ = +0.500\n")
        p = SRC / "_tmp_sigma.md"
        p.write_text(text, encoding="utf-8")
        try:
            v = cc.validate_contract(p, {"verdict": {"sigma": -0.263}})
            self.assertTrue([x for x in v if x.rule == "SIGMA_VALUE"])
        finally:
            p.unlink(missing_ok=True)

    def test_fund_market_missing_json_is_flagged(self):
        """11:00 盘面无 market_data.json，Σ 无法回溯——须显式报出。"""
        self.assertIsNone(real_json("基金每日盘面分析（11:00）"))
        v = cc.validate_contract(real_md("基金每日盘面分析（11:00）",
                                         "fund_market_analysis.md"), None)
        self.assertTrue(v)


class TestJsonArtifact(unittest.TestCase):
    """market_data.json 时点字段完整性。"""

    def test_real_json_missing_snapshot_at(self):
        """三份真实 market_data.json 均缺 snapshot_at，Σ 无法回溯到具体时刻。"""
        for task_dir in ("股票助手", "基金每日操作指引（14:30）", "每日总复盘（15:30）"):
            data = real_json(task_dir)
            if data is None:
                continue
            with self.subTest(task=task_dir):
                self.assertNotIn("snapshot_at", data)
                v = cc.validate_json_artifact(BASE / task_dir / DAY / "market_data.json")
                self.assertTrue([x for x in v if x.rule == "SNAPSHOT_AT"])

    def test_invalid_json_reported_not_raised(self):
        p = SRC / "_tmp_bad.json"
        p.write_text("{not json", encoding="utf-8")
        try:
            v = cc.validate_json_artifact(p)
            self.assertEqual(v[0].rule, "JSON_INVALID")
        finally:
            p.unlink(missing_ok=True)


class TestSigmaConsistencyAcrossTasks(unittest.TestCase):
    """跨任务 Σ 一致性：同名 market_data.json 不得携带互相矛盾的 verdict。"""

    def test_three_snapshots_have_distinct_verdicts(self):
        """9:28/14:30/15:30 三份快照 Σ 各不相同且与 data_stage 对应。"""
        sa = real_json("股票助手")
        fg = real_json("基金每日操作指引（14:30）")
        dr = real_json("每日总复盘（15:30）")
        self.assertIsNotNone(sa and fg and dr)
        self.assertEqual(sa["verdict"]["sigma"], 0.01)
        self.assertEqual(fg["verdict"]["sigma"], -0.263)
        self.assertEqual(dr["verdict"]["sigma"], -0.339)
        self.assertEqual(dr["data_stage"], "close")
        self.assertNotEqual(sa["verdict"]["sigma"], dr["verdict"]["sigma"])

    def test_publish_layer_sigma_is_task_own(self):
        """锁定修复：发布层按 per-slug 数据源取 Σ（ADR-002 修复后行为）。

        原为「缺陷锁定」用例 test_publish_layer_sigma_is_not_task_own——
        断言 stock-assistant 的 Σ != 本任务 verdict Σ（当时发布层把 15:30
        收盘 Σ 错挂到全部条目）。架构师改为 per-slug 数据源后，两者相等，
        本用例翻转为「锁定修复」：9:28 盘中条目必须携带本任务 verdict Σ，
        不得串用每日总复盘（15:30 close）的 Σ。
        """
        entries = (SRC.parent / "_stage/docs/daily/2026-10-14/entries.json")
        if not entries.exists():
            self.skipTest("发布产物未生成，跳过")
        data = json.loads(entries.read_text(encoding="utf-8"))
        by_slug = {e["slug"]: e for e in data}
        sa = real_json("股票助手")
        dr = real_json("每日总复盘（15:30）")
        entry = by_slug.get("stock-assistant")
        self.assertIsNotNone(entry, "entries.json 缺少 stock-assistant 条目")

        # 0) P0-1（架构师 A-04）：降级轮在**数据层**即撤下方向值。
        # 数据不可信时给出方向本身是误导；且 entries.json 会被第三方直接消费。
        if entry.get("degraded"):
            self.assertIsNone(entry["sigma"],
                              "降级条目的 Σ 必须在数据层置 null，不得外泄给消费方")
            self.assertIsNone(entry["rating"], "降级条目的评级必须置 null")
            self.assertFalse(entry["comparable"], "降级条目不可标记为可比")
        else:
            # 1) 非降级时 Σ 必须等于本任务 market_data.json 的 verdict Σ
            #    （per-slug 取数，不得串用每日总复盘的收盘 Σ）
            self.assertEqual(entry["sigma"], sa["verdict"]["sigma"])
            self.assertNotEqual(entry["sigma"], dr["verdict"]["sigma"],
                                "不得串用每日总复盘（15:30 收盘）的 Σ")
        # 2) 时点字段随本任务，而非收盘
        self.assertEqual(entry["stage"], "pre_open",
                         "9:28 是集合竞价快照，性质为 pre_open；标成 intraday "
                         "会让读者把竞价结论当盘中结论读（PM C-11 实锤）")
        # 3b) 上游 market_data.json 里写的 data_stage 是 intraday（上游未细分
        # 竞价），发布层以 SLUG_STAGE 为准——判定权在发布层，不依赖上游字段。


if __name__ == "__main__":
    unittest.main(verbosity=2)
