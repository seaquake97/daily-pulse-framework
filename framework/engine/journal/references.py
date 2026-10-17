#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""references.py — 推导引用的解析与校验（A-11 / A-12 的公共底座）

从 assertions_cross.py 切出。切分判据是「这块逻辑有独立的正确性要求」：
引用解析有自己的下标语法、路径回退策略与「值不可得算不存在」判据，
它既被推导链校验用，也被 missing 登记校验用。两处共用一份实现是必须的——
两处各写一份，迟早在「空值算不算存在」上分叉，届时 A-11 与 A-12
会对同一个引用给出相反结论。

    contracts -> references -> assertions_cross
"""
from __future__ import annotations

from contracts import (
    DERIVATION_FORBIDDEN, DERIVATION_KEYS, E_A11_DERIVATION_REF, E_STRUCTURE,
    E_UNKNOWN_KEY,
)
from assertions import check_keys

# 允许出现在条目内引用里的路径前缀（portfolio. 走数据仓分支，此处只列条目侧）
REF_PREFIXES = ("entry.", "action.", "observation_point.", "risk.",
                "requested_position.")


def resolve_entry_ref(entry: dict, path: str):
    """在条目内按点分路径取值。取不到返回 (False, None)。

    支持 `seg[i]` 与 `seg[i].field` 两种下标写法：
    只按纯点分切分会漏掉 `gate_blocked_actions[0].action_code`——
    下标粘在键名里，切出来的片段是 "gate_blocked_actions[0]"，
    在 dict 里查不到，于是所有「指向门禁留痕」的引用都会被误判为悬空。
    """
    node = entry
    for part in path.split("."):
        key, index = _split_index(part)
        if isinstance(node, dict) and key in node:
            node = node[key]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return False, None
        if index is not None:
            if not isinstance(node, list) or index >= len(node):
                return False, None
            node = node[index]
    return True, node


def _split_index(part: str):
    """拆 `name[3]` -> ("name", 3)；无下标返回 (part, None)。"""
    if part.endswith("]") and "[" in part:
        name, _, raw = part[:-1].partition("[")
        if raw.isdigit():
            return name, int(raw)
    return part, None


def ref_exists(entry: dict, repo, ref) -> bool:
    """引用是否真实存在。分两类来源：

      portfolio.<code>.<字段>  数据仓内该标的的该字段（含顶层 cash / risk 段）
      其他                     本条目内的实际字段路径（entry./action./risk. 等前缀可写可不写）

    「字段存在但值为 None」算**不存在**：引用一个不可得的量当依据，
    等于把缺口藏进推理链，这正是本断言要拦的那类伪装。

    前缀处理上有个坑：不能无条件剥掉 `action.` 再从根部解析——
    `action.price` 剥完变成 `price`，在条目根部查不到，于是合法引用被误判为
    悬空。因此先按完整路径试，只在失败时才逐级剥前缀重试。
    """
    if not isinstance(ref, str) or not ref.strip():
        return False
    text = ref.strip()
    if text.startswith("portfolio."):
        rest = text[len("portfolio."):]
        if rest in ("cash", "risk", "profile", "holdings"):
            return bool(repo.cfg.get(rest))
        parts = rest.split(".")
        if not repo.get(parts[0]):
            return False
        return len(parts) == 1 or repo.has_field(parts[0], ".".join(parts[1:]))
    candidates = [text]
    parts = text.split(".")
    for cut in range(1, len(parts)):
        head = parts[0]
        if head in ("entry", "action", "risk", "observation_point",
                    "requested_position"):
            candidates.append(".".join(parts[cut:]))
    for cand in candidates:
        ok, value = resolve_entry_ref(entry, cand)
        if ok and value is not None:
            return True
    return False


# --- A-11 推导引用必须真实存在 ---------------------------------------------
def check_derivation(entry: dict, loc: str, repo, rep) -> int:
    """A-11：derivation 至少一条；input_ref / output_ref 必须真实存在。

    同时禁 reference_format：它让引用变成「按格式书写」而不是「按事实存在」，
    于是校验通过而依据是空的。
    """
    deriv = entry.get("derivation")
    if not isinstance(deriv, list) or not deriv:
        rep.err(f"{loc}.derivation", "derivation 至少要有一条推导步骤",
                "没有推导链的条目无法判断结论从哪来", E_A11_DERIVATION_REF)
        return 1
    bad = 0
    for i, step in enumerate(deriv):
        step_loc = f"{loc}.derivation[{i}]"
        if not isinstance(step, dict):
            rep.err(step_loc, "推导步骤必须是映射", "", E_STRUCTURE)
            bad += 1
            continue
        check_keys(step, DERIVATION_KEYS, step_loc, rep, E_UNKNOWN_KEY)
        for key in step:
            if key in DERIVATION_FORBIDDEN:
                rep.err(f"{step_loc}.{key}",
                        f"推导步骤不得出现 {key}={step.get(key)!r}",
                        "引用要指向真实字段，不指向格式说明", E_A11_DERIVATION_REF)
                bad += 1
        for field in ("input_ref", "output_ref"):
            ref = step.get(field)
            if not ref:
                rep.err(f"{step_loc}.{field}", f"derivation.{field} 为空",
                        "引用必须指明来源或落点字段", E_A11_DERIVATION_REF)
                bad += 1
            elif not ref_exists(entry, repo, ref):
                rep.err(f"{step_loc}.{field}",
                        f"{field}={ref!r} 在本条目与持仓数据仓中均不存在",
                        "允许 portfolio.<code>.<字段> 或 entry.<路径>；"
                        "引用不可得的量等于把缺口藏进推理链",
                        E_A11_DERIVATION_REF)
                bad += 1
    return bad
