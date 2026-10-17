#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
确定性信号评分 — daily-decision-engine 步骤5
S1量能/S2宽度/S3动量/S4分化/S5资金/S6估值 → Σ → 四档评级。
评级由本代码输出，LLM 禁止参与打分、禁止上调/下调。

用法:
本文件为框架侧 canonical（A-09/F-1）：v1.4.0 由 daily-decision-engine 仓回合（S4 复合动量），同步方向 framework → _engine_stage → GitHub，关系声明见同目录 README.md。
    python3 compute_signals.py <market_data.json> [--kline sh000001_kline.json] [-o out.json]
                              [--rsi 55.0] [--bias 0.03] [--strong-trend]

market_data.json 可选增强字段（有则参与计算，无则标注数据缺口并降权）:
    kline_close: [近30日收盘价...]           # 来自 data_kline
    sector_flows: {"top_inflow": 亿元, "top_outflow": 亿元}

可选技术面入参（S4 动量确认，缺省则 S4 维持纯分化，分项映射见 signal_momentum.py）:
    --rsi 55.0 / --bias 0.03 / --strong-trend
    复合公式：s4 = clamp(0.6 * 分化项 + 0.4 * 动量项)

设计原则（v1.1 修复记录）:
    - S1 用 volume_ratio（量比，已按同时段归一化）而非"半日成交额/全日均值"
    - S3 的 K 线必须按日期升序排序后取 MA 窗口，且剔除当日未完成行
    - S2 宽度项权重 0.7 / 涨跌停项 0.3（原 0.7/0.3 中涨停项 /30 过敏感，改 /50）
    - v1.2: 有效权重 < MIN_DIRECTIONAL_WEIGHT（过半信号缺失）时评级封顶为"信号矛盾"，
      防止单一信号（如仅宽度 S2）主导出方向性结论；verdict 增加 data_insufficient 标记
    - v1.3: S4 保守增强为「分化 + 动量确认」复合信号（见 s4_divergence 文档串）。
      向后兼容铁律：不传 --rsi/--bias 时 S4 与 v1.2 逐字节一致（纯分化，权重/说明不变）。
"""
import argparse
import json
import sys
from pathlib import Path

# A-04：本脚本位于 <project>/_git_engine/scripts，同目录模块与 framework 均相对推导，不写死绝对路径
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    import signal_momentum as _momentum

    _MOMENTUM_IMPORT_ERROR = None
except Exception as _e:  # 载入失败不阻断默认路径（纯分化），仅在显式启用动量时报错退出
    _momentum = None
    _MOMENTUM_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

WEIGHTS = {"S1": 0.20, "S2": 0.20, "S3": 0.15, "S4": 0.15, "S5": 0.15, "S6": 0.15}

# 有效权重低于该值时禁止方向性评级：至少需要 3 个独立维度（如 S1+S2+S3=0.55）
MIN_DIRECTIONAL_WEIGHT = 0.50


def clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def s1_volume(idx, total_yi):
    """量能：沪指量比（相对过去5日同时段，盘中/收盘通用）+ 成交额交叉说明。
    纯流动性信号，不含方向判断（方向由 S3/S4 负责）。"""
    sh = (idx or {}).get("sh000001") or {}
    vr = num(sh.get("volume_ratio"))
    if vr is None:
        return None, "数据缺口：沪指量比缺失，S1降权"
    # 标度 0.8：量比 1.8 饱和（过敏感的 0.5 标度会使 S1 频繁封顶并主导 Σ）
    s = clamp((vr - 1.0) / 0.8)
    note = f"沪指量比 {vr:.2f}（相对过去5日同时段）"
    amt = num(sh.get("amount"))
    if amt and total_yi:
        note += f"；沪指成交额 {amt/1e8:,.0f}亿（两市+北交所 {total_yi:,.0f}亿）"
    return round(s, 3), note


def s2_breadth(mb):
    """宽度：上涨占比为主（0.7），涨跌停差为辅（0.3）。
    中性位 0.48，±0.16 饱和（32% 上涨 ≈ 强普跌）。"""
    up, down = num((mb or {}).get("up")), num((mb or {}).get("down"))
    if not up and not down:
        return None, "数据缺口：涨跌家数缺失"
    total = (up or 0) + (down or 0)
    if total <= 0:
        return None, "数据缺口：涨跌家数无效"
    up_ratio = (up or 0) / total
    lu = num(mb.get("limit_up")) or 0
    ld = num(mb.get("limit_down")) or 0
    s_breadth = clamp((up_ratio - 0.48) / 0.16)
    s_limit = clamp((lu - ld) / 50.0)
    s = clamp(s_breadth * 0.7 + s_limit * 0.3)
    return round(s, 3), (f"上涨占比 {up_ratio*100:.1f}%（{int(up or 0)}/{int(total)}），"
                         f"涨停{int(lu)}-跌停{int(ld)}；宽度项 {s_breadth:+.2f}/涨跌停项 {s_limit:+.2f}")


def s3_momentum(idx, kline_close_sorted, today_str):
    """动量：上证现价 vs MA5/MA20（剔除当日未完成行）+ 20日涨跌幅。"""
    sh = (idx or {}).get("sh000001") or {}
    price = num(sh.get("price"))
    chg20 = num(sh.get("chg_20d"))
    if price is None:
        return None, "数据缺口：上证行情缺失"
    # 仅用历史完整日（日期 < 今日）计算均线
    hist = [c for c in kline_close_sorted if c is not None]
    parts, terms = [], []
    if len(hist) >= 20:
        ma5 = sum(hist[-5:]) / 5
        ma20 = sum(hist[-20:]) / 20
        if ma5 > 0 and ma20 > 0:
            terms.append(clamp((price / ma5 - 1) / 0.02) * 0.5)
            parts.append(f"价格/MA5={price/ma5-1:+.2%}")
            terms.append(clamp((price / ma20 - 1) / 0.04) * 0.5)
            parts.append(f"价格/MA20={price/ma20-1:+.2%}")
    if chg20 is not None:
        terms.append(clamp(chg20 / 5.0))
        parts.append(f"20日涨跌 {chg20:+.2f}%")
    if not terms:
        return None, "数据缺口：缺K线与20日涨跌，S3降权"
    s = clamp(sum(terms) / len(terms))
    return round(s, 3), "，".join(parts)


def s4_divergence(idx, rsi=None, bias=None, strong_trend=False):
    """分化：成长（创业板+科创50）vs 蓝筹（沪深300）。

    v1.3 保守增强：提供技术面入参（--rsi / --bias / --strong-trend）时，
    升级为「分化 + 动量确认」复合信号：
        s4 = clamp(0.6 * 分化项 + 0.4 * 动量项)
    动量项由 signal_momentum.evaluate() 计算（Wilder RSI 超买超卖 + 动态 BIAS 强势补偿）。

    向后兼容铁律：rsi 与 bias 均为 None 时，返回值与说明文案与 v1.2 完全一致（纯分化）。
    数据缺口优先：指数缺失时无论是否提供技术面入参，一律返回 None + 缺口提示。
    """
    cy = num((idx.get("sz399006") or {}).get("change_percent"))
    kc = num((idx.get("sh000688") or {}).get("change_percent"))
    hs = num((idx.get("sh000300") or {}).get("change_percent"))
    if None in (cy, kc, hs):
        return None, "数据缺口：成长/蓝筹指数缺失"
    spread = (cy + kc) / 2 - hs
    s = clamp(spread / 2.0)
    note = f"成长均值 {(cy+kc)/2:+.2f}% vs 沪深300 {hs:+.2f}%，价差 {spread:+.2f}pct"

    momentum = None
    if rsi is not None or bias is not None:
        if _momentum is None:  # 显式启用但模块不可用：报错，禁止静默降级回纯分化
            raise RuntimeError(f"S4 动量确认不可用：{momentum_unavailable_reason()}")
        momentum = _momentum.evaluate(rsi=rsi, bias=bias, strong_trend=strong_trend)
    if momentum is None:
        return round(s, 3), note

    s = clamp(_momentum.S4_DIVERGENCE_WEIGHT * s + _momentum.S4_MOMENTUM_WEIGHT * momentum.score)
    return round(s, 3), f"{note}；{momentum.note}"


def momentum_unavailable_reason() -> "str | None":
    """动量确认不可用的原因（None = 可用）。用于显式启用时先做前置校验，禁止静默降级。"""
    if _momentum is None:
        return f"动量模块 signal_momentum.py 未载入（{_MOMENTUM_IMPORT_ERROR}）"
    return _momentum.unavailable_reason()


def s5_funds_flow(sector):
    """资金：板块主力净流入TOP1 - 净流出TOP1。"""
    if not sector:
        return None, "数据缺口：板块资金流缺失，S5降权"
    ti = num(sector.get("top_inflow"))
    to = num(sector.get("top_outflow"))
    if ti is None and to is None:
        return None, "数据缺口：板块资金流无效"
    net = (ti or 0) - abs(to or 0)
    s = clamp(net / 50.0)
    return round(s, 3), f"主力净流入TOP1（{sector.get('inflow_name','?')}）{ti}亿 - 净流出TOP1（{sector.get('outflow_name','?')}）{to}亿 = 净差 {net}亿"


def s6_valuation(idx):
    """估值：沪深300 PE 绝对水平 + 60日涨跌幅（超跌代理）。"""
    hs = (idx or {}).get("sh000300") or {}
    pe = num(hs.get("pe_ratio"))
    chg60 = num(hs.get("chg_60d"))
    if pe is None:
        return None, "数据缺口：沪深300 PE 缺失"
    s_pe = clamp((15.0 - pe) / 3.0)
    parts = [f"沪深300 PE {pe:.2f}（15为中性，12以下+1/16以上-1）"]
    if chg60 is not None:
        s_pe = clamp(s_pe + clamp(-chg60 / 10.0) * 0.5)
        parts.append(f"60日涨跌 {chg60:+.2f}%（超跌加分项）")
    return round(s_pe, 3), "，".join(parts)


def rating_of(sigma, w_sum=1.0):
    """四档评级。w_sum < MIN_DIRECTIONAL_WEIGHT 时封顶为信号矛盾：
    证据不足（过半信号缺失）禁止给方向，只允许列多空证据+缺口清单。"""
    if w_sum < MIN_DIRECTIONAL_WEIGHT:
        return "信号矛盾"
    if sigma >= 0.50:
        return "进攻"
    if sigma >= 0.15:
        return "均衡"
    if sigma > -0.15:
        return "信号矛盾"
    if sigma > -0.50:
        return "防守"
    return "回避"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--kline", default=None, help="sh000001 日K JSON（data_kline 输出，兼容升/降序）")
    ap.add_argument("--rsi", type=float, default=None,
                    help="Wilder RSI（0~100）；>70 超买 -0.3，<30 超卖 +0.3，启用 S4 动量确认")
    ap.add_argument("--bias", type=float, default=None,
                    help="乖离率（0.03 = +3%%）；由 technical.calculate_bias 判定 status，启用 S4 动量确认")
    ap.add_argument("--strong-trend", action="store_true",
                    help="强势趋势开关：BIAS 阈值放宽 1.5 倍，需配合 --bias 生效")
    ap.add_argument("-o", "--output", default=None)
    args = ap.parse_args()

    # 技术面入参合法性：非法值直接失败退出，禁止静默截断或按默认值继续算
    if args.rsi is not None and not (0.0 <= args.rsi <= 100.0):
        print(f"⛔ --rsi 非法：{args.rsi}（RSI 取值应在 0~100）")
        sys.exit(2)
    if args.bias is not None and args.bias <= -1.0:
        print(f"⛔ --bias 非法：{args.bias}（乖离率必须 > -1.0，否则反推现价非正）")
        sys.exit(2)

    momentum_requested = args.rsi is not None or args.bias is not None
    if momentum_requested:
        reason = momentum_unavailable_reason()
        if reason:
            print(f"⛔ S4 动量确认不可用：{reason}")
            print("   （不传 --rsi/--bias 时 S4 走纯分化，不依赖技术指标库）")
            sys.exit(2)
        if args.strong_trend and args.bias is None:
            print("⚠️ --strong-trend 需配合 --bias 生效：本次未提供 --bias，S4 走纯分化")
    elif args.strong_trend:
        print("⚠️ --strong-trend 需配合 --bias 生效：本次未提供 --rsi/--bias，S4 走纯分化")

    with open(args.path, "r", encoding="utf-8") as f:
        data = json.load(f)

    kline_close_sorted = []
    if args.kline:
        try:
            with open(args.kline, "r", encoding="utf-8") as f:
                kl = json.load(f)
            # 兼容三种输入形态：
            # ① data_kline 原始输出 {"ok":true,"data":{"nodes":[{date,last,...}]}}
            # ② {"data":[{date,close/last,...}]}
            # ③ 裸列表 [{date,close},...]
            rows = kl
            if isinstance(kl, dict):
                rows = kl.get("data", kl)
                if isinstance(rows, dict):
                    rows = rows.get("nodes", rows)
            if isinstance(rows, list):
                parsed = []
                for r in rows:
                    if isinstance(r, dict):
                        # MCP data_kline 的收盘价字段是 last，旧管道/手工 JSON 用 close，双兼容
                        c = r.get("close")
                        if c is None:
                            c = r.get("last")
                        d = r.get("date")
                        c = num(c)
                    else:
                        d, c = None, num(r)
                    if c:
                        parsed.append((str(d) if d else "", c))
                parsed.sort(key=lambda x: x[0])  # 升序，防御降序输入
                today = str(data.get("date", ""))
                # 剔除当日未完成行，均线只用完整历史日
                kline_close_sorted = [c for d, c in parsed if d != today]
                if not parsed:
                    print("⚠️ K线解析到 0 行：检查字段名（应为 date + close/last）")
                elif not kline_close_sorted:
                    print("⚠️ K线剔除当日后无历史行：检查 date 字段")
        except Exception as e:
            print(f"⚠️ K线加载失败: {e}")

    idx = data.get("indices") or {}
    mb = data.get("market_breadth") or {}
    sector = data.get("sector_flows") or {}

    signals, notes = {}, {}
    signals["S1"], notes["S1"] = s1_volume(idx, num(data.get("total_amount_yi")))
    signals["S2"], notes["S2"] = s2_breadth(mb)
    signals["S3"], notes["S3"] = s3_momentum(idx, kline_close_sorted, str(data.get("date", "")))
    signals["S4"], notes["S4"] = s4_divergence(idx, rsi=args.rsi, bias=args.bias,
                                               strong_trend=args.strong_trend)
    signals["S5"], notes["S5"] = s5_funds_flow(sector)
    signals["S6"], notes["S6"] = s6_valuation(idx)

    valid = {k: v for k, v in signals.items() if v is not None}
    w_sum = sum(WEIGHTS[k] for k in valid)
    sigma = sum(WEIGHTS[k] * v for k, v in valid.items()) / w_sum if w_sum else 0.0
    sigma = round(sigma, 3)

    verdict = {
        "rating": rating_of(sigma, w_sum),
        "sigma": sigma,
        "signals": {k: signals[k] for k in signals},
        "weights": WEIGHTS,
        "valid_weight": round(w_sum, 3),
        "data_insufficient": w_sum < MIN_DIRECTIONAL_WEIGHT,
        "notes": notes,
        "degraded": [k for k, v in signals.items() if v is None],
    }

    # 仅在显式启用动量时追加可审计元数据；纯分化模式下 verdict 结构与 v1.2 完全一致
    if momentum_requested:
        mr = _momentum.evaluate(rsi=args.rsi, bias=args.bias, strong_trend=args.strong_trend)
        if mr is not None:
            verdict["s4_technical"] = {
                "rsi": args.rsi,
                "bias": args.bias,
                "strong_trend": args.strong_trend,
                "bias_status": mr.bias_status,
                "bias_score": mr.bias_score,
                "rsi_score": mr.rsi_score,
                "momentum": mr.score,
                "divergence_weight": _momentum.S4_DIVERGENCE_WEIGHT,
                "momentum_weight": _momentum.S4_MOMENTUM_WEIGHT,
            }

    print("=== 信号评分（代码计算，LLM 禁改） ===")
    for k in ["S1", "S2", "S3", "S4", "S5", "S6"]:
        v = signals[k]
        mark = f"{v:+.3f}" if v is not None else " 缺失 "
        print(f"  {k} [{WEIGHTS[k]:.2f}] {mark}  {notes[k]}")
    print(f"\n  Σ = {sigma:+.3f}（有效权重 {w_sum:.2f}）→ 评级: 【{verdict['rating']}】")
    if verdict["degraded"]:
        print(f"  ⚠️ 降级信号: {verdict['degraded']}（已在归一化中降权）")
    if verdict["data_insufficient"]:
        print(f"  ⛔ 有效权重 {w_sum:.2f} < {MIN_DIRECTIONAL_WEIGHT:.2f}：证据不足，"
              f"评级封顶为【信号矛盾】，禁止给方向性结论（决策卡只列多空证据+缺口清单）")
    print("\n  四档口径: Σ≥0.50进攻 / 0.15~0.50均衡 / -0.15~0.15信号矛盾 / -0.50~-0.15防守 / Σ≤-0.50回避")
    if verdict["rating"] == "信号矛盾":
        print("  ⚠️ 信号矛盾档：只允许列多空证据清单+明日待验证信号，禁止给方向、禁止表述为均衡")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(verdict, f, ensure_ascii=False, indent=2)
        print(f"\n✅ verdict 已写入: {args.output}")

    try:
        data["verdict"] = verdict
        with open(args.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ verdict 已合入: {args.path}")
    except Exception as e:
        print(f"⚠️ 合入 market_data.json 失败: {e}")


if __name__ == "__main__":
    main()
