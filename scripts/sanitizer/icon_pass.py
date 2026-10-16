#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""icon_pass.py — 图标引用闭环补全（sanitizer 包的末道变换层）

单一职责：给正文页补上 icon() 假设存在、但上游详情页天生没有的两件东西：
  1. 按需子集 sprite —— 只含产物实际引用的 #i-xxx 的 <symbol> 定义；
  2. 图标 CSS —— .ic/.ic-20/.ic-24 三档尺寸 + .ic-wrap 行内对齐 + currentColor 描边。

## 根因（2026-10-14 P0 事故：消毒产物 SVG 图标双重破碎）
site_theme.icon() 生成 `<svg class="ic"><use href="#i-x"/></svg>` 时假设
「复用页面已有 sprite」—— 该假设只对 build_site 的框架页成立
（site_render.shell 注入 icon_sprite() + inject_tokens()）。上游详情页两者皆无：
消毒把 emoji 换成 <use> 之后，引用悬空（全页 0 个 <symbol> 定义）、无尺寸 CSS
（.ic 规则不存在），图标静默不渲染 —— 页面看起来「没有图标」而非「报错」，
属于最致命的一类失效。本模块在消毒末尾把缺口补上。

## 为什么是子集而不是全量 sprite
全量 sprite 单页 6-10KB，而一页实际引用的 symbol 通常 1-4 个。子集按需生成，
字节增量与引用数成正比；定义顺序 sorted，保证输出字节确定（幂等的前提）。

## 幂等（硬约束）
「无缺口即整段不动」：引用集已被 <symbol> 定义完整覆盖时直接返回原文，
二次运行字节不变。注入块带标记注释 `<!-- icon-subsprite:v1 -->` 便于回溯。

## 已注入页面也要补缺口（B-8 配套，2026-10-15 门禁实测）
旧实现见 MARKER 即整段跳过。但历史产物再次消毒时，新规则可能引入**新**
图标引用（如返工 1 把 ✅/❌ 补进 emoji 映射表），整段跳过会让新引用悬空
——「代码新于产物」的陈旧路径改头变面复活。现在：MARKER 存在但引用集
出现新缺口时，补一个**补充 symbol 块**（只含缺口 symbol，CSS 已在位不
重注），而不是跳过。下一次运行无缺口 → 不动 → 字节幂等保持。

## 位置（设计约束）
CSS 注在 </head> 前（跟随框架页「样式在头部」的惯例）；symbol 块注在
</body> 前（SVG defs 位置无关，与框架页 sprite 等效）。

## Token 漂移说明
尺寸值在消毒时从 design-tokens.css（site_theme 的 Token 源）读取，不落死在本
模块；但已注入过的页面因幂等标记不会刷新。Token 是锁定值（APPLE-DESIGN-SPEC），
若未来确需改尺寸，需连同标记版本一起 bump（v1 → v2）。
"""
from __future__ import annotations

import re

from .html_utils import inject_before

# 注入标记：二次运行检测到即跳过（幂等的唯一依据）
MARKER = "<!-- icon-subsprite:v1 -->"

# 产物中对图标定义的引用：<use href="#i-x"> / url(#i-x)。
# 刻意要求 '#' 前缀 —— <symbol id="i-x"> 定义本身不含 '#'，不会被误统计为引用。
_REF_RE = re.compile(r"#i-([A-Za-z0-9_-]+)")

# Token 缺失时的兜底尺寸（与 design-tokens.css 锁定值一致）
_FALLBACK_SIZES = {"ic": "16px", "ic-20": "20px", "ic-24": "24px"}
_FALLBACK_STROKE = "1.75"

# 已注入图标 CSS 的标记（补充注入时据此判断 CSS 是否已在位）
_ICON_CSS_ORIGIN = 'data-origin="icon-subsprite"'
# 页面里已有的 symbol 定义（补充注入只补缺口，不重注）
_SYMBOL_DEF = re.compile(r'<symbol id="i-([A-Za-z0-9_-]+)"')


def referenced_symbols(html: str) -> set[str]:
    """产物中实际引用的 symbol 名集合（不含 '#' 前缀）。"""
    return set(_REF_RE.findall(html))


def icon_sizes() -> tuple[dict[str, str], str]:
    """从 site_theme 的 Token 源（design-tokens.css）读三档尺寸与描边宽度。

    单一数据源：数值不落死在本模块里，设计师改 Token 后重新消毒即跟随
    （框架页走 var() 自动跟随，正文页在下次消毒时跟随）。
    Token 文件不可读时退回锁定兜底值 —— 图标层故障不阻断整个消毒。
    """
    sizes = dict(_FALLBACK_SIZES)
    stroke = _FALLBACK_STROKE
    try:
        import site_theme as T
        toks = T.load_tokens()
        sizes = {
            "ic": toks.get("--icon-size-inline", _FALLBACK_SIZES["ic"]),
            "ic-20": toks.get("--icon-size-btn", _FALLBACK_SIZES["ic-20"]),
            "ic-24": toks.get("--icon-size-stand", _FALLBACK_SIZES["ic-24"]),
        }
        stroke = toks.get("--icon-stroke", _FALLBACK_STROKE)
    except OSError:
        pass
    return sizes, stroke


def icon_css() -> str:
    """图标层 CSS（与 site_components.css 的 .ic 规则同源同值）。

    stroke/fill 走 currentColor：图标继承所在容器的文字色，与框架页一致，
    不引入第二套配色（P0：禁止硬编码颜色）。
    """
    s, stroke = icon_sizes()
    return (
        f".ic{{width:{s['ic']};height:{s['ic']};flex:0 0 auto;"
        f"stroke:currentColor;stroke-width:{stroke};stroke-linecap:round;"
        f"stroke-linejoin:round;fill:none}}\n"
        f".ic-20{{width:{s['ic-20']};height:{s['ic-20']}}}\n"
        f".ic-24{{width:{s['ic-24']};height:{s['ic-24']}}}\n"
        ".ic-wrap{display:inline-flex;align-items:center;vertical-align:middle;"
        "line-height:0}"
    )


def build_subsprite(names: set[str]) -> str:
    """按引用的 symbol 名生成子集定义块（sorted 保证字节确定）。"""
    import site_theme as T
    body = "".join(
        f'<symbol id="i-{n}" viewBox="0 0 24 24">{T.SYMBOLS[n]}</symbol>'
        for n in sorted(names))
    # 外层包裹与 site_theme.icon_sprite() 完全一致（同一渲染形态）
    return ('<svg width="0" height="0" style="position:absolute" aria-hidden="true" '
            f'focusable="false"><defs>{body}</defs></svg>')


def inject_icon_support(html: str, report) -> str:
    """补全图标引用闭环：按需 symbol 子集 + 图标 CSS。

    幂等由「无缺口即不动」保证：引用集已被定义完整覆盖时原样返回。
    已注入过的页面（MARKER 在）出现新缺口时只补缺口 symbol，不重注
    CSS、不整段跳过（见模块 docstring「B-8 配套」）。
    """
    refs = referenced_symbols(html)
    if not refs:
        return html                                  # 无图标引用：什么都不加
    import site_theme as T
    known = {r for r in refs if r in T.SYMBOLS}
    unknown = sorted(refs - known)
    if unknown:
        # 引用悬空且无法补全：显式标记，绝不静默放过（沉默失效防线）
        report.add("needs-manual-review",
                   f"图标引用未在锁定 symbol 表定义: {', '.join(unknown)}"
                   "（无法生成 <symbol> 定义，引用将悬空）")
    gap = known - set(_SYMBOL_DEF.findall(html))
    if not gap:
        return html                                  # 无缺口（含已注入且未变）
    sprite_block = MARKER + build_subsprite(gap)
    if MARKER in html and _ICON_CSS_ORIGIN in html:
        # 已注入过的页面：CSS 已在位，只补缺口 symbol（补充块）
        out = inject_before(html, r"</body\s*>", sprite_block, "tail")
        report.add("icon", f"补充注入 symbol 子集 {len(gap)} 个: "
                           f"{', '.join(sorted(gap))}")
        return out
    css_block = f'<style data-origin="icon-subsprite">{icon_css()}</style>'
    out = inject_before(html, r"</head\s*>", css_block, "head")
    out = inject_before(out, r"</body\s*>", sprite_block, "tail")
    report.add("icon", f"注入 symbol 子集 {len(gap)} 个: {', '.join(sorted(gap))}")
    report.add("icon", "注入图标 CSS（.ic/.ic-20/.ic-24 尺寸 + .ic-wrap 行内对齐 "
                       "+ currentColor 描边）")
    return out
