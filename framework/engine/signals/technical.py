#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""technical.py — 确定性技术分析指标计算库（纯 Python 标准库，零第三方依赖）

架构对齐：
  参考 ZhuLinsen/daily_stock_analysis 中 src/stock_analyzer.py 的技术指标算法，
  完全移除对 pandas / numpy 等重型依赖，使用原生 Python 列表与浮点数实现。
  保证在未安装三方库的裸环境或沙箱中具备 100% 确定性输出。

核心能力：
  1. 移动平均线 (MA5 / MA10 / MA20 / MA60)
  2. 动态乖离率 (BIAS) 与强势趋势补偿算法（避免龙头踏空）
  3. Wilder's SMMA 平滑 RSI（6日、12日、14日、24日）
  4. 确定性 MACD (DIF, DEA, BAR)
"""
from __future__ import annotations


def calculate_ma(prices: list[float], window: int) -> list[float | None]:
    """计算滑动移动平均线（MA）。

    Args:
        prices: 按时间升序排列的价格序列（末尾为最新价）。
        window: 平滑窗口期，如 5, 10, 20, 60。

    Returns:
        与 prices 等长的列表，数据不足 window 个时该位置为 None。
    """
    if window <= 0:
        raise ValueError("window 必须大于 0")
    n = len(prices)
    result: list[float | None] = [None] * n
    if n < window:
        return result

    running_sum = sum(prices[:window])
    result[window - 1] = round(running_sum / window, 4)

    for i in range(window, n):
        running_sum += prices[i] - prices[i - window]
        result[i] = round(running_sum / window, 4)

    return result


def calculate_bias(
    current_price: float,
    ma: float,
    strong_trend: bool = False,
    base_threshold: float = 0.05,
) -> dict[str, float | str | bool]:
    """计算价格相对均线的乖离率（BIAS），并执行动态强势趋势补偿。

    算法原理：
      - 基础阈值默认为 5%（严进策略，防止追高）；
      - 强势趋势补偿：当 strong_trend=True（如龙头突破、单边主升）时，
        有效阈值自动放宽 1.5 倍（至 7.5%），允许在主升浪中顺势追踪。

    Returns:
        dict:
          - bias: 乖离率数值（如 0.032 表示 +3.2%）
          - threshold: 当前生效的阈值
          - strong_compensated: 是否触发强势放宽
          - status: 'pullback' (回踩), 'normal' (正常区间),
                    'strong_tracking' (强势追踪中), 'chase_risk' (高位追高风险)
    """
    if ma <= 0:
        raise ValueError("均线 ma 必须大于 0")

    bias = round((current_price / ma) - 1.0, 5)
    effective_threshold = round(base_threshold * 1.5, 5) if strong_trend else base_threshold

    status = "normal"
    if bias < 0:
        status = "pullback"
    elif bias > effective_threshold:
        status = "chase_risk"
    elif bias > base_threshold and strong_trend:
        status = "strong_tracking"
    else:
        status = "normal"

    return {
        "bias": bias,
        "threshold": effective_threshold,
        "strong_compensated": strong_trend,
        "status": status,
    }


def calculate_wilder_rsi(prices: list[float], period: int = 14) -> list[float | None]:
    """计算 Wilder's 平滑移动平均（SMMA / Wilder's EMA）RSI。

    递推机制：
      - 第一个 avg_gain / avg_loss 采用前 period 个价差的简单平均；
      - 后续每个时点采用 Wilder's 平滑：
          avg_gain = (prev_avg_gain * (period - 1) + current_gain) / period
          avg_loss = (prev_avg_loss * (period - 1) + current_loss) / period
    """
    if period <= 0:
        raise ValueError("period 必须大于 0")
    n = len(prices)
    result: list[float | None] = [None] * n
    if n <= period:
        return result

    deltas = [prices[i] - prices[i - 1] for i in range(1, n)]

    # 首个周期的平均增益与损失
    gains = [max(d, 0.0) for d in deltas[:period]]
    losses = [max(-d, 0.0) for d in deltas[:period]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    def _to_rsi(g: float, l: float) -> float:
        if l == 0.0 and g == 0.0:
            return 50.0
        if l == 0.0:
            return 100.0
        if g == 0.0:
            return 0.0
        rs = g / l
        return round(100.0 - (100.0 / (1.0 + rs)), 2)

    result[period] = _to_rsi(avg_gain, avg_loss)

    for i in range(period, len(deltas)):
        d = deltas[i]
        curr_gain = max(d, 0.0)
        curr_loss = max(-d, 0.0)
        avg_gain = (avg_gain * (period - 1) + curr_gain) / period
        avg_loss = (avg_loss * (period - 1) + curr_loss) / period
        result[i + 1] = _to_rsi(avg_gain, avg_loss)

    return result


def calculate_macd(
    prices: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> list[dict[str, float] | None]:
    """计算 MACD 指标（DIF, DEA, BAR）。

    EMA 权重计算：alpha = 2.0 / (span + 1.0)
    DIF = EMA(fast) - EMA(slow)
    DEA = EMA(DIF, signal)
    BAR = (DIF - DEA) * 2.0
    """
    if fast <= 0 or slow <= 0 or signal <= 0:
        raise ValueError("fast, slow, signal 参数均必须大于 0")
    if fast >= slow:
        raise ValueError("fast 周期必须小于 slow 周期")

    n = len(prices)
    result: list[dict[str, float] | None] = [None] * n
    if n < slow:
        return result

    def _calc_ema_series(series: list[float], span: int) -> list[float]:
        alpha = 2.0 / (span + 1.0)
        ema = [series[0]]
        for val in series[1:]:
            ema.append(ema[-1] * (1.0 - alpha) + val * alpha)
        return ema

    ema_fast = _calc_ema_series(prices, fast)
    ema_slow = _calc_ema_series(prices, slow)

    dif_series = [round(f - s, 4) for f, s in zip(ema_fast, ema_slow)]

    # DEA 采用 DIF 的 EMA(signal)
    alpha_sig = 2.0 / (signal + 1.0)
    dea_series = [dif_series[0]]
    for d in dif_series[1:]:
        dea_series.append(dea_series[-1] * (1.0 - alpha_sig) + d * alpha_sig)

    for i in range(slow - 1, n):
        dif_val = dif_series[i]
        dea_val = round(dea_series[i], 4)
        bar_val = round((dif_val - dea_val) * 2.0, 4)
        result[i] = {
            "dif": dif_val,
            "dea": dea_val,
            "bar": bar_val,
        }

    return result
