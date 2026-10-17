#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ci_verify.py — 统一 CI 总调度器（把散落的测试套件收敛成一个命令）

    --only K      只跑名称含 K 的项（可重复传）      --exclude K  排除名称含 K 的项（记 SKIP）
    --skip-network 跳过需真实网络的项                --json       机器可读（Actions 消费）
    --list        只打印清单不执行
退出码：0 全部通过（SKIP 不算失败）｜1 有失败项｜2 参数错误。
设计约束：纯标准库 / 路径由 Path(__file__).resolve() 推导（禁止硬编码）/ 单文件 <= 300 行。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable or "python3"
TIMEOUT_SEC = 180
FAIL_TAIL_LINES = 20

TEST_SUITES = (
    "scripts/test_conclusion_contract.py",
    "scripts/test_content_contract.py",
    "scripts/test_dark_mode.py",
    "scripts/test_frame_fixed_point.py",
    "scripts/test_path_scrub.py",
    "scripts/test_render_md.py",
    "scripts/test_sanitize_gate_pipeline.py",
    "scripts/test_sanitize_gate_visual.py",
    "scripts/test_sanitize_pipeline.py",
    "scripts/test_sanitize_scope.py",
    "scripts/test_site_links.py",
    "scripts/test_emoji_body.py",
    "scripts/test_real_outputs.py",
    "framework/scripts/test_validate_config.py",
    "framework/scripts/test_strategies.py",
    "framework/scripts/test_render_strategies.py",
    "framework/engine/signals/test_technical.py",
    "framework/engine/signals/test_signals.py",
    "framework/engine/signals/test_compute_signals.py",
    "framework/engine/collect/test_merge_fallback.py",
    "framework/engine/collect/test_primary_health.py",
    "framework/engine/collect/test_fetch_fallback_data.py",
    "scripts/test_ci_verify.py",
)

RESERVED_SUITES = (
    "framework/engine/collect/test_fallback_fetcher.py",
)

VALIDATORS = (
    ("scripts/scan_compliance.py", (), "compliance"),
    ("scripts/verify_published.py", (), "exit"),
    ("framework/scripts/strategies.py", ("--dir", "{ROOT}/framework/config/strategies"), "exit"),
    ("framework/scripts/render_strategies.py", (), "exit"),
)

NETWORK_SUITES = frozenset()

COMPLIANCE_GATES = (
    ("emoji(P0)", (r"emoji\s*数（P0\s*口径）:\s*(\d+)", r"emoji\(P0\):\s*基线\s*\d+\s*→\s*当前\s*(\d+)"), 0),
    ("紫粉渐变", (r"紫粉渐变/靛蓝:\s*(\d+)",), 0),
    ("弹跳缓动", (r"弹跳缓动:\s*(\d+)",), 0),
)

STATUS_PASS, STATUS_FAIL, STATUS_SKIP = "PASS", "FAIL", "SKIP"


def _item(root: Path, rel: str, kind: str, args: tuple, reserved: bool) -> dict:
    return {
        "name": rel, "kind": kind, "path": root / rel,
        "args": [a.replace("{ROOT}", str(root)) for a in args],
        "network": rel in NETWORK_SUITES, "reserved": reserved,
    }


def build_manifest(root: Path = ROOT) -> list:
    items = [_item(root, r, "test", (), False) for r in TEST_SUITES]
    items += [_item(root, r, "test", (), True) for r in RESERVED_SUITES]
    items += [_item(root, r, k, a, False) for r, a, k in VALIDATORS]
    return items


def select_items(items, only=None, skip_network=False, exclude=None) -> list:
    keys = [str(k).lower() for k in (only or [])]
    drop = [str(k).lower() for k in (exclude or [])]
    picked = []
    for it in items:
        if keys and not any(k in it["name"].lower() for k in keys):
            continue
        reason = "按 --skip-network 跳过" if (skip_network and it["network"]) else ""
        if not reason and any(k in it["name"].lower() for k in drop):
            reason = "按 --exclude 排除"
        picked.append((it, reason))
    return picked


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _blob(value) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def _unittest_counts(text: str) -> dict:
    ran = re.search(r"^Ran (\d+) tests? in", text, re.M)
    skipped = re.search(r"\(skipped=(\d+)\)", text)
    return {"child_ran": int(ran.group(1)) if ran else None,
            "child_skipped": int(skipped.group(1)) if skipped else 0}


def check_compliance(text: str) -> list:
    bad = []
    for label, patterns, limit in COMPLIANCE_GATES:
        hits = []
        for pat in patterns:
            hits += [int(n) for n in re.findall(pat, text)]
        if not hits:
            bad.append(f"{label} 指标行缺失（扫描输出格式已变，护栏失守）")
            continue
        over = max(h for h in hits if h > limit) if any(h > limit for h in hits) else None
        if over is not None:
            bad.append(f"{label} 计数 {over}（上限 {limit}）")
    return bad


def run_item(item: dict, skip_reason: str = "", timeout: int = TIMEOUT_SEC) -> dict:
    res = {"name": item["name"], "kind": item["kind"], "path": str(item["path"]),
           "status": STATUS_SKIP, "duration_ms": 0, "exit_code": None,
           "timed_out": False, "detail": skip_reason, "output": ""}
    if skip_reason:
        return res
    if not item["path"].is_file():
        if item["reserved"]:
            res["detail"] = "预留项尚未落地（文件缺失，按跳过处理）"
            return res
        res["status"], res["detail"] = STATUS_FAIL, "测试文件缺失"
        return res

    cmd = [PY, str(item["path"])] + list(item["args"])
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as err:
        res.update(status=STATUS_FAIL, timed_out=True, duration_ms=_ms(t0),
                   detail=f"超过 {timeout}s 未结束，已杀掉子进程", output=_blob(err.stdout))
        return res
    except OSError as err:
        res.update(status=STATUS_FAIL, duration_ms=_ms(t0), detail=f"无法启动子进程: {err}")
        return res

    res["duration_ms"] = _ms(t0)
    res["exit_code"] = proc.returncode
    res["output"] = _blob(proc.stdout) + _blob(proc.stderr)
    if item["kind"] == "compliance":
        gates = check_compliance(_blob(proc.stdout))
        res["status"] = STATUS_FAIL if gates else STATUS_PASS
        if gates:
            res["detail"] = "合规护栏未通过: " + "; ".join(gates)
        return res
    if proc.returncode == 0:
        res["status"] = STATUS_PASS
    else:
        res.update(status=STATUS_FAIL, detail=f"子进程退出码 {proc.returncode}")
    if item["kind"] == "test":
        res.update(_unittest_counts(res["output"]))
        ran, skipped = res["child_ran"], res["child_skipped"]
        if ran == 0:
            res.update(status=STATUS_FAIL, detail="套件未执行任何用例（Ran 0 tests）")
        elif res["status"] == STATUS_PASS and ran is not None and skipped >= ran:
            res.update(status=STATUS_SKIP, detail=f"套内 {ran} 个用例全被跳过（产物缺失/环境不满足），绿灯不可信")
    return res


def summarize(results) -> dict:
    return {
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == STATUS_PASS),
        "failed": sum(1 for r in results if r["status"] == STATUS_FAIL),
        "skipped": sum(1 for r in results if r["status"] == STATUS_SKIP),
    }


def _fmt(ms: int) -> str:
    return f"{ms / 1000:.2f}s"


def _dump(res: dict) -> None:
    lines = (res.get("output") or "").strip().splitlines()
    if not lines:
        return
    print("        ---- 子进程输出尾部 ----", file=sys.stderr)
    for line in lines[-FAIL_TAIL_LINES:]:
        print(f"        {line}", file=sys.stderr)


def main(argv=None, items=None) -> int:
    parser = argparse.ArgumentParser(prog="ci_verify.py", description="统一 CI 总调度器")
    parser.add_argument("--only", action="append", metavar="KEYWORD", help="只跑名称含关键字的项")
    parser.add_argument("--exclude", action="append", metavar="KEYWORD", help="排除名称含关键字的项（记为 SKIP）")
    parser.add_argument("--skip-network", action="store_true", help="跳过需要真实网络的项")
    parser.add_argument("--json", action="store_true", dest="as_json", help="输出机器可读 JSON")
    parser.add_argument("--list", action="store_true", help="只打印清单不执行")
    args = parser.parse_args(argv)
    for flag, values in (("--only", args.only), ("--exclude", args.exclude)):
        if values is not None and any(not v.strip() for v in values):
            parser.error(f"{flag} 关键字不能为空字符串")

    picked = select_items(build_manifest() if items is None else items,
                          only=args.only, skip_network=args.skip_network,
                          exclude=args.exclude)
    if args.list:
        for it, _ in picked:
            print(it["name"])
        return 0

    if not args.as_json:
        print(f"[ci_verify] {len(picked)} 项待执行 | 仓库根 {ROOT}", flush=True)
    results, t0 = [], time.monotonic()
    for it, reason in picked:
        res = run_item(it, reason)
        results.append(res)
        if not args.as_json:
            print(f"[{res['status']}] {res['name']} ({_fmt(res['duration_ms'])})", flush=True)
            if res["detail"]:
                print(f"        {res['detail']}", flush=True)
        if res["status"] == STATUS_FAIL:
            _dump(res)
    counts = summarize(results)
    counts["duration_ms"] = _ms(t0)

    if args.as_json:
        payload = {
            "ok": counts["failed"] == 0,
            "total": counts["total"], "passed": counts["passed"],
            "failed": counts["failed"], "skipped": counts["skipped"],
            "duration_ms": counts["duration_ms"],
            "items": [
                {"name": r["name"], "status": r["status"],
                 "duration_ms": r["duration_ms"], "exit_code": r["exit_code"],
                 "timed_out": r["timed_out"], "kind": r["kind"],
                 "path": r["path"], "detail": r["detail"],
                 "child_ran": r.get("child_ran"),
                 "child_skipped": r.get("child_skipped")} for r in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1 if counts["failed"] else 0

    print(f"\n总计 {counts['total']} 项 | 通过 {counts['passed']} | "
          f"失败 {counts['failed']} | 跳过 {counts['skipped']} "
          f"| 耗时 {_fmt(counts['duration_ms'])}")
    for r in results:
        if r["status"] == STATUS_FAIL:
            print(f"  失败项: {r['name']} —— {r['detail']}", file=sys.stderr)
            print(f"           重跑: {PY} {r['path']}", file=sys.stderr)
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
