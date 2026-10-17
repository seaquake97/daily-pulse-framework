#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""classification.py — 四分类与抑制层（纯标准库，零依赖）

对「标的 × 资产 × 观察点」三级组合给出不触发类判定：
    actionable / watch_only / monitoring_only / forbidden

规则来自专家团结论，不是本模块的设计偏好：
  · 场外基金（listing=otc）× 价格类观察点 => 方法论不可得（场外基金无分时价），
    必须降为 monitoring_only，并把观察依据换成代理指标（重仓股实时涨跌）
    且标注代理性质；
  · 场外基金 × 净值/仓位类观察点 => actionable，动作只能是买入/卖出/调整定投；
  · 场内标的 × 网格类 => actionable；
  · 场外基金 × 任何 grid/条件单/委托动作 => forbidden。

输出 actionable 时必须同时给出 action / gates_passed / risk；
否则只给 observation_point 且 action 为 None。

被门禁阻断的动作**不删除**，记入 gate_blocked_actions 并把 action 置 None——
降级轮仍要能回答「本来想做什么、被什么挡住了」。
"""
from __future__ import annotations

from contracts import (
    ACTIONABLE_REQUIRED, CLASS_ACTIONABLE, CLASS_FORBIDDEN,
    CLASS_MONITORING_ONLY, CLASS_WATCH_ONLY, DEFAULT_MAX_ACTIONS_PER_OBSERVATION,
    GRID_KIND, LISTING_OTC, PROXY_BASIS_NOTE, PROXY_FLAG, PROXY_INDICATOR,
)


def classify(instrument_code, point_class, repo, proposed_action=None):
    """判定不触发类。返回单个分类字符串。

    三个入参就是「标的 × 资产 × 观察点」：资产由 instrument_code 在数据仓里
    查出的 listing 决定，不由调用方传——传 listing 等于让调用方自述归属，
    双轨隔离要拦的正是自述与数据不符的情况。

    判定表（场内 × 价格/净值/仓位 ⇒ actionable 是基线，不是兜底）：
        标的不在数据仓                      -> forbidden
        场外 × 网格/条件单/委托动作          -> forbidden
        场外 × 价格类                       -> monitoring_only（无分时价）
        场外 × 净值类 / 仓位类              -> actionable（仅三种动作）
        场内 × 价格 / 净值 / 仓位 / 网格    -> actionable
        任一 × 消息面                       -> watch_only

    表里每一格都显式写出，不留 fallthrough：把「场内 × 价格」落到末尾
    的 return 上，意味着一旦有人在上方加了新分支，它会静默变成 watch_only。
    """
    listing = repo.listing_of(instrument_code)
    if listing is None:
        return CLASS_FORBIDDEN
    kind = (proposed_action or {}).get("kind")

    if point_class == "NEWS":
        return CLASS_WATCH_ONLY
    if listing == LISTING_OTC:
        if kind in GRID_KIND or kind == "full_rebalance":
            # 场外没有挂单就没有中间态，网格与全量调仓都不可执行。
            return CLASS_FORBIDDEN
        if point_class == "PRICE":
            return CLASS_MONITORING_ONLY
        if point_class in ("NAV", "POSITION"):
            return CLASS_ACTIONABLE
        return CLASS_WATCH_ONLY
    if point_class in ("PRICE", "NAV", "POSITION", "GRID"):
        return CLASS_ACTIONABLE
    return CLASS_WATCH_ONLY


def proxy_observation(observation_point: dict) -> dict:
    """价格类观察点在场外基金上的替身：换成代理指标并标注代理性质。

    做三件事，且都不可省：
      1. proxy 字段标 PROXY_FLAG；
      2. proxy_basis 写明用的是重仓股实时涨跌；
      3. threshold 清空（None）——原阈值是场内价格，对场外无意义，
         留着会让下游以为可以照抄。原值存入 note 留痕。
    """
    out = dict(observation_point or {})
    original = out.get("threshold")
    out["proxy"] = PROXY_FLAG
    out["proxy_basis"] = PROXY_BASIS_NOTE
    out["threshold"] = None
    out["condition"] = (
        f"{PROXY_INDICATOR}与场外净值方向一致（代理指标，非场外分时价）")
    out["trigger"] = f"{PROXY_INDICATOR}日内涨幅达到既定阈值时重估（代理触发）"
    if original is not None:
        out["note"] = f"原场内价格阈值 {original} 对场外不适用，已转代理指标"
    return out


def apply_suppression(entry: dict, repo, max_actions: int | None = None):
    """抑制层：把「想给但不能给」的动作改写成「不能给 + 留痕」。

    返回抑制后的条目与一份留痕列表。留痕的语义（§4）：
        降级轮仍保留被阻断动作的可追溯记录——
        action 置 None，但原动作进 gate_blocked_actions，
        下游可回答「本来打算做什么、被哪条门禁挡住、当时的值是多少」。

    连带处理两件不做就会自相矛盾的事：
      · derivation 里指向被撤动作的 output_ref 必须改指留痕——
        否则 A-11 会因「引用不存在」把抑制产物判为非法，留痕功能形同虚设；
      · missing 必须登记 action 本身，否则 A-12 看不到「动作确实不可得」。
    """
    cap = max_actions if max_actions is not None \
        else DEFAULT_MAX_ACTIONS_PER_OBSERVATION
    suppressed = dict(entry or {})
    act = suppressed.get("action")
    obs = suppressed.get("observation_point") or {}
    blocked = list(suppressed.get("gate_blocked_actions") or [])
    missing = list(suppressed.get("missing") or [])

    if not isinstance(act, dict):
        return suppressed, blocked

    point_class = obs.get("point_class")
    verdict = classify(act.get("instrument_code"), point_class, repo, act)

    if verdict == CLASS_ACTIONABLE:
        suppressed["action"] = act
        return suppressed, blocked

    trace = _trace(act, "GATE_METHOD_UNAVAILABLE" if
                   verdict == CLASS_MONITORING_ONLY else
                   ("GATE_OTC_GRID_FORBIDDEN" if verdict == CLASS_FORBIDDEN
                    else "GATE_TRACK_OR_CLASS_UNSUPPORTED"),
                   obs.get("code") if
                   verdict == CLASS_MONITORING_ONLY else point_class,
                   "methodology" if verdict == CLASS_MONITORING_ONLY
                   else "track_boundary")
    blocked.append(trace)
    suppressed["gate_blocked_actions"] = blocked
    suppressed["derivation"] = _retarget_derivation(
        suppressed.get("derivation"), len(blocked) - 1)
    suppressed["action"] = None
    suppressed["requested_position"] = None
    suppressed["gates_passed"] = []
    if "action" not in missing:
        missing.append("action")
    suppressed["missing"] = missing

    if verdict == CLASS_MONITORING_ONLY:
        # 不是「不给」，是「方法论不可得」：观察点换成代理指标，动作撤下。
        suppressed["observation_point"] = proxy_observation(obs)
    return suppressed, blocked


def _retarget_derivation(derivation, trace_index: int) -> list:
    """把指向被撤动作的 output_ref 改指门禁留痕。

    改指而不是清空：清空会让这条推导凭空消失，而它的产出其实还在——
    只是从「待执行动作」挪进了「被阻断留痕」。指向留痕才是它现在的真实落点。
    """
    if not isinstance(derivation, list):
        return derivation
    out = []
    for step in derivation:
        if not isinstance(step, dict):
            out.append(step)
            continue
        ref = step.get("output_ref")
        patched = dict(step)
        if isinstance(ref, str) and (
                ref == "action" or ref.startswith("action.")):
            patched["output_ref"] = f"gate_blocked_actions[{trace_index}].action_code"
        out.append(patched)
    return out


def _trace(act: dict, gate_id: str, blocking_value, domain: str) -> dict:
    """生成门禁留痕。blocking_value 记**当时的判据值**：
    只记「被挡了」而不记「因为什么值被挡」，事后无法复盘。"""
    return {
        "action_code": act.get("code"), "gate_id": gate_id,
        "blocking_value": blocking_value if blocking_value is not None
        else "unknown",
        "blocking_domain": domain,
    }


def build_output(entry: dict, repo, max_actions: int | None = None) -> dict:
    """产出下游消费结构：分类结论 + 抑制后的条目 + 门禁留痕。

    不触发类是硬约束：返回 actionable 时若 action / gates_passed / risk
    任一缺失，宁可降为 watch_only 也不放行——一个自称 actionable 却没给
    数量与风控的结论，会被下游当成「可以执行」。
    """
    suppressed, blocked = apply_suppression(entry, repo, max_actions)
    obs = suppressed.get("observation_point") or {}
    act = suppressed.get("action")
    point_class = obs.get("point_class")
    verdict = classify((act or {}).get("instrument_code"), point_class, repo, act) \
        if act else _classify_without_action(suppressed, repo)

    if verdict == CLASS_ACTIONABLE:
        missing = [k for k in ACTIONABLE_REQUIRED
                   if not suppressed.get(k)]
        if missing:
            # 自称 actionable 却缺数量/风控的产物会被下游当成「可以执行」。
            # 宁可降为 watch_only 并留痕，也不放行半条建议。
            blocked.append({
                "action_code": (act or {}).get("code"),
                "gate_id": "GATE_ACTIONABLE_INCOMPLETE",
                "blocking_value": ",".join(missing),
                "blocking_domain": "contract",
            })
            suppressed["gate_blocked_actions"] = blocked
            suppressed["action"] = None
            suppressed["missing"] = list(
                dict.fromkeys(list(suppressed.get("missing") or []) + ["action"]))
            verdict = CLASS_WATCH_ONLY

    return {"classification": verdict, "entry": suppressed,
            "gate_blocked_actions": blocked,
            "actionable": verdict == CLASS_ACTIONABLE}


def _classify_without_action(suppressed: dict, repo) -> str:
    """无动作条目按观察点判定。已被抑制过的条目沿用抑制结论，
    不重算——重算会把 monitoring_only 悄悄变回 actionable。"""
    obs = suppressed.get("observation_point") or {}
    if obs.get("proxy") == PROXY_FLAG:
        return CLASS_MONITORING_ONLY
    if suppressed.get("gate_blocked_actions"):
        return CLASS_WATCH_ONLY
    return CLASS_WATCH_ONLY


__all__ = ["classify", "proxy_observation", "apply_suppression",
           "build_output"]