#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_fallback_fetcher.py — 备援抓取器回归（默认全离线，CI 可跑）

守护四类真实风险（都是双源对拍时踩到的）：
  ① 字段错位：腾讯 f36/f37 与派单相反；新浪成交量单位随前缀变（100 倍坑）
  ② 脏数据上线：现价<=0、涨跌幅越界、源返回空记录必须丢弃并留告警
  ③ 静默兜底：全部源失败必须抛 AllSourcesFailed，不许返回空 dict 冒充成功
  ④ 熔断失效：连续失败 3 次后冷却期内必须直接拒访，而不是每个请求硬等超时

默认不联网：解析喂构造的 GBK 字节串，编排用 mock 替换 http_get；真实网络用例由
skipUnless(PULSE_NET_TEST=1) 守卫。运行：python3 test_fallback_fetcher.py（加环境变量跑联网）
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import quote_sources as QS  # noqa: E402
from fallback_fetcher import (  # noqa: E402
    AllSourcesFailed, FetchResult, fetch_indices, fetch_indices_detail, fetch_single, main)
from quote_sources import (  # noqa: E402
    CircuitBreaker, SourceUnavailable, parse_sina, parse_tencent)

FETCHER = HERE / "fallback_fetcher.py"

# 2026-10-16 真实抓到的 sh000001 原始串（线上为 GBK 字节流，用例走 encode/decode 复现）：源改版这里最先炸
REAL_TENCENT = (
    'v_sh000001="1~上证指数~000001~3716.28~3707.48~3723.80~472632158~0~0~0.00~0~0.00~0~0.00~0~'
    '0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~~20261016161500~8.80~0.24~3750.77~3681.28~'
    '3716.28/472632158/732475190866~472632158~73247519~0.97~16.16~~3750.77~3681.28~1.87~'
    '582443.77~652011.73~0.00~-1~-1~0.97~0";')
REAL_SINA = (
    'var hq_str_sh000001="上证指数,3723.7972,3707.4760,3716.2842,3750.7703,3681.2830,0,0,'
    '472632158,732475190866,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-10-16,15:35:27,00,";')


def tx_line(code="sh000001", name="上证指数", price="3716.28", prev="3707.48",
            open_="3723.80", vol="472632158", ts="20261016161500", chg="8.80", pct="0.24",
            comp="3716.28/472632158/732475190866", f57="73247519.0866"):
    """按腾讯真实布局拼一行（合成串只喂异常分支；基准用例用 REAL_TENCENT）。"""
    f = (["1", name, code[2:], price, prev, open_, vol]            # f0..f6
         + ["0", "0"] + ["0.00", "0"] * 10 + [""]                 # f7..f29
         + [ts, chg, pct, "3750.77", "3681.28", comp, vol, "73247519", "0.97", "16.16", ""]
         + ["3750.77", "3681.28", "1.87", "582443.77", "652011.73", "0.00", "-1", "-1",
            "0.97", "0"]                                          # f41..f50
         + [""] * 6 + [f57])                                      # f57 为成交额万元
    return f'v_{code}="' + "~".join(f) + '";'


def sina_line(code="sh000001", name="上证指数", open_="3723.7972", prev="3707.4760",
              price="3716.2842", vol="472632158", amt="732475190866",
              date="2026-10-16", clock="15:35:27"):
    """按新浪真实布局拼一行。"""
    f = ([name, open_, prev, price, "3750.7703", "3681.2830", "0", "0", vol, amt]
         + ["0"] * 20 + [date, clock, "00", ""])
    return f'var hq_str_{code}="' + ",".join(f) + '";'


class TencentParseTest(unittest.TestCase):
    """腾讯方言解析（含 GBK 解码链路）与脏数据拦截。"""

    def test_real_sample_full_record(self):
        rec, warn = parse_tencent(REAL_TENCENT.encode("gbk").decode("gbk"), ["sh000001"])
        self.assertEqual(warn, [])
        self.assertEqual(rec["sh000001"], {
            "name": "上证指数", "price": 3716.28, "change_percent": 0.24, "change": 8.8,
            "amount": 732475190866.0,      # f35 第三段，单位元
            "volume": 472632158.0,         # f36，单位手
            "time": "2026-10-16", "quote_time": "2026-10-16 16:15:00", "source": "tencent"})

    def test_anti_factual_price_actually_read(self):
        # 改价格则结果必须跟着变，证明断言不是恒真
        alt = REAL_TENCENT.replace("~3716.28~", "~3800.00~")
        self.assertEqual(parse_tencent(alt, ["sh000001"])[0]["sh000001"]["price"], 3800.0)

    def test_batch_multiple_lines_and_missing_code(self):
        raw = "\n".join([tx_line(), tx_line("sz399006", "创业板指", "2772.38", "2783.17",
                                           vol="166968940")])
        rec, warn = parse_tencent(raw, ["sh000001", "sz399006"])
        self.assertEqual(warn, [])
        self.assertEqual(rec["sz399006"]["name"], "创业板指")
        # 请求了但源没返回的代码必须告警，不能静默消失
        rec2, warn2 = parse_tencent(raw, ["sh000001", "sz399001"])
        self.assertNotIn("sz399001", rec2)
        self.assertTrue(any("腾讯未返回 sz399001" in w for w in warn2))

    def test_amount_falls_back_to_f57_when_comp_missing(self):
        rec = parse_tencent(tx_line(comp="无复合串"), ["sh000001"])[0]
        self.assertEqual(rec["sh000001"]["amount"], 732475190866.0)

    def test_dirty_records_dropped_with_reason(self):
        """空记录 / 非正价 / 涨跌幅越界：都不许上线，且必须说清为什么。"""
        cases = [
            ('v_sh000001="";', "字段数异常"),
            (tx_line(price="0.00"), "现价缺失或非正"),
            (tx_line(pct="30.5"), "涨跌幅越界"),
        ]
        for raw, keyword in cases:
            with self.subTest(keyword=keyword):
                rec, warn = parse_tencent(raw, ["sh000001"])
                self.assertEqual(rec, {})
                self.assertTrue(any(keyword in w for w in warn), warn)

    def test_unparsable_timestamp_warned(self):
        rec, warn = parse_tencent(tx_line(ts="未知"), ["sh000001"])
        self.assertTrue(any("时间字段不可解析" in w for w in warn))
        self.assertEqual(rec["sh000001"]["quote_time"], "")


class SinaParseTest(unittest.TestCase):
    """新浪方言解析：涨跌幅须自算，成交量单位随市场前缀变。"""

    def test_real_sample_change_percent_computed(self):
        r = parse_sina(REAL_SINA.encode("gbk").decode("gbk"), ["sh000001"])[0]["sh000001"]
        self.assertEqual(r["price"], 3716.2842)
        self.assertEqual(r["change"], round(3716.2842 - 3707.4760, 4))
        self.assertAlmostEqual(r["change_percent"],
                               (3716.2842 - 3707.4760) / 3707.4760 * 100, places=4)
        self.assertEqual((r["amount"], r["source"]), (732475190866.0, "sina"))

    def test_volume_unit_normalization(self):
        """仅 sh000xxx 指数在新浪是「手」，其余全是「股」（相差 100 倍）。"""
        cases = [
            (sina_line(), "sh000001", 472632158.0),                      # 沪指：原样
            (sina_line("sz399006", vol="16696894025"), "sz399006", 166968940.25),
            (sina_line("sz000001", vol="111185079"), "sz000001", 1111850.79),
            (sina_line("bj899050", vol="719091949"), "bj899050", 7190919.49),
        ]
        for raw, code, expect in cases:
            with self.subTest(code=code):
                self.assertEqual(parse_sina(raw, [code])[0][code]["volume"], expect)

    def test_dirty_records_dropped(self):
        cases = [('var hq_str_sh000001="";', "空记录"), (sina_line(prev=""), "昨收")]
        for raw, keyword in cases:
            with self.subTest(keyword=keyword):
                rec, warn = parse_sina(raw, ["sh000001"])
                self.assertEqual(rec, {})
                self.assertTrue(any(keyword in w for w in warn), warn)


class CircuitBreakerTest(unittest.TestCase):
    """熔断：连续失败 3 次进冷却，冷却期内拒访，到点半开。"""

    def setUp(self):
        self.now, self.cb = [1000.0], CircuitBreaker(clock=lambda: self.now[0])

    def _fail(self, times):
        for _ in range(times):
            self.cb.record_failure()

    def test_opens_only_at_threshold(self):
        self._fail(2)
        self.assertTrue(self.cb.allow(), "未到阈值不应熔断")
        self._fail(1)
        self.assertFalse(self.cb.allow(), "连续失败 3 次必须熔断")
        self.assertEqual(self.cb.consecutive_failures, 3)

    def test_cooldown_window_then_half_open(self):
        self._fail(3)
        self.now[0] += 299.0
        self.assertFalse(self.cb.allow(), "冷却未满 300s 仍应拒绝")
        self.assertAlmostEqual(self.cb.remaining(), 1.0, places=3)
        self.now[0] += 2.0
        self.assertTrue(self.cb.allow(), "冷却结束应半开放行")
        self.assertEqual(self.cb.consecutive_failures, 0, "半开时计数复位")

    def test_success_resets_counter(self):
        self._fail(2)
        self.cb.record_success()
        self.assertEqual(self.cb.consecutive_failures, 0)
        self.assertTrue(self.cb.allow())


class DegradeTest(unittest.TestCase):
    """主备降级编排（http_get 用 mock 替换，不联网）。"""

    def test_primary_failure_falls_back_to_sina(self):
        with mock.patch.object(QS, "http_get",
                               side_effect=[SourceUnavailable("HTTP 503"), REAL_SINA]):
            res = fetch_indices_detail(["sh000001"], QS.default_providers())
        self.assertEqual(res.sources, ["sina"], "主源失败必须自动落到备源")
        self.assertEqual(res.data["sh000001"]["source"], "sina")
        self.assertTrue(any("tencent 抓取失败" in w for w in res.warnings))

    def test_all_sources_failed_raises(self):
        with mock.patch.object(QS, "http_get", side_effect=SourceUnavailable("超时（>5s）")):
            with self.assertRaises(AllSourcesFailed):
                fetch_indices(["sh000001"])
        with mock.patch.object(QS, "http_get", side_effect=SourceUnavailable("HTTP 500")):
            with self.assertRaises(AllSourcesFailed):
                fetch_single("sh000001")

    def test_open_breaker_skips_primary(self):
        ps = QS.default_providers()
        for _ in range(3):
            ps[0].breaker.record_failure()
        with mock.patch.object(QS, "http_get", return_value=REAL_SINA):
            res = fetch_indices_detail(["sh000001"], ps)
        self.assertTrue(any("熔断冷却" in w for w in res.warnings))
        self.assertEqual(res.sources, ["sina"])

    def test_partial_missing_is_reported_not_hidden(self):
        with mock.patch.object(QS, "http_get", side_effect=[tx_line(), REAL_SINA]):
            res = fetch_indices_detail(["sh000001", "sz399001"], QS.default_providers())
        self.assertEqual(res.missing, ["sz399001"])
        self.assertTrue(any("全部源均未返回有效数据" in w for w in res.warnings))

    def test_fetch_indices_contract_shape(self):
        with mock.patch.object(QS, "http_get", return_value=REAL_TENCENT):
            data = fetch_indices(["sh000001"])
        self.assertEqual(set(data["sh000001"]),
                         {"name", "price", "change_percent", "change", "amount",
                          "volume", "time", "quote_time", "source"})

    def test_argument_validation_and_ok_flag(self):
        with self.assertRaises(ValueError):
            fetch_indices_detail(["123456"])
        with self.assertRaises(ValueError):
            fetch_indices_detail([])
        with self.assertRaises(ValueError):
            fetch_single("SH000001")
        self.assertFalse(FetchResult({}, [], [], ["sh000001"]).ok)
        self.assertTrue(FetchResult({"sh000001": {}}, ["tencent"], [], []).ok)


class CliTest(unittest.TestCase):
    """CLI 退出码（全部离线：成功/失败分支都用 mock 喂数据）。"""

    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_bad_arguments_exit_3(self):
        cases = [["--code", "sh000001", "--json"], [], ["--json", "--timeout", "0"],
                 ["--json", "--codes", "NOPE"]]
        for argv in cases:
            with self.subTest(argv=argv):
                self.assertEqual(self._run(argv)[0], 3)

    def test_subprocess_bad_args_exit_3(self):
        proc = subprocess.run([sys.executable, str(FETCHER), "--json", "--code", "sh000001"],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 3)
        self.assertIn("参数错误", proc.stderr)

    def test_single_code_output_is_json(self):
        with mock.patch.object(QS, "http_get", return_value=REAL_TENCENT):
            code, out = self._run(["--code", "sh000001"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["name"], "上证指数")

    def test_all_sources_failed_exit_2(self):
        with mock.patch.object(QS, "http_get", side_effect=SourceUnavailable("HTTP 503")):
            code, out = self._run(["--json"])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["ok"])


@unittest.skipUnless(os.environ.get("PULSE_NET_TEST") == "1",
                     "联网用例：需设 PULSE_NET_TEST=1 才执行")
class LiveNetworkTest(unittest.TestCase):
    """真实网络冒烟（默认跳过）。"""

    def test_default_indices_live(self):
        res = fetch_indices_detail(list(QS.DEFAULT_CODES))
        self.assertTrue(res.ok, f"全部源失败：{res.warnings}")
        self.assertEqual(res.missing, [], f"存在缺失：{res.warnings}")
        for code, row in res.data.items():
            with self.subTest(code=code):
                self.assertGreater(row["price"], 0)
                self.assertLessEqual(abs(row["change_percent"]), 20.0)
                self.assertGreater(row["amount"], 0)
                self.assertRegex(row["time"], r"^\d{4}-\d{2}-\d{2}$")

    def test_single_stock_live(self):
        """个股兜底路径：新浪/腾讯个股成交量均为「股」源，须归一化为手。"""
        row = fetch_single("sh600000")
        self.assertEqual(row["name"], "浦发银行")
        self.assertGreater(row["volume"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
