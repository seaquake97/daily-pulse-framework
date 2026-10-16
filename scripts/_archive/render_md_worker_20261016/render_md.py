#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""render_md.py — Markdown → 站点详情页统一渲染器（CLI 入口，薄装配）

FRAMEWORK-DESIGN v2.0 §2：上游任务退化为 md 内容源后，本脚本是详情页 HTML 的
**唯一生产者**。只做装配（解析参数 → 读文件 → 调 md_render.document → 落盘），
零业务逻辑；规则全在 md_render/ 包内。

用法：
  python3 scripts/render_md.py --md <path> --slug <slug> --date <YYYY-MM-DD> \
      --out <path> [--market-data <path>]

  # 14:30 基金指引（存量 md 无 front-matter，走 L2 启发式）
  python3 scripts/render_md.py \
      --md "/Users/lianghaizhen/WorkBuddy/基金每日操作指引（14:30）/2026-10-16/fund_operation_guide.md" \
      --slug fund-guide --date 2026-10-16 --out /tmp/fund-guide.html \
      --market-data "/Users/lianghaizhen/WorkBuddy/基金每日操作指引（14:30）/2026-10-16/market_data.json"

退出码：
  0  渲染成功
  1  参数/IO 错误（md 不存在、out 不可写、market-data 解析失败等）
  2  输入校验失败（slug 未知、日期非法、md 为空）

管线位置（publish_to_github.py 步骤 4 之后、4.5 sanitize 之前）：
  落盘 md → render_md.py → sanitize_body.py → frame_pass.py → build_site
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from md_render import document as D          # noqa: E402  组装层
from md_render.meta import TASK_NAMES, resolve_stage  # noqa: E402

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Markdown → 站点详情页统一渲染器（FRAMEWORK-DESIGN v2.0）")
    ap.add_argument("--md", required=True, help="源 Markdown 文件路径")
    ap.add_argument("--slug", required=True, choices=sorted(TASK_NAMES),
                    help="任务 slug（驱动标题规范）")
    ap.add_argument("--date", required=True, help="数据日期 YYYY-MM-DD")
    ap.add_argument("--out", required=True, help="输出 HTML 路径")
    ap.add_argument("--market-data", default=None,
                    help="market_data.json 路径（meta L3 兜底，可选）")
    args = ap.parse_args()

    if not _DATE_RE.match(args.date):
        print(f"[render][ERROR] 日期格式错误: {args.date}（应为 YYYY-MM-DD）",
              file=sys.stderr)
        return 2

    md_path = Path(args.md)
    if not md_path.is_file():
        print(f"[render][ERROR] md 文件不存在: {md_path}", file=sys.stderr)
        return 1
    md_text = md_path.read_text(encoding="utf-8", errors="replace")
    if not md_text.strip():
        print(f"[render][ERROR] md 内容为空: {md_path}", file=sys.stderr)
        return 2

    market_data = None
    if args.market_data:
        mdp = Path(args.market_data)
        if mdp.is_file():
            try:
                market_data = json.loads(mdp.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"[render][WARN] market_data.json 解析失败，按 L3 缺失继续: {e}",
                      file=sys.stderr)
        else:
            print(f"[render][WARN] market_data.json 不存在，按 L3 缺失继续: {mdp}",
                  file=sys.stderr)

    try:
        html, meta, log = D.render_page(md_text, args.slug, args.date, market_data)
    except ValueError as e:
        print(f"[render][ERROR] 渲染失败: {e}", file=sys.stderr)
        return 2

    out = Path(args.out)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(html.encode("utf-8"))
    except OSError as e:
        print(f"[render][ERROR] 输出写入失败 {out}: {e}", file=sys.stderr)
        return 1

    print(f"[render] 标题: {D.canonical_title(args.slug, args.date)}")
    print(f"[render] meta: rating={meta.rating or '数据缺口'}"
          f"（{meta.rating_src or 'L1/L2/L3 全缺'}）"
          f" stage={resolve_stage(meta, args.slug)}"
          f"（{meta.stage_src or 'SLUG_STAGE 兜底'}）")
    for line in log:
        print(f"[render] {line}")
    print(f"[render] 写出 {out}（{len(html.encode('utf-8'))} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
