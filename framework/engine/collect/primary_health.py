#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""primary_health.py — 主源健康度判定：该不该启用备用源

## 为什么单独成模块
「要不要走备用源」与「备用源数据怎么合进去」是两件事：前者是**判定**（只读，可单独测试、
可单独复用给告警/日志），后者是**写入**（merge_fallback.py 的职责）。混在一起会让
merge_fallback 既做判断又做合并，集成期一旦改判定口径就会动到合并逻辑。

## 判定口径（三条，命中任意一条即判降级）
  ① 结构缺失：market_data 非 dict / indices 缺失或为空
  ② 核心字段缺失：核心指数缺条目，或 price / change_percent 缺失（现价非正等同缺失）
  ③ 连接器缺口：data_gaps 命中连接器类关键词（说明主源通道本身不可用）

## 刻意不判的两类
  · 板块资金流 / 涨跌家数 / PE-PB / 多日涨跌幅 —— 备用源**补不了**，判了也只是白跑一次抓取，
    缺口仍要留在 data_gaps（由 merge_fallback 声明）。
  · 「数据看着旧」——时间戳新鲜度不参与判定：主源即使给的是旧值，按契约它仍是主源，
    是否被备用源覆盖由 merge_fallback 的「主源优先」铁律管，本模块不越权判新旧。

## 缺失时不静默默认
  所有分支都显式给出原因（degradation_reasons），不允许「查不到就当正常」。
  判定结果只用于**是否触发备用源抓取**，不改写任何数据。
"""
from __future__ import annotations

# 核心指数：缺任一即认为主源不可信（须为 merge_fallback.FALLBACK_INDEX_CODES 的子集，
# 否则备用源根本补不了——test 内有漂移守卫）
CORE_INDEX_CODES = ("sh000001", "sz399001", "sh000300")
# 备用源补得了、且缺失即算降级的字段
ESSENTIAL_FIELDS = ("price", "change_percent")
# 连接器类缺口关键词（说明主源通道不可用，而非单个字段没采到）
CONNECTOR_GAP_KEYWORDS = ("连接器未连接", "连接器不可用", "MCP 不可达", "MCP 未连接",
                          "westock-mcp")

__all__ = ["CONNECTOR_GAP_KEYWORDS", "CORE_INDEX_CODES", "ESSENTIAL_FIELDS",
           "degradation_reasons", "is_primary_degraded"]


def _num(value):
    """转 float；None / 非数值 → None（不抛、不猜）。"""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _field_missing(row: dict, field: str) -> bool:
    value = _num(row.get(field))
    if value is None:
        return True
    return field == "price" and value <= 0      # 现价非正等同缺失


def degradation_reasons(market_data, include_connector_gaps: bool = True) -> list[str]:
    """逐条列出主源降级原因；未降级返回空列表。

    Args:
        include_connector_gaps: 是否把「data_gaps 含连接器类缺口」计入降级（默认计入）。
            置 False 则只看数据本身缺不缺——适用于「主源数据已完整就不用备用源」的集成口径：
            实测 2026-10-16 那份 market_data 的 indices 是完整的，但 data_gaps 里留了
            「westock-mcp 连接器未连接」的痕迹（当时已改走公开源采集成功），
            计入就会为一份完整快照多跑一次抓取。两种口径都合理，交给集成方显式选。
    """
    if not isinstance(market_data, dict):
        return ["主源数据缺失或非 dict（无法判定完整性）"]

    indices = market_data.get("indices")
    if not isinstance(indices, dict) or not indices:
        return [f"indices 缺失或为空（{type(indices).__name__}）"]

    reasons: list[str] = []
    for code in CORE_INDEX_CODES:
        row = indices.get(code)
        if row is None:
            reasons.append(f"缺核心指数 {code}")
            continue
        if not isinstance(row, dict):
            reasons.append(f"{code} 条目非 dict（{type(row).__name__}）")
            continue
        for field in ESSENTIAL_FIELDS:
            if _field_missing(row, field):
                reasons.append(f"{code}.{field} 缺失或非数值")

    if include_connector_gaps:
        gaps = market_data.get("data_gaps")
        if isinstance(gaps, list):
            hits = [g for g in gaps if isinstance(g, str)
                    and any(k in g for k in CONNECTOR_GAP_KEYWORDS)]
            if hits:
                reasons.append(f"data_gaps 含连接器类缺口：{hits[0][:40]}")
    return reasons


def is_primary_degraded(market_data, include_connector_gaps: bool = True) -> bool:
    """主源是否降级（True = 建议启用备用源）。判定依据见 degradation_reasons。"""
    return bool(degradation_reasons(market_data,
                                    include_connector_gaps=include_connector_gaps))
