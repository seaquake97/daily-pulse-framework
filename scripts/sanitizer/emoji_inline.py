#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""emoji_inline.py — emoji → 内联 SVG / 保留包裹（变换层）

单一职责：把 HTML 正文里的 emoji 按 emoji_map 的策略落到标记上。
依赖方向：向下依赖 emoji_map + site_theme（表现层基础设施），不反向依赖。

## 为什么 emoji 换成 <use> 而不是 <img> 或字符
· <img> 要外链，破坏「零外部请求」；
· 保留字符就是P0 禁止的「emoji 作为功能图标」；
· <use href="#i-x"> 复用页面已有 sprite，零请求、零重复定义，
  且与站点框架的图标形态完全一致（同一 symbol 表、同一 stroke 规则）。

## 幂等性（本任务硬约束）
替换产物自身不含任何 emoji 字符，也不含会被下一轮再次命中的标记：
· SVG 走<svg class="ic">…<use/></svg>，不含 emoji；
· 保留策略走 <span class="ip-mark">原字符</span>，原字符是 emoji ——
  所以下一轮必须能识别「已在 span 内」并跳过。实现上：只替换**不在**
  ip-mark / 已有 class 的祖先内的 emoji，且产出后该 span 不再被重复包裹
  （包裹函数对已包裹内容是幂等的：见到 <span class="ip-mark"> 包裹体直接返回原文）。
这保证了 sanitize(sanitize(x)) == sanitize(x)。

## 保留路径白名单化（B-5 / K-1~K-3，2026-10-15 设计师门禁）
「保留原字符」曾是一切未映射 emoji 的默认归宿，功能图标位 emoji 借此
包一层 ip-mark 静默通过 P0 闸门（ip-mark 是扫描器豁免范围）。现收敛为：
  K-1 IP 标识白名单（emoji_map.is_ip_mark 显式集合）→ 保留 + ip-mark
     包裹，唯一合法保留路径；
  K-2 其余未映射 emoji → needs-manual-review（退出码 2）+ 页面保守保留
     原字符。**不包 ip-mark** —— 包了即绕开 P0 扫描器，正是要堵的洞；
  K-3 is_protected（ADR-003 方向冗余编码如 ▲▼）路径不受影响。

## <style>/<script> 保护（2026-10-15 补段时连带修复）
EMOJI_PATTERN 覆盖的是「文本节点里的 emoji」，绝不包含 CSS/JS 源码字符串：
上游实测 `.action-list li::before { content: "➔" }` 把箭头当列表符号用，
若对 <style> 块做替换，会把 CSS 字符串切成 HTML 片段 → 样式表直接损坏。
故 <style>/<script> 块与 ip-mark 一样先 stash、处理后原样还原。
"""
from __future__ import annotations

import re

from . import emoji_map as M

# 与 site_content._EMOJI_ANY / scan_compliance.P0_EMOJI_RE 同口径（分段枚举，
# 刻意不覆盖 ▲▼↔ 等冗余编码）。2026-10-15 补 \u26c0-\u26ff 与 \u2700-\u27bf
# 两段：QA 实测上游 stock-review.html 的 ✅(U+2705)/❌(U+274C) 状态标记
# （TRIGGERED/NOT_TRIGGERED）原样漏过消毒，属 P0「emoji 作功能图标」缺口。
EMOJI_PATTERN = re.compile(
    "([\U0001F300-\U0001F9FF\U0001FAFF"
    "\u2600-\u26bf\u26c0-\u26ff\u2700-\u27bf\u2b00-\u2bff"
    "\ufe0f\u200d\u2b50]+)"
)

# 已被保留策略包裹的片段：再次消毒时整段跳过（幂等的关键）
_IP_MARK_SPAN = re.compile(
    r'<span class="ip-mark"[^>]*>.*?</span>', re.S)

# CSS / JS 源码块：emoji 替换的禁区（见模块 docstring「style/script 保护」）
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)
_SCRIPT_BLOCK = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)

_SVG_SPAN = re.compile(r'<svg class="ic[^"]*"[^>]*>.*?</svg>', re.S)


def _icon(symbol: str, extra_class: str = "") -> str:
    """生成内联 SVG。延迟 import site_theme —— 避免包层反向依赖表现层。"""
    import site_theme as T
    return T.icon(symbol, extra_class=extra_class)


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def replace_emoji(html: str, report) -> str:
    """把 html 中的 emoji 按策略替换，返回新html 并记录报告。

    报告条目形如：
      emoji→svg: ⚠️ → #i-alert-triangle (warn)
      emoji→kept: 🍜 (个人 IP 标识，白名单保留)
      needs-manual-review: 未映射 emoji：不在 IP 标识白名单，疑功能图标位……
    """
    # 先把已处理过的片段保护起来（幂等：二次运行不再重复处理）
    # CSS/JS 源码块同样保护：内容字符串里的符号（如 content:"➔"）不是
    # 文本节点 emoji，替换它会损坏样式表/脚本（2026-10-15 实测该类数据存在）
    protected: list[str] = []

    def stash(m: re.Match) -> str:
        protected.append(m.group(0))
        return f"\x00P{len(protected) - 1}\x00"

    work = _IP_MARK_SPAN.sub(stash, html)
    work = _STYLE_BLOCK.sub(stash, work)
    work = _SCRIPT_BLOCK.sub(stash, work)

    def repl(m: re.Match) -> str:
        token = m.group(1)
        hit = M.lookup(token)
        if hit:
            symbol, cls = hit
            report.add("emoji", f"{_escape(token)} → #i-{symbol}"
                       + (f" ({cls})" if cls else ""))
            return f'<span class="ic-wrap {cls}">{_icon(symbol)}</span>' if cls \
                else f'<span class="ic-wrap">{_icon(symbol)}</span>'

        if M.is_protected(token):
            report.add("emoji-kept", f"{_escape(token)} (ADR-003 方向冗余编码，保留)")
            return token

        if M.is_ip_mark(token):
            # K-1：IP 标识白名单是唯一合法保留路径（保留 + ip-mark 包裹）。
            # 白名单外的 emoji 走 K-2，不再搭这条便车。
            report.add("emoji-kept", f"{_escape(token)} (个人 IP 标识，白名单保留)")
            return f'<span class="ip-mark" title="{_escape(token)}" ' \
                   f'aria-label="{_escape(token)}" role="img">{token}</span>'

        # K-2：未映射且不在 IP 白名单 → needs-manual-review（退出码 2），
        # 页面保守保留原字符但不包 ip-mark。包 ip-mark 会让 P0 扫描器豁免
        # 该字符，功能图标位 emoji 就此静默通过门禁（2026-10-15 实锤）。
        # 保留字符而非删除：换皮不阉割，判断交给人。
        report.add("needs-manual-review",
                   f"未映射 emoji {_escape(token)}：不在 IP 标识白名单，"
                   "疑功能图标位，页面保守保留原字符，需人工确认"
                   "（补 emoji_map 映射或加入 IP 白名单）")
        return token

    work = EMOJI_PATTERN.sub(repl, work)

    # 还原被保护的片段
    for i, frag in enumerate(protected):
        work = work.replace(f"\x00P{i}\x00", frag)
    return work