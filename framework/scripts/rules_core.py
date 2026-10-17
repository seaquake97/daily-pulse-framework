#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rules_core.py — 校验规则集的公共底座（纯标准库，零依赖）

依赖图（严格单向，无环）：
    codes.py（叶子）
      -> rules_core.py     本文件：Report / 错误码 / 位置换算 / 类型断言
      -> rules_stock.py         股票轨规则
      -> rules_fund.py          基金轨规则
      -> rules.py               门面：调度 + 汇总

为什么拆这么细：v2 加了双轨隔离后，单文件规则集会突破 300 行上限。
拆分的判据是「改哪条规则要动哪个文件」——双轨边界规则（otc 禁入网格）
属股票轨，定投与赎回窗口规则属基金轨，各自独立演进。
"""
from __future__ import annotations

# 契约版本：v2 = 双轨隔离（ADR-007 U1/U6）
SCHEMA_VERSION = 2
SUPPORTED_VERSIONS = (2,)

# ---------------------------------------------------------------------------
# 错误码：给 CI 断言与外部脚本一个稳定抓手。
# 只加不改、只扩不改义——改义等于让历史告警记录失效。
# ---------------------------------------------------------------------------
E_VERSION = "E_VERSION"
E_STRUCTURE = "E_STRUCTURE"
E_PROFILE = "E_PROFILE"
E_RISK = "E_RISK"
E_CASH = "E_CASH"
E_TRACK_OTC_IN_GRID = "E_TRACK_OTC_IN_GRID"      # 场外标的出现在股票轨
E_TRACK_GRID_KEY_IN_FUND = "E_TRACK_GRID_KEY_IN_FUND"  # 基金段出现网格键
E_LISTING = "E_LISTING"                            # listing 缺失或与所属段冲突
E_CODE_FORMAT = "E_CODE_FORMAT"
E_CODE_PREFIX = "E_CODE_PREFIX"
E_DUPLICATE = "E_DUPLICATE"
E_REQUIRED = "E_REQUIRED"
E_TYPE = "E_TYPE"
E_RANGE = "E_RANGE"
E_GRID = "E_GRID"
E_FUND = "E_FUND"
E_ENUM = "E_ENUM"
E_UNKNOWN_KEY = "E_UNKNOWN_KEY"

W_ZERO_SHARES = "W_ZERO_SHARES"
W_NO_GRID_PARAMS = "W_NO_GRID_PARAMS"
W_BASE_PRICE = "W_BASE_PRICE"
W_MIN_POSITION = "W_MIN_POSITION"
W_EMPTY = "W_EMPTY"
W_GRID_ORPHAN = "W_GRID_ORPHAN"

# 网格键全集：基金轨段一旦出现其中任意一个即判违规。
# 单一事实源——schema.json 与本模块共用同一份清单的语义（清单本体在 schema）。
GRID_KEYS = ("base_price", "range_low", "range_high", "step_pct", "per_trade",
             "min_position", "max_position")

# 场内 / 场外。归属由数据决定，不由代码硬编码（ADR-007 §2.2）。
LISTING_EXCHANGE = "exchange"
LISTING_OTC = "otc"
FUND_PLAN_TYPES = ("regular", "smart", "smart_take_profit", "holding", "none")


class Report:
    """校验结果收集器。

    line_index 由 yaml_min.parse_yaml_subset_indexed 产出，把
    `holdings.stock.positions[3].shares` 这类逻辑位置翻译成文件行号。
    """

    def __init__(self, line_index: dict | None = None) -> None:
        self.errors: list = []
        self.warnings: list = []
        self.line_index = line_index or {}

    def _locate(self, loc: str) -> dict:
        """给一条诊断附上行号。找不到就返回 0（不猜行号）。"""
        no = self.line_index.get(loc, 0)
        if no:
            return {"location": loc, "line": no}
        # 逐级回退到最近的已知祖先（如 ...positions[3] 命中则用其行号）。
        # 守卫必须写成「probe 变短才继续」：对不含 "." 的 loc（如 "holdings"），
        # rsplit(".", 1)[0] 会原样返回自身，只判空会死循环。
        probe = loc
        while "." in probe:
            probe = probe.rsplit(".", 1)[0]
            no = self.line_index.get(probe, 0)
            if no:
                return {"location": loc, "line": no}
        return {"location": loc, "line": 0}

    def err(self, loc: str, msg: str, hint: str = "", code: str = E_STRUCTURE) -> None:
        item = {"level": "error", "message": msg, "hint": hint, "code": code}
        item.update(self._locate(loc))
        self.errors.append(item)

    def warn(self, loc: str, msg: str, hint: str = "", code: str = E_STRUCTURE) -> None:
        item = {"level": "warning", "message": msg, "hint": hint, "code": code}
        item.update(self._locate(loc))
        self.warnings.append(item)

    @property
    def ok(self) -> bool:
        return not self.errors


def pos_loc(seg: str, i: int, key: str = "") -> str:
    """统一的位置串构造：`holdings.stock.positions[3].shares`。

    位置串同时是 line_index 的键，所以构造方式必须与 yaml_min 的索引前缀一致，
    不能一处用点分、一处用下划线。
    """
    base = f"holdings.{seg}[{i}]"
    return f"{base}.{key}" if key else base


def check_keys(item: dict, allowed: tuple, loc: str, rep: Report, code: str) -> None:
    """封闭键集检查：出现未知键即硬错误（拼写错误必须炸，不能静默生效）。"""
    for k in item:
        if k not in allowed:
            rep.err(loc, f"未知键 '{k}'", f"本段合法键：{', '.join(allowed)}", code)


def need(item: dict, key: str, loc: str, rep: Report) -> None:
    if item.get(key) is None:
        rep.err(f"{loc}.{key}", f"缺少必填字段 {key}", "", E_REQUIRED)


def num(item: dict, key: str, loc: str, rep: Report, lo: float = 0.0,
        hi: float | None = None, lo_exclusive: bool = False,
        code: str = E_TYPE) -> None:
    v = item.get(key)
    if v is None:
        return
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        rep.err(f"{loc}.{key}", f"{key}={v!r} 必须是数值", "", code)
        return
    bad = v <= lo if lo_exclusive else v < lo
    if bad or (hi is not None and v > hi):
        bound = f"({lo}, {hi}]" if hi is not None else f"> {lo}"
        rep.err(f"{loc}.{key}", f"{key}={v} 超出允许范围 {bound}", "", E_RANGE)


def count(item: dict, key: str, loc: str, rep: Report, hi: int | None = None) -> None:
    v = item.get(key)
    if v is None:
        return
    if isinstance(v, bool) or not isinstance(v, int):
        rep.err(f"{loc}.{key}", f"{key}={v!r} 必须是非负整数", "", E_TYPE)
        return
    if v < 0 or (hi is not None and v > hi):
        rep.err(f"{loc}.{key}", f"{key}={v} 超出允许范围", "", E_RANGE)