#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""signal_momentum.py — S4 动量确认子模块（v1.3 保守增强）

职责单一：把外部技术面入参（Wilder RSI / 动态乖离率 BIAS / 强势趋势开关）
换算成一个 ∈ [-0.5, +0.5] 的动量确认项，供 compute_signals.py 的 S4 复合使用。

算法契约（与 compute_signals.py 的 S4 公式绑定）：
    s4 = clamp(0.6 * 分化项 + 0.4 * 动量项)
    动量项 = mean(可用分项)，分项来自：
      1) BIAS status 分项（由 technical.calculate_bias 判定，含强势趋势 1.5 倍阈值补偿）
           pullback（回踩）        → +0.3
           normal（正常）          →  0.0
           strong_tracking（强势） → +0.5
           chase_risk（追高）      → -0.5
      2) RSI 分项（Wilder RSI）
           RSI > 70               → -0.3（超买）
           30 <= RSI <= 70        →  0.0
           RSI < 30               → +0.3（超卖）
    未提供任何入参时 evaluate() 返回 None —— S4 保持纯分化（v1.2 行为，逐字节不变）。

依赖：framework/engine/signals/technical.py（纯标准库技术指标库）。
路径推导遵循 A-04：由 __file__ 相对定位，不写死用户名/绝对路径，支持 PULSE_ROOT 覆盖。
"""
from __future__ import annotations

import os
import sys
from collections import namedtuple
from pathlib import Path

# A-04：相对推导 <project>/framework/engine/signals（本文件位于 <project>/_git_engine/scripts）
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = Path(os.environ.get("PULSE_ROOT", str(_HERE.parents[1]))).resolve()
_FRAMEWORK_SIGNALS = _PROJECT_ROOT / "framework" / "engine" / "signals"

if str(_FRAMEWORK_SIGNALS) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_SIGNALS))

try:
    from technical import calculate_bias

    TECHNICAL_IMPORT_ERROR = None
except Exception as _e:  # 引擎独立分发时 framework/ 可能不存在 —— 降级但不静默（见 unavailable_reason）
    calculate_bias = None
    TECHNICAL_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

# --- 权重与阈值常量（单一数据源，禁止在别处重复硬编码） ---
S4_DIVERGENCE_WEIGHT = 0.6
S4_MOMENTUM_WEIGHT = 0.4

BIAS_BASE_THRESHOLD = 0.05          # 与 technical.calculate_bias 的 base_threshold 默认值一致
BIAS_MA_BASE = 100.0                # 由乖离率反推现价的基准均线（bias = price/ma - 1）

RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
RSI_OVERBOUGHT_SCORE = -0.3
RSI_OVERSOLD_SCORE = 0.3

BIAS_STATUS_SCORE = {
    "pullback": 0.3,
    "normal": 0.0,
    "strong_tracking": 0.5,
    "chase_risk": -0.5,
}
BIAS_STATUS_LABEL = {
    "pullback": "回踩",
    "normal": "正常",
    "strong_tracking": "强势追踪",
    "chase_risk": "追高风险",
}

MomentumResult = namedtuple("MomentumResult", "score note bias_status bias_score rsi_score")


class TechnicalUnavailable(RuntimeError):
    """请求了动量确认但技术指标库不可用 —— 必须显式报错，禁止静默降级为纯分化。"""


def unavailable_reason() -> str | None:
    """返回动量确认不可用的原因；可用时返回 None。"""
    if calculate_bias is None:
        return (f"技术指标库不可用（technical.calculate_bias 未载入：{TECHNICAL_IMPORT_ERROR}；"
                f"已尝试路径 {_FRAMEWORK_SIGNALS}）")
    return None


def bias_status_of(bias: float, strong_trend: bool = False) -> str:
    """把乖离率换算成 technical.calculate_bias 的 status（含强势趋势 1.5 倍阈值补偿）。

    只拿到乖离率（price/ma - 1）而没有现价/均线时，取基准均线 BIAS_MA_BASE 反推现价，
    再交给 technical.calculate_bias 判定，保证阈值逻辑与指标库完全一致、不重复实现。
    """
    reason = unavailable_reason()
    if reason:
        raise TechnicalUnavailable(reason)
    price = BIAS_MA_BASE * (1.0 + float(bias))
    return calculate_bias(
        current_price=price,
        ma=BIAS_MA_BASE,
        strong_trend=strong_trend,
        base_threshold=BIAS_BASE_THRESHOLD,
    )["status"]


def rsi_score_of(rsi: float) -> float:
    """Wilder RSI 分项：超买 -0.3 / 超卖 +0.3 / 中性 0.0。"""
    v = float(rsi)
    if v > RSI_OVERBOUGHT:
        return RSI_OVERBOUGHT_SCORE
    if v < RSI_OVERSOLD:
        return RSI_OVERSOLD_SCORE
    return 0.0


def evaluate(rsi: float | None = None, bias: float | None = None,
             strong_trend: bool = False) -> MomentumResult | None:
    """把外部技术面入参换算为动量确认项。

    Returns:
        MomentumResult —— 至少提供了一个入参时；score ∈ [-0.5, +0.5]
        None —— 未提供任何入参，调用方应保持纯分化逻辑（v1.2 行为）
    """
    if rsi is None and bias is None:
        return None

    status = None
    b_score = None
    r_score = None
    terms = []

    if bias is not None:
        status = bias_status_of(bias, strong_trend)
        b_score = BIAS_STATUS_SCORE[status]
        terms.append(b_score)
    if rsi is not None:
        r_score = rsi_score_of(rsi)
        terms.append(r_score)

    score = round(sum(terms) / len(terms), 4)

    parts = []
    if bias is not None:
        parts.append(f"BIAS {float(bias):+.2%} {BIAS_STATUS_LABEL[status]} {b_score:+.2f}")
    if rsi is not None:
        label = "超买" if float(rsi) > RSI_OVERBOUGHT else (
            "超卖" if float(rsi) < RSI_OVERSOLD else "中性")
        parts.append(f"RSI {float(rsi):.1f} {label} {r_score:+.2f}")
    tail = "，取均值" if len(parts) == 2 else ""
    note = f"动量确认 {score:+.2f}（{'；'.join(parts)}{tail}）"

    return MomentumResult(score=score, note=note, bias_status=status,
                          bias_score=b_score, rsi_score=r_score)
