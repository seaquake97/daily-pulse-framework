#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gradient_pass.py — 渐变消除（变换层）

单一职责：把 CSS 里的 linear/radial/conic-gradient 换成 design-token 的
背景色分层。依赖方向：向下依赖 token_map，不反向依赖。

## 为什么渐变必须消除（不是「尽量少用」）
APPLE-DESIGN-SPEC 的基线是纯静态、零渐变：站点的层级靠**留白 + 发丝线 +
表面明度差**表达，不靠色彩渐变。渐变会让同一份内容在框架页与正文页
呈现出两套不同的视觉语言 —— 这正是本任务要解决的「风格割裂」。

## 处置策略：渐变 → 分层底色（不是删掉 background）
渐变往往同时承载「这里是个区块」的信息。直接删掉 background 会让区块
失去底色（视觉塌陷），因此替换为等价的**纯色 Token 底**：
  · 浅色渐变 → --surface-alt / --surface-sunken（按原渐变明度决定深浅）
  · 深色渐变 → --surface-inverse（深色表面，文字反白走 --fg-on-inverse）
  · 无法判定明度 → --surface-alt，并在报告标记为「需人工确认」
判断依据是渐变内**所有色标的平均亮度**，与具体色相无关 —— 这样紫粉渐变
不会被「换个色相保留」，而是真的消失（P0-2）。

## 深色渐变为什么必须落 --surface-inverse 而不是 --fg（B-3，2026-10-15 门禁实锤）
旧实现把深色渐变收敛到 --fg，与「深底浅字」的 color:#fff 收敛目标撞车：
header { background: var(--fg); color: var(--fg) } —— 前景色当背景，
fg-on-fg 不可见文本。根因是未区分 role：--fg 是**文字** token，
深色区块要的是**表面** token。design-tokens.css 为此成对定义了
--surface-inverse（浅色 #1D1D1F / 深色模式 #2C2C2E）与 --fg-on-inverse
（#F5F5F7），本模块与 token_map 的深底浅字规则共同消费这一对。
另一个硬道理：--fg 在深色模式下会翻成 #F5F5F7（亮色），深色渐变落 --fg
等于让深色模式用户看到一个发白的区块 —— 深浅两套模式下都是错的。

## 紫粉渐变专项
上游 daily-review.html 的封面卡片里有 6 组radial+linear 叠加渐变，
其中 theme-var-3 用的是 rgba(168,85,247)（紫）→ #3B1F66（紫）。
本模块不区分色相，只按明度替换为中性 Token —— 紫色随之消失，
不需要维护一张「哪些紫色要换」的 blacklist（blacklist 必然漏）。
"""
from __future__ import annotations

import re

from . import token_map as TM

# 渐变函数（含嵌套括号）：linear-gradient(...) / radial-gradient(...) / conic-gradient(...)
_GRADIENT_RE = re.compile(
    r"(?:repeating-)?(?:linear|radial|conic)-gradient\(", re.I)

# 提取一段渐变函数的完整文本（括号配平）
def _extract_fn(text: str, start: int) -> tuple[str, int]:
    """从 text[start]（指向 '('）取出完整函数调用文本，返回 (函数文本, 结束下标)。"""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start - len(_fn_name(text, start)):i + 1], i + 1
    return text[start - len(_fn_name(text, start)):], len(text)


def _fn_name(text: str, paren: int) -> str:
    """回溯 '(' 之前的函数名（含 -gradient）。"""
    i = paren - 1
    while i >= 0 and (text[i].isalnum() or text[i] in "-_"):
        i -= 1
    return text[i + 1:paren]


_HEX_RE = re.compile(r"#([0-9a-fA-F]{3,8})\b")
_RGB_RE = re.compile(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)")


def _luminance(color_text: str) -> float | None:
    """估算一个色标的相对亮度（0=黑 1=白）。无法解析返回 None。"""
    m = _HEX_RE.search(color_text)
    if m:
        return TM.hex_luminance(m.group(0))
    m = _RGB_RE.search(color_text)
    if m:
        r, g, b = (float(m.group(i)) / 255 for i in (1, 2, 3))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    return None


def token_for_gradient(fn_text: str) -> tuple[str, bool]:
    """渐变函数 → (Token, 是否确定)。不确定时调用方需在报告里标注。"""
    lums = [l for l in (_luminance(c) for c in
                        re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", fn_text))
            if l is not None]
    if not lums:
        return "--surface-alt", False
    avg = sum(lums) / len(lums)
    if avg >= 0.75:
        return "--surface-alt", True
    if avg >= 0.45:
        return "--surface-sunken", True
    if avg <= 0.28:
        # 深色带（收敛目标亮度 < 0.2 的深底区块）：落 --surface-inverse，
        # 与 token_map 的「深底浅字 → --fg-on-inverse」成对（B-3）。
        # 保留 0.28 作为深色带下沿（既有校准值）：0.2 是设计师给出的
        # 「明确深色」核心判据，0.2–0.28 的中深渐变同样需要深色表面落点，
        # 且在深色模式下 --fg 会翻亮成发白区块，整条深色带都不能落 --fg。
        return "--surface-inverse", True
    return "--surface-alt", False


def _replace_in_css(css: str, report, where: str) -> str:
    """替换一段 CSS 里的所有渐变。"""
    out = []
    pos = 0
    while True:
        m = _GRADIENT_RE.search(css, pos)
        if not m:
            out.append(css[pos:])
            break
        paren = m.end() - 1
        fn_text, end = _extract_fn(css, paren)
        token, certain = token_for_gradient(fn_text)
        out.append(css[pos:m.start()])
        out.append(f"var({token})")
        note = "" if certain else "（明度判别不确定，建议人工确认）"
        report.add("gradient", f"{where}: {_fn_name(css, paren)} → var({token}){note}")
        pos = end
    return "".join(out)


_STYLE_BLOCK = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.S | re.I)


def strip_gradients(html: str, report) -> str:
    """处理整篇 HTML：<style> 块内的渐变 + style="" 属性里的渐变。"""
    def style_repl(m: re.Match) -> str:
        return m.group(1) + _replace_in_css(m.group(2), report, "<style>") + m.group(3)

    html = _STYLE_BLOCK.sub(style_repl, html)
    return _replace_inline_styles(html, report)


def _replace_inline_styles(html: str, report) -> str:
    """处理 style="..." 属性里的渐变（position/z-index 等不动）。"""
    def repl(m: re.Match) -> str:
        attr = m.group(1)
        if not _GRADIENT_RE.search(attr):
            return m.group(0)
        new = _replace_in_css(attr, report, "style属性")
        return f'style="{new}"'

    return re.sub(r'style="([^"]*)"', repl, html)