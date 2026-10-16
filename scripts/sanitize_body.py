#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""sanitize_body.py — 发布层正文消毒入口（CLI + 薄编排）

把上游任务产出的研判正文 HTML 转换为与站点框架同风格（Apple Token 体系）。

**只改呈现，不改内容语义。** 换 emoji 载体、去渐变、摘 JS、收敛色值、
对齐标题层级 —— 可见文本一字不删。唯一的元素级删除是 <script> 与 <canvas>，
而 script 承载的数据在删除前已验证「在静态文本中有冗余」或被静态化保留。

用法
    # 单文件（stdout 输出净化结果，报告写 stderr）
    python3 scripts/sanitize_body.py --in body.html --out clean.html

    # 目录批量（就地覆盖，加 --dry-run 只报告不改文件）
    python3 scripts/sanitize_body.py --dir _stage/docs/daily --in-place --dry-run

    # 报告落盘（JSON，供门禁与证据归档）
    python3 scripts/sanitize_body.py --dir _stage/docs/daily --in-place \
        --report evidence/sanitize-report.json

退出码
    0  成功
    1  参数/IO 错误
    2  存在 needs-manual-review 项（有内容被判为需人工确认，不算干净通过）

依赖方向：本文件是入口，只做装配（解析参数 → 调 sanitizer 包 → 写文件），
不含任何消毒规则；规则全在 sanitizer/ 包内。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import site_theme as T                       # noqa: E402  基础设施：图标表
from sanitizer import emoji_map as EM        # noqa: E402
from sanitizer.core import load_utilities_css, sanitize_html  # noqa: E402
from sanitizer.report import SanitizeReport  # noqa: E402


def verify_icons() -> None:
    """构建期校验：emoji 映射表引用的 symbol 必须都在 site_theme 里定义。

    不做这步，映射表与图标表不同步时会在渲染某个页面时才 KeyError，
    变成难以定位的沉默失效。这里提前失败并说清缺哪个。
    """
    missing = EM.verify_symbols(set(T.SYMBOLS))
    if missing:
        raise SystemExit(f"[FATAL] emoji 映射表引用了未定义的 symbol: {missing}")


# 框架页（由 build_site.py 生成）不参与正文消毒。
# 理由：框架页已全量合规（emoji=0 / gradient=0 / script=0），且它们在
# 步骤 5 会被重新生成 —— 对它们做消毒既无收益，又会破坏框架页的字节幂等。
FRAMEWORK_PAGES = frozenset({"index.html"})


def _report_lines(rep: SanitizeReport) -> list[str]:
    return [f"    [{c.kind}] {c.detail}" for c in rep.changes]


def process_file(path: Path, utilities: str | None, dry_run: bool) -> SanitizeReport:
    """净化单个文件；dry_run 时只报告不落盘。"""
    original = path.read_text(encoding="utf-8")
    cleaned, report = sanitize_html(original, source=str(path),
                                    utilities_css=utilities)
    if not dry_run and cleaned != original:
        path.write_text(cleaned, encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="发布层正文消毒（换皮不阉割）")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--in", dest="infile", help="单个 HTML 文件")
    src.add_argument("--dir", help="目录（递归处理 *.html）")
    ap.add_argument("--out", help="输出文件（仅配合 --in）")
    ap.add_argument("--in-place", action="store_true", help="就地覆盖原文件")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    ap.add_argument("--report", help="审计报告 JSON 落盘路径")
    ap.add_argument("--utilities", default=None,
                    help="预编译工具类 CSS 路径（默认 scripts/assets/body-utilities.css）")
    args = ap.parse_args()

    verify_icons()
    utilities = load_utilities_css(args.utilities)

    reports: list[dict] = []
    manual_review = 0

    if args.infile:
        p = Path(args.infile)
        if not p.exists():
            print(f"[ERROR] 文件不存在: {p}", file=sys.stderr)
            return 1
        original = p.read_text(encoding="utf-8")
        cleaned, rep = sanitize_html(original, source=str(p),
                                     utilities_css=utilities)
        if args.out:
            out = Path(args.out)
            if not args.dry_run:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(cleaned, encoding="utf-8")
        elif args.in_place and not args.dry_run:
            p.write_text(cleaned, encoding="utf-8")
        reports.append(rep.to_dict())
        manual_review += rep.count_of("needs-manual-review")
        print(f"[sanitize] {p.name}: {rep.summary() or 'no-change'}")
        for line in _report_lines(rep):
            print(line)
    else:
        root = Path(args.dir)
        if not root.is_dir():
            print(f"[ERROR] 目录不存在: {root}", file=sys.stderr)
            return 1
        files = sorted(p for p in root.rglob("*.html")
                       if p.name not in FRAMEWORK_PAGES)
        skipped = sorted(p.name for p in root.rglob("*.html")
                         if p.name in FRAMEWORK_PAGES)
        if skipped:
            print(f"[skip] 框架页不消毒: {', '.join(sorted(set(skipped)))}")
        if not files:
            print(f"[WARN] {root} 下没有待消毒的正文 *.html")
        for p in files:
            rep = process_file(p, utilities, args.dry_run)
            reports.append(rep.to_dict())
            manual_review += rep.count_of("needs-manual-review")
            print(f"[sanitize] {p.relative_to(root)}: {rep.summary() or 'no-change'}")
            for line in _report_lines(rep):
                print(line)

    if args.report:
        rp = Path(args.report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps({"files": reports}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
        print(f"[report] {rp}")

    print(f"\n[summary] 文件 {len(reports)} 个 | "
          f"待人工确认 {manual_review} 处")
    if manual_review:
        print("[WARN] 存在 needs-manual-review：已保守保留而非删除，需人工判断")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())