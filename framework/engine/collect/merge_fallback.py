#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_fallback.py — 备用源数据合并器（Phase B）

## 为什么需要它
备用源（fallback_fetcher.py）只能拿到指数与个股的**基础行情**（现价/涨跌/成交额/时间），
拿不到资金流、涨跌家数、PE/PB、量比、多日涨跌幅。它进 market_data 之前必须有一个
确定性合并器决定「哪些能补、哪些只能声明缺口」——否则会出现两类静默事故：
  ① 备用源把主源已采集到的值覆盖掉（主源口径被污染，且无任何报错）；
  ② 拿不到的字段被填 0 或估算（本项目 P0，见 C-4 契约：补零会让站点把「没数据」显示成「评分为零」）。

## 铁律（违反即事故）
  1. **主源绝对优先**：主源已有值（即使看起来是旧值）一律保留，备用源只补主源缺失的字段。
  2. **缺失才填补**：主源缺 code 或字段为 None 时才用备用源填；绝不覆盖、绝不虚构。
  3. **脏值即丢弃**：price <= 0 或 |change_percent| > 20 的记录整条丢弃并计入 gaps，绝不写入；
     空串/纯空白字符串等同缺失（源层时间戳不可解析时给的是空串），不写入、不冒充已补。
  4. **拿不到就声明**：备用源也提供不了的字段只写 data_gaps，字段留缺失，绝不填 0。
  5. **不改入参**：所有函数返回深拷贝后的新对象，调用方原对象零副作用。

## 输出契约（字段名不可改）
  market_data["data_source"]    = "primary_westock" | "fallback_public" | "degraded"
  market_data["data_gaps"]      = 缺口字符串列表（已有则合并去重，不覆盖）
  market_data["fallback_fields"] = 由备用源填补的字段名（点分路径，累计去重以保证幂等）

## 与 L-4 门禁的分工
本模块只负责**如实写入** data_gaps；「data_gaps 非空时禁止输出可执行动作」由
content_contract.py / check_report.py 判定，本模块不做任何动作门禁。
"""
from __future__ import annotations

import copy

# --- 常量（单一数据源） ---
MAX_CHANGE_PCT = 20.0           # 与 quote_sources.MAX_CHANGE_PCT 一致（test 内有漂移守卫）

SOURCE_PRIMARY = "primary_westock"
SOURCE_FALLBACK = "fallback_public"
SOURCE_DEGRADED = "degraded"
VALID_SOURCE_STATUS = (SOURCE_PRIMARY, SOURCE_FALLBACK, SOURCE_DEGRADED)

# 备用源覆盖范围（与 quote_sources.DEFAULT_CODES 对齐，test 内有漂移守卫）
FALLBACK_INDEX_CODES = ("sh000001", "sz399001", "sz399006", "sh000300", "sh000688")
# market_data 全景需要、但备用源覆盖不到 bj899050 —— 主源缺失时必须声明缺口
REQUIRED_INDEX_CODES = FALLBACK_INDEX_CODES + ("bj899050",)

# 允许从备用源注入的字段：仅 market_data 真正消费的字段。
# change / volume / quote_time / source 属源侧元数据，不注入，避免 market_data 形状漂移。
MERGEABLE_FIELDS = ("name", "price", "change_percent", "amount", "time")
# 备用源永远拿不到、只能声明缺口的字段
UNFILLABLE_INDEX_FIELDS = ("pe_ratio", "volume_ratio", "chg_5d", "chg_10d",
                           "chg_20d", "chg_60d", "chg_ytd")
# 备用源永远拿不到的顶层区块（只报每份快照都应有的两块，避免把任务态字段误报成缺口）
UNFILLABLE_SECTIONS = ("sector_flows", "market_breadth")

POSITION_CODE_KEYS = ("code", "symbol", "stock_code")

__all__ = ["MAX_CHANGE_PCT", "MERGEABLE_FIELDS", "UNFILLABLE_INDEX_FIELDS",
           "UNFILLABLE_SECTIONS", "VALID_SOURCE_STATUS", "apply_source_metadata",
           "merge_all", "merge_indices", "merge_positions", "positions_to_mapping",
           "record_is_valid"]


def _num(value):
    """转 float；None / 非数值 → None（不抛、不猜）。"""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _usable(value) -> bool:
    """值能否用于填补：None 与空串/纯空白字符串均视为缺失。

    源层事实（quote_sources）：时间戳不可解析时 time/quote_time 为**空串而非 None**，
    腾讯 f35/f57 双缺时 amount 为 None。空串若当有效值写入，等于用空值冒充「已补上」。
    """
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _append_unique(target: list, item: str) -> None:
    if item not in target:
        target.append(item)


def record_is_valid(rec) -> tuple[bool, str]:
    """备用源单条记录合法性：price > 0 且 |change_percent| <= MAX_CHANGE_PCT。

    返回 (是否可用, 不可用原因)。change_percent 缺失视为可用（只补现价的场景合法）。
    """
    if not isinstance(rec, dict):
        return False, f"记录类型非法（{type(rec).__name__}）"
    price = _num(rec.get("price"))
    if price is None or price <= 0:
        return False, f"现价缺失或非正（{rec.get('price')!r}）"
    pct = _num(rec.get("change_percent"))
    if pct is not None and abs(pct) > MAX_CHANGE_PCT:
        return False, f"涨跌幅越界 {pct}%（阈值 ±{MAX_CHANGE_PCT}%）"
    return True, ""


def merge_indices(market_data: dict, fallback: dict, filled: list | None = None):
    """用备用源填补 market_data["indices"] 的主源缺口。

    Args:
        market_data: 主源快照（不被修改）
        fallback: {code: {name, price, change_percent, ...}}，来自 fallback_fetcher
        filled: 可选收集器，累计本次填补的字段（点分路径，供 fallback_fields 使用）

    Returns:
        (新 market_data, fallback_gaps)
    """
    doc = copy.deepcopy(market_data if isinstance(market_data, dict) else {})
    block = doc.get("indices") if isinstance(doc.get("indices"), dict) else None
    fb = fallback if isinstance(fallback, dict) else {}
    gaps: list[str] = []

    codes = sorted(set(block or {}) | set(fb) | set(REQUIRED_INDEX_CODES))
    for code in codes:
        row = (block or {}).get(code)
        row = row if isinstance(row, dict) else None
        rec = fb.get(code)

        usable, why = False, "备用源未返回该代码"
        if rec is not None:
            usable, why = record_is_valid(rec)
            if not usable:
                gaps.append(f"indices.{code} 备用源数据非法已丢弃（{why}）")

        target = dict(row) if row is not None else {}
        for field in MERGEABLE_FIELDS:
            if row is not None and _usable(row.get(field)):
                continue                      # 主源优先：已有值一律不覆盖
            if not usable:
                continue
            value = rec.get(field) if isinstance(rec, dict) else None
            if not _usable(value):
                continue                      # 空串/空白等同缺失，绝不写入空值冒充已补
            target[field] = value
            if filled is not None:
                _append_unique(filled, f"indices.{code}.{field}")

        if row is None and not target:
            gaps.append(f"indices.{code} 缺失，备用源无法填补（{why}）")
            continue

        for field in MERGEABLE_FIELDS:
            if not _usable(target.get(field)):
                gaps.append(f"indices.{code}.{field} 缺失，备用源未提供")
        for field in UNFILLABLE_INDEX_FIELDS:
            if target.get(field) is None:
                gaps.append(f"indices.{code}.{field} 缺失，备用源无法提供")
        if block is None:                      # 懒创建：无内容可写时不凭空塞空 indices 区块
            block = {}
            doc["indices"] = block
        block[code] = target

    for section in UNFILLABLE_SECTIONS:
        value = doc.get(section)
        if value is None or value == {} or value == []:
            gaps.append(f"{section} 缺失，备用源无法提供")
    return doc, gaps


def merge_positions(holdings, fallback_prices: dict, filled: list | None = None):
    """用备用源现价填补持仓清单的缺失价格（只补 price，主源优先）。

    Args:
        holdings: list[dict]（每项含 code/symbol/stock_code 之一）；
                  传 dict（market_data["holdings"] 形态）时按键名补 code 后转 list 处理
        fallback_prices: {code: {name, price, change_percent, ...}}
        filled: 可选收集器，累计本次填补字段（点分路径）

    Returns:
        (新持仓 list, gaps)
    """
    if isinstance(holdings, dict):
        items = []
        for code, item in holdings.items():
            row = dict(item) if isinstance(item, dict) else {}
            row.setdefault("code", code)
            items.append(row)
    elif isinstance(holdings, list):
        items = [dict(item) if isinstance(item, dict) else item for item in holdings]
    else:
        items = []

    fb = fallback_prices if isinstance(fallback_prices, dict) else {}
    gaps: list[str] = []

    for item in items:
        if not isinstance(item, dict):
            gaps.append("持仓项非 dict，无法匹配备用源")
            continue
        code = next((str(item[k]) for k in POSITION_CODE_KEYS
                     if item.get(k) not in (None, "")), None)
        if code is None:
            gaps.append("持仓项缺 code/symbol/stock_code，无法匹配备用源")
            continue
        if _usable(item.get("price")):
            continue                          # 主源优先：已有价不覆盖
        rec = fb.get(code)
        if rec is None:
            gaps.append(f"holdings.{code}.price 缺失，备用源未返回")
            continue
        usable, why = record_is_valid(rec)
        if not usable:
            gaps.append(f"holdings.{code} 备用源数据非法已丢弃（{why}）")
            gaps.append(f"holdings.{code}.price 缺失，备用源无法填补")
            continue
        item["price"] = rec["price"]
        if filled is not None:
            _append_unique(filled, f"holdings.{code}.price")
    return items, gaps


def apply_source_metadata(market_data: dict, source_status: str, gaps: list,
                          filled: list | None = None) -> dict:
    """写入数据源契约字段（data_source / data_gaps / fallback_fields）。

    data_gaps 与 fallback_fields 均为「合并去重」语义：已有内容保留，重复调用幂等。
    source_status 非法直接 ValueError —— 状态字写错会让下游误判降级等级，禁止静默兜底。
    """
    if source_status not in VALID_SOURCE_STATUS:
        raise ValueError(f"source_status 非法：{source_status!r}（须为 "
                         f"{' / '.join(VALID_SOURCE_STATUS)}）")
    doc = copy.deepcopy(market_data if isinstance(market_data, dict) else {})

    merged_gaps: list[str] = []
    existing = doc.get("data_gaps")
    if isinstance(existing, list):
        merged_gaps.extend(g for g in existing if isinstance(g, str))
    for g in gaps or []:
        if isinstance(g, str):
            _append_unique(merged_gaps, g)

    merged_fields: list[str] = []
    existing_fields = doc.get("fallback_fields")
    if isinstance(existing_fields, list):
        merged_fields.extend(f for f in existing_fields if isinstance(f, str))
    for f in filled or []:
        if isinstance(f, str):
            _append_unique(merged_fields, f)

    doc["data_source"] = source_status
    doc["data_gaps"] = merged_gaps
    doc["fallback_fields"] = merged_fields
    return doc


def positions_to_mapping(items) -> dict:
    """持仓 list → market_data['holdings'] 要求的 dict 形态（按 code 建键）。

    schema 规定 holdings 为对象，list 不能直接写回；缺 code 的条目无法建键，
    直接丢弃——其缺失已在 merge_positions 的 gaps 中声明，不是静默丢失。
    """
    out: dict = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        code = next((str(item[k]) for k in POSITION_CODE_KEYS
                     if item.get(k) not in (None, "")), None)
        if code is not None:
            out[code] = item
    return out


def merge_all(market_data: dict, fallback: dict, holdings=None,
              source_status: str = SOURCE_FALLBACK, fallback_positions: dict | None = None):
    """一次性合并指数 + 持仓 + 元数据（collect 步骤的单一入口）。

    Args:
        fallback: 指数备用源结果 {code: rec}
        fallback_positions: 个股备用源结果；缺省与 fallback 同源（一次抓取同时含指数+个股时）
        source_status: 由调用方按实际取数结果判定，本函数不猜测 ——
            主源成功=primary_westock / 部分或全部走备用=fallback_public / 两边都残缺=degraded

    Returns:
        (新 market_data, gaps)；持仓合并结果写回 market_data["holdings"]（传了 holdings 才写）。
    """
    filled: list[str] = []
    doc, gaps = merge_indices(market_data, fallback, filled=filled)
    if holdings is not None:
        positions, pos_gaps = merge_positions(
            holdings, fallback if fallback_positions is None else fallback_positions,
            filled=filled)
        gaps = gaps + pos_gaps
        doc["holdings"] = positions_to_mapping(positions)
    doc = apply_source_metadata(doc, source_status, gaps, filled=filled)
    return doc, gaps
