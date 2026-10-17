#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""journal_fixtures.py — 决策日志测试基座（纯标准库，零依赖）

抽出独立模块的理由：test_journal.py 与 test_journal_cases.py 合计必须守住
300 行上限（与 framework/scripts/fixtures_support.py 同款判据），而
「合法骨架 + 逐条反例的构造器」两套件都要用。

只放基座，不放断言：断言留在各自套件里，失败信息才指向对的用例。

纪律：**不硬编码持仓数据**。真实数据仓由 datahub.load_index 读
config/portfolio.yaml（可被 PULSE_CONFIG 覆盖）；测试用 config/portfolio.example.yaml
作为确定性夹具，它与真实文件同结构但不含私人数据。
若真实数据仓不可用则整套件 SKIP——绿灯不可信比红灯更糟。
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent.parent / "scripts"
for _p in (str(_HERE), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import paths  # noqa: E402
from datahub import PortfolioIndex, parse_yaml_subset  # noqa: E402
from diagnostics import JournalReport  # noqa: E402
from schema import action, new_entry, observation_point  # noqa: E402
from validate import validate_entry, validate_log  # noqa: E402

# 确定性夹具：与真实 portfolio.yaml 同结构（v2 双轨），不含私人数据。
EXAMPLE = paths.PROJECT_ROOT / "config" / "portfolio.example.yaml"

# 反例专用的虚构代码：必须确定不在任何数据仓里，
# 否则「孤儿标的」用例会随真实持仓变动而时红时绿（典型的顺序依赖陷阱）。
ORPHAN_CODE = "999998"


def example_index() -> PortfolioIndex:
    """从 portfolio.example.yaml 建索引。"""
    cfg = parse_yaml_subset(EXAMPLE.read_text(encoding="utf-8"))
    return PortfolioIndex(cfg)


def real_index():
    """真实数据仓索引。文件不存在时返回 None（由测试决定 SKIP 还是报错）。"""
    cfg_path = paths.PORTFOLIO
    if not Path(cfg_path).is_file():
        return None
    try:
        return PortfolioIndex(parse_yaml_subset(
            Path(cfg_path).read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001  数据仓损坏同样按「不可用」处理
        return None


def run_entry(ent: dict, repo, max_actions: int = 3) -> JournalReport:
    """跑单条目断言，返回报告。"""
    rep = JournalReport()
    validate_entry(ent, repo, rep, 0)
    return rep


def run_log(entries: list, repo, max_actions: int = 3) -> JournalReport:
    """跑整份日志（追加 A-08 / A-13）。"""
    rep = JournalReport()
    validate_log(entries, repo, rep, max_actions)
    return rep


def codes_of(rep: JournalReport) -> set:
    return {e.get("code") for e in rep.errors}


def assert_rejected(case, ent: dict, want: str, repo=None, max_actions: int = 3) -> None:
    """断言：某条构造必定被拒，且错误码包含 want。

    「必定」是这条辅助的核心：它先确认基线条目（同一构造器的未改版）
    通过校验，再确认改坏的版本报出目标码。少了前半段，一个「所有条目
    都因为别的原因报错」的测试也会绿——那样的断言什么都没证明。
    """
    repo = repo if repo is not None else example_index()
    base = run_entry(new_entry(), repo)
    case.assertTrue(base.ok,
                    f"基线条目本身必须先通过校验：{[e['message'] for e in base.errors]}")
    rep = run_entry(ent, repo, max_actions)
    case.assertFalse(rep.ok, f"反例必须被拒，但校验通过了：{ent}")
    case.assertIn(want, codes_of(rep),
                  f"期望错误码 {want}，实际 {sorted(codes_of(rep))}："
                  f"{[e['message'] for e in rep.errors]}")
    return rep


__all__ = ["EXAMPLE", "ORPHAN_CODE", "example_index", "real_index",
           "run_entry", "run_log", "codes_of", "assert_rejected",
           "new_entry", "action", "observation_point", "JournalReport"]