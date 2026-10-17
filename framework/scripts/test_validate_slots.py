#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_validate_slots.py — 槽位契约校验器负例测试

测试目标不是「校验器能通过真实配置」，而是「每条断言都能抓住它对应的那类错误」。
因此每个用例都构造一个必然违规的输入，并断言命中预期错误码——
一个抓不住错误的断言等于没有断言（这是专家团 30 轮讨论最贵的教训：
指标看起来在工作，实际从未被检验）。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_slots as vs  # noqa: E402

BASE = {
    "version": 2,
    "slots": [
        {
            "slot_id": "s1", "time": "09:28", "track": "stock", "name": "n",
            "data_stage": "pre_open", "inputs": ["holdings_snapshot"],
            "required_outputs": ["stance", "actions"],
            "allow_mechanisms": ["网格"], "notes": "备注",
        },
        {
            "slot_id": "s2", "time": "11:00", "track": "fund", "name": "n",
            "data_stage": "intraday", "inputs": ["proxy_index_quote"],
            "required_outputs": ["stance", "actions"],
            "allow_mechanisms": [], "notes": "备注",
        },
    ],
    "narrative_time_rules": [
        {"lag_status": "plan", "usable_for_action": True},
        {"lag_status": "done", "usable_for_action": False},
        {"lag_status": "superseded", "usable_for_action": False},
    ],
}


def mk(**over):
    """构造一份必然违规的配置（默认 2 槽，不满足双轨三层约定）。"""
    import copy
    d = copy.deepcopy(BASE)
    d.update(copy.deepcopy(over))
    return d


def codes(errors):
    return {e.split(":")[0] for e in errors}


class TestSlotContract(unittest.TestCase):

    def _six(self):
        """把 BASE 扩成合规的 6 槽（股票 3 + 基金 3）。"""
        d = mk()
        s = d["slots"]
        s[0]["slot_id"] = "stock_open"
        s[1]["slot_id"] = "fund_morning"
        s.append(dict(s[0], slot_id="stock_morning_close", time="11:30"))
        # fund_action 是唯一执行槽：必须要求 amount_unit（否则 S-09 会红）
        s.append(dict(s[1], slot_id="fund_action", time="14:30",
                      required_outputs=["stance", "actions", "amount_unit"]))
        s.append(dict(s[0], slot_id="stock_pm_close", time="15:05"))
        s.append(dict(s[1], slot_id="fund_wrap", time="15:35"))
        return d

    def test_real_config_passes(self):
        """真实槽位契约文件必须零错误——否则门禁本身在说谎。"""
        errs = vs.validate_slots_dict(vs._load(vs.SLOTS_PATH))
        self.assertEqual(errs, [], f"真实配置校验失败: {errs}")

    def test_six_slot_base_passes(self):
        self.assertEqual(vs.validate_slots_dict(self._six()), [])

    # ---- S-01 字段缺失 ----
    def test_s01_missing_required_field(self):
        d = self._six()
        del d["slots"][0]["data_stage"]
        self.assertIn("S-01", codes(vs.validate_slots_dict(d)))

    def test_s01_non_mapping_slot(self):
        d = self._six()
        d["slots"][1] = "not-a-mapping"
        self.assertIn("S-01", codes(vs.validate_slots_dict(d)))

    # ---- S-02 slot_id 重复 ----
    def test_s02_duplicate_slot_id(self):
        d = self._six()
        d["slots"][1]["slot_id"] = d["slots"][0]["slot_id"]
        self.assertIn("S-02", codes(vs.validate_slots_dict(d)))

    # ---- S-03 time 格式 ----
    def test_s03_bad_time_format(self):
        d = self._six()
        d["slots"][0]["time"] = "9点28"
        self.assertIn("S-03", codes(vs.validate_slots_dict(d)))

    # ---- S-04 track 非法 ----
    def test_s04_invalid_track(self):
        d = self._six()
        d["slots"][0]["track"] = "futures"
        self.assertIn("S-04", codes(vs.validate_slots_dict(d)))

    # ---- S-05 非交易时段 ----
    def test_s05_outside_trading_window(self):
        d = self._six()
        d["slots"][0]["time"] = "03:00"
        self.assertIn("S-05", codes(vs.validate_slots_dict(d)))

    # ---- S-06 fund 槽声明中间态机制（核心隔离断言）----
    def test_s06_fund_slot_declares_grid(self):
        """场外基金槽出现网格机制 → 必须红。这是「基金轨独立」的执行形式。"""
        d = self._six()
        d["slots"][1]["allow_mechanisms"] = ["网格"]
        self.assertIn("S-06", codes(vs.validate_slots_dict(d)))

    # ---- S-07 fund 槽消费场内字段 ----
    def test_s07_fund_slot_consumes_intraday(self):
        """场外基金槽消费分时行情 → 必须红（场外无分时净值）。"""
        d = self._six()
        d["slots"][1]["inputs"] = ["intraday_quote"]
        self.assertIn("S-07", codes(vs.validate_slots_dict(d)))

    def test_s07_fund_slot_consumes_grid_state(self):
        d = self._six()
        d["slots"][3]["inputs"] = ["grid_state", "dca_plan_state"]
        self.assertIn("S-07", codes(vs.validate_slots_dict(d)))

    # ---- S-08 required_outputs 空 ----
    def test_s08_empty_required_outputs(self):
        d = self._six()
        d["slots"][0]["required_outputs"] = []
        self.assertIn("S-08", codes(vs.validate_slots_dict(d)))

    # ---- S-09 申赎槽缺 amount_unit ----
    def test_s09_fund_action_missing_amount_unit(self):
        """申赎执行槽不给金额口径 → 骑墙建议，必须红。"""
        d = self._six()
        d["slots"][3]["slot_id"] = "fund_action"
        d["slots"][3]["required_outputs"] = ["stance", "actions"]
        self.assertIn("S-09", codes(vs.validate_slots_dict(d)))

    # ---- S-10 stock 槽机制为空 ----
    def test_s10_stock_slot_without_mechanisms(self):
        d = self._six()
        d["slots"][0]["allow_mechanisms"] = []
        self.assertIn("S-10", codes(vs.validate_slots_dict(d)))

    # ---- S-11 轨道槽数 ----
    def test_s11_wrong_track_counts(self):
        errs = vs.validate_slots_dict(mk())
        self.assertIn("S-11", codes(errs))

    def test_s11_fund_track_missing(self):
        d = self._six()
        d["slots"] = [x for x in d["slots"] if x["track"] == "stock"]
        self.assertIn("S-11", codes(vs.validate_slots_dict(d)))

    # ---- S-12 叙述时效规则 ----
    def test_s12_missing_lag_status(self):
        d = self._six()
        d["narrative_time_rules"] = [{"lag_status": "plan", "usable_for_action": True}]
        self.assertIn("S-12", codes(vs.validate_slots_dict(d)))

    def test_s12_superseded_usable_for_action(self):
        """被推翻的判断不得 usable_for_action=true —— 否则旧结论会被当新依据。"""
        d = self._six()
        for r in d["narrative_time_rules"]:
            if r["lag_status"] == "superseded":
                r["usable_for_action"] = True
        self.assertIn("S-12", codes(vs.validate_slots_dict(d)))

    def test_s12_missing_rules_entirely(self):
        d = self._six()
        del d["narrative_time_rules"]
        self.assertIn("S-12", codes(vs.validate_slots_dict(d)))

    # ---- S-13 notes 缺失 ----
    def test_s13_missing_notes(self):
        """notes 为空会让后续有人把另一轨职责塞进来而无痕迹。"""
        d = self._six()
        d["slots"][0]["notes"] = "   "
        self.assertIn("S-13", codes(vs.validate_slots_dict(d)))

    # ---- 静默测试：本校验器必须真的能红 ----
    def test_silent_test_validator_actually_fires(self):
        """回归护栏：若某条规则被改成「永不触发」，本用例会红。

        这是元规则——「看起来在工作」比坏掉更危险。做法是统计 6 槽基线
        只产生 0 错误，任一负例加入后错误数必须增加。
        """
        base_errs = len(vs.validate_slots_dict(self._six()))
        self.assertEqual(base_errs, 0)
        broken = self._six()
        broken["slots"][1]["allow_mechanisms"] = ["网格"]
        self.assertGreater(len(vs.validate_slots_dict(broken)), base_errs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
