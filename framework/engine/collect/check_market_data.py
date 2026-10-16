#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_market_data.py — market_data.json 权威契约校验（纯标准库，零依赖）

## 为什么需要它（GAP-A1）

历史 22 份产物的交叉统计显示两类真实漂移：
  ① 涨跌字段 `chg_pct` 与 `change_percent` 双写法并存（18 份用旧字段）；
  ② `data_stage` 有 5 份缺失（早期产物）。

原 validate_market_data.py 只覆盖部分硬断言（成交额交叉、日期匹配），
字段命名/类型/单位/双写法无人管。本脚本把这些变成可执行断言。

## 校验分三层（逐层收敛，报错即定位）
  L1 结构：必填字段、类型、单位声明
  L2 一致：日期匹配、涨跌字段不并存、评级与有效权重自洽
  L3 缺口：data_gaps 非空时下游不得用其数值出动作（只提示，不阻断）

## 用法
    python3 check_market_data.py --in path/to/market_data.json [--json] [--strict]
    python3 check_market_data.py --dir <任务目录>/<日期>            # 批模式
    python3 check_market_data.py --dir-glob '/path/*/2026-10-16'    # 多日期

退出码：0 通过｜1 校验失败（存在 error）｜2 参数/IO 错误
"""
from __future__ import annotations

import argparse
import glob as _glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "market_data.schema.json"

STAGES = ("pre_open", "intraday", "close")
RATINGS = ("进攻", "均衡", "信号矛盾", "防守", "回避")
MIN_VALID_WEIGHT = 0.50
CHG_FIELDS = ("change_percent", "chg_pct")


def load_schema() -> dict:
    if not SCHEMA_PATH.exists():
        print(f"[fatal] schema 缺失: {SCHEMA_PATH}", file=sys.stderr)
        raise SystemExit(2)
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check(doc: dict, schema: dict) -> tuple[list[str], list[str]]:
    err: list[str] = []
    warn: list[str] = []

    # ---- L1 结构 ----
    for key in schema["required"]:
        if key not in doc:
            err.append(f"缺必填字段: {key}")
    if not isinstance(doc.get("date"), str):
        err.append("date 必须是字符串（YYYY-MM-DD）")
    else:
        import re
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", doc["date"]):
            err.append(f"date 格式错误: {doc['date']!r}（应为 YYYY-MM-DD）")
    stage = doc.get("data_stage")
    if stage is not None and stage not in STAGES:
        err.append(f"data_stage 取值非法: {stage!r}（应为 {STAGES}）")

    idx_spec = schema["fields"]["indices"]
    indices = doc.get("indices")
    if indices is not None:
        if not isinstance(indices, dict):
            err.append("indices 必须是对象（key=full_code）")
        else:
            for code, item in indices.items():
                if not isinstance(item, dict):
                    err.append(f"indices.{code} 必须是对象")
                    continue
                for f in idx_spec["required_item_fields"]:
                    if f not in item:
                        err.append(f"indices.{code} 缺字段: {f}")
                for f in ("change_percent", "chg_pct"):
                    if f in item and not _num(item[f]):
                        err.append(f"indices.{code}.{f} 必须是数字（%），"
                                   f"实际 {type(item[f]).__name__}")
                if _num(item.get("amount")) and item["amount"] < 0:
                    err.append(f"indices.{code}.amount 为负: {item['amount']}")

    hold = doc.get("holdings")
    if hold is not None:
        if not isinstance(hold, dict):
            err.append("holdings 必须是对象")
        else:
            hspec = schema["fields"]["holdings"]
            for code, item in hold.items():
                if not isinstance(item, dict):
                    err.append(f"holdings.{code} 必须是对象")
                    continue
                for f in hspec["required_item_fields"]:
                    if f not in item:
                        err.append(f"holdings.{code} 缺字段: {f}")
                for f in CHG_FIELDS:
                    if f in item and not _num(item[f]):
                        err.append(f"holdings.{code}.{f} 必须是数字（%）")

    br = doc.get("market_breadth")
    if br is not None:
        if not isinstance(br, dict):
            err.append("market_breadth 必须是对象")
        else:
            for f in ("up", "down", "flat"):
                if f not in br:
                    err.append(f"market_breadth 缺字段: {f}")
                elif not isinstance(br[f], int) or isinstance(br[f], bool):
                    err.append(f"market_breadth.{f} 必须是整数")

    # ---- L2 一致 ----
    date = doc.get("date")
    if isinstance(indices, dict):
        for code, item in indices.items():
            if not isinstance(item, dict):
                continue
            t = item.get("time")
            if t and isinstance(date, str) and t != date:
                err.append(f"indices.{code}.time={t!r} 与 date={date!r} 不符")
            both = [f for f in CHG_FIELDS if f in item]
            if len(both) == 2:
                err.append(f"indices.{code}: {both} 双写法并存，"
                           f"必须只用 change_percent（v1.3 契约）")
            elif both and _num(item[both[0]]):
                if item[both[0]] is not None and abs(item[both[0]]) > 11:
                    warn.append(f"indices.{code}.{both[0]}={item[both[0]]} 超出 ±11% 常识区间")

    v = doc.get("verdict")
    if isinstance(v, dict):
        if v.get("rating") is not None and v["rating"] not in RATINGS:
            err.append(f"verdict.rating 非法: {v['rating']!r}（五档之一）")
        if "sigma" in v and v["sigma"] is not None and not _num(v["sigma"]):
            err.append("verdict.sigma 必须是数字或 null")
        vw = v.get("valid_weight")
        if _num(vw) and vw < MIN_VALID_WEIGHT and v.get("rating") != "信号矛盾":
            err.append(f"verdict.valid_weight={vw} < {MIN_VALID_WEIGHT}，"
                       f"rating 必须为 信号矛盾（实际 {v.get('rating')!r}）")
    elif v is not None:
        err.append("verdict 必须是对象")

    # ---- L3 缺口（只提示） ----
    gaps = doc.get("data_gaps")
    if isinstance(gaps, list) and gaps and v and v.get("rating"):
        warn.append("data_gaps 非空：下游结论层必须降级为『不输出可执行动作』"
                    f"（当前 verdict.rating={v.get('rating')!r} 仅供内部分析）")
    if stage is None:
        warn.append("data_stage 缺失：站点将无法标注数据时点，发布层会回落默认 close")

    return err, warn


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="market_data.json 契约校验（GAP-A1）")
    ap.add_argument("--in", dest="infile", help="单个 market_data.json")
    ap.add_argument("--dir", help="目录（含 market_data.json）")
    ap.add_argument("--dir-glob", dest="dir_glob", help="glob 批量（配合 --dir-glob）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--strict", action="store_true", help="警告也算失败")
    args = ap.parse_args(argv)

    schema = load_schema()
    targets: list[Path] = []
    if args.infile:
        targets = [Path(args.infile)]
    elif args.dir:
        targets = [Path(args.dir) / "market_data.json"]
    elif args.dir_glob:
        targets = [Path(p) for p in sorted(_glob.glob(args.dir_glob))]
    else:
        ap.error("需 --in / --dir / --dir-glob 之一")

    if not targets:
        print("[fatal] 未匹配到任何目标", file=sys.stderr)
        return 2

    results, n_err, n_warn = [], 0, 0
    skipped = 0
    for t in targets:
        # targets 既可能是「任务目录」也可能是「market_data.json 本身」
        p = t if t.name == "market_data.json" else t / "market_data.json"
        if not p.exists():
            # 目录里根本没有 market_data.json = 该任务当天没跑，不是契约违规。
            # 计为 skipped 而非 error，否则信号被噪声淹没（2026-10-16 实测修正）。
            skipped += 1
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            results.append({"file": str(p), "error": [f"解析失败: {exc}"], "warn": []})
            n_err += 1
            continue
        e, w = check(doc, schema)
        results.append({"file": str(p), "error": e, "warn": w})
        n_err += len(e)
        n_warn += len(w)

    if args.json:
        print(json.dumps({"total": len(targets), "checked": len(results),
                          "skipped": skipped, "errors": n_err,
                          "warnings": n_warn, "results": results},
                         ensure_ascii=False, indent=1))
    else:
        for r in results:
            tag = "FAIL" if r["error"] else ("WARN" if r["warn"] else "OK")
            print(f"[{tag}] {r['file']}")
            for m in r["error"]:
                print(f"   [error] {m}")
            for m in r["warn"]:
                print(f"   [warn]  {m}")
        print(f"\n校验 {len(results)} 个文件 | 跳过（无产物）{skipped} "
              f"| error {n_err} | warning {n_warn}")
        print("[fai] 契约未通过" if n_err else
              ("[fail] 严格模式下警告视为失败" if args.strict and n_warn else "[ok] 契约通过"))

    if n_err:
        return 1
    return 1 if (args.strict and n_warn) else 0


if __name__ == "__main__":
    raise SystemExit(main())
