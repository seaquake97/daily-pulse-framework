#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rules_fund.py — 基金轨（场外基金）校验规则

基金轨 = 场外基金：联接基金 / 场外指数 / QDII / 主动权益。
依据 ADR-007 §2.2：场外基金没有挂单与条件单，**没有中间态**，
因此动作只有「买入 / 卖出 / 调整定投」三种。

由此产生两条硬约束：
  1. 基金段出现任何网格键（基准价/区间/步长/单笔/最小底仓/最大顶仓）即违规
     ——报 E_TRACK_GRID_KEY_IN_FUND；
  2. 场外标的不得有 available（可用量是挂单概念，场外申赎无此中间态）。

增加两个基金专属字段：
  · holding_period_days 持有期/赎回费窗口——场外赎回费按持有天数档位计，
    是基金轨独有的风控参数，股票轨不适用；
  · plan 定投计划类型——驱动「定投日历」而非「日内网格」。
"""
from __future__ import annotations

import re

from rules_core import (
    E_DUPLICATE, E_ENUM, E_FUND, E_LISTING, E_REQUIRED,
    E_TRACK_GRID_KEY_IN_FUND, E_TRACK_OTC_IN_GRID, E_UNKNOWN_KEY,
    FUND_PLAN_TYPES, GRID_KEYS, LISTING_OTC, Report, check_keys, count,
    need, num, pos_loc,
)

POS_KEYS = ("code", "name", "listing", "amount", "holding_period_days",
            "plan", "note")
PLAN_KEYS = ("code", "type", "amount_per_period", "amount_per_period_max",
            "day_of_month", "note")

REQUIRED_LISTING = ("listing 必须显式声明：基金轨只收 otc（场外）标的。"
                    "场内 ETF/LOF 属于股票轨")


def validate_fund(cfg_fund, rep: Report) -> None:
    """校验 holdings.fund 段（positions + plans）。"""
    if cfg_fund is None:
        rep.err("holdings.fund", "缺少必填段 holdings.fund", "无内容写 {}")
        return
    if not isinstance(cfg_fund, dict):
        rep.err("holdings.fund", "fund 必须是映射", "写成 {positions: [], plans: []}")
        return
    check_keys(cfg_fund, ("positions", "plans"), "holdings.fund", rep, E_UNKNOWN_KEY)
    positions = cfg_fund.get("positions")
    plans = cfg_fund.get("plans")
    if positions is None:
        rep.err("holdings.fund.positions",
                "缺少必填段 positions", "无内容写 []", E_REQUIRED)
        positions = []
    if plans is None:
        rep.err("holdings.fund.plans",
                "缺少必填段 plans", "无内容写 []", E_REQUIRED)
        plans = []
    for nm, arr in (("positions", positions), ("plans", plans)):
        if not isinstance(arr, list):
            rep.err(f"holdings.fund.{nm}", f"{nm} 必须是列表", "无内容写 []")
    codes: set = set()
    if isinstance(positions, list):
        codes = _validate_positions(positions, rep)
    if isinstance(plans, list):
        _validate_plans(plans, codes, rep)


def _reject_grid_keys(item: dict, loc: str, rep: Report) -> None:
    """基金条目一旦带网格键即硬错误。

    不靠 schema 的 additionalProperties 兜底（schema 是文档，规则才是执行体），
    也不靠键名猜测——这里是显式列举网格键全集，命中即报可定位的错误。
    """
    hits = [k for k in GRID_KEYS if k in item]
    if hits:
        rep.err(loc, f"基金段出现网格键：{', '.join(sorted(hits))}",
                "场外基金没有挂单与条件单，不存在日内中间态，"
                "网格键对它无效；请删除这些键，"
                "定投节奏用 plans 段 + holding_period_days 表达",
                E_TRACK_GRID_KEY_IN_FUND)


def _validate_positions(positions: list, rep: Report) -> set:
    seen: set = set()
    for i, f in enumerate(positions):
        loc = pos_loc("fund.positions", i)
        if not isinstance(f, dict):
            rep.err(loc, "基金条目必须是映射")
            continue
        _reject_grid_keys(f, loc, rep)
        check_keys(f, POS_KEYS, loc, rep, E_UNKNOWN_KEY)
        for k in ("code", "name", "amount"):
            need(f, k, loc, rep)
        listing = f.get("listing")
        if listing is None:
            rep.err(f"{loc}.listing", REQUIRED_LISTING, "", E_LISTING)
        elif listing != LISTING_OTC:
            rep.err(f"{loc}.listing",
                    f"listing={listing!r} 与基金轨冲突：基金轨只收场外标的",
                    "场内 ETF/LOF 可挂单可网格，属于股票轨，"
                    "请移到 holdings.stock.positions", E_TRACK_OTC_IN_GRID)
        code = f.get("code")
        if code is not None:
            code = str(code)
            if not re.fullmatch(r"\d{6}", code):
                rep.err(f"{loc}.code",
                        f"code={code!r} 不是 6 位数字",
                        "场外基金代码不带市场前缀", E_FUND)
            elif code in seen:
                rep.err(f"{loc}.code", f"重复基金 {code}", "", E_DUPLICATE)
            else:
                seen.add(code)
        num(f, "amount", loc, rep)
        # 赎回费窗口：场外独有。缺省视为 0（多数货币/指数基金持有满 7 天免赎回费，
        # 但那是标的具体条款，不能替用户假设），仅做类型与上界校验。
        hp = f.get("holding_period_days")
        if hp is not None and (isinstance(hp, bool) or not isinstance(hp, int)
                               or not 0 <= hp <= 3650):
            rep.err(f"{loc}.holding_period_days",
                    f"holding_period_days={hp!r} 必须是 0~3650 的整数",
                    "填该基金赎回费免收档位的天数；不确定可留空", E_FUND)
        plan = f.get("plan")
        if plan is not None and plan not in FUND_PLAN_TYPES:
            rep.err(f"{loc}.plan", f"plan={plan!r} 非法",
                    f"可选：{' / '.join(FUND_PLAN_TYPES)}", E_ENUM)
        if "available" in f:
            rep.err(f"{loc}.available",
                    "基金段不允许 available",
                    "可用量是挂单概念，场外申赎无此中间态；"
                    "在场内交易才谈得上 T+1 冻结", E_TRACK_GRID_KEY_IN_FUND)
    return seen


def _validate_plans(plans: list, held: set, rep: Report) -> None:
    for i, p in enumerate(plans):
        loc = pos_loc("fund.plans", i)
        if not isinstance(p, dict):
            rep.err(loc, "定投计划条目必须是映射")
            continue
        _reject_grid_keys(p, loc, rep)
        check_keys(p, PLAN_KEYS, loc, rep, E_UNKNOWN_KEY)
        for k in ("code", "type"):
            need(p, k, loc, rep)
        code = p.get("code")
        if code is not None:
            code = str(code)
            if not re.fullmatch(r"\d{6}", code):
                rep.err(f"{loc}.code", f"code={code!r} 不是 6 位数字", "", E_FUND)
            elif code not in held:
                # 不加 `and held` 守卫：那样「positions 为空、plans 非空」
                # 会整段跳过检查，变成静默通过——正是本规则要防的情况。
                rep.err(f"{loc}.code",
                        f"定投标的 {code} 不在 fund.positions 中",
                        "无持仓的定投计划不参与计算，确认代码是否写错", E_FUND)
        t = p.get("type")
        if t is not None and t not in FUND_PLAN_TYPES:
            rep.err(f"{loc}.type", f"type={t!r} 非法",
                    f"可选：{' / '.join(FUND_PLAN_TYPES)}", E_ENUM)
        num(p, "amount_per_period", loc, rep)
        num(p, "amount_per_period_max", loc, rep)
        lo, hi = p.get("amount_per_period"), p.get("amount_per_period_max")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and hi < lo:
            rep.err(f"{loc}.amount_per_period_max",
                    f"每期上限 {hi} < 下限 {lo}",
                    "智慧定投的浮动区间必须满足 上限 >= 下限", E_FUND)
        dom = p.get("day_of_month")
        if dom is not None and (isinstance(dom, bool) or not isinstance(dom, int)
                                or not 1 <= dom <= 28):
            rep.err(f"{loc}.day_of_month",
                    f"day_of_month={dom!r} 必须是 1~28 的整数",
                    "选 28 而非 30/31：短月不存在该日期，定投日必须可实现", E_FUND)