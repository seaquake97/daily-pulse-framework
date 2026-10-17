#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_pipeline.py — 采集三步编排入口（GAP-A3）

## 为什么需要它

三步此前散落在 5 本任务书里靠自然语言串联：调 MCP → 手写 JSON → 跑评分 →
生成 md → 跑发布。每一步失败都靠人肉判断，且「跑到哪一步了」不可查。

本脚本把三步变成**一条可审计的命令**：

    run_pipeline.py --date 2026-10-16 --stage all [--dry-run]

## 分步与职责边界（重要）

  collect  取数：校验 market_data.json 契约（组装由内容侧完成——
           MCP 调用必须由 agent 执行，脚本无法替代；脚本负责**校验**，
           并可选执行确定性规范化）
  score    评分：跑 compute_signals.py → validate_market_data.py
           （顺序不可颠倒，validator 强制 verdict 存在）
  report   生成：校验报告 md 章节契约（撰写由内容侧完成，同上）
  publish  发布：调 publish_to_github.py（唯一推送者传 --push）

**为什么 collect/report 不做「生成」**：MCP 调用与研判撰写需要 LLM 判断力，
硬要脚本化只会得到一个巨大的 if-else。把「可确定性部分」（校验/规范化/
评分/发布）脚本化，把「需要判断部分」交给 agent 并用契约守住输出质量——
这是本框架的核心取舍。

## 环境变量（全部可覆盖，无硬编码）
  PULSE_WORKBUDDY_ROOT   工作区根（默认由 paths.WORKBUDDY_ROOT 推导，不写死用户名）
  PULSE_FRAMEWORK_ROOT  框架根（默认本文件的上上级）
  PULSE_SITE_ROOT       站点根（含 scripts/publish_to_github.py）
  PULSE_ENGINE_SCRIPTS  引擎脚本目录（默认 daily-decision-engine/scripts）
  PULSE_PYTHON          Python 解释器（默认 python3）

退出码：0 全部通过｜1 某步未通过｜2 参数错误｜3 步骤依赖缺失
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # <site>/framework/engine/
sys.path.insert(0, str(HERE.parent / "scripts"))   # A-04: framework/scripts 集中路径
import paths
FRAMEWORK = HERE.parent                          # <site>/framework/
# 站点根 = framework 的上一级（publish_to_github.py 在 <site>/scripts/ 下）
SITE_DEFAULT = FRAMEWORK.parent
SITE_ROOT = Path(os.environ.get("PULSE_SITE_ROOT", str(SITE_DEFAULT)))
WORKBUDDY = paths.WORKBUDDY_ROOT
PYTHON = os.environ.get("PULSE_PYTHON", sys.executable)
ENGINE = Path(os.environ.get(
    "PULSE_ENGINE_SCRIPTS",
    str(Path.home() / ".workbuddy/skills/daily-decision-engine/scripts")))

# slug → 上游任务目录名（发布管线同源映射）
TASK_DIR = {
    "stock-assistant": "股票助手",
    "fund-market": "基金每日盘面分析（11:00）",
    "fund-guide": "基金每日操作指引（14:30）",
    "stock-review": "股票复盘",
    "daily-review": "每日总复盘（15:30）",
}


def _log(step: str, msg: str) -> None:
    print(f"[{step}] {msg}", flush=True)


# 子模块脚本绝对路径（HERE 已 resolve，用相对拼接会随 cwd 变化而失效——
# 2026-10-16 实测踩过：单独跑校验器正常，经 pipeline 调用却全部报失败）
COLLECT_DIR = HERE / "collect"
REPORT_DIR = HERE / "report"
CHECK_MD = REPORT_DIR / "check_report.py"
NORMALIZE = COLLECT_DIR / "normalize_market_data.py"
CHECK_MD_DATA = COLLECT_DIR / "check_market_data.py"


def preflight() -> list[str]:
    """依赖预检：缺什么直接说，不在运行中途崩。

    ⚠ 环境变量必须在**函数内**重新解析，不能用导入时的模块级常量——
    那样测试/外部覆盖 PULSE_* 后预检仍按旧值判断，缺失依赖漏检，
    错误一路跑到子进程才爆（2026-10-16 实测踩过）。
    """
    engine = Path(os.environ.get("PULSE_ENGINE_SCRIPTS", str(ENGINE)))
    site = Path(os.environ.get("PULSE_SITE_ROOT", str(SITE_ROOT)))
    wb = Path(os.environ.get("PULSE_WORKBUDDY_ROOT", str(WORKBUDDY)))

    missing = []
    if not engine.is_dir():
        missing.append(f"引擎脚本目录不存在: {engine}（设 PULSE_ENGINE_SCRIPTS）")
    if not (site / "scripts" / "publish_to_github.py").exists():
        missing.append(f"发布脚本不存在: {site / 'scripts' / 'publish_to_github.py'}"
                       f"（设 PULSE_SITE_ROOT）")
    if not wb.is_dir():
        missing.append(f"工作区不存在: {wb}（设 PULSE_WORKBUDDY_ROOT）")
    return missing


def run_step(args, step: str, slug: str) -> bool:
    """跑一个任务的某一步，返回是否通过。"""
    wb = Path(os.environ.get("PULSE_WORKBUDDY_ROOT", str(WORKBUDDY)))
    site = Path(os.environ.get("PULSE_SITE_ROOT", str(SITE_ROOT)))
    eng = Path(os.environ.get("PULSE_ENGINE_SCRIPTS", str(ENGINE)))
    tdir = wb / TASK_DIR[slug] / args.date
    if not tdir.is_dir():
        _log(step, f"{slug}: 目录不存在 {tdir}（该任务当日未运行？）")
        return args.allow_missing

    if step == "collect":
        mdp = tdir / "market_data.json"
        if not mdp.exists():
            _log(step, f"{slug}: 无 market_data.json")
            return args.allow_missing
        if args.normalize:
            n = subprocess.run(
                [PYTHON, str(NORMALIZE),
                 "--in", str(mdp), "--task", slug, "--write"],
                capture_output=True, text=True)
            if n.returncode != 0:
                _log(step, f"{slug}: 规范化失败\n{n.stdout[-400:]}")
                return False
        c = subprocess.run(
            [PYTHON, str(CHECK_MD_DATA),
             "--dir", str(tdir)],
            capture_output=True, text=True)
        tail = (c.stdout or "").strip().splitlines()
        _log(step, f"{slug}: " + (tail[-1] if tail else "无输出"))
        return c.returncode == 0

    if step == "score":
        mdp = tdir / "market_data.json"
        kline = tdir / "sh000001_kline.json"
        if not mdp.exists():
            _log(step, f"{slug}: 无 market_data.json")
            return args.allow_missing
        # 顺序铁律：先 compute_signals（写入 verdict），后 validate（强制 verdict 存在）
        cs = subprocess.run(
            [PYTHON, str(eng / "compute_signals.py"), str(mdp)]
            + (["--kline", str(kline)] if kline.exists() else []),
            capture_output=True, text=True)
        if cs.returncode != 0:
            _log(step, f"{slug}: compute_signals 失败\n{(cs.stderr or cs.stdout)[-400:]}")
            return False
        v = subprocess.run(
            [PYTHON, str(eng / "validate_market_data.py"), str(mdp),
             "--expect-date", args.date],
            capture_output=True, text=True)
        _log(step, f"{slug}: " + ("评分+校验通过" if v.returncode == 0
                                  else (v.stderr or v.stdout)[-200:]))
        return v.returncode == 0

    if step == "report":
        mds = sorted(tdir.glob("*.md"))
        if not mds:
            _log(step, f"{slug}: 无 md 产出")
            return args.allow_missing
        ok = True
        for md in mds:
            r = subprocess.run(
                [PYTHON, str(CHECK_MD),
                 "--md", str(md), "--task", slug,
                 "--market-data", str(tdir / "market_data.json")],
                capture_output=True, text=True)
            tail = (r.stdout or "").strip().splitlines()
            status = tail[-1] if tail else "无输出"
            _log(step, f"{slug}/{md.name}: {status}")
            if r.returncode != 0:
                ok = False
                for ln in tail:
                    if "error" in ln:
                        _log(step, f"    {ln.strip()[:110]}")
        return ok

    if step == "publish":
        cmd = [PYTHON, str(site / "scripts" / "publish_to_github.py"),
               "--date", args.date]
        if args.unified_render:
            cmd.append("--unified-render")
        if args.push:
            cmd.append("--push")
        p = subprocess.run(cmd, capture_output=True, text=True)
        tail = (p.stdout or "").strip().splitlines()
        _log(step, f"exit={p.returncode} | " + (tail[-1] if tail else "无输出"))
        if p.returncode not in (0,):
            for ln in tail[-6:]:
                _log(step, f"    {ln.strip()[:110]}")
        return p.returncode == 0

    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="采集三步编排入口（GAP-A3）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  run_pipeline.py --date 2026-10-16 --stage all\n"
               "  run_pipeline.py --date 2026-10-16 --stage collect report --dry-run\n")
    ap.add_argument("--date", required=True)
    ap.add_argument("--stage", default="all",
                    help="collect|score|report|publish|all（可逗号分隔多选）")
    ap.add_argument("--task", default="all", help="slug 或 all")
    ap.add_argument("--push", action="store_true",
                    help="真实推送（仅发布阶段有效；默认只做门禁自检）")
    ap.add_argument("--unified-render", action="store_true",
                    help="发布阶段启用统一渲染（忽略上游旧 HTML）")
    ap.add_argument("--normalize", action="store_true",
                    help="collect 阶段先执行确定性规范化（补字段/改名）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将执行的命令")
    ap.add_argument("--allow-missing", action="store_true",
                    help="任务当日未产出时不算失败（默认算失败）")
    args = ap.parse_args(argv)

    if len(args.date) != 10 or args.date[4] != "-" or args.date[7] != "-":
        print(f"[fatal] 日期格式错误: {args.date!r}（应为 YYYY-MM-DD）", file=sys.stderr)
        return 2

    missing = preflight()
    if missing:
        for m in missing:
            print(f"[fatal] {m}", file=sys.stderr)
        return 3

    steps = (["collect", "score", "report", "publish"] if args.stage == "all"
             else [s.strip() for s in args.stage.split(",")])
    tasks = (list(TASK_DIR) if args.task == "all"
             else [args.task.strip()])

    print(f"=== 采集三步编排 · {args.date} ===")
    print(f"  阶段: {' → '.join(steps)}")
    print(f"  任务: {', '.join(tasks)}")
    print(f"  引擎: {ENGINE}")
    print(f"  推送: {'是（--push）' if args.push else '否（仅门禁自检）'}")
    if args.dry_run:
        print("  模式: dry-run（不实际执行）")
    print()

    if args.dry_run:
        site = Path(os.environ.get("PULSE_SITE_ROOT", str(SITE_ROOT)))
        eng = Path(os.environ.get("PULSE_ENGINE_SCRIPTS", str(ENGINE)))
        for st in steps:
            if st == "publish":
                cmd = [PYTHON, str(site / "scripts" / "publish_to_github.py"),
                       "--date", args.date]
                if args.unified_render:
                    cmd.append("--unified-render")
                if args.push:
                    cmd.append("--push")
                print("  would run:", " ".join(cmd))
            elif st == "score":
                print("  would run:",
                      f"{PYTHON} {eng / 'compute_signals.py'} <market_data.json> "
                      f"→ {eng / 'validate_market_data.py'} <market_data.json> "
                      f"--expect-date {args.date}")
            elif st == "collect":
                print("  would run:",
                      f"{PYTHON} {CHECK_MD_DATA} --dir <任务目录>/{args.date}")
            elif st == "report":
                print("  would run:",
                      f"{PYTHON} {CHECK_MD} --md <md> --task <slug> "
                      f"--market-data <market_data.json>")
        return 0

    failed: list[str] = []
    for st in steps:
        _log(st, f"── 开始 ──")
        if st == "publish":
            ok = run_step(args, st, tasks[0] if tasks else "daily-review")
            if not ok:
                failed.append(f"publish@{args.date}")
        else:
            for slug in tasks:
                if not run_step(args, st, slug):
                    failed.append(f"{st}:{slug}")
        _log(st, f"── 结束 ──")
        print()

    if failed:
        print(f"[fail] {len(failed)} 处未通过：")
        for f in failed:
            print(f"  - {f}")
        return 1
    print("[ok] 全流程通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
