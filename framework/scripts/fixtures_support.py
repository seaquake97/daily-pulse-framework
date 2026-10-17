#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fixtures_support.py — 两个测试套件共用的测试基座（纯标准库）

抽出独立模块的理由：test_validate_config.py 与 test_migrate_portfolio.py 合计
必须守住 300 行上限，而「最小合法配置 + 深层覆盖构造器」这段基座两者都要用。
放一份而不是各写一份——两份基座必然漂移，届时「校验器通过」与「测试通过」
会指向不同的配置，排查从难变成无从下手。

只放测试基座，不放断言：断言留在各自套件里，失败信息才指向对的用例。
"""
from __future__ import annotations

import copy
import unittest

from validate_config import Report, validate

# 最小合法 v2 配置。基金轨留空数组而非省略——「缺段」与「空段」语义不同。
MINIMAL = {
    "version": 2,
    "profile": {"owner": "t", "base_currency": "CNY", "mode": "personal"},
    "risk": {"max_single_position_pct": 20, "max_total_drawdown_pct": 15,
             "grid_step_pct_cap": 5, "fund_holding_days_min": 7},
    "cash": {"currency": "CNY", "amount": 1000},
    "holdings": {"stock": {"positions": [{"code": "600919", "name": "示例",
                    "listing": "exchange", "shares": 100, "cost": 1.696}],
                "grid": []}, "fund": {"positions": [], "plans": []}, "gold": []},
}
# YAML 子集解析器必须显式拒绝的语法：动态特性 + 缩进错乱 + 流式集合。
# 收集在一处，两个套件共用同一份清单。
BAD_YAML = {
    "重复键": "a: 1\na: 2\n", "Tab缩进": "a:\n\tb: 1\n",
    "锚点": "a: 1\nb: &anc 2\n", "别名": "a: 1\nb: *anc\n",
    "标签": "a: !!str 1\n", "多文档": "a: 1\n---\nb: 2\n",
    "块标量": "a: |\n  text\n", "流式集合": "a: [1, 2]\n",
}
FUND = {"code": "000979", "name": "某基金", "listing": "otc", "amount": 100.0}
GRID = {"code": "600312", "name": "G", "listing": "exchange", "enabled": True,
        "base_price": 10, "range_low": 1, "range_high": 10, "step_pct": 2.5,
        "per_trade": 100, "min_position": 0, "max_position": 100}


def cfg(**over) -> dict:
    """在 MINIMAL 上做深层覆盖。deepcopy 是必需的：测试共享同一份嵌套 dict
    会让改动静默跨用例传播，制造难查的顺序依赖。"""
    out = copy.deepcopy(MINIMAL)
    for dotted, val in over.items():
        node, keys = out, dotted.split(".")
        for k in keys[:-1]:
            node = node[int(k)] if isinstance(node, list) else node[k]
        node[int(keys[-1]) if isinstance(node, list) else keys[-1]] = val
    return out


def fund_cfg(pos: dict, plan: dict | None = None) -> dict:
    """只含一只场外基金的基金段（附可选定投计划）。"""
    return cfg(**{"holdings.fund.positions": [pos],
                  "holdings.fund.plans": [plan] if plan else []})


def run(conf: dict) -> Report:
    rep = Report()
    validate(conf, rep)
    return rep


def codes_of(rep: Report) -> set:
    return {e.get("code") for e in rep.errors}


def assert_rejected(case: unittest.TestCase, cases: dict) -> None:
    """表格驱动统一入口：每个用例都必须「报得出错」，want 非空时校验错误码。

    case 必须显式传入——subTest 是 TestCase 的方法，模块级函数拿不到 self。
    """
    for label, (conf, want) in cases.items():
        with case.subTest(case=label):
            rep = run(conf)
            case.assertFalse(rep.ok)
            if want:
                case.assertIn(want, codes_of(rep))
