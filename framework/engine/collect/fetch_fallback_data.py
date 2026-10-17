#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_fallback_data.py — 备用源自动抓取与合并编排器（Phase B 核心集成门面）

职责：
  连接 primary_health（健康体检）+ fallback_fetcher（多源抓取）+ merge_fallback（数据合入）。
  提供单一入口 `ensure_market_data(market_data, holdings=None, force=False)`：
  1. 判定主源数据是否真实缺失（默认 include_connector_gaps=False，数据完整不白跑网络）；
  2. 需要时调 fallback_fetcher 一次性批量抓取指数与持仓标的；
  3. 调 merge_all 遵循「主源优先、缺失才补、脏值丢弃、缺口声明」四大铁律合入；
  4. 将抓取失败的 missing 代码贯通写入 data_gaps（防静默降级）。
"""
from __future__ import annotations

import copy
import logging
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import fallback_fetcher as FF
import merge_fallback as MF
import primary_health as PH
from quote_sources import DEFAULT_CODES, HOLDING_CODES

LOG = logging.getLogger("fetch_fallback_data")


def ensure_market_data(
    market_data: dict,
    holdings: list[dict] | dict[str, dict] | None = None,
    codes: list[str] | None = None,
    holding_codes: list[str] | None = None,
    force: bool = False,
    include_connector_gaps: bool = False,
    fetch_fn=None,
) -> tuple[dict, list[str]]:
    """确保市场数据的完整性。若主源缺失或不健康，自动从备用源抓取并合入。

    Args:
        market_data: 当前市场数据字典。
        holdings: 持仓列表或字典（可选）。
        codes: 需要确保的指数代码（默认取 DEFAULT_CODES + bj899050）。
        holding_codes: 需要确保的持仓代码（默认取 HOLDING_CODES）。
        force: 是否强制执行备用源抓取（即使主源看起来完整）。
        include_connector_gaps: 是否因 data_gaps 含有连接器字样而触发抓取（默认 False）。
        fetch_fn: 可注入的抓取函数（测试用，签名同 fallback_fetcher.fetch_indices_detail）。

    Returns:
        (updated_market_data, gaps_list)
    """
    doc = copy.deepcopy(market_data if isinstance(market_data, dict) else {})
    gaps: list[str] = []

    # 1. 主源健康度判定
    degraded = force or PH.is_primary_degraded(doc, include_connector_gaps=include_connector_gaps)
    if not degraded:
        return doc, []

    reasons = PH.degradation_reasons(doc, include_connector_gaps=include_connector_gaps)
    LOG.info("主源判定降级，原因: %s", "; ".join(reasons))

    # 2. 准备抓取目标清单
    target_indices = list(codes or (list(DEFAULT_CODES) + ["bj899050"]))
    target_holdings = list(holding_codes or HOLDING_CODES)
    all_targets = list(dict.fromkeys(target_indices + target_holdings))

    fetcher = fetch_fn or FF.fetch_indices_detail
    try:
        res = fetcher(all_targets)
    except Exception as exc:
        LOG.error("备用源抓取全部失败: %s", exc)
        res = FF.FetchResult(data={}, sources=[], warnings=[f"备用源网络异常: {exc}"], missing=all_targets)

    # 3. 分离指数与持仓结果
    fallback_indices = {c: res.data[c] for c in target_indices if c in res.data}
    fallback_positions = {c: res.data[c] for c in target_holdings if c in res.data}

    # 4. 执行数据合并
    source_status = "fallback_public" if res.data else "degraded"
    merged_doc, merge_gaps = MF.merge_all(
        market_data=doc,
        fallback=fallback_indices,
        holdings=holdings,
        fallback_positions=fallback_positions,
        source_status=source_status,
    )
    gaps.extend(merge_gaps)

    # 5. missing 代码贯通：抓取未成功的代码显式声明为 data_gaps，防静默丢失
    for m in res.missing:
        miss_gap = f"代码 {m} 备用源未能取得有效数据（missing）"
        if miss_gap not in merged_doc.get("data_gaps", []):
            merged_doc.setdefault("data_gaps", []).append(miss_gap)
        if miss_gap not in gaps:
            gaps.append(miss_gap)

    return merged_doc, gaps
