#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quote_sources.py — 行情源适配层（把腾讯/新浪的 GBK 方言转成统一契约记录）

**为什么单独一层**：两个源的字段口径互不相认，且不统一的地方只有同时对拍才能发现。
把它们关在本文件里，上层编排（fallback_fetcher.py）只认一个形状的记录，
脏方言不外溢。全部纯标准库，零第三方依赖。

## 两源口径差异（2026-10-16 双源实测，5 指数 + sh600000/sz000001 对拍）

腾讯 http://qt.gtimg.cn/q=<code,...>   GBK   v_<code>="<f0>~<f1>~..."
  f1=名称 f3=现价 f4=昨收 f5=今开 f30=时间(YYYYMMDDHHMMSS) f31=涨跌额 f32=涨跌幅%
  f35="现价/成交量/成交额"，第三段即成交额元（sh000001 实测 732475190866，精确值）
  f36=成交量，单位恒为「手」（sh600000 实测 922942 手 = 92294200 股）；f57=成交额万元
  注：派单给出的 36/37 映射与实测相反——f36 是手、f37 才是万元，本实现以实测为准。

新浪 http://hq.sinajs.cn/list=<code,...>   GBK   var hq_str_<code>="f0,f1,..."
  必须带 Referer: https://finance.sina.com.cn，缺失时返回空记录（不报错，静默为空）
  f0=名称 f1=今开 f2=昨收 f3=现价 f8=成交量 f9=成交额元 f30=日期 f31=时间
  无涨跌幅字段，须自算 (现价-昨收)/昨收*100
  成交量单位不统一：仅 sh000xxx 指数为「手」（与腾讯相等），其余全是「股」
  （sz000001 实测 111185079 = 腾讯 1111851 手的 100 倍）——本文件统一归一化为「手」。

bj899050（北证50）已实测两源均有数据，成交量同个股口径为「股」，按 sh000 之外的路径处理。

成交额两源单位均为元，无需换算。

## 出口契约（每条记录）
  {name, price, change_percent, change, amount, volume, time, quote_time, source}
  amount 单位元，volume 单位手，time 为 YYYY-MM-DD，quote_time 为源给的完整时点。

## 铁律
  脏数据绝不下线：现价<=0、|涨跌幅|>20%、缺名称/昨收的记录直接丢弃，原因回传为告警。
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

ENCODING = "gbk"
TIMEOUT = 5.0
MAX_CHANGE_PCT = 20.0
CB_THRESHOLD, CB_COOLDOWN_SEC = 3, 300.0
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
SINA_REFERER = "https://finance.sina.com.cn"
TENCENT_URL = "http://qt.gtimg.cn/q={codes}"
SINA_URL = "http://hq.sinajs.cn/list={codes}"
DEFAULT_CODES = ("sh000001", "sz399001", "sz399006", "sh000300", "sh000688")
HOLDING_CODES = (
    "sh600312", "sz000791", "sh563230", "sz159611", "sh600863",
    "sz000429", "sh600919", "sz003816", "sh518600",
)
CODE_RE = re.compile(r"^(sh|sz|bj)\d{6}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FetcherError(Exception):
    """本模块异常基类：参数错误与全部源失败都继承它，便于上层一次性兜住。"""


class SourceUnavailable(FetcherError):
    """单次抓取失败：网络/HTTP/超时/解码。"""


class AllSourcesFailed(FetcherError):
    """所有数据源均未返回任何可用记录。"""


def _num(raw) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


class CircuitBreaker:
    """连续失败 threshold 次即熔断，冷却 cooldown 秒后半开（放一次试探请求）。

    clock 可注入，单测用假时钟推进，不必真睡 300 秒。
    """

    def __init__(self, threshold: int = CB_THRESHOLD, cooldown: float = CB_COOLDOWN_SEC,
                 clock=time.monotonic):
        self.threshold = threshold
        self.cooldown = cooldown
        self._clock = clock
        self.consecutive_failures = 0
        self.opened_at = None

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if self._clock() - self.opened_at >= self.cooldown:
            self.opened_at, self.consecutive_failures = None, 0  # 冷却结束，转半开
            return False
        return True

    def allow(self) -> bool:
        return not self.is_open

    def remaining(self) -> float:
        return 0.0 if self.opened_at is None else max(
            self.cooldown - (self._clock() - self.opened_at), 0.0)

    def record_success(self) -> None:
        self.consecutive_failures, self.opened_at = 0, None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold and self.opened_at is None:
            self.opened_at = self._clock()


@dataclass
class Provider:
    """一个数据源：URL 模板、请求头、解析函数，以及它自己的熔断器。"""

    name: str
    url_tpl: str
    headers: dict
    parse: object  # Callable[[str, list[str]], tuple[dict[str, dict], list[str]]]
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    def fetch(self, codes: list[str], timeout: float = TIMEOUT) -> tuple[dict, list[str]]:
        raw = http_get(self.url_tpl.format(codes=",".join(codes)), self.headers, timeout)
        return self.parse(raw, codes)


def http_get(url: str, headers: dict, timeout: float = TIMEOUT) -> str:
    """GET 并按 GBK 解码。任何失败都转成 SourceUnavailable，不吞异常。"""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                    timeout=timeout) as resp:
            body = resp.read()
            status = getattr(resp, "status", None) or resp.getcode()
    except urllib.error.HTTPError as exc:
        raise SourceUnavailable(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SourceUnavailable(f"网络错误 {exc.reason}") from exc
    except TimeoutError as exc:
        raise SourceUnavailable(f"超时（>{timeout}s）") from exc
    except OSError as exc:
        raise SourceUnavailable(f"IO 错误 {exc}") from exc
    if status != 200:
        raise SourceUnavailable(f"HTTP {status}")
    if not body:
        raise SourceUnavailable("响应体为空")
    try:
        return body.decode(ENCODING)
    except UnicodeDecodeError as exc:
        raise SourceUnavailable(f"GBK 解码失败 {exc}") from exc


def _index_body(raw: str, prefix: str) -> dict[str, str]:
    """把 `v_sh000001="..."` / `var hq_str_sh000001="..."` 拆成 {code: 引号内正文}。"""
    table = {}
    for line in (raw or "").splitlines():
        if '="' not in line:
            continue
        key, _, body = line.partition('="')
        table[key.replace(prefix, "").strip()] = body.rstrip(";").rstrip('"')
    return table


def _build_record(code: str, source: str, name, price_raw, prev_raw,
                  pct_raw=None, chg_raw=None, amount_raw=None, volume=None,
                  quote: str = "") -> tuple[dict | None, str | None]:
    """把源生字段收敛成契约记录；校验不通过返回 (None, 丢弃原因)。"""
    price = _num(price_raw)
    if price is None or price <= 0:
        return None, f"{code}/{source}: 现价缺失或非正（{price_raw!r}）"
    prev, pct = _num(prev_raw), _num(pct_raw)
    if pct is not None and abs(pct) > MAX_CHANGE_PCT:
        return None, f"{code}/{source}: 涨跌幅越界 {pct}%（阈值 ±{MAX_CHANGE_PCT}%）"
    if pct is None:
        if prev is None or prev <= 0:
            return None, f"{code}/{source}: 缺昨收，无法推算涨跌幅（{prev_raw!r}）"
        pct = round((price - prev) / prev * 100, 4)
    chg = _num(chg_raw)
    if chg is None and prev is not None:
        chg = round(price - prev, 4)
    if not (name or "").strip():
        return None, f"{code}/{source}: 名称为空（源疑似未返回该代码）"
    return {"name": name.strip(), "price": price, "change_percent": pct, "change": chg,
            "amount": _num(amount_raw), "volume": volume, "time": quote[:10],
            "quote_time": quote, "source": source}, None


def parse_tencent(raw: str, codes: list[str]) -> tuple[dict[str, dict], list[str]]:
    """解析腾讯批量返回（多只用换行分隔）。返回 (code 到记录的映射, 告警)。"""
    out, warn = {}, []
    table = {k: v.split("~") for k, v in _index_body(raw, "v_").items()}
    for code in codes:
        f = table.get(code)
        if f is None:
            warn.append(f"腾讯未返回 {code}")
            continue
        if len(f) < 38:
            warn.append(f"腾讯 {code} 字段数异常（{len(f)} < 38），已丢弃")
            continue
        comp = f[35].split("/") if "/" in f[35] else []
        amount = _num(comp[2]) if len(comp) >= 3 else None
        if amount is None:
            wan = _num(f[57]) if len(f) > 57 else None
            amount = wan * 1e4 if wan else None
        if amount is None:
            warn.append(f"腾讯 {code} 成交额缺失，amount 置空")
        ts = f[30]
        quote = (f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}"
                 if len(ts) == 14 and ts.isdigit() else "")
        if not quote:
            warn.append(f"腾讯 {code} 时间字段不可解析（{ts!r}）")
        volume = _num(f[36])
        rec, err = _build_record(code, "tencent", f[1], f[3], f[4], f[32], f[31],
                                 amount, volume if volume is not None else _num(f[6]), quote)
        if rec is None:
            warn.append(err or f"腾讯 {code} 校验未通过")
        else:
            out[code] = rec
    return out, warn


def parse_sina(raw: str, codes: list[str]) -> tuple[dict[str, dict], list[str]]:
    """解析新浪批量返回。新浪无涨跌幅字段，由 (现价-昨收)/昨收 推算。"""
    out, warn = {}, []
    table = {k: v.split(",") for k, v in _index_body(raw, "var hq_str_").items()}
    for code in codes:
        f = table.get(code)
        if f is None:
            warn.append(f"新浪未返回 {code}")
            continue
        if len(f) < 32 or not f[0].strip():
            warn.append(f"新浪 {code} 返回空记录（多为缺 Referer 或代码不存在），已丢弃")
            continue
        volume = _num(f[8])
        if volume is not None and not code.startswith("sh000"):
            volume /= 100.0  # 新浪 sz 指数与个股口径为「股」，归一化为「手」
        date, clock = f[30].strip(), f[31].strip()
        quote = f"{date} {clock}" if DATE_RE.match(date) and len(clock) >= 8 else date
        rec, err = _build_record(code, "sina", f[0], f[3], f[2], None, None,
                                 _num(f[9]), volume, quote)
        if rec is None:
            warn.append(err or f"新浪 {code} 校验未通过")
        else:
            out[code] = rec
    return out, warn


def default_providers() -> list[Provider]:
    """主备顺序：腾讯优先，新浪备选。"""
    return [Provider("tencent", TENCENT_URL, {"User-Agent": UA}, parse_tencent),
            Provider("sina", SINA_URL,
                     {"User-Agent": UA, "Referer": SINA_REFERER}, parse_sina)]
