#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""inject_strategies.py — 把策略片段注入静态页（默认 dry-run，显式 --write 才落盘）

## 为什么默认干跑

  目标页 site/methodology/index.html 是人工维护的静态资产，与构建链路多人并行
  编辑。默认写盘会在一次误敲命令里覆盖别人的改动，且不可回滚。因此：
  **不带 --write 一律只算不改**，包括指定了 --out 的场景。

## 为什么用「开始/结束」成对锚点

  单锚点 <!--__STRATEGIES__--> 一旦被替换掉，第二次注入就找不到落点，重建链路
  只能先手工补锚。成对锚点把「上次注入的内容」圈成区间，重复注入是幂等的：
  第 N 次与第 1 次之外，第 2..N 次产出的字节完全一致（构建幂等的前提）。

## 用法

    python3 inject_strategies.py                       # 干跑，只打报告
    python3 inject_strategies.py --write               # 写回原文件
    python3 inject_strategies.py --out /tmp/preview.html --write
    python3 inject_strategies.py --src <页> --dir <策略目录> --no-css

## 退出码

  0  成功（含「无变化」空操作）
  2  源文件缺失 / 不可读
  3  锚点 <!--__STRATEGIES__--> 缺失（显式报错，绝不静默跳过）
  4  缺 </head> 且未关闭样式注入（无处安放 CSS，宁可失败不产出裸 HTML）
  5  写盘失败
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import render_strategies as R  # noqa: E402

# 本文件位置：<project>/framework/scripts/inject_strategies.py
_ROOT = _HERE.parents[1]
DEFAULT_SRC = _ROOT / "site" / "methodology" / "index.html"

_EXIT_SRC, _EXIT_ANCHOR, _EXIT_HEAD, _EXIT_WRITE = 2, 3, 4, 5
_HEAD_RE = re.compile(r"</head\s*>", re.I)
_STYLE_RE = re.compile(r'<style\s+data-origin="strategies"[^>]*>.*?</style>', re.S | re.I)


def inject_fragment(html: str, fragment: str) -> str:
    """按锚点区间替换片段。锚点缺失抛 ValueError——静默跳过会让后续构建悄悄少一块。"""
    begin = html.find(R.BEGIN_MARK)
    if begin < 0:
        raise ValueError(f"目标页缺少注入锚点 {R.BEGIN_MARK}")
    end = html.find(R.END_MARK, begin + len(R.BEGIN_MARK))
    tail = end + len(R.END_MARK) if end >= 0 else begin + len(R.BEGIN_MARK)

    block = f"{R.BEGIN_MARK}\n{fragment}\n{R.END_MARK}" if fragment else R.BEGIN_MARK
    # 空片段只留裸锚点：内容缺失时保留落点，下次有策略还能原地补回来
    return html[:begin] + block + html[tail:]


def inject_css(html: str, css: str) -> str:
    """把策略区块样式注入 <head> 末尾（与 frame_pass 的 data-origin 防腐标记同制）。"""
    block = f'<style {R.STYLE_ORIGIN}>\n{css.strip()}\n</style>\n'
    if _STYLE_RE.search(html):
        return _STYLE_RE.sub(lambda _m: block.strip(), html, count=1)
    if not _HEAD_RE.search(html):
        raise ValueError("目标页缺少 </head>，无法注入样式")
    return _HEAD_RE.sub(lambda _m: block + _m.group(0), html, count=1)


def build(src: Path, strategy_dir: Path, *, with_css: bool = True) -> tuple[str, dict]:
    """产出注入后的完整页面 + 变更报告。"""
    original = src.read_text(encoding="utf-8")
    fragment = R.render_fragment(strategy_dir)
    result = inject_fragment(original, fragment)
    css_done = False
    if with_css:
        result = inject_css(result, R.strategy_css())
        css_done = True
    count = fragment.count('<article class="strat-card"')
    return result, {
        "strategies": count,
        "had_endmark": R.END_MARK in original,
        "css_injected": css_done,
        "changed": result != original,
        "bytes_before": len(original.encode("utf-8")),
        "bytes_after": len(result.encode("utf-8")),
    }


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(_ROOT))
    except ValueError:
        return path.name


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="策略片段注入静态页（默认 dry-run）")
    ap.add_argument("--src", default=str(DEFAULT_SRC), help="目标静态页")
    ap.add_argument("--dir", default=str(R.DEFAULT_STRATEGY_DIR), help="策略配置目录")
    ap.add_argument("--out", default=None, help="输出到指定文件（默认写回 --src）")
    ap.add_argument("--write", action="store_true", help="真正落盘；不带此参数只干跑")
    ap.add_argument("--no-css", action="store_true", help="不注入配套样式表")
    args = ap.parse_args(argv)

    src = Path(args.src)
    if not src.is_file():
        print(f"[fail] 目标页不存在: {_rel(src)}（--src 指定有效静态页）", file=sys.stderr)
        return _EXIT_SRC

    try:
        result, rep = build(src, Path(args.dir), with_css=not args.no_css)
    except ValueError as exc:
        code = _EXIT_ANCHOR if "锚点" in str(exc) else _EXIT_HEAD
        print(f"[fail] {_rel(src)}: {exc}", file=sys.stderr)
        return code

    dest = Path(args.out) if args.out else src
    mode = "落盘" if args.write else "dry-run"
    delta = rep["bytes_after"] - rep["bytes_before"]
    sign = "+" if delta >= 0 else ""
    print(f"[{mode}] {_rel(src)} → {_rel(dest)}")
    print(f"  策略卡片: {rep['strategies']} 个"
          f" / 字节 {rep['bytes_before']} → {rep['bytes_after']} ({sign}{delta})"
          f" / 样式表注入: {'是' if rep['css_injected'] else '否'}"
          f" / 二次注入锚点: {'命中' if rep['had_endmark'] else '首次注入'}"
          f" / 内容变化: {'有' if rep['changed'] else '无（空操作）'}")

    if not args.write:
        print("  未落盘：确认无误后追加 --write")
        return 0
    try:
        if dest != src:
            dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(result, encoding="utf-8")
    except OSError as exc:
        print(f"[fail] 写入失败 {dest}: {exc}", file=sys.stderr)
        return _EXIT_WRITE
    print(f"  已写入 {_rel(dest)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
