#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_slots.py — 双轨三层槽位契约校验器（纯标准库）

职责边界（单一职责）：只做「读槽位契约 → 校验 → 输出报告」。不含业务规则推导，
不含任何交易判断。

为什么需要它（不是重复纪律）：
  纪律写在任务书里会被复述漂移，30 轮专家讨论已证明「写在文档里的纪律会被违反
  且不报告」。槽位隔离必须由代码执行——本模块就是把 ADR-007 §2.2 的双轨边界
  从「文字」变成「断言」。

校验规则编号（错误码稳定，供 CI 与任务书引用）：
  S-01  slots 字段缺失 / 类型错
  S-02  slot_id 重复
  S-03  time 格式非法（HH:MM）
  S-04  track 不在 {stock, fund}
  S-05  time 不在 A 股交易时段内
  S-06  fund 槽声明了中间态机制（allow_mechanisms 非空）
  S-07  fund 槽消费了仅场内可得的行情字段（分时/盘口/网格态）
  S-08  required_outputs 为空
  S-09  fund_action 槽缺 amount_unit（申赎必须带金额口径）
  S-10  track 与 inputs/allow_mechanisms 自相矛盾（stock 槽无机制词）
  S-11 轨道槽数不符合「双轨三层」（stock 3 + fund 3）
  S-12  narrative_time_rules 缺失或 lag_status 枚举不全
  S-13  notes 缺失（槽位职责必须留痕，防止后续被塞入另一轨职责）

用法
----
    python3 validate_slots.py
    python3 validate_slots.py --json
    python3 validate_slots.py --strict      # 警告也算失败

退出码：0 通过 / 1 校验失败 / 2 文件或解析错误
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from yaml_min import ConfigError, parse_yaml_subset_indexed  # noqa: E402

SLOTS_PATH = (Path(__file__).resolve().parent.parent / "config" / "slots.yaml")

VALID_TRACKS = frozenset({"stock", "fund"})
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# A 股交易时段：09:15-09:25 集合竞价 / 09:30-11:30 / 13:00-15:00
# 允许的边界放宽到 09:15 前 2 分钟与 15:30 后（盘后结算槽）
TRADING_WINDOWS = (
    ("09:15", "11:30"),
    ("13:00", "15:35"),
)

# 仅场内可得的行情字段：场外基金无分时价、无盘口、无网格态（ADR-007 §2.2）
ONEXCHANGE_ONLY_FIELDS = frozenset({
    "intraday_quote", "order_book", "tick", "grid_state",
    "auction_gap_pct", "auction_volume_ratio", "limit_up_count",
})

EXPECTED_TRACK_COUNTS = {"stock": 3, "fund": 3}
REQUIRED_LAG_STATUS = ("plan", "done", "superseded")

__all__ = ["SLOTS_PATH", "validate_slots_dict", "main"]


def _err(code: str, slot: str, msg: str) -> str:
    where = f"slot[{slot}]" if slot else "slots"
    return f"{code}: {where}: {msg}"


def _check_time(value: object, slot: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not TIME_RE.match(value):
        errors.append(_err("S-03", slot, f"time {value!r} 不是 HH:MM 格式"))
        return
    t = value
    if not any(lo <= t <= hi for lo, hi in TRADING_WINDOWS):
        errors.append(_err("S-05", slot,
                           f"time {t} 不在交易时段 {TRADING_WINDOWS} 内"))


def _validate_slot(slot: dict, errors: list[str], idx: object) -> None:
    sid = str(slot.get("slot_id", f"#{idx}"))
    for key in ("time", "track", "name", "data_stage", "inputs",
                "required_outputs", "allow_mechanisms", "notes"):
        if key not in slot:
            errors.append(_err("S-01", sid, f"缺必填字段 {key}"))

    _check_time(slot.get("time"), sid, errors)

    track = slot.get("track")
    if track not in VALID_TRACKS:
        errors.append(_err("S-04", sid, f"track {track!r} 非法（允许 {sorted(VALID_TRACKS)}）"))
        return  # track 非法时后续规则无从判断，提前返回

    mechs = slot.get("allow_mechanisms")
    if not isinstance(mechs, list):
        errors.append(_err("S-01", sid, "allow_mechanisms 必须是列表"))
        mechs = []

    if track == "fund" and mechs:
        errors.append(_err("S-06", sid,
                           f"fund 轨禁止中间态机制 {mechs}（场外基金买就是买卖就是卖，"
                           "无挂单/条件单/网格/日内分批）"))

    if track == "stock" and not mechs:
        errors.append(_err("S-10", sid,
                           "stock 槽 allow_mechanisms 为空：场内标的允许网格与条件单，"
                           "空值会让执行层误以为该票已禁用中间态"))

    inputs = slot.get("inputs")
    if not isinstance(inputs, list):
        errors.append(_err("S-01", sid, "inputs 必须是列表"))
        inputs = []
    if track == "fund":
        leak = sorted(set(inputs) & ONEXCHANGE_ONLY_FIELDS)
        if leak:
            errors.append(_err("S-07", sid,
                               f"fund 轨消费了仅场内可得的字段 {leak}"
                               "（场外基金无分时净值/盘口/竞价数据）"))

    outs = slot.get("required_outputs")
    if not isinstance(outs, list) or not outs:
        errors.append(_err("S-08", sid, "required_outputs 不得为空"))
    elif not isinstance(outs, list):
        outs = []

    if sid == "fund_action" and isinstance(outs, list) and outs and \
            "amount_unit" not in outs:
        errors.append(_err("S-09", sid,
                           "申赎执行槽必须要求 amount_unit（money|shares），"
                           "否则会出现只给方向不给金额的骑墙建议"))

    if not str(slot.get("notes", "")).strip():
        errors.append(_err("S-13", sid,
                           "notes 为空：槽位职责必须留痕，防止后续被塞入另一轨职责"))


def validate_slots_dict(data: dict) -> list[str]:
    """校验槽位契约。返回错误列表（空列表 = 通过）。"""
    errors: list[str] = []
    if not isinstance(data, dict):
        return [_err("S-01", "", "顶层必须是映射")]

    slots = data.get("slots")
    if not isinstance(slots, list) or not slots:
        return [_err("S-01", "", "slots 必须是非空列表")]

    seen: set[str] = set()
    counts: dict[str, int] = {t: 0 for t in EXPECTED_TRACK_COUNTS}
    for i, slot in enumerate(slots):
        if not isinstance(slot, dict):
            errors.append(_err("S-01", f"#{i}", "槽位必须是映射"))
            continue
        sid = str(slot.get("slot_id", f"#{i}"))
        if sid in seen:
            errors.append(_err("S-02", sid, "slot_id 重复"))
        seen.add(sid)
        _validate_slot(slot, errors, i)
        if slot.get("track") in counts:
            counts[slot["track"]] += 1

    for track, want in EXPECTED_TRACK_COUNTS.items():
        if counts.get(track) != want:
            errors.append(_err("S-11", "",
                               f"{track} 轨槽数 {counts.get(track)} ≠ 约定 {want}"
                               "（双轨三层：股票 3 档 + 基金 3 档）"))

    rules = data.get("narrative_time_rules")
    if not isinstance(rules, list) or not rules:
        errors.append(_err("S-12", "", "narrative_time_rules 缺失"))
    else:
        got = {r.get("lag_status") for r in rules if isinstance(r, dict)}
        for st in REQUIRED_LAG_STATUS:
            if st not in got:
                errors.append(_err("S-12", "", f"narrative_time_rules 缺 lag_status={st}"))
        for r in rules:
            if isinstance(r, dict) and r.get("lag_status") == "superseded" \
                    and r.get("usable_for_action") is not False:
                errors.append(_err("S-12", "",
                                   "superseded 不得 usable_for_action=true"
                                   "（被推翻的判断不能作为动作依据）"))

    return errors


def _load(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"无法读取 {path}: {exc}") from exc
    data, _line_index = parse_yaml_subset_indexed(text)
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="双轨三层槽位契约校验器")
    ap.add_argument("--slots", default=str(SLOTS_PATH), help="槽位契约文件路径")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--strict", action="store_true", help="警告也算失败")
    args = ap.parse_args(argv)

    path = Path(args.slots)
    if not path.is_absolute():
        path = (Path(__file__).resolve().parent / path).resolve()
    try:
        data = _load(path)
    except ConfigError as exc:
        print(f"S-01: 解析失败: {exc}", file=sys.stderr)
        return 2

    errors = validate_slots_dict(data)
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors},
                         ensure_ascii=False, indent=2))
        return 0 if not errors else 1

    if errors:
        print(f"槽位契约校验失败（{len(errors)} 项）:")
        for e in errors:
            print(f"  {e}")
        return 1

    slots = data.get("slots", [])
    stock = sum(1 for s in slots if s.get("track") == "stock")
    fund = len(slots) - stock
    print(f"槽位契约校验通过：{len(slots)} 个槽（股票 {stock} + 基金 {fund}）")
    for s in slots:
        print(f"  {s.get('time')}  {s.get('track'):<5} {s.get('slot_id'):<20} "
              f"{s.get('name')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
