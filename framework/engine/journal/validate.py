#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate.py — 决策日志校验层门面（纯标准库，零第三方依赖）

职责边界（单一职责）：只做「收条目 → 调断言 → 出报告」，不含规则实现，
不含持仓数据加载策略的选择，只接受已构建的 PortfolioIndex。

对外三个入口：
    validate_entry(entry, repo, rep)        单条目断言（A-01..A-07、A-09..A-12、
                                            A-14..A-16 + 结构检查）
    validate_log(entries, repo, rep, ...)   整份决策日志（追加 A-08 / A-13）
    validate_entry_standalone(entry, repo)  便捷包装，返回新的 Report

为什么需要门面而不是让调用方直接 import 断言函数：
  1. 断言顺序影响错误条数。A-02 先于 A-06 跑，则「观察点字段缺失」的条目
     不会先被孤儿标的淹没——先报根因，再报派生问题；
  2. 调用方（CI、任务脚本）不该记住 12 个函数的顺序；
  3. 断言数量会随版本增加，顺序表只应有一处。
"""
from __future__ import annotations

from assertions import (
    check_amount_unit, check_exit_available, check_grid_base_price,
    check_instrument_known, check_observation_point, check_requested_position,
    check_risk_fields, check_track_independence,
)
from assertions_cross import (
    check_degraded_marking, check_log_level, check_missing,
    check_reasoning_basis, check_unverified_no_action,
)
from references import check_derivation
from structure import (
    check_covers_paths, check_enum_fields, check_structure,
)
from contracts import (
    ASSERTION_CODES, DEFAULT_MAX_ACTIONS_PER_OBSERVATION, JOURNAL_VERSION,
)
from diagnostics import JournalReport, format_diagnostics, item_loc

# 单条目断言的执行顺序。注释里写的是「为什么在这个位置」，不是复述函数名：
# 顺序错了会产生误导性的错误组合（例如 A-06 先报会让 A-02 的根因被埋掉）。
ENTRY_CHECKS = (
    check_structure,             # 结构先行：后续断言都在稳定的形状上跑
    check_observation_point,     # A-02 观察点四字段
    check_enum_fields,           # 枚举合法性（point_class 等 A-08/A-15 的依赖）
    check_requested_position,    # A-01 目标仓位（依赖 action 是否存在）
    check_amount_unit,           # A-03 金额口径（横跨 requested_position/action）
    check_grid_base_price,       # A-04 网格锚点
    check_exit_available,        # A-05 可平仓证明（依赖数据仓）
    check_instrument_known,      # A-06 孤儿标的（依赖数据仓）
    check_risk_fields,           # A-07 风控四字段
    check_track_independence,    # A-15 跨轨独立性（依赖数据仓 listing）
    check_degraded_marking,      # A-09 降级标注
    check_reasoning_basis,       # A-10 推理来源
    check_derivation,            # A-11 推导引用（依赖数据仓）
    check_missing,               # A-12 缺失登记
    check_unverified_no_action,  # A-14 UNVERIFIED 禁带动作
    check_covers_paths,          # A-16 覆盖声明
)


def validate_entry(entry: dict, repo, rep: JournalReport, index: int = 0) -> int:
    """单条目断言。index 为其在决策日志中的位置（决定错误定位串）。

    返回命中的错误条数。entry 不是映射时直接报一条 E_J_STRUCTURE 并返回——
    不在此处 raise：调用方可能正在校验一整份日志，单条畸形不该中断整批。
    """
    loc = item_loc(index)
    if not isinstance(entry, dict):
        rep.err(loc, "决策日志条目必须是映射",
                f"version={JOURNAL_VERSION}，构造器见 schema.py", "E_J_STRUCTURE")
        return 1
    hits = 0
    for check in ENTRY_CHECKS:
        hits += check(entry, loc, repo, rep)
    return hits


def validate_log(entries, repo, rep: JournalReport,
                 max_actions: int = DEFAULT_MAX_ACTIONS_PER_OBSERVATION,
                 line_index: dict | None = None) -> int:
    """整份决策日志。entries 为条目列表。

    先跑条目级断言再跑日志级（A-08/A-13）：若某条目结构已崩，
    它携带的 kind 可能不可信，此时统计动作数只会产出误导性计数。
    """
    if not isinstance(entries, list):
        rep.err("decision_log", "decision_log 必须是列表",
                "无内容写 []", "E_J_STRUCTURE")
        return 1
    hits = 0
    for i, ent in enumerate(entries):
        hits += validate_entry(ent, repo, rep, i)
    if all(isinstance(e, dict) for e in entries):
        hits += check_log_level(entries, repo, rep, max_actions, line_index)
    return hits


def validate_entry_standalone(entry: dict, repo,
                              line_index: dict | None = None) -> JournalReport:
    """便捷包装：建 Report、跑单条目断言、返回报告。"""
    rep = JournalReport(line_index)
    validate_entry(entry, repo, rep, 0)
    return rep


def validate_standalone(entries, repo,
                        max_actions: int = DEFAULT_MAX_ACTIONS_PER_OBSERVATION,
                        line_index: dict | None = None) -> JournalReport:
    rep = JournalReport(line_index)
    validate_log(entries, repo, rep, max_actions, line_index)
    return rep


def assertion_coverage() -> dict:
    """错误码 → 是否至少被一条断言产出。

    供 CI 自检：新加断言若忘了落进 ENTRY_CHECKS 或 check_log_level，
    这里会显示该错误码永远不会被报出——一个从不触发的断言等于没有断言。
    """
    produced = set()
    for check in ENTRY_CHECKS:
        produced |= _codes_of_source(check)
    produced |= _codes_of_source(check_log_level)
    return {code: code in produced for code in ASSERTION_CODES}


def _codes_of_source(func) -> set:
    """从函数源码里取 contracts 中定义的错误码字面量。"""
    import inspect

    from contracts import (  # 局部导入：只在自检时用到，不占运行期依赖
        E_A01_REQUESTED_POSITION, E_A02_OBSERVATION_FIELDS, E_A03_AMOUNT_UNIT,
        E_A04_GRID_BASE_PRICE, E_A05_EXIT_AVAILABLE, E_A06_ORPHAN_INSTRUMENT,
        E_A07_RISK_FIELDS, E_A08_GRID_REBALANCE_EXCLUSIVE,
        E_A09_DEGRADED_MARKING, E_A10_REASONING_BASIS, E_A11_DERIVATION_REF,
        E_A12_MISSING_MUST_BE_NULL, E_A13_ACTION_COUNT_CAP,
        E_A14_UNVERIFIED_WITH_ACTION, E_A15_TRACK_INDEPENDENCE,
        E_A16_COVERS_PATHS,
    )
    universe = {
        E_A01_REQUESTED_POSITION, E_A02_OBSERVATION_FIELDS, E_A03_AMOUNT_UNIT,
        E_A04_GRID_BASE_PRICE, E_A05_EXIT_AVAILABLE, E_A06_ORPHAN_INSTRUMENT,
        E_A07_RISK_FIELDS, E_A08_GRID_REBALANCE_EXCLUSIVE,
        E_A09_DEGRADED_MARKING, E_A10_REASONING_BASIS, E_A11_DERIVATION_REF,
        E_A12_MISSING_MUST_BE_NULL, E_A13_ACTION_COUNT_CAP,
        E_A14_UNVERIFIED_WITH_ACTION, E_A15_TRACK_INDEPENDENCE,
        E_A16_COVERS_PATHS,
    }
    try:
        src = inspect.getsource(func)
    except (OSError, TypeError):
        return universe  # 拿不到源码时保守：视为全产出，由测试另行兜底
    return {c for c in universe if c in src}


def main(argv=None) -> int:
    """CLI：校验一份决策日志 JSON 文件。

        python3 validate.py --log out/decision_log.json
        python3 validate.py --log out/decision_log.json --json

    退出码：0 通过 / 1 校验失败 / 2 文件或解析错误。
    持仓数据仓路径走 --portfolio 或 paths.PORTFOLIO，不读隐式默认。
    """
    import argparse
    import json
    import sys
    from pathlib import Path

    from datahub import load_index

    ap = argparse.ArgumentParser(description="决策日志校验器（ADR-007 范式切换）")
    ap.add_argument("--log", required=True, help="决策日志 JSON 路径")
    ap.add_argument("--portfolio", default=None,
                    help="持仓数据仓路径（默认取 paths.PORTFOLIO）")
    ap.add_argument("--max-actions", type=int,
                    default=DEFAULT_MAX_ACTIONS_PER_OBSERVATION,
                    help="同一观察点的动作数上限")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    log_path = Path(args.log).expanduser()
    if not log_path.is_file():
        print(f"[fail] 决策日志不存在: {log_path}", file=sys.stderr)
        return 2
    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        print(f"[fail] 决策日志解析失败: {err}", file=sys.stderr)
        return 2
    try:
        repo = load_index(args.portfolio)
    except (FileNotFoundError, ValueError) as err:
        print(f"[fail] 持仓数据仓不可用: {err}", file=sys.stderr)
        return 2

    entries = payload.get("decision_log") if isinstance(payload, dict) \
        else payload
    rep = validate_standalone(entries, repo, args.max_actions)
    if args.json:
        print(json.dumps(rep.summary(), ensure_ascii=False, indent=2))
        return 0 if rep.ok else 1
    for line in format_diagnostics(rep, "error"):
        print(line, file=sys.stderr)
    if rep.ok:
        total = len(entries) if isinstance(entries, list) else 0
        print(f"[ok] 决策日志校验通过（{total} 条）")
        return 0
    print(f"[fail] 决策日志校验未通过：{len(rep.errors)} 个错误", file=sys.stderr)
    return 1


__all__ = ["validate_entry", "validate_log", "validate_entry_standalone",
           "validate_standalone", "assertion_coverage", "JournalReport",
           "format_diagnostics", "ENTRY_CHECKS", "main"]


if __name__ == "__main__":
    import sys
    sys.exit(main())