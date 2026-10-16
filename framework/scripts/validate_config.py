#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_config.py — 持仓配置校验器 CLI（纯标准库，零第三方依赖）

职责边界（单一职责）：只做「读配置 → 调规则 → 输出结果」。依赖图为四层叶子：
  · yaml_min.py  YAML 子集解析（无内部依赖）
  · codes.py     证券代码规范化（无内部依赖，与 parse_holdings.py 对齐）
  · rules.py     校验规则集（依赖 codes）
  · 本文件       CLI 门面：读文件、调规则、输出。不含业务规则

用法
----
    python3 validate_config.py --config holdings.yaml
    python3 validate_config.py --config holdings.yaml --json          # 机器可读
    python3 validate_config.py --config holdings.yaml --quiet         # 只报错误
    python3 validate_config.py --config holdings.yaml --strict        # 警告也算失败
    python3 validate_config.py --config holdings.yaml --export out.json

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
from yaml_min import ConfigError, parse_yaml_subset  # noqa: E402

# 对外 API 单一入口：以下名字从下层 re-export，调用方只需 import 本模块
__all__ = ["SCHEMA_VERSION", "Report", "build_summary", "validate",
           "normalize_code", "code_mismatch", "market_of", "main"]

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "config" / "schema.json"






def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="持仓配置校验器（daily-pulse-framework）")
    ap.add_argument("--config", required=True, help="holdings.yaml 路径")
    ap.add_argument("--schema", default=None, help="schema.json 路径（默认取内置）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（供 CI/脚本消费）")
    ap.add_argument("--quiet", action="store_true", help="只输出错误，忽略警告")
    ap.add_argument("--export", default=None, help="把解析结果写成 JSON（喂给引擎）")
    ap.add_argument("--strict", action="store_true", help="警告也视为失败（CI 用）")
    args = ap.parse_args(argv)

    path = Path(args.config).expanduser()
    if not path.is_file():
        print(f"[fail] 配置文件不存在: {path}", file=sys.stderr)
        return 2

    try:
        cfg = parse_yaml_subset(path.read_text(encoding="utf-8"))
    except ConfigError as e:
        if args.json:
            print(json.dumps({"ok": False, "fatal": str(e)}, ensure_ascii=False, indent=2))
        else:
            print(f"[fail] YAML 解析失败: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"[fail] 读取失败: {e}", file=sys.stderr)
        return 2

    rep = Report()
    validate(cfg, rep)
    summary = build_summary(cfg)

    if args.export:
        Path(args.export).expanduser().write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = rep.ok and not (args.strict and rep.warnings)
    if args.json:
        print(json.dumps({
            "ok": ok, "errors": rep.errors, "warnings": rep.warnings,
            "summary": summary, "config": str(path),
        }, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    if not args.quiet:
        for w in rep.warnings:
            print(f"[warn] {w['location']}: {w['message']}"
                  + (f"\n        提示: {w['hint']}" if w["hint"] else ""))
    for e in rep.errors:
        print(f"[error] {e['location']}: {e['message']}"
              + (f"\n        提示: {e['hint']}" if e["hint"] else ""), file=sys.stderr)

    if ok:
        print(f"[ok] 配置校验通过 {path}")
        print(f"     股票 {summary['stock_count']} 只 / "
              f"网格 {summary['grid_enabled']} 启用（共 {summary['grid_total']}）/ "
              f"基金 {summary['fund_count']} 只")
        print(f"     纯基金 {summary['fund_amount']} 元 / "
              f"黄金 {summary['gold_amount']} 元（两者口径独立，不相加）")
        if rep.warnings:
            print(f"     {len(rep.warnings)} 条警告（--strict 下会失败）")
        return 0

    print(f"[fail] 配置校验未通过：{len(rep.errors)} 个错误，"
          f"{len(rep.warnings)} 个警告", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())