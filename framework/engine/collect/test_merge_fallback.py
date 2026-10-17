#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_merge_fallback.py — 备用源数据合并器单测（全离线，mock dict 模拟 fallback_fetcher 输出）

验证五条铁律：主源优先不覆盖 / 缺失才填补 / 脏值丢弃 / 缺口如实记录 / 幂等且不改入参。

运行：python3 framework/engine/collect/test_merge_fallback.py
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import merge_fallback as mf  # noqa: E402
import quote_sources as qs  # noqa: E402  （仅取常量做漂移守卫，不发起网络请求）


def primary_doc() -> dict:
    """主源快照：故意留出整条缺失 / 字段为 None / 字段缺 key 三种缺口形态。"""
    return {
        "date": "2026-10-16", "total_amount_yi": 4145.0,
        "indices": {                                        # sz399006 整条缺失
            "sh000001": {"name": "上证指数", "price": 3726.11, "change_percent": 0.5, "amount": 1.2e11, "time": "2026-10-16", "pe_ratio": 16.2, "volume_ratio": 3.58, "chg_20d": -5.29},
            "sz399001": {"name": "深证成指", "price": 11903.73, "change_percent": 0.74, "amount": 1.4e11, "time": "2026-10-16"},
            "sh000300": {"price": None, "change_percent": None, "amount": 3.0e10, "time": "2026-10-16"},
            "sh000688": {"name": "科创50", "price": 1400.0, "change_percent": 1.1, "amount": 9.0e10, "time": "2026-10-16"},
        },
        "market_breadth": {"up": 4648, "down": 545, "flat": 0, "limit_up": 42, "limit_down": 2},
        "sector_flows": {"top_inflow": 17.1, "top_outflow": 4.22},
    }


def fallback_doc() -> dict:
    """模拟 fetch_indices 输出：含主源已存在的干扰项与一条脏值（price -1）。"""
    return {
        "sh000001": {"name": "上证指数(备用)", "price": 9999.0, "change_percent": 9.9, "amount": 1.0e11, "time": "2026-10-16", "change": 300.0, "volume": 123.0, "quote_time": "2026-10-16 15:00:00", "source": "tencent"},
        "sz399006": {"name": "创业板指", "price": 2801.87, "change_percent": 0.67, "amount": 7.2e10, "time": "2026-10-16", "source": "sina"},
        "sh000300": {"name": "沪深300", "price": 4181.22, "change_percent": 0.37, "amount": 3.1e10, "time": "2026-10-16", "source": "sina"},
        "sh000688": {"name": "科创50", "price": -1.0, "change_percent": 1.1, "amount": 9.0e10, "time": "2026-10-16", "source": "sina"},
    }


def holdings_list() -> list[dict]:
    return [
        {"name": "江苏银行", "code": "sh600919", "price": 12.52},
        {"name": "中国广核", "code": "sz003816", "price": None},
        {"name": "华能蒙电", "code": "sh600863"},
        {"name": "粤高速A", "code": "sz000429", "price": None},
        {"name": "黄金ETF", "code": "sh518600", "price": None},
        {"name": "缺代码标的", "shares": 100},
    ]


def fallback_positions() -> dict:
    return {
        "sz003816": {"name": "中国广核", "price": 4.46, "change_percent": 1.2},
        "sh600863": {"name": "华能蒙电", "price": 4.05, "change_percent": -0.5},
        "sh518600": {"name": "黄金ETF", "price": 0.0, "change_percent": 0.0},
        "sh600919": {"name": "江苏银行", "price": 99.0, "change_percent": 5.0},
    }


def pick(items, code):
    return next(i for i in items if i.get("code") == code)


def merge_one(row, fb_row, code="sh000001"):
    """单指数合并夹具；fb_row 必须自带合法 price，否则整条会被判脏值丢弃。"""
    return mf.merge_indices({"indices": {code: dict(row)}}, {code: dict(fb_row)})


class TestConstants(unittest.TestCase):
    """与源层常量的漂移守卫（阈值/代码集分裂会造成两处口径不一致）。"""

    def test_change_pct_threshold_aligned(self):
        self.assertEqual(mf.MAX_CHANGE_PCT, qs.MAX_CHANGE_PCT)

    def test_index_codes_aligned(self):
        self.assertEqual(tuple(mf.FALLBACK_INDEX_CODES), tuple(qs.DEFAULT_CODES))

    def test_source_status_vocabulary(self):
        self.assertEqual(mf.VALID_SOURCE_STATUS,
                         ("primary_westock", "fallback_public", "degraded"))


class TestRecordValidation(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(mf.record_is_valid({"price": 10.0, "change_percent": 3.2})[0])

    def test_change_percent_absent_is_valid(self):
        self.assertTrue(mf.record_is_valid({"price": 10.0})[0])

    def test_boundary_values_pass(self):
        self.assertTrue(mf.record_is_valid({"price": 10.0, "change_percent": 20.0})[0])
        self.assertTrue(mf.record_is_valid({"price": 10.0, "change_percent": -20.0})[0])

    def test_non_positive_price_rejected(self):
        for price in (0, -1.0, None, "abc", []):
            ok, why = mf.record_is_valid({"price": price, "change_percent": 1.0})
            self.assertFalse(ok, f"price={price!r} 应被判非法")
            self.assertIn("现价", why)

    def test_change_percent_out_of_range_rejected(self):
        for pct in (20.01, -20.01, 99.0):
            ok, why = mf.record_is_valid({"price": 10.0, "change_percent": pct})
            self.assertFalse(ok)
            self.assertIn("越界", why)

    def test_non_dict_rejected(self):
        ok, why = mf.record_is_valid(["price", 10])
        self.assertFalse(ok)
        self.assertIn("类型非法", why)


class TestMergeIndices(unittest.TestCase):
    def setUp(self):
        self.src = primary_doc()
        self.fb = fallback_doc()
        self.filled: list[str] = []
        self.doc, self.gaps = mf.merge_indices(self.src, self.fb, filled=self.filled)

    def test_primary_values_never_overwritten(self):
        row = self.doc["indices"]["sh000001"]
        self.assertEqual(row["price"], 3726.11)          # 备用源 9999.0 未写入
        self.assertEqual(row["change_percent"], 0.5)
        self.assertEqual(row["name"], "上证指数")         # 备用源 "(备用)" 未写入
        self.assertEqual(row["amount"], 1.2e11)
        self.assertNotIn("indices.sh000001.price", self.filled)

    def test_missing_row_is_created_from_fallback(self):
        row = self.doc["indices"]["sz399006"]
        self.assertEqual(row["price"], 2801.87)
        self.assertEqual(row["change_percent"], 0.67)
        self.assertEqual(row["name"], "创业板指")
        self.assertIn("indices.sz399006.price", self.filled)

    def test_none_fields_are_filled(self):
        row = self.doc["indices"]["sh000300"]
        self.assertEqual(row["price"], 4181.22)
        self.assertEqual(row["change_percent"], 0.37)
        self.assertEqual(row["name"], "沪深300")
        self.assertIn("indices.sh000300.price", self.filled)

    def test_dirty_record_dropped(self):
        self.assertEqual(self.doc["indices"]["sh000688"]["price"], 1400.0)  # -1.0 未写入
        self.assertTrue(any("indices.sh000688 备用源数据非法已丢弃" in g for g in self.gaps))
        self.assertFalse(any(f.startswith("indices.sh000688.") for f in self.filled))

    def test_empty_string_time_not_written(self):
        """源层时间戳不可解析时给空串（非 None）：空串不得写入，也不得冒充已补。"""
        base = {"price": 3726.11, "change_percent": 0.5}
        doc, gaps = merge_one(dict(base, time=""), dict(base, name="上证指数", time=""))
        self.assertEqual(doc["indices"]["sh000001"]["time"], "")
        self.assertTrue(any("indices.sh000001.time 缺失，备用源未提供" in g for g in gaps))

    def test_empty_string_in_primary_is_still_a_gap_to_fill(self):
        base = {"price": 3726.11, "change_percent": 0.5}
        doc, _ = merge_one(dict(base, time=""),
                           dict(base, name="上证指数", time="2026-10-16"))
        self.assertEqual(doc["indices"]["sh000001"]["time"], "2026-10-16")

    def test_none_amount_declared_as_gap(self):
        """腾讯 f35/f57 双缺时 amount 为 None：不填 0、只声明缺口。"""
        base = {"name": "科创50", "price": 1400.0, "change_percent": 1.1}
        doc, gaps = merge_one(dict(base), dict(base, amount=None, time="2026-10-16"),
                              code="sh000688")
        self.assertNotIn("amount", doc["indices"]["sh000688"])
        self.assertTrue(any("indices.sh000688.amount 缺失，备用源未提供" in g for g in gaps))

    def test_blank_name_not_written(self):
        base = {"price": 4181.22, "change_percent": 0.37}
        doc, _ = merge_one(dict(base), dict(base, name="   ", time="2026-10-16"),
                           code="sh000300")
        self.assertNotIn("name", doc["indices"]["sh000300"])

    def test_no_shape_drift(self):
        """源侧元数据（source/quote_time/volume/change）不注入 indices。"""
        for code, row in self.doc["indices"].items():
            for banned in ("source", "quote_time", "volume", "change"):
                self.assertNotIn(banned, row, f"{code} 不应出现 {banned}")

    def test_unfillable_fields_declared_as_gaps(self):
        for field in mf.UNFILLABLE_INDEX_FIELDS:
            self.assertTrue(any(f"indices.sz399001.{field} 缺失，备用源无法提供" in g
                                for g in self.gaps), f"{field} 未声明缺口")

    def test_out_of_coverage_code_declared(self):
        self.assertTrue(any("indices.bj899050 缺失，备用源无法填补" in g for g in self.gaps))
        self.assertNotIn("bj899050", self.doc["indices"])  # 不注入空壳条目

    def test_unfillable_sections_declared(self):
        doc, gaps = mf.merge_indices({"indices": {}}, {})
        for section in ("sector_flows", "market_breadth"):
            self.assertTrue(any(f"{section} 缺失，备用源无法提供" in g for g in gaps))
        self.assertEqual(doc["indices"], {})

    def test_no_empty_indices_block_injected(self):
        doc, _ = mf.merge_indices({"date": "2026-10-16"}, {})
        self.assertNotIn("indices", doc)

    def test_present_sections_not_reported(self):
        self.assertFalse(any("sector_flows" in g for g in self.gaps))
        self.assertFalse(any("market_breadth" in g for g in self.gaps))

    def test_input_not_mutated(self):
        snapshot = copy.deepcopy(self.src)
        mf.merge_indices(self.src, self.fb)
        self.assertEqual(self.src, snapshot)

    def test_idempotent(self):
        once, gaps1 = mf.merge_indices(self.src, self.fb)
        twice, gaps2 = mf.merge_indices(once, self.fb)
        self.assertEqual(once["indices"], twice["indices"])
        self.assertEqual(gaps1, gaps2)

    def test_empty_fallback_keeps_primary_intact(self):
        doc, gaps = mf.merge_indices(self.src, {})
        self.assertEqual(doc["indices"]["sh000001"], self.src["indices"]["sh000001"])
        self.assertEqual(doc["indices"]["sh000688"], self.src["indices"]["sh000688"])
        self.assertTrue(gaps)


class TestMergePositions(unittest.TestCase):
    def setUp(self):
        self.src = holdings_list()
        self.fb = fallback_positions()
        self.filled: list[str] = []
        self.out, self.gaps = mf.merge_positions(self.src, self.fb, filled=self.filled)

    def test_existing_price_not_overwritten(self):
        self.assertEqual(pick(self.out, "sh600919")["price"], 12.52)   # 备用源 99.0 未写入
        self.assertNotIn("holdings.sh600919.price", self.filled)

    def test_missing_price_filled(self):
        self.assertEqual(pick(self.out, "sz003816")["price"], 4.46)
        self.assertEqual(pick(self.out, "sh600863")["price"], 4.05)
        self.assertIn("holdings.sz003816.price", self.filled)

    def test_absent_code_declared(self):
        self.assertTrue(any("holdings.sz000429.price 缺失，备用源未返回" in g
                            for g in self.gaps))
        self.assertIsNone(pick(self.out, "sz000429")["price"])

    def test_dirty_position_dropped(self):
        self.assertIsNone(pick(self.out, "sh518600")["price"])         # 备用源 0.0 未写入
        self.assertTrue(any("holdings.sh518600 备用源数据非法已丢弃" in g for g in self.gaps))

    def test_code_missing_declared(self):
        self.assertTrue(any("缺 code/symbol/stock_code" in g for g in self.gaps))

    def test_input_not_mutated(self):
        snapshot = copy.deepcopy(self.src)
        mf.merge_positions(self.src, self.fb)
        self.assertEqual(self.src, snapshot)

    def test_idempotent(self):
        once, gaps1 = mf.merge_positions(self.src, self.fb)
        twice, gaps2 = mf.merge_positions(once, self.fb)
        self.assertEqual(once, twice)
        self.assertEqual(gaps1, gaps2)

    def test_dict_input_supported(self):
        """market_data['holdings'] 为 dict 形态时按键名补 code 后处理。"""
        out, gaps = mf.merge_positions({"sz003816": {"name": "中国广核", "price": None}},
                                       self.fb)
        self.assertEqual(out[0]["code"], "sz003816")
        self.assertEqual(out[0]["price"], 4.46)
        self.assertEqual(gaps, [])

    def test_bad_input_type(self):
        self.assertEqual(mf.merge_positions(None, self.fb), ([], []))

    def test_positions_to_mapping_keys_by_code(self):
        out, _ = mf.merge_positions(holdings_list(), self.fb)
        mapping = mf.positions_to_mapping(out)
        self.assertIsInstance(mapping, dict)
        self.assertEqual(mapping["sz003816"]["price"], 4.46)
        self.assertNotIn("缺代码标的", json.dumps(mapping, ensure_ascii=False))
        self.assertEqual(len(mapping), 5)  # 缺 code 的条目无法建键，已在 gaps 声明


class TestApplySourceMetadata(unittest.TestCase):
    def test_valid_statuses(self):
        for status in mf.VALID_SOURCE_STATUS:
            self.assertEqual(mf.apply_source_metadata({}, status, ["g1"])["data_source"],
                             status)

    def test_invalid_status_rejected(self):
        for bad in ("primary", "fallback", "", None, "PRIMARY_WESTOCK"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    mf.apply_source_metadata({}, bad, [])

    def test_gaps_merged_not_overwritten(self):
        doc = mf.apply_source_metadata({"data_gaps": ["westock-mcp 连接器未连接"]},
                                       mf.SOURCE_FALLBACK, ["板块资金流缺失"])
        self.assertEqual(doc["data_gaps"], ["westock-mcp 连接器未连接", "板块资金流缺失"])

    def test_gaps_deduplicated(self):
        doc = mf.apply_source_metadata({}, mf.SOURCE_FALLBACK, ["同一缺口", "同一缺口"])
        self.assertEqual(doc["data_gaps"], ["同一缺口"])

    def test_fallback_fields_recorded_and_cumulative(self):
        doc = mf.apply_source_metadata({}, mf.SOURCE_FALLBACK, [], filled=["indices.sz399006.price"])
        again = ["indices.sz399006.price", "holdings.sz003816.price"]
        doc = mf.apply_source_metadata(doc, mf.SOURCE_FALLBACK, [], filled=again)
        self.assertEqual(doc["fallback_fields"], again)

    def test_fields_empty_when_nothing_filled(self):
        doc = mf.apply_source_metadata({}, mf.SOURCE_PRIMARY, [])
        self.assertEqual(doc["fallback_fields"], [])

    def test_non_list_existing_gaps_survive_as_empty(self):
        doc = mf.apply_source_metadata({"data_gaps": "损坏值"}, mf.SOURCE_DEGRADED, ["g"])
        self.assertEqual(doc["data_gaps"], ["g"])

    def test_input_not_mutated(self):
        src = {"data_gaps": ["已有"]}
        mf.apply_source_metadata(src, mf.SOURCE_FALLBACK, ["新增"], filled=["f"])
        self.assertEqual(src, {"data_gaps": ["已有"]})

    def test_idempotent(self):
        once = mf.apply_source_metadata({"indices": {}}, mf.SOURCE_FALLBACK,
                                        ["缺口A"], filled=["indices.x.price"])
        twice = mf.apply_source_metadata(once, mf.SOURCE_FALLBACK,
                                         ["缺口A"], filled=["indices.x.price"])
        self.assertEqual(once, twice)


class TestMergeAll(unittest.TestCase):
    def test_end_to_end(self):
        doc, gaps = mf.merge_all(primary_doc(), fallback_doc(), holdings_list(),
                                 fallback_positions=fallback_positions())
        self.assertEqual(doc["data_source"], mf.SOURCE_FALLBACK)
        self.assertEqual(doc["indices"]["sz399006"]["price"], 2801.87)
        self.assertEqual(doc["indices"]["sh000001"]["price"], 3726.11)
        # schema 要求 holdings 为对象，merge_all 写回时按 code 建键
        self.assertIsInstance(doc["holdings"], dict)
        self.assertEqual(doc["holdings"]["sz003816"]["price"], 4.46)
        self.assertTrue(doc["fallback_fields"])
        self.assertTrue(doc["data_gaps"])
        self.assertTrue(all(isinstance(g, str) for g in gaps))

    def test_positions_default_to_same_fallback_source(self):
        """一次抓取同时含指数+个股时，fallback_positions 可省略，同源复用。"""
        combined = dict(fallback_doc())
        combined.update(fallback_positions())
        doc, _ = mf.merge_all(primary_doc(), combined, holdings_list())
        self.assertEqual(doc["holdings"]["sz003816"]["price"], 4.46)

    def test_holdings_untouched_when_not_provided(self):
        src = primary_doc()
        src["holdings"] = {"sh600919": {"name": "江苏银行", "price": 12.52}}
        doc, _ = mf.merge_all(src, fallback_doc())
        self.assertEqual(doc["holdings"], src["holdings"])

    def test_idempotent_two_passes(self):
        once, _ = mf.merge_all(primary_doc(), fallback_doc(), holdings_list(),
                               fallback_positions=fallback_positions())
        twice, _ = mf.merge_all(once, fallback_doc(), holdings_list(),
                                fallback_positions=fallback_positions())
        self.assertEqual(once, twice)

    def test_degraded_when_no_fallback_data(self):
        doc, gaps = mf.merge_all(primary_doc(), {}, holdings_list(),
                                 source_status=mf.SOURCE_DEGRADED)
        self.assertEqual(doc["data_source"], mf.SOURCE_DEGRADED)
        self.assertEqual(doc["fallback_fields"], [])
        self.assertTrue(gaps)


if __name__ == "__main__":
    unittest.main(verbosity=2)
