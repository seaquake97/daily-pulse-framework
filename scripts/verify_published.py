#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_published.py — 发布后一致性校验（CAP-03）

## 为什么必须有这道闸

2026-10-16 两位专家（PM C-01、架构师 A-06）**独立**发现同一个问题：
`_stage`（构建暂存）里的降级轮已经撤下方向值，但 `_git_pulse`（线上源仓）
未同步——**线上仍在输出「数据源降级」与「进攻 +0.510」并列的危险组合**。
根因不是逻辑错，而是**流程没有"发布后验证"这一步**：推送成功被当成发布成功。

本脚本把 `_stage` 与 `_git_pulse` 逐文件比对，并额外做内容级断言
（降级条目不得带方向值）。任何漂移 exit 1。

## 用法
    python3 verify_published.py                 # 比对 + 内容断言
    python3 verify_published.py --json          # 机器可读

退出码：0 一致｜1 发现漂移或内容违规｜2 参数/IO 错误
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STAGE = ROOT / "_stage" / "docs"
PULSE = ROOT / "_git_pulse" / "docs"
# 允许的漂移：这些文件不参与逐字节比对（时间戳/构建元信息）
SKIP = {"manifest.json"}


def _files(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def _fp(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="发布后一致性校验（CAP-03）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not STAGE.is_dir() or not PULSE.is_dir():
        print(f"[fatal] 目录缺失: stage={STAGE.exists()} pulse={PULSE.exists()}",
              file=sys.stderr)
        return 2

    s_files, p_files = _files(STAGE), _files(PULSE)
    only_stage = sorted(s_files - p_files - SKIP)
    only_pulse = sorted(p_files - s_files - SKIP)
    diff = []
    for rel in sorted(s_files & p_files):
        if rel in SKIP:
            continue
        if _fp(STAGE / rel) != _fp(PULSE / rel):
            diff.append(rel)

    # 内容级断言：降级条目不得带方向值（两位专家实测的线上问题）
    content_bad = []
    for rel in sorted(f for f in s_files if f.endswith("entries.json")):
        for e in json.loads((STAGE / rel).read_text(encoding="utf-8")):
            if e.get("degraded") and (e.get("rating") or e.get("sigma") is not None):
                content_bad.append(f"{rel}:{e.get('slug')} rating={e.get('rating')} "
                                   f"sigma={e.get('sigma')}")
    # HTML 层：降级卡片不得同现评级徽章
    for rel in sorted(f for f in s_files if f.endswith("index.html")):
        t = (STAGE / rel).read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'<li class="tl-item"[^>]*>(.*?)</li>', t, re.S):
            seg = m.group(1)
            if "数据源降级" in seg and 'class="rating ' in seg:
                content_bad.append(f"{rel}: 降级卡片同现评级徽章")

    drift = len(only_stage) + len(only_pulse) + len(diff)
    result = {"onlyStage": only_stage, "onlyPulse": only_pulse,
              "differing": diff, "contentViolations": content_bad,
              "driftCount": drift}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(f"文件数: stage {len(s_files)} | pulse {len(p_files)}")
        if only_stage:
            print(f"[仅 stage 有] {len(only_stage)} 个（尚未推送）")
            for f in only_stage[:6]:
                print(f"    {f}")
        if only_pulse:
            print(f"[仅 pulse 有] {len(only_pulse)} 个（线上多余）")
            for f in only_pulse[:6]:
                print(f"    {f}")
        if diff:
            print(f"[内容不一致] {len(diff)} 个")
            for f in diff[:6]:
                print(f"    {f}")
        if content_bad:
            print(f"[内容违规] {len(content_bad)} 处")
            for c in content_bad[:6]:
                print(f"    {c}")
        if not drift and not content_bad:
            print("[ok] stage 与线上一致，内容契约通过")
        else:
            print(f"[fail] 漂移 {drift} 个文件 | 内容违规 {len(content_bad)} 处"
                  f" —— 需重新推送 publish_to_github.py --push")
    return 1 if (drift or content_bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
