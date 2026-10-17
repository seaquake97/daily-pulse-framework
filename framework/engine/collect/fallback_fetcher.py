#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fallback_fetcher.py — 多源行情编排层（主备降级 + 熔断 + CLI）

## 为什么需要它
主数据源不可达时，采集层此前没有兜底：要么拿到空快照，要么把上一交易日的旧值当今天用。
本模块把「取不到数据」变成可观测事件（降级记录 + 告警 + 退出码），而不是静默污染下游。

源适配（腾讯/新浪 GBK 方言解析、字段错位证据）在 quote_sources.py，本文件只做编排。

## 降级策略
  优先腾讯；腾讯失败或处于熔断冷却则自动切新浪；只有仍缺失的代码才会走到下一个源。
  每个源独立计数：连续失败 3 次即熔断，冷却 300 秒后半开放一次试探请求。

## 铁律
  全部源失败必须抛 AllSourcesFailed（退出码 2），绝不返回空 dict 假装成功。

用法
    python3 fallback_fetcher.py --json
    python3 fallback_fetcher.py --code sh000001
    python3 fallback_fetcher.py --codes sh000001,sh000688

退出码：0 成功｜2 全部数据源失败｜3 参数错误
部分缺失（个别代码两源都取不到）仍返回 0，消费方必须自行检查输出里的 missing 字段。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from quote_sources import (  # noqa: E402  （与 collect 层既有导入约定一致）
    CODE_RE, DEFAULT_CODES, HOLDING_CODES, TIMEOUT, AllSourcesFailed, CircuitBreaker, FetcherError,
    Provider, SourceUnavailable, default_providers, http_get, parse_sina, parse_tencent,
)

__all__ = ["AllSourcesFailed", "CircuitBreaker", "FetchResult", "FetcherError",
           "HOLDING_CODES", "Provider", "SourceUnavailable", "fetch_batch",
           "fetch_holdings", "fetch_indices", "fetch_indices_detail",
           "fetch_single", "main", "parse_sina", "parse_tencent"]

LOG = logging.getLogger("fallback_fetcher")


@dataclass
class FetchResult:
    """一次抓取的完整证据：数据 + 实际用到哪些源 + 降告警 + 缺失代码。"""

    data: dict[str, dict]
    sources: list[str]
    warnings: list[str]
    missing: list[str]

    @property
    def ok(self) -> bool:
        return bool(self.data)


def fetch_indices_detail(codes: list[str], providers: list[Provider] | None = None,
                         timeout: float = TIMEOUT) -> FetchResult:
    """按主备顺序抓取并逐源降级，返回含降级证据的 FetchResult。"""
    if not codes:
        raise ValueError("codes 不能为空")
    bad = [c for c in codes if not CODE_RE.match(c)]
    if bad:
        raise ValueError(f"代码格式非法（须 sh/sz/bj + 6 位数字）：{', '.join(bad)}")
    data, sources, warnings, todo = {}, [], [], list(codes)
    for p in providers if providers is not None else default_providers():
        if not todo:
            break
        if not p.breaker.allow():
            warnings.append(f"{p.name} 处于熔断冷却（剩余 {p.breaker.remaining():.0f}s），已跳过")
            LOG.warning("%s 熔断中，剩余 %.0fs", p.name, p.breaker.remaining())
            continue
        try:
            parsed, pw = p.fetch(todo, timeout)
        except SourceUnavailable as exc:
            p.breaker.record_failure()
            warnings.append(
                f"{p.name} 抓取失败：{exc}（连续失败 {p.breaker.consecutive_failures} 次）")
            LOG.warning("%s 抓取失败：%s", p.name, exc)
            continue
        p.breaker.record_success()
        warnings.extend(pw)
        for msg in pw:
            LOG.warning("%s", msg)
        if parsed:
            sources.append(p.name)
            data.update(parsed)
            todo = [c for c in todo if c not in parsed]
    if todo:
        warnings.append(f"全部源均未返回有效数据：{', '.join(todo)}")
        LOG.warning("缺失代码：%s", ", ".join(todo))
    return FetchResult(data, sources, warnings, todo)


def fetch_indices(codes: list[str]) -> dict[str, dict]:
    """抓取指数列表，返回 {code: {name, price, change_percent, change, amount, volume, time, source}}。"""
    res = fetch_indices_detail(list(codes))
    if not res.data:
        raise AllSourcesFailed("；".join(res.warnings) or "无可用数据")
    return res.data


def fetch_batch(codes: list[str]) -> dict[str, dict]:
    """批量抓取（指数与个股通用）。内部合并为单次 HTTP 请求。"""
    return fetch_indices(codes)


def fetch_holdings(codes: list[str] | None = None) -> dict[str, dict]:
    """抓取持仓标的行情（默认抓取 HOLDING_CODES 9 只核心标的）。"""
    target = list(codes or HOLDING_CODES)
    return fetch_indices(target)


def fetch_single(code: str, timeout: float = TIMEOUT) -> dict:
    """抓取单只标的（指数或个股通用）。取不到就抛，不返回空壳。"""
    if not CODE_RE.match(code or ""):
        raise ValueError(f"代码格式非法（须 sh/sz/bj + 6 位数字）：{code!r}")
    res = fetch_indices_detail([code], timeout=timeout)
    if not res.data:
        raise AllSourcesFailed("；".join(res.warnings) or f"{code} 无可用数据")
    return res.data[code]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fallback_fetcher",
                                 description="多源行情备援抓取（腾讯主 / 新浪备）")
    ap.add_argument("--json", action="store_true", help="输出全部默认指数的 JSON")
    ap.add_argument("--code", help="抓取单只代码，如 sh000001")
    ap.add_argument("--codes", help="逗号分隔代码列表，覆盖默认指数集")
    ap.add_argument("--timeout", type=float, default=TIMEOUT,
                    help=f"单次请求超时秒（默认 {TIMEOUT}）")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s",
                        stream=sys.stderr)
    if args.code and (args.json or args.codes):
        print("[参数错误] --code 不能与 --json/--codes 同时使用", file=sys.stderr)
        return 3
    if not (args.code or args.json or args.codes):
        print("[参数错误] 需指定 --json / --code / --codes 之一", file=sys.stderr)
        return 3
    if not 0 < args.timeout <= 30:
        print(f"[参数错误] --timeout 须落在 (0, 30] 秒，当前 {args.timeout}", file=sys.stderr)
        return 3
    try:
        if args.code:
            row = fetch_single(args.code, timeout=args.timeout)
            print(json.dumps({"ok": True, "code": args.code, "data": row},
                             ensure_ascii=False, indent=2))
            return 0
        codes = ([c.strip() for c in args.codes.split(",") if c.strip()]
                 if args.codes else list(DEFAULT_CODES))
        res = fetch_indices_detail(codes, timeout=args.timeout)
    except ValueError as exc:
        print(f"[参数错误] {exc}", file=sys.stderr)
        return 3
    except AllSourcesFailed as exc:
        print(f"[抓取失败] {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": res.ok, "count": len(res.data), "sources": res.sources,
                      "missing": res.missing, "warnings": res.warnings, "data": res.data},
                     ensure_ascii=False, indent=2))
    return 0 if res.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
