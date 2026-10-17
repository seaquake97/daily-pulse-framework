#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assertions.py — 决策日志 A-01..A-08 断言实现（纯标准库，零依赖）

一条断言 = 一个「写错就红」的判据。16 条分布在两个文件，
划分依据是**依赖对象**而非行数：
    A-01..A-08 只看条目自身与动作字段    -> 本文件
    A-09..A-16 需要降级标注 / 推导引用 / 缺失登记 / 跨条目关系
                                        -> assertions_cross.py
依赖方向：
    contracts -> datahub -> assertions / assertions_cross -> validate

三条通用约定：
  · 每个 check_* 返回命中错误条数（供测试断言「恰好命中哪条」），不自行抛出；
  · loc 一律由 validate.py 传入，本层不猜位置（保持与 rules*.py 同风格）；
  · 数据仓查不到标的时返回错误而非放行——把「查不到」当「没问题」，
    是这一层最容易出现的静默失效。
"""
from __future__ import annotations

from contracts import (
    AMOUNT_UNIT, E_A01_REQUESTED_POSITION, E_A02_OBSERVATION_FIELDS,
    E_A03_AMOUNT_UNIT, E_A04_GRID_BASE_PRICE, E_A05_EXIT_AVAILABLE,
    E_A06_ORPHAN_INSTRUMENT, E_A07_RISK_FIELDS, E_A15_TRACK_INDEPENDENCE,
    E_UNKNOWN_KEY, EXIT_KIND, FUND_ACTION_KIND, GRID_KIND, LISTING_OTC,
    OBS_KEYS, OBS_MANDATORY, POINT_CLASS, REQUESTED_POSITION_KEYS,
    RISK_KEYS, RISK_MANDATORY,
)

# A-15 判定用：这些键只在场内有意义，场外动作携带即跨轨引用。
# 口径与 rules_core.GRID_KEYS 对齐（禁的是「场内机制」而非某几个具体键名）。
ON_TRACK_ONLY_KEYS = ("base_price", "grid_enabled", "available", "shares",
                      "per_trade", "step_pct", "range_low", "range_high")


def check_keys(obj, allowed: tuple, loc: str, rep,
               code: str = E_UNKNOWN_KEY) -> int:
    """封闭键集：出现未知键即硬错误。拼错键必须炸——静默生效的拼写错误
    会让「写了 method_semantics」与「没写」不可区分，A-07 就再也拦不住。"""
    if not isinstance(obj, dict):
        return 0
    bad = 0
    for key in obj:
        if key not in allowed:
            rep.err(loc, f"未知键 '{key}'",
                    f"本段合法键：{', '.join(allowed)}", code)
            bad += 1
    return bad


# --- A-01 目标仓位：给方向不给数量即拒 --------------------------------------
def check_requested_position(entry: dict, loc: str, repo, rep) -> int:
    """A-01：必须给出「买多少」。三种拒法：整段缺失 / amount 为 None / basis 为空。

    basis 为空最常被忽略：没有依据的数量（随手写个 100）既不可执行也不可复盘，
    与没有数量同质。action 为 None 的条目不受本条约束——观察条目本就不该有仓位，
    强求它给仓位会把 A-14（UNVERIFIED 禁带动作）的语义搅浑。
    """
    if entry.get("action") is None:
        return 0
    req_loc = f"{loc}.requested_position"
    req = entry.get("requested_position")
    if not isinstance(req, dict):
        rep.err(req_loc, "缺少 requested_position",
                "指令要求给出买多少：只给方向不给数量等于没给建议",
                E_A01_REQUESTED_POSITION)
        return 1
    bad = check_keys(req, REQUESTED_POSITION_KEYS, req_loc, rep)
    if req.get("amount") is None:
        rep.err(f"{req_loc}.amount", "requested_position.amount 为空",
                "明确建议必须给数量（元或股）", E_A01_REQUESTED_POSITION)
        bad += 1
    if not str(req.get("basis") or "").strip():
        rep.err(f"{req_loc}.basis", "requested_position.basis 为空",
                "给出数量的依据，如「网格第一档 per_trade=100」",
                E_A01_REQUESTED_POSITION)
        bad += 1
    return bad


# --- A-02 观察点四字段 ------------------------------------------------------
def check_observation_point(entry: dict, loc: str, repo, rep) -> int:
    """A-02：trigger / condition / invalidation / monitoring_window 任一缺失即拒。

    这四个是观察点的可执行性下限：只有 trigger 没有 invalidation 的观察点
    无法证伪，只有 condition 没有 monitoring_window 的观察点没人负责盯。
    """
    obs = entry.get("observation_point")
    obs_loc = f"{loc}.observation_point"
    if not isinstance(obs, dict):
        rep.err(obs_loc, "缺少 observation_point",
                "每条建议都要有「凭什么」", E_A02_OBSERVATION_FIELDS)
        return 1
    bad = check_keys(obs, OBS_KEYS, obs_loc, rep)
    for field in OBS_MANDATORY:
        val = obs.get(field)
        if val is None or str(val).strip() == "":
            rep.err(f"{obs_loc}.{field}",
                    f"observation_point.{field} 缺失",
                    "触发条件 / 成立条件 / 失效条件 / 观察窗口四者缺一不可",
                    E_A02_OBSERVATION_FIELDS)
            bad += 1
    if obs.get("point_class") is not None and \
            obs.get("point_class") not in POINT_CLASS:
        rep.err(f"{obs_loc}.point_class",
                f"point_class={obs.get('point_class')!r} 非法",
                f"只能是 {' / '.join(POINT_CLASS)}", E_ENUM)
        bad += 1
    return bad


# --- A-03 金额口径：money|shares，二者不可同时给 ---------------------------
def check_amount_unit(entry: dict, loc: str, repo, rep) -> int:
    """A-03：金额与份额必须标明口径，且不得同时给两个数。

    「若给两者且隐含换算 → 拒」的实现：converted_amount 是换算结果位，
    一旦同时给了口径值与换算值，说明有人在做 money<->shares 换算执行。
    场外 NAV 与场内分时价不可比（NAV 滞后一天），换算出的数字会被执行器
    当真值用，因此硬拒而非警告。
    """
    bad = 0
    for name in ("requested_position", "action"):
        blk = entry.get(name)
        if not isinstance(blk, dict):
            continue
        base = f"{loc}.{name}"
        amount, unit = blk.get("amount"), blk.get("amount_unit")
        if amount is None and unit is None:
            continue
        if unit is None:
            rep.err(f"{base}.amount_unit",
                    f"{name}.amount={amount!r} 但未标 amount_unit",
                    "金额写 money，份额写 shares；不标口径等于让下游猜",
                    E_A03_AMOUNT_UNIT)
            bad += 1
        elif unit not in AMOUNT_UNIT:
            rep.err(f"{base}.amount_unit", f"amount_unit={unit!r} 非法",
                    f"只能是 {' / '.join(AMOUNT_UNIT)}", E_A03_AMOUNT_UNIT)
            bad += 1
        if blk.get("converted_amount") is not None:
            rep.err(f"{base}.converted_amount",
                    f"{name} 同时给出金额与换算值 "
                    f"（converted_amount={blk.get('converted_amount')!r}）",
                    "禁止 money<->shares 的换算执行：场外 NAV 与场内分时价"
                    "不可比，换算结果会被执行器当真值", E_A03_AMOUNT_UNIT)
            bad += 1
    return bad


# --- A-04 网格动作必须给 base_price ---------------------------------------
def check_grid_base_price(entry: dict, loc: str, repo, rep) -> int:
    """A-04：网格类动作缺 base_price 即拒。

    不从数据仓代填：数据仓的 base_price 是配置基准，动作里的 base_price 是
    「本轮挂单以哪价为锚」，两者可能不同（下移网格后锚点要跟着动），
    代填会让操作者看不出本轮用的是哪一档。
    """
    act = entry.get("action")
    if not isinstance(act, dict) or act.get("kind") not in GRID_KIND:
        return 0
    base = f"{loc}.action"
    val = act.get("base_price")
    if val is None:
        rep.err(f"{base}.base_price", "网格类动作必须给 base_price",
                "挂单锚点必须显式声明，不从配置静默代填", E_A04_GRID_BASE_PRICE)
        return 1
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        rep.err(f"{base}.base_price", f"base_price={val!r} 必须是数值", "",
                E_A04_GRID_BASE_PRICE)
        return 1
    return 0


# --- A-05 出场类动作必须证明可平仓 -----------------------------------------
def check_exit_available(entry: dict, loc: str, repo, rep) -> int:
    """A-05：出场动作必须证明 available >= amount。

    数据仓查不到标的时返回错误（E_A06 同时也会报）：把「查不到」当「可平仓」
    是本条最容易出现的静默失效——它会让 T+1 冻结仓被当成可卖仓。
    """
    act = entry.get("action")
    if not isinstance(act, dict) or act.get("kind") not in EXIT_KIND:
        return 0
    base = f"{loc}.action"
    if act.get("amount_unit") != "shares":
        rep.err(f"{base}.amount_unit",
                "出场动作必须以 shares 口径给出才能与 available 比较",
                f"amount_unit={act.get('amount_unit')!r}："
                "元口径证明不了可平仓份额", E_A05_EXIT_AVAILABLE)
        return 1
    code = act.get("instrument_code")
    available = repo.available_of(code)
    if available is None:
        rep.err(f"{base}.instrument_code",
                f"标的 {code!r} 不在数据仓，无法证明当前可平仓量",
                "出场动作必须对可核对的持仓执行", E_A05_EXIT_AVAILABLE)
        return 1
    amount = act.get("amount")
    if isinstance(available, (int, float)) and isinstance(amount, (int, float)) \
            and amount > available:
        rep.err(f"{base}.amount",
                f"卖出 {amount} 股 > available {available} 股",
                "出场类动作必须证明当前可平仓", E_A05_EXIT_AVAILABLE)
        return 1
    return 0


# --- A-06 孤儿标的 ---------------------------------------------------------
def check_instrument_known(entry: dict, loc: str, repo, rep) -> int:
    """A-06：action.instrument_code 必须存在于持仓数据仓。

    track=news 的条目无 instrument_code（消息面不对应单一标的），放行。
    """
    act = entry.get("action")
    if not isinstance(act, dict) or act.get("track") == "news":
        return 0
    base = f"{loc}.action"
    code = act.get("instrument_code")
    if not code:
        rep.err(f"{base}.instrument_code", "缺少 instrument_code",
                "动作必须指明标的（消息面条目除外）", E_A06_ORPHAN_INSTRUMENT)
        return 1
    if repo.has(code):
        return 0
    rep.err(f"{base}.instrument_code",
            f"孤儿标的 {code!r}：不在持仓数据仓内",
            "所有动作只能针对已持仓标的（ADR-007 U7：任务基于个人持仓数据）",
            E_A06_ORPHAN_INSTRUMENT)
    return 1


# --- A-07 风控四字段 -------------------------------------------------------
def check_risk_fields(entry: dict, loc: str, repo, rep) -> int:
    """A-07：stop_loss / method_semantics / confidence / limit_conditions
    任一缺失即拒。风控随建议下发（ADR-007 §2.3），不是可选段。"""
    risk = entry.get("risk")
    base = f"{loc}.risk"
    if not isinstance(risk, dict):
        rep.err(base, "缺少 risk 段",
                "ADR-007 §2.3：风控不撤，改为随每条建议下发", E_A07_RISK_FIELDS)
        return 1
    bad = check_keys(risk, RISK_KEYS, base, rep)
    for field in RISK_MANDATORY:
        val = risk.get(field)
        if val is None or (isinstance(val, (list, str, dict)) and len(val) == 0):
            rep.err(f"{base}.{field}", f"risk.{field} 缺失",
                    "止损 / 方法语义 / 置信度 / 限制条件四者缺一不可",
                    E_A07_RISK_FIELDS)
            bad += 1
    conf = risk.get("confidence")
    if conf is not None and not isinstance(conf, bool):
        if not isinstance(conf, (int, float)) or not 0 < conf <= 1:
            rep.err(f"{base}.confidence",
                    f"confidence={conf!r} 必须是 (0, 1] 的数值", "",
                    E_A07_RISK_FIELDS)
            bad += 1
    return bad


# --- A-15 跨轨独立性 --------------------------------------------------------
def check_track_independence(entry: dict, loc: str, repo, rep) -> int:
    """A-15：场外基金动作不得引用网格/委托/持仓类场内机制。

    判据是数据仓 listing（由数据决定），不是 action.track 自述：
    track 写错时，「场内标的被标成 fund」正是双轨隔离要拦的那类错位。
    """
    act = entry.get("action")
    if not isinstance(act, dict):
        return 0
    if repo.listing_of(act.get("instrument_code")) != LISTING_OTC:
        return 0
    base = f"{loc}.action"
    bad = 0
    kind = act.get("kind")
    if kind not in FUND_ACTION_KIND:
        rep.err(f"{base}.kind", f"场外基金出现 kind={kind!r}",
                f"场外基金只有 {' / '.join(FUND_ACTION_KIND)} 三种动作："
                "没有挂单就没有中间态（ADR-007 §2.2）", E_A15_TRACK_INDEPENDENCE)
        bad += 1
    for key in ON_TRACK_ONLY_KEYS:
        if act.get(key) is not None:
            rep.err(f"{base}.{key}",
                    f"场外动作携带场内专有键 {key}={act.get(key)!r}",
                    "场内机制（网格/挂单/可用量）在场外不存在，"
                    "引用即说明这条建议混了轨", E_A15_TRACK_INDEPENDENCE)
            bad += 1
    if act.get("track") == "stock":
        rep.err(f"{base}.track",
                "数据仓判定该标的为场外，动作却声明 track=stock",
                "归属由 listing 决定，不由代码或自述决定（ADR-007 §2.2）",
                E_A15_TRACK_INDEPENDENCE)
        bad += 1
    return bad
