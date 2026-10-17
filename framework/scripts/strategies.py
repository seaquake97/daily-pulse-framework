#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategies.py — 声明式策略库解析与校验器（纯标准库，零第三方依赖）

架构对齐：
  参考 ZhuLinsen/daily_stock_analysis 中的 strategies/*.yaml 声明式策略范式，
  结合 daily-pulse-framework 的纯标准库与 yaml_min.py 解析契约。
  提供策略读取、Schema 校验、无 emoji 门禁与 CLI。

用法：
    python3 strategies.py --dir ../config/strategies/
    python3 strategies.py --file ../config/strategies/grid_trading.yaml
    python3 strategies.py --dir ../config/strategies/ --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from yaml_min import ConfigError, parse_yaml_subset  # noqa: E402

VALID_CATEGORIES = frozenset({"strategic", "execution", "defensive", "trend", "framework"})
# 轨道维度（ADR-007 §2.2）：stock = 场内标的（可挂单/网格/分批）；
# fund = 场外基金（无中间态，动作只有买入/卖出/调整定投额，禁网格类机制）。
VALID_TRACKS = frozenset({"stock", "fund"})
# 场外基金禁止出现的机制词——命中即判该策略不适用于 fund 轨（ADR-007 §2.2 / 收割 H-1、H-2）
FUND_FORBIDDEN_TERMS = ("网格", "挂单", "条件单", "做T", "做 T", "委托档位",
                        "分批", "日内", "T+0", "摊薄成本", "限价")
NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]")


class StrategyError(Exception):
    """策略定义或校验失败。"""


# 否定语境：机制词出现在「禁止/不得/无/严禁/不存在」等表述中时不算违规
_NEGATION = ("禁止", "不得", "严禁", "不存在", "无", "不适用", "不参与", "并非", "不是")
_FUND_TERM_RE = re.compile("(" + "|".join(re.escape(x) for x in FUND_FORBIDDEN_TERMS) + ")")


def _fund_mechanism_hits(data: dict) -> list[str]:
    """找出 fund 轨策略中「作为机制使用」的中间态词。

    否定句（如「禁止出现挂单」）不计入违规——纪律文本本身必须能说出被禁的机制，
    否则无法解释规则。这是 validator 首次实跑即抓到的自身误报（2026-10-17）。
    """
    text = json.dumps(data, ensure_ascii=False)
    hits: set[str] = set()
    # 按分句切分：否定词在本句内任意位置出现即视为否定语境。
    # 不用固定字符窗口——实跑证明窗口会在长句里漏判（第三处误报）。
    for clause in re.split(r"[。；;，,\n]", text):
        if not _FUND_TERM_RE.search(clause):
            continue
        if any(neg in clause for neg in _NEGATION):
            continue
        hits.update(m.group(1) for m in _FUND_TERM_RE.finditer(clause))
    return sorted(hits)


def validate_strategy_dict(data: dict, source_name: str = "strategy") -> list[str]:
    """校验单个策略字典的结构规范与合规性。返回错误信息列表，空表示合法。"""
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"{source_name}: 顶级结构必须为 mapping 字典"]

    # 1. 必填字段检查
    required_fields = ("name", "display_name", "category", "description", "rules")
    for f in required_fields:
        if f not in data or data[f] is None:
            errors.append(f"{source_name}: 缺少必填字段 '{f}'")

    if errors:
        return errors

    # 2. 字段类型与值校验
    name = str(data.get("name", "")).strip()
    if not NAME_PATTERN.match(name):
        errors.append(f"{source_name}: name '{name}' 格式不合法，必须由小写字母、数字与下划线组成")

    category = str(data.get("category", "")).strip()
    if category not in VALID_CATEGORIES:
        errors.append(f"{source_name}: category '{category}' 不在允许类别中 ({sorted(VALID_CATEGORIES)})")

    rules = data.get("rules")
    if not isinstance(rules, list) or len(rules) == 0:
        errors.append(f"{source_name}: rules 必须为非空列表")

    # 3. 轨道校验（ADR-007 §2.2 双轨隔离）：track 必填；fund 轨禁止中间态机制词
    track = str(data.get("track", "")).strip()
    if track not in VALID_TRACKS:
        errors.append(f"{source_name}: track '{track}' 不在允许轨道中 "
                      f"({sorted(VALID_TRACKS)})——stock=场内可网格，fund=场外无中间态")
    elif track == "fund":
        bad = _fund_mechanism_hits(data)
        if bad:
            errors.append(f"{source_name}: track=fund 的策略禁止出现中间态机制词 {bad}"
                          "（场外基金无挂单/条件单/网格/日内机制，见 ADR-007 §2.2）")

    # 4. 团队 P0-1 铁律校验：全文字禁止 emoji
    raw_text = json.dumps(data, ensure_ascii=False)
    emoji_hits = EMOJI_RE.findall(raw_text)
    if emoji_hits:
        errors.append(f"{source_name}: 违反团队 P0-1 铁律，策略中包含禁止的 emoji 字符: {emoji_hits[:5]}")

    return errors


def load_strategy(path: Path) -> dict:
    """加载并解析单个 YAML 策略文件。"""
    if not path.is_file():
        raise StrategyError(f"策略文件不存在: {path}")

    text = path.read_text(encoding="utf-8")
    try:
        data = parse_yaml_subset(text)
    except ConfigError as exc:
        raise StrategyError(f"{path.name} YAML 解析错误: {exc}") from exc

    errs = validate_strategy_dict(data, source_name=path.name)
    if errs:
        raise StrategyError("; ".join(errs))

    return data


def load_all_strategies(strategy_dir: Path) -> dict[str, dict]:
    """加载目录下的所有 .yaml 策略，返回 name -> dict。"""
    if not strategy_dir.is_dir():
        raise StrategyError(f"策略目录不存在: {strategy_dir}")

    strategies: dict[str, dict] = {}
    for yml in sorted(strategy_dir.glob("*.yaml")):
        s = load_strategy(yml)
        name = s["name"]
        if name in strategies:
            raise StrategyError(f"发现重复策略名称 '{name}': {yml.name}")
        strategies[name] = s

    return strategies


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="声明式策略库解析与校验 CLI")
    ap.add_argument("--dir", default=None, help="策略目录路径")
    ap.add_argument("--file", default=None, help="单个策略文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = ap.parse_args(argv)

    if not args.dir and not args.file:
        ap.print_help()
        return 2

    try:
        if args.file:
            target = Path(args.file)
            data = load_strategy(target)
            results = {data["name"]: data}
        else:
            target_dir = Path(args.dir)
            results = load_all_strategies(target_dir)

        if args.json:
            print(json.dumps({"ok": True, "count": len(results), "strategies": results},
                             ensure_ascii=False, indent=2))
        else:
            print(f"[ok] 策略校验全部通过，共加载 {len(results)} 个策略:")
            for name, item in results.items():
                print(f"  - [{item['category']}] {item['display_name']} ({name}): {len(item['rules'])} 条规则")
        return 0

    except StrategyError as err:
        if args.json:
            print(json.dumps({"ok": False, "error": str(err)}, ensure_ascii=False, indent=2))
        else:
            print(f"[fail] 策略校验失败: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
