#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""render_md.py — 统一渲染器门面 + CLI（薄装配层，零业务逻辑）

框架唯一呈现层生产者（FRAMEWORK-DESIGN v2.0 §2）：上游任务只产 md（内容层），
本脚本渲染为详情页 HTML（呈现层），终结「五个任务五套 HTML 生成器」的风格分裂
与 md-only 任务无页面问题（用户实锤：14:30 推送是空的）。

本文件只做三件事（code-organization 铁律：入口只装配）：
    解析参数 → 三步装配（extract_meta → render_md → build_page）→ 落盘
全部规则在 md_render/ 包内：meta（标题规范 + 三级兜底）/ blocks（块解析）/
inline（行内渲染）/ document（组装 + 章节视觉映射）。

再导出（publish_to_github 与 test_render_md 的导入契约，禁改签名）：
    render_title / extract_meta / render_md / build_page / _clean_title / _math_text

契约（FRAMEWORK-DESIGN v2.0）：
  - 标题规范：<TASK_NAMES[slug]> · YYYY-MM-DD（周X）<阶段标签>
  - meta 三级兜底：L1 front-matter → L2 正文启发式 → L3 market_data.json
    → 诚实降级「数据缺口」徽章（严禁编造评级）
  - md 正文 100% 无损保留：只做结构包裹与视觉映射，不删不改任何文字
  - 零 script / 零渐变 / 零裸 hex / 零内联 CSS（样式靠 frame_pass 注入的
    detail-frame.css，单一 Token 源）
  - 幂等：纯函数式渲染，同输入两次输出字节一致

退出码：0 成功 / 1 IO 失败 / 2 参数或校验失败（publish 步骤 4.1 据此外爆）

用法：
  render_md.py --md <path> --slug <slug> --date <YYYY-MM-DD> --out <path>
               [--market-data <market_data.json>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from md_render.document import build_page, render_md            # noqa: E402
from md_render.inline import _math_text                         # noqa: E402
from md_render.meta import (SLUG_STAGE, TASK_NAMES, _clean_title,  # noqa: E402
                            extract_meta, render_title)

__all__ = ["TASK_NAMES", "SLUG_STAGE", "render_title", "extract_meta",
           "render_md", "build_page", "main"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="统一渲染器：任务 md → Apple 风格 HTML")
    ap.add_argument("--md", required=True, help="上游任务产出的 Markdown 路径")
    ap.add_argument("--slug", required=True, choices=list(TASK_NAMES),
                    help="任务 slug（决定标题阶段标签）")
    ap.add_argument("--date", required=True, help="报告日期 YYYY-MM-DD")
    ap.add_argument("--out", required=True, help="输出 HTML 路径")
    ap.add_argument("--market-data", default=None,
                    help="market_data.json（L3 兜底数据源，可缺）")
    args = ap.parse_args(argv)

    # ---- 读入（IO 失败 → 退出码 1，由 publish 转退出码 3）----
    try:
        md_text = Path(args.md).read_text(encoding="utf-8")
    except OSError as e:
        print(f"[render][ERROR] 读取 md 失败: {e}", file=sys.stderr)
        return 1
    market_data = None
    if args.market_data:
        try:
            market_data = json.loads(Path(args.market_data).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            # L3 是兜底源，缺失/损坏不阻断渲染（L1/L2 仍可能给出 meta）
            print(f"[render][warn] market-data 不可用，L3 兜底跳过: {e}",
                  file=sys.stderr)

    # ---- 三步装配（校验失败 → 退出码 2）----
    log: list[str] = []
    try:
        meta = extract_meta(md_text, market_data)
        body = render_md(md_text, log)
        page = build_page(args.slug, args.date, meta, body)
    except ValueError as e:                       # 日期非法 / slug 未知等
        print(f"[render][ERROR] {e}", file=sys.stderr)
        return 2

    # ---- 落盘（原子性由 publish 的阶段目录 + 重跑幂等保证）----
    out = Path(args.out)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
    except OSError as e:
        print(f"[render][ERROR] 写入失败: {e}", file=sys.stderr)
        return 1

    for ln in log:
        print(f"[render] {ln}")
    print(f"[render] {args.slug} {args.date}: {len(page.encode('utf-8'))} bytes | "
          f"rating={meta.get('rating')} stage={meta.get('stage')} "
          f"(meta source: {meta.get('source')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
