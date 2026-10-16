#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
观点台账结算器 — daily-decision-engine 步骤7
读取 archive/<T-1>/viewpoint.json 与今日 market_data.json，按三态结算昨日观点，
输出命中率统计。可追责、可复盘，杜绝"昨天说啥今天忘"。

用法:
    python3 settle_viewpoints.py --archive <归档根目录> --today YYYY-MM-DD [--market-data <path>]

viewpoint.json 格式（由当日任务生成）:
{
  "date": "YYYY-MM-DD",
  "verdict": {"rating": "防守", "sigma": -0.28},
  "viewpoints": [
    {
      "id": "V1",
      "claim": "若两市成交额跌破1.5万亿，则轮动动能受阻，暂停主动买入",
      "type": "conditional",
      "condition": {"metric": "total_amount_yi", "op": "<", "value": 15000},
      "action": "暂停主动买入，仅保留定投",
      "status": "pending"     # 次日由本脚本结算
    }
  ]
}
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta


def num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def get_metric(market, metric):
    """从今日 market_data.json 提取指标值。"""
    if metric == "total_amount_yi":
        return num(market.get("total_amount_yi"))
    if metric.startswith("idx:"):
        # idx:sh000001.change_percent；畸形指标名返回 None（该条记 UNEVALUABLE，不拖垮整体结算）
        parts = metric[4:].split(".")
        if len(parts) != 2:
            return None
        code, field = parts
        item = (market.get("indices") or {}).get(code) or {}
        return num(item.get(field))
    if metric.startswith("mb:"):
        return num((market.get("market_breadth") or {}).get(metric[3:]))
    if metric.startswith("hd:"):
        return num((market.get("holdings") or {}).get(metric[3:], {}).get("price")
                   if isinstance((market.get("holdings") or {}).get(metric[3:]), dict) else None)
    return None


def evaluate(vp, market):
    """单条观点四态结算。返回 (status, detail)。"""
    cond = vp.get("condition") or {}
    metric, op, target = cond.get("metric"), cond.get("op"), num(cond.get("value"))
    # eval_at 时点对齐（v1.3 终验修复）：收盘时点观点遇到非收盘数据 → UNEVALUABLE，
    # 防止 11:00/14:30 盘中任务用盘中价误触发收盘观点（原脚本完全忽略 eval_at）
    eval_at = vp.get("eval_at")
    stage = market.get("data_stage")
    if eval_at == "close" and stage not in (None, "close"):
        return "UNEVALUABLE", f"观点评估时点为 close，今日数据时点为 {stage}，防盘中数据误触发"
    actual = get_metric(market, metric) if metric else None
    if actual is None or target is None:
        return "UNEVALUABLE", f"指标 {metric} 今日数据缺失（实际值 {actual}）"
    ok_map = {
        "<": actual < target,
        "<=": actual <= target,
        ">": actual > target,
        ">=": actual >= target,
        "==": abs(actual - target) < 1e-9,
    }
    hit = ok_map.get(op)
    if hit is None:
        return "UNEVALUABLE", f"不支持的比较符 {op}"
    return ("TRIGGERED", f"{metric} 实际 {actual} {op} {target} 成立") if hit \
        else ("NOT_TRIGGERED", f"{metric} 实际 {actual} 未满足 {op} {target}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", required=True, help="归档根目录（含 YYYY-MM-DD 子目录）")
    ap.add_argument("--today", required=True, help="今日 YYYY-MM-DD")
    ap.add_argument("--market-data", default=None, help="今日 market_data.json（缺省自动找 archive/<today>/）")
    args = ap.parse_args()

    today = datetime.strptime(args.today, "%Y-%m-%d")
    yday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    # 跳过周末找上一个交易日存档（粗粒度：向前找最多4天）
    prev_path = None
    for back in range(1, 5):
        cand = os.path.join(args.archive, (today - timedelta(days=back)).strftime("%Y-%m-%d"), "viewpoint.json")
        if os.path.exists(cand):
            prev_path = cand
            break

    market_path = args.market_data or os.path.join(args.archive, args.today, "market_data.json")
    market = load_json(market_path)

    if not prev_path:
        print(f"📭 未找到昨日观点台账（向前4日无存档）→ 台账显示「待建立」")
        print(json.dumps({"status": "no_ledger", "today": args.today}, ensure_ascii=False))
        return
    if not market:
        print(f"🚫 今日 market_data.json 缺失或损坏: {market_path} → 无法结算，全部观点记 UNEVALUABLE")
        print(json.dumps({"status": "unevaluable_all", "today": args.today}, ensure_ascii=False))
        return

    prev = load_json(prev_path)
    vps = prev.get("viewpoints") or []
    settled = []
    for vp in vps:
        if vp.get("type") == "conditional":
            status, detail = evaluate(vp, market)
        elif vp.get("type") == "directional":
            # 方向性观点：claim 中含方向词，需人工/LLM 判定 → 标记为 NEEDS_JUDGMENT
            status, detail = "NEEDS_JUDGMENT", "方向性观点需结合盘面人工判定"
        else:
            status, detail = "UNEVALUABLE", "未知观点类型"
        settled.append({**vp, "status": status, "settle_detail": detail})

    counts = {"TRIGGERED": 0, "NOT_TRIGGERED": 0, "UNEVALUABLE": 0, "NEEDS_JUDGMENT": 0, "MISSED_NEUTRAL": 0}
    for s in settled:
        counts[s["status"]] += 1

    # MISSED_NEUTRAL（漏报）判定：昨日全中性/无实质观点，而期间波动超阈值 → 骑墙被定价
    neutral_only = len(vps) == 0 or all(
        vp.get("type") == "neutral" or not vp.get("condition") for vp in vps)
    if neutral_only and market:
        sh_today = num((market.get("indices") or {}).get("sh000001", {}).get("change_percent"))
        hs300_today = num((market.get("indices") or {}).get("sh000300", {}).get("change_percent"))
        vol_proxy = abs(sh_today or 0) + abs(hs300_today or 0)
        if vol_proxy > 1.0:
            settled.append({
                "id": "MN1",
                "claim": "昨日未出具带条件的方向性观点（全中性）",
                "type": "meta",
                "status": "MISSED_NEUTRAL",
                "settle_detail": f"期间指数波动代理 {vol_proxy:.2f}pct > 1.0 阈值，中性观点记为漏报",
            })
            counts["MISSED_NEUTRAL"] += 1

    # HIT 判定：条件触发即 HIT（条件已含方向语义）
    hits = counts["TRIGGERED"]
    evaluable = counts["TRIGGERED"] + counts["NOT_TRIGGERED"]
    hit_rate = f"{hits/evaluable*100:.0f}%" if evaluable else "样本不足"

    # 三维分统：按观点类型分层
    by_type = {}
    for s in settled:
        t = s.get("type", "unknown")
        by_type.setdefault(t, {"hit": 0, "total": 0})
        by_type[t]["total"] += 1
        if s["status"] == "TRIGGERED":
            by_type[t]["hit"] += 1

    out = {
        "status": "settled",
        "today": args.today,
        "ledger_date": prev.get("date"),
        "counts": counts,
        "hits": hits,
        "evaluable": evaluable,
        "hit_rate": hit_rate,
        "by_type": by_type,
        "viewpoints": settled,
    }
    print("=== 昨日观点兑现结算（四态） ===")
    for s in settled:
        icon = {"TRIGGERED": "✅", "NOT_TRIGGERED": "❌", "UNEVALUABLE": "⚠️",
                "NEEDS_JUDGMENT": "🔶", "MISSED_NEUTRAL": "🕳️"}[s["status"]]
        print(f"  {icon} [{s.get('id')}] {s.get('claim', '')[:60]}")
        print(f"      → {s['status']}: {s.get('settle_detail', '')}")
    print(f"\n  命中 {hits}/{evaluable}，命中率 {hit_rate}，条件未触发 {counts['NOT_TRIGGERED']}，"
          f"无法评估 {counts['UNEVALUABLE']}，漏报 {counts['MISSED_NEUTRAL']}")
    print("  分类型命中率: " + "，".join(
        f"{t} {v['hit']}/{v['total']}" for t, v in by_type.items() if v["total"]))
    if evaluable and hits / evaluable < 0.5:
        print("  🚨 滚动命中率 <50%：报告头部必须标注「策略引擎校准中」，并提示人工复核信号权重")
    if counts["MISSED_NEUTRAL"]:
        print("  🕳️ 昨日全中性被记为漏报——骑墙有成本，倒逼差异化输出")

    out_path = os.path.join(args.archive, args.today, "settlement.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 结算结果已写入: {out_path}")


if __name__ == "__main__":
    main()
