#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""structure.py — 决策日志结构与枚举检查（纯标准库，零依赖）

从 assertions.py 切出的独立模块。切分判据是「改哪条规则要动哪个文件」：
    结构类（骨架、键集、枚举、覆盖声明）属本文件；
    业务语义类（数量、金额口径、可平仓、跨轨）属 assertions.py。
两者的失败原因不同：结构缺失是构造错误，语义违规是研判错误，
排查时要看的材料与责任人都不一样。

A-16（covers_paths 非空）放在本文件而非 assertions_cross.py：
它判的是「条目形状是否完整」，不涉及降级、推导、跨条目关系，
与本文件其余检查同源。
"""
from __future__ import annotations

from contracts import (
    ACTION_KEYS, ACTION_KIND, BLOCKED_KEYS, CHAIN_KEYS,
    CLASSIFICATION_VERIFIED, E_A16_COVERS_PATHS,
    E_ENUM, E_REQUIRED, E_STRUCTURE, E_TYPE, E_UNKNOWN_KEY, ENTRY_KEYS,
    FALSIFIABILITY, OBSERVABLE_CLASS, PRECISION_SOURCE, REASONING_BASIS,
    RESOLUTION_STATUS, TRACK,
)
from assertions import check_keys
from diagnostics import item_loc


def check_enum_fields(entry: dict, loc: str, repo, rep) -> int:
    """四类枚举合法性：observable_class / falsifiability / track / kind /
    classification_verified / precision_source / reasoning_basis。

    单独成函数而非并入各段检查：枚举校验横跨 observation_point 与顶层，
    拆开会让同一类错误出现在两个函数里，改枚举时容易只改一处。
    """
    bad = 0
    obs = entry.get("observation_point")
    if isinstance(obs, dict):
        for field, allowed in (("observable_class", OBSERVABLE_CLASS),
                               ("falsifiability", FALSIFIABILITY)):
            val = obs.get(field)
            if val is not None and val not in allowed:
                rep.err(f"{loc}.observation_point.{field}",
                        f"{field}={val!r} 非法",
                        f"只能是 {' / '.join(allowed)}", E_ENUM)
                bad += 1
    act = entry.get("action")
    if isinstance(act, dict):
        act_loc = f"{loc}.action"
        check_keys(act, ACTION_KEYS, act_loc, rep)
        if act.get("track") is not None and act.get("track") not in TRACK:
            rep.err(f"{act_loc}.track", f"track={act.get('track')!r} 非法",
                    f"只能是 {' / '.join(TRACK)}", E_ENUM)
            bad += 1
        if act.get("kind") is not None and act.get("kind") not in ACTION_KIND:
            rep.err(f"{act_loc}.kind", f"kind={act.get('kind')!r} 非法",
                    f"只能是 {' / '.join(ACTION_KIND)}", E_ENUM)
            bad += 1
        for field in ("amount", "price", "priority", "base_price"):
            val = act.get(field)
            if val is None or isinstance(val, bool):
                continue
            if not isinstance(val, (int, float)):
                rep.err(f"{act_loc}.{field}",
                        f"{field}={val!r} 必须是数值", "", E_TYPE)
                bad += 1
    for field, allowed in (("classification_verified", CLASSIFICATION_VERIFIED),
                           ("precision_source", PRECISION_SOURCE),
                           ("reasoning_basis", REASONING_BASIS)):
        val = entry.get(field)
        if val is not None and val not in allowed:
            rep.err(f"{loc}.{field}", f"{field}={val!r} 非法",
                    f"只能是 {' / '.join(allowed)}", E_ENUM)
            bad += 1
    return bad


# --- A-16 covers_paths 必须非空 ---------------------------------------------
def check_covers_paths(entry: dict, loc: str, repo, rep) -> int:
    """A-16：covers_paths 声明本条断言覆盖哪些文件，必须非空。

    空数组会让「这条建议覆盖了什么」永远不可回答：审阅者无法定位到
    受影响的产物，改动落点也就无从追溯。
    """
    paths = entry.get("covers_paths")
    if paths is None:
        rep.err(f"{loc}.covers_paths", "缺少 covers_paths",
                "声明本条断言覆盖的文件路径", E_A16_COVERS_PATHS)
        return 1
    if not isinstance(paths, list):
        rep.err(f"{loc}.covers_paths", "covers_paths 必须是列表",
                "写成 [\"framework/engine/journal/validate.py\"]",
                E_A16_COVERS_PATHS)
        return 1
    if not paths:
        rep.err(f"{loc}.covers_paths", "covers_paths 为空",
                "每条断言都要声明覆盖的文件，否则无法追溯改动落点",
                E_A16_COVERS_PATHS)
        return 1
    return 0


def check_structure(entry: dict, loc: str, repo, rep) -> int:
    """顶层结构与失效链 / 门禁留痕的结构合法性。

    这些不是 A-01..A-16 之一，但没有它们，后续断言会在 None 上崩——
    一个会崩在校验层的校验器，在 CI 里表现为「测试红了」而不是
    「错误码是 E_A02」，排查成本高得多。
    """
    bad = check_keys(entry, ENTRY_KEYS, loc, rep, E_UNKNOWN_KEY)
    chain = entry.get("invalidation_chain")
    if not isinstance(chain, list) or not chain:
        rep.err(f"{loc}.invalidation_chain",
                "invalidation_chain 至少要有一条",
                "失效链为空等于没有退出条件", E_REQUIRED)
        bad += 1
    else:
        for i, item in enumerate(chain):
            item_loc = f"{loc}.invalidation_chain[{i}]"
            if not isinstance(item, dict):
                rep.err(item_loc, "失效链条目必须是映射", "", E_STRUCTURE)
                bad += 1
                continue
            bad += check_keys(item, CHAIN_KEYS, item_loc, rep, E_UNKNOWN_KEY)
            for field in ("code", "condition", "action_if_hit"):
                if not str(item.get(field) or "").strip():
                    rep.err(f"{item_loc}.{field}",
                            f"invalidation_chain[{i}].{field} 缺失",
                            "只写「失效了」而不写命中后动作的条目等于没写",
                            E_REQUIRED)
                    bad += 1
            if item.get("resolution_status") is not None and \
                    item.get("resolution_status") not in RESOLUTION_STATUS:
                rep.err(f"{item_loc}.resolution_status",
                        f"resolution_status={item.get('resolution_status')!r} 非法",
                        f"只能是 {' / '.join(RESOLUTION_STATUS)}",
                        E_UNKNOWN_KEY)
                bad += 1
    blocked = entry.get("gate_blocked_actions")
    if blocked is None:
        rep.err(f"{loc}.gate_blocked_actions", "缺少 gate_blocked_actions",
                "无阻断写 []；被阻断的动作要留痕，不能静默消失",
                E_REQUIRED)
        bad += 1
    elif not isinstance(blocked, list):
        rep.err(f"{loc}.gate_blocked_actions",
                "gate_blocked_actions 必须是列表", "无阻断写 []", E_STRUCTURE)
        bad += 1
    else:
        for i, item in enumerate(blocked):
            item_loc = f"{loc}.gate_blocked_actions[{i}]"
            if not isinstance(item, dict):
                rep.err(item_loc, "门禁留痕条目必须是映射", "", E_STRUCTURE)
                bad += 1
                continue
            bad += check_keys(item, BLOCKED_KEYS, item_loc, rep, E_UNKNOWN_KEY)
            for field in ("action_code", "gate_id"):
                if not str(item.get(field) or "").strip():
                    rep.err(f"{item_loc}.{field}",
                            f"gate_blocked_actions[{i}].{field} 缺失",
                            "门禁留痕必须能指回具体动作与具体门禁",
                            E_REQUIRED)
                    bad += 1
    for field in ("gates_passed",):
        val = entry.get(field)
        if val is not None and not isinstance(val, list):
            rep.err(f"{loc}.{field}", f"{field} 必须是列表", "无内容写 []",
                    E_STRUCTURE)
            bad += 1
    for field in ("as_of", "verified_by"):
        if not str(entry.get(field) or "").strip():
            rep.err(f"{loc}.{field}", f"{field} 缺失",
                    "谁在什么时候给的结论，缺一项都无法追溯",
                    E_REQUIRED)
            bad += 1
    return bad
