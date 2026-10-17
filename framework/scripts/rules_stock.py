#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rules_stock.py — 股票轨（场内可交易标的）校验规则

股票轨 = 场内可交易标的：个股 + 场内 ETF/LOF。允许 available 可用量、
grid 网格参数（基准价/区间/步长/单笔/最小底仓/最大顶仓）、分批与做 T。

依据 ADR-007 §2.2：用户前提「基金没有挂单/条件单」**只对场外基金成立**，
场内 ETF 有挂单，因此留在股票轨而非基金轨。

本模块承担双轨边界的**一侧**：场外标的不得进入股票轨的任何一段。
基金侧的边界（基金段禁网格键）见 rules_fund.py。
"""
from __future__ import annotations

# 代码规范化统一走 codes.py —— 全框架唯一实现，与 parse_holdings.py 对齐。
# 不在本模块重复实现前缀规则：两份实现一旦漂移就是静默故障。
from codes import code_mismatch, normalize_code
from rules_core import (
    E_CODE_FORMAT, E_CODE_PREFIX, E_DUPLICATE, E_GRID, E_LISTING,
    E_REQUIRED, E_TRACK_OTC_IN_GRID, E_UNKNOWN_KEY, LISTING_EXCHANGE,
    Report, W_BASE_PRICE, W_GRID_ORPHAN, W_MIN_POSITION, W_NO_GRID_PARAMS,
    W_ZERO_SHARES, check_keys, count, need, num, pos_loc,
)

POS_KEYS = ("code", "name", "listing", "shares", "available", "cost", "note")
GRID_KEYS = ("code", "name", "listing", "enabled", "base_price", "range_low",
             "range_high", "step_pct", "per_trade", "min_position",
             "max_position", "guide")

# listing 必填：归属由数据决定（ADR-007 §2.2「不由代码硬编码」）。
# 不给默认值是刻意的——留空会让「这只到底是场内还是场外」重新变成隐式契约，
# 而隐式契约正是 MEMORY.md 时代「代码列填 -」那类静默错位的根源。
REQUIRED_LISTING = "listing 必须显式声明：exchange=场内（可挂单/网格），otc=场外（仅申赎）"


def _check_code(raw, loc: str, rep: Report, seen: dict, kind: str) -> str:
    """校验 6 位证券代码，返回规范化代码（带市场前缀）。"""
    if raw is None:
        rep.err(f"{loc}.code", f"缺少必填字段 code", "", E_REQUIRED)
        return ""
    norm = normalize_code(raw)
    if len(norm) != 8 or not norm[:2] in ("sh", "sz", "bj") or not norm[2:].isdigit():
        rep.err(f"{loc}.code", f"code={raw!r} 无法识别市场",
                "须为 6 位数字；场内 ETF 用 6 位基金代码", E_CODE_FORMAT)
        return ""
    bad = code_mismatch(raw)
    if bad:
        rep.err(f"{loc}.code", bad, "去掉前缀只填 6 位数字可避免此问题", E_CODE_PREFIX)
    if norm in seen:
        rep.err(f"{loc}.code", f"重复{kind} {norm}",
                f"与 {seen[norm]} 冲突", E_DUPLICATE)
    else:
        seen[norm] = loc
    return norm


def validate_stock(cfg_stock, rep: Report) -> None:
    """校验 holdings.stock 段（positions + grid）。"""
    if cfg_stock is None:
        rep.err("holdings.stock", "缺少必填段 holdings.stock", "无内容写 {}")
        return
    if not isinstance(cfg_stock, dict):
        rep.err("holdings.stock", "stock 必须是映射", "写成 {positions: [], grid: []}")
        return
    check_keys(cfg_stock, ("positions", "grid"), "holdings.stock", rep, E_UNKNOWN_KEY)
    positions = cfg_stock.get("positions")
    grid = cfg_stock.get("grid")
    if positions is None:
        rep.err("holdings.stock.positions", "缺少必填段 positions", "无内容写 []", E_REQUIRED)
        positions = []
    if grid is None:
        rep.err("holdings.stock.grid", "缺少必填段 grid", "无内容写 []", E_REQUIRED)
        grid = []
    for nm, arr in (("positions", positions), ("grid", grid)):
        if not isinstance(arr, list):
            rep.err(f"holdings.stock.{nm}", f"{nm} 必须是列表", "无内容写 []")
    if isinstance(positions, list) and isinstance(grid, list):
        _validate_positions(positions, rep)
        _validate_grid(grid, positions, rep)


def _validate_positions(positions: list, rep: Report) -> None:
    seen: dict = {}
    for i, s in enumerate(positions):
        loc = pos_loc("stock.positions", i)
        if not isinstance(s, dict):
            rep.err(loc, "股票条目必须是映射")
            continue
        check_keys(s, POS_KEYS, loc, rep, E_UNKNOWN_KEY)
        for k in ("code", "name", "shares", "cost"):
            need(s, k, loc, rep)
        listing = s.get("listing")
        if listing is None:
            rep.err(f"{loc}.listing", REQUIRED_LISTING, "", E_LISTING)
        elif listing != LISTING_EXCHANGE:
            rep.err(f"{loc}.listing",
                    f"listing={listing!r} 与股票轨冲突：股票轨只收场内标的",
                    "场外基金请移到 holdings.fund.positions", E_TRACK_OTC_IN_GRID)
        _check_code(s.get("code"), loc, rep, seen, "持仓")
        count(s, "shares", loc, rep)
        count(s, "available", loc, rep)
        num(s, "cost", loc, rep)
        if s.get("shares") == 0:
            rep.warn(f"{loc}.shares", "持仓为 0",
                     "已清仓请从配置删除，勿留 0 占用行情请求配额", W_ZERO_SHARES)
        av, sh = s.get("available"), s.get("shares")
        if isinstance(av, int) and isinstance(sh, int) and av > sh:
            rep.err(f"{loc}.available",
                    f"available={av} > shares={sh}",
                    "可用份额不可能超过持仓份额")


def _validate_grid(grid: list, positions: list, rep: Report) -> None:
    """网格段校验。

    注意这里是股票轨的 grid 段——**只允许 exchange**。
    场外标的出现在这里即报 E_TRACK_OTC_IN_GRID，这是双轨隔离的核心断言。
    """
    seen: dict = {}
    held = {}
    for i, s in enumerate(positions if isinstance(positions, list) else []):
        if isinstance(s, dict) and s.get("code"):
            held[normalize_code(s.get("code"))] = s
    for i, g in enumerate(grid):
        loc = pos_loc("stock.grid", i)
        if not isinstance(g, dict):
            rep.err(loc, "网格条目必须是映射")
            continue
        check_keys(g, GRID_KEYS, loc, rep, E_UNKNOWN_KEY)
        for k in ("code", "name", "enabled"):
            need(g, k, loc, rep)
        listing = g.get("listing")
        if listing is None:
            rep.err(f"{loc}.listing", REQUIRED_LISTING, "", E_LISTING)
        elif listing != LISTING_EXCHANGE:
            rep.err(f"{loc}.listing",
                    f"listing={listing!r} 的标的不允许出现在股票轨 grid 段",
                    "场外基金没有挂单与条件单，不存在中间态，"
                    "网格策略对它无效；请移到 holdings.fund.positions",
                    E_TRACK_OTC_IN_GRID)
        norm = _check_code(g.get("code"), loc, rep, seen, "网格参数")
        en = g.get("enabled")
        if not isinstance(en, bool):
            rep.err(f"{loc}.enabled", f"enabled={en!r} 必须是 true/false",
                    "底仓长线持有写 false，不要留空")
            en = False
        for k in ("base_price", "range_low", "range_high", "step_pct"):
            num(g, k, loc, rep, lo=0.0, lo_exclusive=True)
        count(g, "per_trade", loc, rep)
        count(g, "min_position", loc, rep)
        count(g, "max_position", loc, rep)
        rng = (g.get("range_low"), g.get("range_high"))
        if en:
            if None in rng:
                rep.err(f"{loc}.range_low",
                        "启用网格时必须同时给出 range_low 与 range_high", "", E_GRID)
            elif rng[0] >= rng[1]:
                rep.err(f"{loc}.range_low",
                        f"区间非法：low={rng[0]} >= high={rng[1]}",
                        "下沿必须严格小于上沿", E_GRID)
            if g.get("base_price") is None:
                rep.err(f"{loc}.base_price", "启用网格时必须给出 base_price", "", E_GRID)
            elif rng[0] is not None and not (rng[0] <= g["base_price"] <= rng[1]):
                rep.warn(f"{loc}.base_price",
                         f"base_price={g['base_price']} 不在区间 [{rng[0]}, {rng[1]}] 内",
                         "基准价通常取区间中枢，越界说明参数未校准",
                         W_BASE_PRICE)
            if g.get("step_pct") is None:
                rep.err(f"{loc}.step_pct", "启用网格时必须给出 step_pct", "", E_GRID)
            elif not (0 < g["step_pct"] <= 50):
                rep.err(f"{loc}.step_pct",
                        f"step_pct={g['step_pct']} 超出 (0, 50]", "", E_GRID)
        else:
            for k in ("range_low", "range_high", "step_pct"):
                if g.get(k) is not None:
                    rep.warn(f"{loc}.{k}",
                             f"enabled=false 但仍设置了 {k}={g[k]!r}",
                             "该值不会被引擎读取，确认是否漏改 enabled",
                             W_NO_GRID_PARAMS)
        mn, mx = g.get("min_position"), g.get("max_position")
        if isinstance(mn, int) and isinstance(mx, int) and mn > mx:
            rep.err(f"{loc}.min_position",
                    f"min_position={mn} > max_position={mx}", "底仓不应大于顶仓", E_GRID)
        if norm and norm in held and en:
            sh = held[norm].get("shares")
            if isinstance(mn, int) and isinstance(sh, int) and mn > sh:
                rep.warn(f"{loc}.min_position",
                         f"min_position={mn} 超过当前持仓 {sh}",
                         "网格会立即触发停卖，请确认参数",
                         W_MIN_POSITION)
        elif norm and norm not in held:
            rep.warn(loc, f"网格标的 {norm} 不在 stock.positions 中",
                     "无持仓的网格参数不参与计算，确认是否漏填持仓",
                     W_GRID_ORPHAN)