#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""codes.py — 证券代码规范化（纯标准库，零依赖）

**这是全框架唯一的市场前缀推断实现。**
规则与 `daily-decision-engine/scripts/parse_holdings.py` 的 `full_code()` 逐条对齐，
任何一方修改都必须同步另一方，否则会出现「配置校验说 ok、实际取数打空」的静默故障。

为什么单独成模块：normalize_code 被 validate_config.py（CLI 摘要）与 rules.py（校验规则）
共同依赖。若放在其中任一方，另一个就要反向导入，形成循环依赖。
本模块无任何内部依赖，是依赖图的叶子节点。
"""
from __future__ import annotations

import re

# 与 parse_holdings.py:53-58 保持一致，顺序有意义（startswith 元组按序匹配）
SH_PREFIX = ("60", "68", "9", "50", "51", "52", "58")
SZ_PREFIX = ("00", "30", "15", "16", "56")

# 北交所：4 / 8 开头（parse_holdings.py:57）
BJ_PREFIX = ("4", "8")


def market_of(digits: str) -> str:
    """按 6 位代码段推断市场。无法判定返回空串。"""
    if digits.startswith(SH_PREFIX):
        return "sh"
    if digits.startswith(SZ_PREFIX):
        return "sz"
    if digits.startswith(BJ_PREFIX):
        return "bj"
    return ""


def normalize_code(raw) -> str:
    """补全市场前缀。已带前缀则原样返回（转小写）。

    >>> normalize_code("600919")
    'sh600919'
    >>> normalize_code("sz003816")
    'sz003816'
    """
    s = str(raw).strip().lower()
    if re.fullmatch(r"(sh|sz|bj)\d{6}", s):
        return s
    digits = re.sub(r"\D", "", s)
    if len(digits) != 6:
        return s
    mkt = market_of(digits)
    return f"{mkt}{digits}" if mkt else s


def code_mismatch(raw) -> str:
    """用户显式写了市场前缀、但与代码段推断冲突时返回中文描述，否则返回空串。

    这类错误必须硬失败：写错前缀会让行情请求打到错误市场，表现为「代码找不到」，
    很容易被误判为「该标的不存在」而掩盖配置错误。
    """
    s = str(raw).strip().lower()
    m = re.fullmatch(r"(sh|sz|bj)(\d{6})", s)
    if not m:
        return ""
    expected = market_of(m.group(2))
    return "" if expected == m.group(1) else \
        f"代码 {m.group(2)} 按段应属 {expected or '未知市场'}，却写成 {m.group(1)}"
