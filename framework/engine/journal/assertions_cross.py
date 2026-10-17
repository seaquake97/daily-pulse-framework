#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assertions_cross.py — 决策日志 A-09..A-14 / A-16 断言（纯标准库，零依赖）

本文件承载**需要跨字段或跨条目**才能判定的断言：
    降级标注（A-09）     阈值哨兵值必须带 degraded 标记，且理由必须写明
    推导引用（A-11）     input_ref / output_ref 必须在本条目或数据仓里真实存在
    缺失登记（A-12）     missing[] 与实际字段值必须互斥
    条目级关系（A-08/A-13/A-14）  需要看邻近条目或观察点分组

结构与枚举检查（A-16、键集、失效链骨架）已切到 structure.py：
它们只看条目自身形状，与本文件的跨字段判据不同源，混在一起会让
「结构缺失」与「语义违规」两类错误在同一个文件里互相干扰。

A-10（reasoning_basis 禁 GENERATED）虽只是枚举拒值，仍放在这里：
它与 A-11 同属「研判可信度链」——GENERATED 推理的典型症状就是
derivation 全是格式化的空引用，两条一起看才说得清问题出在哪。
"""
from __future__ import annotations

from contracts import (
    DEFAULT_MAX_ACTIONS_PER_OBSERVATION, DEGRADED_SENTINELS,
    E_A08_GRID_REBALANCE_EXCLUSIVE, E_A09_DEGRADED_MARKING,
    E_A10_REASONING_BASIS, E_A12_MISSING_MUST_BE_NULL, E_A13_ACTION_COUNT_CAP,
    E_A14_UNVERIFIED_WITH_ACTION, EXCLUSIVE_PAIRS, REASONING_BASIS,
    REASONING_BASIS_FORBIDDEN,
)
from references import resolve_entry_ref


# --- A-09 阈值降级必须显式标注 ---------------------------------------------
def check_degraded_marking(entry: dict, loc: str, repo, rep) -> int:
    """A-09：阈值被降级成哨兵值（0 / 「阈值带」/ TBD）时必须标 degraded。

    这条拦的是伪装：把「拿不到真值」写成 threshold=0，读者会当成
    「阈值就是 0」而据此下单。判定只看哨兵值是否出现，不判断数值合理——
    数值合理性属于数据层职责，混进来会让本条变成万能挡箭牌。

    同时要求 degraded=True 时必须写 degraded_reason：光标一个 degraded
    不告诉别人降级的是什么，等于把问题转交而不是解决。
    """
    bad = 0
    obs = entry.get("observation_point")
    targets = [(f"{loc}.observation_point.threshold",
                (obs or {}).get("threshold") if isinstance(obs, dict) else None,
                (obs or {}).get("degraded") if isinstance(obs, dict) else None,
                (obs or {}).get("degraded_reason") if isinstance(obs, dict) else None)]
    act = entry.get("action")
    targets += [
        (f"{loc}.action.price", (act or {}).get("price"),
         (act or {}).get("degraded"), (act or {}).get("degraded_reason"))
        if isinstance(act, dict) else
        (f"{loc}.action.price", None, None, None),
        (f"{loc}.action.base_price", (act or {}).get("base_price"),
         (act or {}).get("degraded"), (act or {}).get("degraded_reason"))
        if isinstance(act, dict) else
        (f"{loc}.action.base_price", None, None, None),
    ]
    for where, value, degraded, reason in targets:
        is_sentinel = isinstance(value, str) and value in DEGRADED_SENTINELS
        is_zero = (not isinstance(value, bool)
                   and isinstance(value, (int, float)) and value == 0)
        if is_sentinel or is_zero:
            if not degraded:
                rep.err(where,
                        f"阈值被降级为占位值 {value!r} 却未标注 degraded",
                        "阈值降级必须显式标注，禁止伪装成正常值；"
                        "确实没有阈值就写 missing 并把字段置 None",
                        E_A09_DEGRADED_MARKING)
                bad += 1
            elif not str(reason or "").strip():
                rep.err(where, "degraded=True 但 degraded_reason 为空",
                        "说明降级原因与影响范围，别把问题转交下一个人",
                        E_A09_DEGRADED_MARKING)
                bad += 1
    return bad


# --- A-10 reasoning_basis 禁 GENERATED -------------------------------------
def check_reasoning_basis(entry: dict, loc: str, repo, rep) -> int:
    """A-10：reasoning_basis 出现 GENERATED 即拒。

    单独报这个码而不并入通用枚举错误：GENERATED 不是「取值不在枚举里」，
    它是「这条推理的来源被机器生成却当成了人的判断」，
    两者在排查时要看的材料完全不同。
    """
    val = entry.get("reasoning_basis")
    if val == REASONING_BASIS_FORBIDDEN:
        rep.err(f"{loc}.reasoning_basis",
                "reasoning_basis=GENERATED 不被允许",
                f"只能是 {' / '.join(REASONING_BASIS)}；"
                "机器生成的推理不能记为人的判断来源", E_A10_REASONING_BASIS)
        return 1
    return 0


# --- A-12 missing[] 与实际值互斥 -------------------------------------------
def check_missing(entry: dict, loc: str, repo, rep) -> int:
    """A-12：missing[] 非空时，对应字段必须为 None 而不是默认值。

    元规则「不可用优于默认值」的落点。默认的 0 与真实的 0 在下游无法区分，
    于是取数失败被当成「确实是 0」静默通过——这是最贵的一类静默故障。
    """
    missing = entry.get("missing")
    if missing is None:
        return 0
    if not isinstance(missing, list):
        rep.err(f"{loc}.missing", "missing 必须是列表", "无缺口写 []",
                E_A12_MISSING_MUST_BE_NULL)
        return 1
    bad = 0
    for i, field in enumerate(missing):
        where = f"{loc}.missing[{i}]"
        if not isinstance(field, str) or not field.strip():
            rep.err(where, f"missing 条目 {field!r} 非法",
                    "写字段路径，如 action.price", E_A12_MISSING_MUST_BE_NULL)
            bad += 1
            continue
        ok, value = resolve_entry_ref(entry, field.strip())
        if not ok:
            rep.err(where, f"missing 指向不存在的字段 {field!r}",
                    "missing 只能登记本条目真实存在的字段路径",
                    E_A12_MISSING_MUST_BE_NULL)
            bad += 1
        elif value is not None:
            rep.err(f"{loc}.{field.strip()}",
                    f"{field!r} 登记为 missing 却带有值 {value!r}",
                    "不可得字段必须为 None，不可用默认值代替"
                    "（元规则：不可用优于默认值）", E_A12_MISSING_MUST_BE_NULL)
            bad += 1
    return bad


# --- A-13 同观察点动作数上限 / A-08 grid 与 full_rebalance 互斥 -------------
def check_log_level(entries: list, repo, rep,
                    max_actions: int = DEFAULT_MAX_ACTIONS_PER_OBSERVATION,
                    line_index: dict | None = None) -> int:
    """跨条目断言：A-13 动作数上限 + A-08 互斥。

    两条放一起是因为都靠「按 observation_point 分组」这同一遍扫描。
    分组键取 observation_point.code；缺失时退回 instrument_code，
    否则「code 写漏」会让同标的的网格与调仓落到不同组，A-08 形同虚设。

    max_actions 可配置（默认 3）：上限是产品决策不是常量，
    写死在函数体里会让调参变成改代码。
    """
    if max_actions is None or not isinstance(max_actions, int) or max_actions < 1:
        raise ValueError("max_actions 必须是不小于 1 的整数")
    groups: dict = {}
    for i, ent in enumerate(entries):
        if not isinstance(ent, dict):
            continue
        obs = ent.get("observation_point") or {}
        act = ent.get("action") or {}
        key = obs.get("code") or act.get("instrument_code") or f"__idx_{i}"
        groups.setdefault(str(key), []).append((i, ent))
    bad = 0
    for key, members in groups.items():
        kinds = [e.get("action", {}).get("kind") for _, e in members
                 if isinstance(e.get("action"), dict)]
        for a, b in EXCLUSIVE_PAIRS:
            if a in kinds and b in kinds:
                loc = f"decision_log[{members[kinds.index(b)][0]}].action.kind"
                rep.err(loc,
                        f"观察点 {key!r} 同时出现 {a} 与 {b} 动作",
                        f"{a} 与 {b} 对同一观察点互斥：网格已覆盖区间内的"
                        "分批买卖，再叠全量调仓等于同一决策记两遍",
                        E_A08_GRID_REBALANCE_EXCLUSIVE)
                bad += 1
        if len(members) > max_actions:
            loc = f"decision_log[{members[max_actions][0]}]"
            rep.err(loc,
                    f"观察点 {key!r} 下有 {len(members)} 条动作，"
                    f"上限 {max_actions}",
                    "同一观察点给多条动作等于把一个决策摊成多句，"
                    "读者无法判断先做哪条；拆成多个观察点更清楚",
                    E_A13_ACTION_COUNT_CAP)
            bad += 1
    return bad


# --- A-14 UNVERIFIED 条目禁带动作 ------------------------------------------
def check_unverified_no_action(entry: dict, loc: str, repo, rep) -> int:
    """A-14：classification_verified=UNVERIFIED 的条目禁止携带动作。

    UNVERIFIED 意味着这条观察的可信度未经语义核验。带着动作下发，
    等于让一个自己都说不清可靠性的条目去驱动资金。
    """
    if entry.get("classification_verified") != "UNVERIFIED":
        return 0
    if entry.get("action") is None:
        return 0
    rep.err(f"{loc}.action",
            "classification_verified=UNVERIFIED 的条目禁止携带动作",
            "未核验条目只能作为 observation：先核验语义，再给动作",
            E_A14_UNVERIFIED_WITH_ACTION)
    return 1

