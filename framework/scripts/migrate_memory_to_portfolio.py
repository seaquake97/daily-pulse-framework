#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""migrate_memory_to_portfolio.py — MEMORY.md 三表 → portfolio.yaml v2

一次性迁移工具，但必须可复跑且幂等（ADR-007 §4：方向是 MEMORY.md → yaml
一次性迁移，此后 yaml 为准）。因此：
  · 同一 MEMORY.md 两次运行产出**逐字节相同**的 yaml（无时间戳、无随机序）；
  · 只认 --memory 参数，**不读任何隐式默认路径**——静默默认路径是这个工具
    最危险的失败模式（读到别的机器的旧文件还以为迁成功了）；
  · 不覆盖已有 portfolio.yaml，除非显式 --force。

用法
----
    python3 migrate_memory_to_portfolio.py --memory /path/to/MEMORY.md
    python3 migrate_memory_to_portfolio.py --memory <path> --out config/portfolio.yaml
    python3 migrate_memory_to_portfolio.py --memory <path> --dry-run     # 只打印摘要

迁移边界（ADR-007 §2.2 的双轨判据在此落地）：
  · MEMORY.md「股票持仓」表含个股与场内 ETF，一律 listing: exchange → 股票轨
  · MEMORY.md「网格交易参数」表 → stock.grid，行级 '-' 表示 enabled:false
  · MEMORY.md「基金持仓」表 → listing: otc → 基金轨
  · 表中「黄金（非基金）」行 → holdings.gold 单列，**不进 fund.positions**

不迁的列（刻意丢弃，理由见 ARCH-R5-FRAMEWORK.md §2.2）：
现价 / 市值 / 盈亏额 / 盈亏率 / 当日盈亏 / 持有收益 / 昨日收益 / 占纯基金比 /
交易在途金额 —— 全部是每日变量，写进配置必然过期。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from memory_plan_amounts import (  # noqa: E402
    _match_plan_amount, parse_plan_amounts,
)
from yaml_emit import dump_yaml  # noqa: E402

# 定投方式中文 → schema 枚举（schema/definitions.fundPosition.properties.plan）
PLAN_MAP = {
    "智慧定投": "smart",
    "普通定投": "regular",
    "智慧止盈定投": "smart_take_profit",
    "定投持仓": "holding",
    "": "none",
}

# 风控参数与现金：MEMORY.md 未直接给出数值，取保守默认并在 note 中标注
# 「需按个人情况复核」。硬编造用户的风控偏好比留空更危险。
RISK_DEFAULTS = {
    "max_single_position_pct": 20,
    "max_total_drawdown_pct": 15,
    "grid_step_pct_cap": 5,
    "fund_holding_days_min": 7,
}

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _to_float(s: str, default=None):
    m = _NUM.search(str(s).replace(",", "").replace("%", ""))
    return float(m.group(0)) if m else default


def _to_int(s: str, default=None):
    v = _to_float(s)
    return int(v) if v is not None else default



def parse_tables(text: str) -> dict:
    """从 MEMORY.md 抽出三张表。

    按「标题行 + 表格行」定位，不按行号硬编码——MEMORY.md 每次更新都会
    在上文增删段落，按行号读是这类一次性脚本最常见的静默失效来源。
    """
    tables: dict = {}
    for key, header_kw in (("stocks", "股票持仓"),
                           ("grid", "网格交易参数"),
                           ("funds", "基金持仓")):
        tables[key] = _find_table(text, header_kw)
    return tables


def _find_table(text: str, header_kw: str) -> list:
    """找出标题含 header_kw 的那张表，返回去掉表头与分隔行的数据行。"""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.lstrip("# ").startswith(header_kw):
            start = i
            break
    if start is None:
        return []
    rows = []
    seen_sep = False
    for ln in lines[start + 1:]:
        s = ln.strip()
        if not s.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(set(c) <= set("-: ") and c for c in cells):
            seen_sep = True
            continue
        if not seen_sep and rows == []:
            continue                      # 表头行
        rows.append(cells)
    return rows


def _split_holdings(s: str):
    """「持仓/可用」列形如 `100 / 100`、`2300 / 1800`。"""
    parts = [p.strip() for p in str(s).split("/")]
    return _to_int(parts[0], 0), (_to_int(parts[1], 0) if len(parts) > 1 else None)


def _split_range(s: str):
    """「18.50 - 24.50」→ (18.50, 24.50)；`-` → (None, None)。"""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*$", str(s))
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def build_stock_track(rows: list, grid_rows: list) -> dict:
    """MEMORY.md 两表 → holdings.stock。

    网格表的 `证券代码` 带市场前缀（sh600312），持仓表不带。统一按 6 位存，
    校验器会用 codes.py 补全——配置层不冗余存前缀，避免两处写不一致。
    """
    grid_by_code = {}
    for r in grid_rows:
        if len(r) < 5:
            continue
        name = r[0]
        code = re.sub(r"\D", "", r[1])[:6]
        if not code:
            continue
        low, high = _split_range(r[3])
        step = _to_float(r[4])
        grid_by_code[code] = {
            "name": name, "enabled": bool(step and low and high),
            "base_price": _to_float(r[2]) if step else None,
            "range_low": low, "range_high": high,
            "step_pct": step,
            "per_trade": _to_int(re.sub(r"[^\d]", "", r[5])) if step else None,
            "min_position": _to_int(re.sub(r"[^\d]", "", r[6])),
            "max_position": _to_int(re.sub(r"[^\d]", "", r[7])),
            "guide": r[9] if len(r) > 9 else None,
        }

    positions = []
    for r in rows:
        if len(r) < 4:
            continue
        name, code = r[0], re.sub(r"\D", "", r[1])[:6]
        if not code:
            continue
        shares, available = _split_holdings(r[2])
        positions.append({
            "code": code, "name": name, "listing": "exchange",
            "shares": shares, "available": available,
            "cost": _to_float(r[3], 0.0),
            # 股票持仓表第 10 列（索引 9）是「状态/方向」，进 note。
            "note": r[9] if len(r) > 9 and r[9] else None,
        })

    grid = []
    for code, g in grid_by_code.items():
        item = {"code": code, "name": g["name"], "listing": "exchange",
                "enabled": g["enabled"]}
        for k in ("base_price", "range_low", "range_high", "step_pct",
                  "per_trade", "min_position", "max_position", "guide"):
            v = g[k]
            if v is None or (k == "guide" and not v):
                continue
            item[k] = v
        grid.append(item)

    return {"positions": positions, "grid": grid}


def build_fund_track(rows: list, amounts: list) -> tuple:
    """MEMORY.md 基金表 → (fund.positions, fund.plans, gold[])。"""
    positions, plans, gold = [], [], []
    for r in rows:
        if len(r) < 3:
            continue
        name, code_raw, amount = r[0], r[1], _to_float(r[2], 0.0)
        note = r[7] if len(r) > 7 else ""
        if not re.fullmatch(r"\d{6}", code_raw.strip()):
            # 代码列不是 6 位数字 -> 黄金行。MEMORY.md 里黄金代码列为 "-"。
            gold.append({"name": name, "amount": amount,
                         "note": "实物/积存金，非基金，单列统计"})
            continue
        code = code_raw.strip()
        plan = PLAN_MAP.get(note.strip(), "none")
        positions.append({
            "code": code, "name": name, "listing": "otc", "amount": amount,
            "holding_period_days": RISK_DEFAULTS["fund_holding_days_min"],
            "plan": plan, "note": note or None,
        })
        # plans 覆盖全部有定投安排的标的（含普通定投）——只收智慧定投会漏掉
        # 标普500 / 纳指100 / 汇添富 这三笔每日定投，而它们恰恰是定投日历里
        # 频率最高的三笔。金额从散文段按名称匹配回来，匹配不到就留空。
        if plan != "none":
            got = _match_plan_amount(name, amounts)
            lo, hi = got if got else (None, None)
            plans.append({"code": code, "type": plan,
                          "amount_per_period": lo,
                          "amount_per_period_max": hi if hi != lo else None,
                          "day_of_month": None})
    return {"positions": positions, "plans": plans}, gold


def build_portfolio(text: str) -> dict:
    """MEMORY.md 全文 → portfolio v2 dict。"""
    t = parse_tables(text)
    stock = build_stock_track(t["stocks"], t["grid"])
    fund, gold = build_fund_track(t["funds"], parse_plan_amounts(text))
    return {
        "version": 2,
        "profile": {"owner": "portfolio-owner", "base_currency": "CNY",
                    "mode": "personal",
                    "note": "由 MEMORY.md 三表迁移生成，此后以本文件为准"},
        "risk": dict(RISK_DEFAULTS),
        "cash": {"currency": "CNY", "amount": 0,
                 "note": "MEMORY.md 无现金余额字段，请按实际可用现金填写"},
        "holdings": {"stock": stock, "fund": fund, "gold": gold},
    }


HEADER = """本文件由 scripts/migrate_memory_to_portfolio.py 从 MEMORY.md 三表生成。
事实源已从 MEMORY.md 转移到本文件（ADR-007 §4）：此后请改这里，不要改 MEMORY.md。
双轨结构：stock 轨收场内标的（可网格），fund 轨收场外基金（禁网格键）。"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MEMORY.md 三表 → portfolio.yaml v2")
    ap.add_argument("--memory", required=True,
                    help="MEMORY.md 路径（唯一输入，无默认值——静默默认路径会读到错文件）")
    ap.add_argument("--out", default=None, help="输出 yaml 路径（默认打印到 stdout）")
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")
    ap.add_argument("--dry-run", action="store_true", help="只打印解析摘要，不写文件")
    args = ap.parse_args(argv)

    src = Path(args.memory).expanduser()
    if not src.is_file():
        print(f"[fail] MEMORY.md 不存在: {src}", file=sys.stderr)
        return 2
    text = src.read_text(encoding="utf-8")

    cfg = build_portfolio(text)
    h = cfg["holdings"]
    summary = {
        "股票轨持仓": len(h["stock"]["positions"]),
        "网格参数": len(h["stock"]["grid"]),
        "网格启用": len([g for g in h["stock"]["grid"] if g.get("enabled")]),
        "基金轨持仓": len(h["fund"]["positions"]),
        "定投计划": len(h["fund"]["plans"]),
        "黄金条目": len(h["gold"]),
    }

    if args.dry_run:
        print("[dry-run] 解析摘要：")
        for k, v in summary.items():
            print(f"  {k}: {v}")
        return 0

    out_text = dump_yaml(cfg, header=HEADER)
    if args.out:
        dst = Path(args.out).expanduser()
        if dst.exists() and not args.force:
            print(f"[fail] 输出文件已存在: {dst}（加 --force 覆盖）", file=sys.stderr)
            return 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(out_text, encoding="utf-8")
        print(f"[ok] 已生成 {dst}")
    else:
        sys.stdout.write(out_text)
        return 0

    for k, v in summary.items():
        print(f"     {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())