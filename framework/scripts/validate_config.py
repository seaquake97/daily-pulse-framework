#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_config.py — 统一持仓数据仓校验器 CLI（纯标准库，零第三方依赖）

职责边界（单一职责）：只做「读配置 → 调规则 → 输出结果」。依赖图为四层叶子：
  · yaml_min.py   YAML 子集解析 + 路径→行号索引（无内部依赖）
  · codes.py      证券代码规范化（无内部依赖，与 parse_holdings.py 对齐）
  · rules*.py     校验规则集（依赖 codes）
  · 本文件        CLI 门面：读文件、调规则、输出。不含业务规则

v2 变更：portfolio.yaml 双轨结构；错误带行号与稳定错误码；
--export 导出标准化 holdings.json（含 track 字段）。

用法
----
    python3 validate_config.py --config config/portfolio.yaml
    python3 validate_config.py --config config/portfolio.yaml --json      # 机器可读
    python3 validate_config.py --config config/portfolio.yaml --quiet     # 只报错误
    python3 validate_config.py --config config/portfolio.yaml --strict    # 警告也算失败
    python3 validate_config.py --config config/portfolio.yaml --export out.json

退出码：0 通过 / 1 校验失败 / 2 文件或解析错误
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codes import code_mismatch, market_of, normalize_code  # noqa: E402
from rules import SCHEMA_VERSION, Report, build_summary, validate  # noqa: E402
from yaml_min import (  # noqa: E402
    ConfigError, parse_yaml_subset, parse_yaml_subset_indexed,
)

# 对外 API 单一入口：以下名字从下层 re-export，调用方只需 import 本模块
__all__ = ["SCHEMA_VERSION", "Report", "build_summary", "validate",
           "build_export", "normalize_code", "code_mismatch", "market_of",
           "parse_yaml_subset", "parse_yaml_subset_indexed", "ConfigError",
           "main"]

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "config" / "schema.json"


def build_export(cfg: dict) -> dict:
    """导出标准化 holdings.json：每个标的带 track 字段。

    track 让下游任务不必靠「在哪个段里」反推轨道——双轨隔离的判定结果
    直接落进产物，研判脚本读 track 即可分轨，不用重新解析结构。
    """
    hold = (cfg or {}).get("holdings") or {}
    stock = hold.get("stock") or {}
    fund = hold.get("fund") or {}
    grid_by_code = {}
    for g in stock.get("grid") or []:
        if isinstance(g, dict) and g.get("code"):
            grid_by_code[normalize_code(g.get("code"))] = g
    items = []
    for s in stock.get("positions") or []:
        if not isinstance(s, dict):
            continue
        norm = normalize_code(s.get("code", ""))
        g = grid_by_code.get(norm, {})
        items.append({
            "track": "stock", "listing": "exchange", "code": norm,
            "name": s.get("name"), "shares": s.get("shares"),
            "available": s.get("available", s.get("shares")),
            "cost": s.get("cost"),
            "grid_enabled": bool(g.get("enabled")),
            "grid_base_price": g.get("base_price"),
            "grid_range": [g.get("range_low"), g.get("range_high")],
            "grid_step_pct": g.get("step_pct"), "note": s.get("note"),
        })
    for f in fund.get("positions") or []:
        if not isinstance(f, dict):
            continue
        items.append({
            "track": "fund", "listing": "otc", "code": str(f.get("code", "")),
            "name": f.get("name"), "amount": f.get("amount"),
            "holding_period_days": f.get("holding_period_days"),
            "plan": f.get("plan", "none"), "note": f.get("note"),
            # 场外基金无网格。显式写 false 而非省略：
            # 消费方不该靠「字段不存在」去推断一条轨道规则。
            "grid_enabled": False,
        })
    for g in hold.get("gold") or []:
        if not isinstance(g, dict):
            continue
        items.append({
            "track": "gold", "listing": None, "code": None,
            "name": g.get("name"), "amount": g.get("amount"),
            "grid_enabled": False, "note": g.get("note"),
        })
    plans = [{
        "code": str(p.get("code", "")), "type": p.get("type"),
        "amount_per_period": p.get("amount_per_period"),
        "amount_per_period_max": p.get("amount_per_period_max"),
        "day_of_month": p.get("day_of_month"), "note": p.get("note"),
    } for p in fund.get("plans") or [] if isinstance(p, dict)]
    return {
        "version": (cfg or {}).get("version"),
        "profile": (cfg or {}).get("profile"),
        "risk": (cfg or {}).get("risk"),
        "cash": (cfg or {}).get("cash"),
        "positions": items,
        "plans": plans,
        "summary": build_summary(cfg),
    }


def _fmt(prefix: str, item: dict) -> str:
    line = f"第 {item['line']} 行" if item.get("line") else "位置未知"
    head = f"[{prefix}] {item['location']}（{line}）"
    code = f" [{item.get('code', '')}]" if item.get("code") else ""
    tail = f"\n        提示: {item['hint']}" if item.get("hint") else ""
    return f"{head}{code}: {item['message']}{tail}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="持仓配置校验器（daily-pulse-framework）")
    ap.add_argument("--config", required=True, help="portfolio.yaml 路径")
    ap.add_argument("--schema", default=None, help="schema.json 路径（默认取内置）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（供 CI/脚本消费）")
    ap.add_argument("--quiet", action="store_true", help="只输出错误，忽略警告")
    ap.add_argument("--export", default=None, help="把标准化持仓写成 JSON（喂给引擎）")
    ap.add_argument("--strict", action="store_true", help="警告也视为失败（CI 用）")
    args = ap.parse_args(argv)

    path = Path(args.config).expanduser()
    if not path.is_file():
        print(f"[fail] 配置文件不存在: {path}", file=sys.stderr)
        return 2

    try:
        cfg, line_index = parse_yaml_subset_indexed(path.read_text(encoding="utf-8"))
    except ConfigError as e:
        if args.json:
            print(json.dumps({"ok": False, "fatal": str(e)}, ensure_ascii=False, indent=2))
        else:
            print(f"[fail] YAML 解析失败: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"[fail] 读取失败: {e}", file=sys.stderr)
        return 2

    rep = Report(line_index)
    validate(cfg, rep)
    summary = build_summary(cfg)

    if args.export:
        out = Path(args.export).expanduser()
        if out.parent and not out.parent.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(build_export(cfg), ensure_ascii=False, indent=2),
                       encoding="utf-8")

    ok = rep.ok and not (args.strict and rep.warnings)
    if args.json:
        print(json.dumps({
            "ok": ok, "errors": rep.errors, "warnings": rep.warnings,
            "summary": summary, "config": str(path),
        }, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    if not args.quiet:
        for w in rep.warnings:
            print(_fmt("warn", w))
    for e in rep.errors:
        print(_fmt("error", e), file=sys.stderr)

    if ok:
        print(f"[ok] 配置校验通过 {path}")
        print(f"     股票轨 {summary['stock_count']} 只"
              f"（网格 {summary['grid_enabled']} 启用 / 共 {summary['grid_total']}）"
              f" / 基金轨 {summary['fund_count']} 只（定投计划 {summary['plan_count']} 项）")
        print(f"     基金 {summary['fund_amount']} 元 / "
              f"黄金 {summary['gold_amount']} 元（两者口径独立，不相加）")
        if rep.warnings:
            print(f"     {len(rep.warnings)} 条警告（--strict 下会失败）")
        return 0

    print(f"[fail] 配置校验未通过：{len(rep.errors)} 个错误，"
          f"{len(rep.warnings)} 个警告", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())