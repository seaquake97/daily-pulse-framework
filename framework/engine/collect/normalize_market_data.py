#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""normalize_market_data.py — market_data.json 规范化修复器（GAP-A1）

## 为什么需要（2026-10-16 实测 22 份产物发现）

两类**真实生产漂移**，它们一直在悄悄发生，靠人眼看不出来：

  ① **data_stage 缺失**（5 份）：11:00 基金盘面连续两天没写该字段。
     后果：发布层靠 SLUG_STAGE 兜底才没出错——一旦任务名变化或新增任务，
     站点就会把盘中数据标成收盘数据（口径错误，且无任何报错）。

  ② **chg_pct / change_percent 双写法**（旧产物）：10-13 总复盘的指数项
     只有 `chg_pct`，连 `name`/`time` 都没有。消费方读 `change_percent`
     会静默拿到 None —— 涨跌数据在页面上凭空消失，不报错。

本脚本做**确定性规范化**（不猜数据、不补数值）：
  · 补 data_stage（来自调用方显式传入或任务→时点映射，绝不默认 close）
  · chg_pct → change_percent 改名（值原样搬移）
  · 补 data_gaps 说明（记录本次规范化动作，可追溯）

## 铁律
  **禁止凭空造数**：字段缺失且无可靠来源时，只在 data_gaps 声明缺失，
  绝不填 0 或估算值——补零是本项目最严重的 P0（见 C-4 契约）。

用法
    python3 normalize_market_data.py --in market_data.json --stage intraday [--write]
    python3 normalize_market_data.py --dir-glob '/path/*/2026-10-16' --task fund-market [--write]

退出码：0 成功｜1 校验仍不通过｜2 参数/IO 错误
"""
from __future__ import annotations

import argparse
import glob as _glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from check_market_data import STAGES, check, load_schema  # noqa: E402

# slug → 该任务的数据时点（与 daily-decision-engine 的调度语义一致）。
# 不用「默认 close」兜底：时点猜错会让站点标注错误口径，属静默故障。
TASK_STAGE = {
    "stock-assistant": "pre_open",
    "fund-market": "intraday",
    "fund-guide": "intraday",
    "stock-review": "close",
    "daily-review": "close",
}
# 目录名 → slug（上游任务目录与站点 slug 不同名，无法自动推断时据此回退）
DIR_SLUG = {
    "股票助手": "stock-assistant",
    "基金每日盘面分析（11:00）": "fund-market",
    "基金每日操作指引（14:30）": "fund-guide",
    "股票复盘": "stock-review",
    "每日总复盘（15:30）": "daily-review",
}


def normalize(doc: dict, stage: str | None) -> tuple[dict, list[str]]:
    """返回 (规范化后副本, 动作日志)。原对象不修改。"""
    out = json.loads(json.dumps(doc, ensure_ascii=False))
    log: list[str] = []

    gaps = out.setdefault("data_gaps", [])
    if not isinstance(gaps, list):
        gaps = []
        out["data_gaps"] = gaps

    # ① data_stage
    if out.get("data_stage") in (None, "", "null"):
        if stage and stage in STAGES:
            out["data_stage"] = stage
            log.append(f"补 data_stage={stage}（来源：调用方显式指定）")
        else:
            log.append("⚠ data_stage 仍缺失，且未提供可推断来源——已记入 data_gaps，"
                       "**不做默认填充**（默认 close 会造成口径错标）")

    # ② chg_pct → change_percent（只改名，不改值）
    for section in ("indices", "holdings"):
        block = out.get(section)
        if not isinstance(block, dict):
            continue
        for key, item in block.items():
            if not isinstance(item, dict):
                continue
            if "chg_pct" in item:
                if "change_percent" in item:
                    if item["chg_pct"] != item["change_percent"]:
                        log.append(f"⚠ {section}.{key} 双字段值不一致"
                                   f"（chg_pct={item['chg_pct']} vs "
                                   f"change_percent={item['change_percent']}），"
                                   f"保留 change_percent 并记缺口")
                        gaps.append(f"{section}.{key}: chg_pct 与 change_percent "
                                    f"值不一致，已以 change_percent 为准")
                    else:
                        log.append(f"{section}.{key}: 删除冗余 chg_pct"
                                   f"（与 change_percent 同值）")
                    item.pop("chg_pct", None)
                else:
                    item["change_percent"] = item.pop("chg_pct")
                    log.append(f"{section}.{key}: chg_pct → change_percent（值原样搬移）")

    # ③ 残缺声明（index 项缺 name/time 等非必填但影响展示的字段）
    for section in ("indices",):
        block = out.get(section)
        if isinstance(block, dict):
            thin = [k for k, v in block.items()
                    if isinstance(v, dict) and ("name" not in v or "time" not in v)]
            if thin:
                gaps.append(f"{section} 的 {', '.join(thin[:6])}"
                            f"{' 等' if len(thin) > 6 else ''} 缺 name/time，"
                            f"展示层将退化为纯代码")

    if log:
        gaps.insert(0, "规范化处理：" + "；".join(log[:3])
                    + (f"；等 {len(log)} 项" if len(log) > 3 else ""))
    return out, log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="market_data.json 规范化修复（GAP-A1）")
    ap.add_argument("--in", dest="infile")
    ap.add_argument("--dir")
    ap.add_argument("--dir-glob", dest="dir_glob")
    ap.add_argument("--stage", choices=list(STAGES), help="显式指定 data_stage")
    ap.add_argument("--task", choices=list(TASK_STAGE),
                    help="由任务推导 data_stage（与 --stage 二选一）")
    ap.add_argument("--write", action="store_true", help="写回文件（默认仅预演）")
    ap.add_argument("--recheck", action="store_true", default=True,
                    help="规范化后重跑契约校验（默认开启）")
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

    changed = failed = 0
    for t in targets:
        p = t if t.name == "market_data.json" else t / "market_data.json"
        if not p.exists():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"[FAIL] {p}: 解析失败 {exc}")
            failed += 1
            continue

        stage = args.stage
        if not stage and args.task:
            stage = TASK_STAGE[args.task]
        if not stage:
            guess = DIR_SLUG.get(p.parent.parent.name)
            stage = TASK_STAGE.get(guess) if guess else None

        new_doc, log = normalize(doc, stage)
        if not log:
            print(f"[skip] {p}: 无需规范化")
            continue
        changed += 1
        print(f"[fix] {p}")
        for m in log:
            print(f"      · {m}")
        if args.write:
            p.write_text(json.dumps(new_doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
            e, _w = check(new_doc, schema)
            if e:
                print(f"      ✗ 写回后契约仍未通过: {e[:2]}")
                failed += 1
            else:
                print("      ✓ 写回且契约通过")
        else:
            print("      （预演，加 --write 落盘）")

    print(f"\n规范化 {changed} 个 | 失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
