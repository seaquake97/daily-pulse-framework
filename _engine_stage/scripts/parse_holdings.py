#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MEMORY.md 持仓动态解析器 — daily-decision-engine 步骤4
从用户级 MEMORY.md 提取股票持仓、网格参数、基金持仓，输出结构化 holdings.json。
禁止在任务代码/提示词中写死持仓——本脚本是唯一事实源。

用法:
    python3 parse_holdings.py [--memory <path>] [-o holdings.json] [--codes-only]
"""
import argparse
import json
import os
import re
import sys


def _resolve_memory_path(cli_value: str | None) -> str | None:
    """持仓记忆文件解析（A-05）：仅接受显式来源，无隐式默认。

    优先级：--memory 命令行参数 > DECISION_ENGINE_MEMORY 环境变量。
    两者皆空即返回 None，由 main() 报错退出——绝不静默读取任何私人
    记忆文件（旧实现回退 ./holdings-memory.md，仍属隐式默认，已移除）。
    """
    if cli_value:
        return cli_value
    return os.environ.get("DECISION_ENGINE_MEMORY")


def to_float(s):
    if s is None:
        return None
    s = str(s).replace(",", "").replace("，", "").replace("元", "").replace("%", "").strip()
    s = re.sub(r"[+＋]", "", s)
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def to_int(s):
    v = to_float(s)
    return int(v) if v is not None else None


def full_code(raw, market_hint=None):
    """6位代码 → 带市场前缀（sh/sz/bj）。"""
    raw = str(raw).strip()
    m = re.match(r"^(sh|sz|bj)(\d{6})$", raw)
    if m:
        return raw.lower()
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 6:
        return None
    if digits.startswith(("60", "68", "9", "50", "51", "52", "58")):
        return f"sh{digits}"
    if digits.startswith(("00", "30", "15", "16", "56")):
        return f"sz{digits}"
    if digits.startswith("4") or digits.startswith("8"):
        return f"bj{digits}"
    return None


def parse_tables(md_text):
    """提取所有 markdown 表格为 [[cells,...],...] 列表（按表格分组）。"""
    lines = md_text.splitlines()
    tables, cur = [], []
    for ln in lines:
        s = ln.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            cur.append(cells)
        else:
            if len(cur) >= 2:
                tables.append(cur)
            cur = []
    if len(cur) >= 2:
        tables.append(cur)
    return tables


def classify_table(header):
    h = " ".join(header)
    if "证券代码" in h and "网格步长" in h:
        return "grid"
    if "占纯基金比" in h or ("昨日收益" in h and "定投" in h):
        return "funds"
    if "盈亏率" in h and ("持仓/可用" in h or "成本" in h):
        return "stocks"
    return None


def parse_stocks(rows):
    out = []
    for r in rows[1:]:
        if len(r) < 9:
            continue
        code = full_code(r[1])
        if not code:
            continue
        out.append({
            "name": r[0],
            "code": code,
            "raw_code": r[1],
            "shares": to_int((r[2] or "").split("/")[0]),
            "available": to_int((r[2] or "").split("/")[-1]),
            "cost": to_float(r[3]),
            "market_value": to_float(r[5]),
            "pnl": to_float(r[6]),
            "pnl_pct": to_float(r[7]),
            "note": r[9] if len(r) > 9 else "",
        })
    return out


def parse_grid(rows):
    out = []
    for r in rows[1:]:
        if len(r) < 8:
            continue
        code = full_code(r[1])
        if not code:
            continue
        rng = (r[3] or "").replace(" ", "")
        lo = hi = None
        m = re.match(r"([\d.]+)-([\d.]+)", rng)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
        out.append({
            "name": r[0],
            "code": code,
            "base_price": to_float(r[2]),
            "range_low": lo,
            "range_high": hi,
            "step_pct": to_float(r[4]),
            "per_trade": r[5],
            "min_position": r[6],
            "max_position": r[7],
            "guide": r[9] if len(r) > 9 else "",
        })
    return out


def parse_funds(rows):
    out = []
    for r in rows[1:]:
        if len(r) < 6:
            continue
        code = r[1].strip()
        if code in ("-", ""):
            # 黄金等非基金行：代码为空，按名称归类
            if "黄金" in r[0]:
                out.append({"name": r[0], "code": "GOLD", "amount": to_float(r[2]),
                            "pnl": to_float(r[3]), "note": r[7] if len(r) > 7 else ""})
            continue
        if not re.fullmatch(r"\d{6}", code):
            continue
        out.append({
            "name": r[0],
            "code": code,
            "amount": to_float(r[2]),
            "pnl": to_float(r[3]),
            "yesterday_pnl": to_float(r[4]),
            "weight_pct": to_float(r[5]),
            "pending": r[6],
            "note": r[7] if len(r) > 7 else "",
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--memory", default=None,
                   help="持仓记忆文件（MEMORY.md）路径；亦可用环境变量 "
                        "DECISION_ENGINE_MEMORY 指定。二者皆缺则报错退出，"
                        "不读取任何隐式默认文件（A-05）。")
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--codes-only", action="store_true", help="只输出需要行情的代码清单")
    args = ap.parse_args()

    memory = _resolve_memory_path(args.memory)
    if not memory:
        print("❌ 未指定持仓记忆文件：请通过 --memory <路径> 显式传入，"
              "或设置环境变量 DECISION_ENGINE_MEMORY。不读取任何隐式默认文件（A-05）。",
              file=sys.stderr)
        sys.exit(2)
    try:
        with open(memory, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"❌ 记忆文件不存在: {memory}", file=sys.stderr)
        sys.exit(2)

    tables = parse_tables(text)
    stocks, grid, funds = [], [], []
    for t in tables:
        kind = classify_table(t[0])
        if kind == "stocks":
            stocks += parse_stocks(t)
        elif kind == "grid":
            grid += parse_grid(t)
        elif kind == "funds":
            funds += parse_funds(t)

    result = {
        "source": args.memory,
        "stocks": stocks,
        "grid": grid,
        "funds": funds,
        "summary": {
            "stock_count": len(stocks),
            "stock_market_value": round(sum(s["market_value"] or 0 for s in stocks), 2),
            "fund_count": len([f for f in funds if f["code"] != "GOLD"]),
            "fund_amount": round(sum(f["amount"] or 0 for f in funds if f["code"] != "GOLD"), 2),
            "gold_amount": round(sum(f["amount"] or 0 for f in funds if f["code"] == "GOLD"), 2),
        },
    }

    if not stocks and not funds:
        print("❌ 未解析到任何持仓表——请检查 MEMORY.md 表格格式是否变更", file=sys.stderr)
        sys.exit(1)

    if args.codes_only:
        codes = [s["code"] for s in stocks]
        print(",".join(codes))
        return

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"✅ holdings.json 已写入: {args.output}")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"股票 {result['summary']['stock_count']} 只 / 基金 {result['summary']['fund_count']} 只 / 黄金 {result['summary']['gold_amount']} 元")
    # 自检：市值与金额合理性
    if result["summary"]["stock_market_value"] <= 0 or result["summary"]["fund_amount"] <= 0:
        print("⚠️ 持仓金额异常（<=0），请人工复核 MEMORY.md", file=sys.stderr)
        sys.exit(1)
    print("🎉 持仓解析通过。")


if __name__ == "__main__":
    main()
