#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schema.py — 决策日志条目结构与纯标准库构造器（零第三方依赖）

依赖方向：contracts -> schema -> datahub -> validate -> classification。
本模块只定义「一条建议长什么样」与「怎么把它造出来」，不做任何判定。

为什么用 dict + 构造器而不是 dataclass：
  · 校验层要报「未知键」与「缺键」两类错误，dataclass 会在构造时抛异常，
    把「造错」和「校验不过」混成同一个失败点，错误信息反而更差；
  · 产物要直接落 JSON 给下游任务读，dict 无转换损耗；
  · 缺字段时保留键并置 None——这正是 A-12「不可得走 missing 而不是默认值」
    要表达的形状，dataclass 表达不了「键存在但值不可得」。

不变式（由 validate.py 强制，本模块不重复断言）：
  · 造出来的条目**不保证**通过校验。构造器只保证键集封闭、值类型合理。
    一个「保证合法」的构造器会让人误以为漏写字段没事，从而绕过 A-01..A-16。
"""
from __future__ import annotations

from contracts import JOURNAL_VERSION  # 键集与枚举单一事实源在 contracts.py

# re-export：下游（校验层 / 任务脚本）习惯从 schema 取键集，而键集本体
# 只在 contracts 里存一份。此处再导出不构成第二份清单。
from contracts import (  # noqa: F401
    ACTION_KEYS, CHAIN_KEYS, CLASSIFICATION_VERIFIED, DERIVATION_KEYS,
    ENTRY_KEYS, FALSIFIABILITY, OBSERVABLE_CLASS, OBS_KEYS, PRECISION_SOURCE,
    REASONING_BASIS, REQUESTED_POSITION_KEYS, RISK_KEYS, TRACK,
)


def observation_point(code: str, trigger: str, condition: str,
                      invalidation: str, monitoring_window: str,
                      observable_class: str = "QUANTIFIED",
                      falsifiability: str = "FALSIFIABLE",
                      point_class: str | None = None,
                      threshold=None, proxy: str | None = None,
                      proxy_basis: str | None = None,
                      note: str | None = None) -> dict:
    """观察点。一条建议的「凭什么」。

    point_class 显式给出而不从 trigger 文本推断：'突破 21.00' 既可能是价格类
    也可能是网格触发条件，靠关键词猜会在改写文案后静默错判，而四分类层的
    全部结论都建立在这个分类上。宁可要求调用方写明，也不猜。
    """
    return {
        "code": code, "trigger": trigger, "condition": condition,
        "invalidation": invalidation, "monitoring_window": monitoring_window,
        "observable_class": observable_class, "falsifiability": falsifiability,
        "point_class": point_class, "threshold": threshold,
        "proxy": proxy, "proxy_basis": proxy_basis, "note": note,
    }


def action(code: str, track: str, instrument_code: str | None, kind: str,
           amount=None, amount_unit: str | None = None, price=None,
           priority: int = 2, trigger: str | None = None,
           invalidation: str | None = None, base_price=None,
           converted_amount=None, degraded: bool = False,
           degraded_reason: str | None = None) -> dict:
    """动作。amount_unit 必须由调用方显式给出 money|shares，不给默认——
    A-03 的整个存在意义就是禁止「猜这个数是钱还是股」。"""
    return {
        "code": code, "track": track, "instrument_code": instrument_code,
        "kind": kind, "amount": amount, "amount_unit": amount_unit,
        "converted_amount": converted_amount, "price": price,
        "priority": priority, "trigger": trigger, "invalidation": invalidation,
        "base_price": base_price, "degraded": degraded,
        "degraded_reason": degraded_reason,
    }


def requested_position(instrument_code: str, amount, amount_unit: str,
                       basis: str, converted_amount=None) -> dict:
    """目标仓位。A-01 的落点：给「买多少」，不给只给方向。

    basis 是给出该数量的依据（如「占可用现金 30%」），必填——没有依据的
    数量和没有数量一样不可执行。
    """
    return {"instrument_code": instrument_code, "amount": amount,
            "amount_unit": amount_unit, "basis": basis,
            "converted_amount": converted_amount}


def risk(tier: str, max_trade_loss=None, thesis_invalidation: str | None = None,
         method_semantics: str | None = None, stop_loss=None,
         confidence=None, limit_conditions=None,
         exception_owner: str | None = None,
         declared_exception: str | None = None) -> dict:
    """风控随建议下发（ADR-007 §2.3：风控不撤，改为随建议走）。

    method_semantics 必填且无默认：entry_gate（只卡进场）/ hard_cap（只卡上限）
    / both 语义完全不同，猜错会让执行器把止损当进场门槛。
    """
    return {
        "tier": tier, "max_trade_loss": max_trade_loss,
        "thesis_invalidation": thesis_invalidation,
        "method_semantics": method_semantics, "stop_loss": stop_loss,
        "confidence": confidence, "limit_conditions": limit_conditions,
        "exception_owner": exception_owner,
        "declared_exception": declared_exception,
    }


def invalidation_item(code: str, condition: str, action_if_hit: str,
                      resolution_status: str = "OPEN") -> dict:
    """失效链上的一条。action_if_hit 是「命中后怎么办」，
    只写「失效了」而不写动作的条目等于没写。"""
    return {"code": code, "condition": condition,
            "action_if_hit": action_if_hit,
            "resolution_status": resolution_status}


def derivation_step(step: str, input_ref: str, output_ref: str) -> dict:
    """推导链一步。input_ref / output_ref 必须是本条目或数据仓里的**实际路径**
    （A-11），不是「格式说明」。故本构造器不提供 reference_format 参数——
    提供它就等于邀请调用方用它。"""
    return {"step": step, "input_ref": input_ref, "output_ref": output_ref}


def blocked_action(action_code: str, gate_id: str, blocking_value,
                   blocking_domain: str) -> dict:
    """被门禁阻断的动作留痕。动作为 None 不等于动作不存在。"""
    return {"action_code": action_code, "gate_id": gate_id,
            "blocking_value": blocking_value,
            "blocking_domain": blocking_domain}


def entry(observation: dict, act: dict | None, risk_block: dict | None,
          requested: dict, invalidation_chain: list,
          classification_verified: str, precision_source: str,
          as_of: str, verified_by: str, reasoning_basis: str,
          derivation: list, covers_paths: list,
          gates_passed: list | None = None,
          gate_blocked_actions: list | None = None,
          missing: list | None = None,
          version: int = JOURNAL_VERSION) -> dict:
    """组装一条决策日志条目。

    显式列出全部顶层键（含为 None 的），而不是 `**kwargs` 兜底：
    少写一个键与写错一个键要能被校验层区分开，`**kwargs` 会让两者都变成
    「键不存在」，A-12 与 A-02 就都失去了判据。
    """
    return {
        "observation_point": observation, "action": act, "risk": risk_block,
        "invalidation_chain": invalidation_chain,
        "classification_verified": classification_verified,
        "precision_source": precision_source, "as_of": as_of,
        "verified_by": verified_by, "reasoning_basis": reasoning_basis,
        "derivation": derivation, "gate_blocked_actions":
            gate_blocked_actions or [], "gates_passed": gates_passed or [],
        "missing": missing or [], "covers_paths": covers_paths,
        "requested_position": requested, "version": version,
    }


def new_entry(**over) -> dict:
    """在合法骨架上做顶层覆盖，供测试构造反例。

    用它而不是手写字典：手写时若忘记某个键，报错会指向「你少写了一个键」
    而不是「你写的那个键值违规」，测的就不是规则本身了。
    """
    base = entry(
        observation_point("OP-1", "站上 21.00 元", "收盘价 >= 21.00",
                          "收盘价跌破 19.80", "当日 14:30", "QUANTIFIED",
                          "FALSIFIABLE", "PRICE", 21.0),
        action("ACT-1", "stock", "600312", "grid", amount=100,
               amount_unit="shares", price=21.0, base_price=20.4),
        risk("low", max_trade_loss=100, thesis_invalidation="跌破 19.80",
             method_semantics="both", stop_loss=0.05, confidence=0.7,
             limit_conditions=["单日不追高"]),
        requested_position("600312", 100, "shares", "网格第一档 per_trade=100"),
        [invalidation_item("INV-1", "收盘跌破 19.80", "停网格并减半底仓")],
        "SEMANTIC_VERIFIED", "EXTERNAL_PRIMARY", "2026-10-17T14:30:00+08:00",
        "framework/engine/journal", "MODEL_INTUITION",
        [derivation_step("按网格参数挂买", "portfolio.600312.base_price",
                         "action.price")],
        ["framework/engine/journal/validate.py"],
        gates_passed=["GATE_INSTRUMENT_KNOWN", "GATE_LISTING_MATCHES_TRACK"])
    base.update(over)
    return base


__all__ = ["observation_point", "action", "requested_position", "risk",
           "invalidation_item", "derivation_step", "blocked_action", "entry",
           "new_entry"]