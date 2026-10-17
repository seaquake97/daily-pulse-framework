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
· IP 标识走 <span class="ip-mark" title="文字语义" …><svg…></span>
  （PM-07 起图形也是 SVG，span 内无 emoji 字符）；
· 历史产物的**旧形态** ip-mark（title/aria-label/内容皆为 emoji 原字符）
  由 _upgrade_legacy_ip_marks 先行重写升级，重写后即新形态；新形态整体
  stash 跳过（其 <use> 引用不该被本层触碰）。两级配合保证
  sanitize(sanitize(x)) == sanitize(x)，且旧产物不会被 stash 永久豁免
  （2026-10-16 实测：旧 stash 白名单整体放过 ip-mark，30 处 emoji 稳上线，
  扫描器看得见、消毒链碰不到 —— PM-07 要堵的正是这个洞）。

## 保留路径白名单化（B-5 / K-1~K-3，2026-10-15 设计师门禁；PM-07 收紧）
「保留原字符」曾是一切未映射 emoji 的默认归宿，功能图标位 emoji 借此
包一层 ip-mark 静默通过 P0 闸门（ip-mark 是扫描器豁免范围）。现收敛为：
  K-1 IP 标识白名单（emoji_map.is_ip_mark 显式集合）→ SVG 图标 + ip-mark
      包裹（title/aria-label 挂文字语义）。这是 ip-mark 的唯一合法内容；
  K-2 其余未映射 emoji → needs-manual-review（退出码 2）+ 页面保守保留
      原字符。**不包 ip-mark** —— 包了即绕开 P0 扫描器，正是要堵的洞；
  K-3 is_protected（ADR-003 方向冗余编码如 ▲▼）路径不受影响。
PM-07（2026-10-16 总监裁决）：K-1 从「保留原字符」升级为「SVG 图标」——
ip-mark 不再是 emoji 的避难所；扫描器口径（scan_compliance / 各测试）
也不再剥 ip-mark 再扫，包内出现 emoji 字符同样计入违规。

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

# 已被保留策略包裹的片段：再次消毒时整段跳过（幂等的关键）。
# 注意：只豁免**新形态**（内含 SVG）。旧形态（emoji 原字符）必须先经
# _upgrade_legacy_ip_marks 升级，否则历史产物里的 emji 永远躲过消毒链。
_IP_MARK_SPAN = re.compile(
    r'<span class="ip-mark"[^>]*>.*?</span>', re.S)

# 历史产物里的旧形态 ip-mark：title/aria-label/内容三位一体都是 emoji 原字符
# （PM-07 前的保留策略）。内容段 [^<]+ 不匹配新形态的 `<svg…>` —— 升级后
# 本正则天然失配，幂等由此成立。
_LEGACY_IP_MARK = re.compile(
    r'<span class="ip-mark" title="([^"]*)" aria-label="([^"]*)" role="img">'
    r'([^<]+)</span>')

# CSS / JS 源码块：emoji 替换的禁区（见模块 docstring「style/script 保护」）
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)
_SCRIPT_BLOCK = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)

_SVG_SPAN = re.compile(r'<svg class="ic[^"]*"[^>]*>.*?</svg>', re.S)


def _icon(symbol: str, size: str = "ic", extra_class: str = "") -> str:
    """生成内联 SVG。延迟 import site_theme —— 避免包层反向依赖表现层。"""
    import site_theme as T
    return T.icon(symbol, size=size, extra_class=extra_class)


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _ip_mark_span(symbol: str, label: str) -> str:
    """IP 标识的标准包裹体：文字语义在 title/aria-label，图形是 SVG symbol。

    尺寸取 ic-20：.ip-mark 是 20px 固定盒（--icon-size-btn），图标填满盒子，
    与盒子的 inline-flex 居中布局对齐（detail-frame.css §ip-mark）。
    """
    return (f'<span class="ip-mark" title="{label}" aria-label="{label}" '
            f'role="img">{_icon(symbol, size="ic-20")}</span>')


def _upgrade_legacy_ip_marks(html: str, report) -> str:
    """旧形态 ip-mark（emoji 原字符）→ 新形态（SVG symbol + 文字语义）。

    PM-07 根因修复：旧实现把 ip-mark 整体 stash 跳过消毒，历史产物里的
    emoji 成了消毒链的永逸区 —— P0 扫描器按原文扫描照样命中（30 处实锤），
    但 sanitize 永不触碰。现在旧形态先升级重写，新形态才进 stash 白名单。

    白名单外的 ip-mark（人为手写或上游直传）不猜：保守保留原样并记
    needs-manual-review，让门禁响亮地失败而不是静默放行。
    """
    def repl(m: re.Match) -> str:
        raw = m.group(3).strip()
        hit = M.IP_MARK_SYMBOL.get(M.strip_variation(raw))
        if not hit:
            report.add("needs-manual-review",
                       f"ip-mark 内的 {_escape(raw)} 不在 IP 标识白名单，"
                       "疑历史遗留包裹，需人工确认（补 emoji_map.IP_MARK_SYMBOL"
                       " 或剥离包裹）")
            return m.group(0)
        symbol, label = hit
        report.add("emoji", f"{_escape(raw)} → #i-{symbol}"
                           f"（IP 标识升级 SVG，ip-mark 包裹保留：{label}）")
        return _ip_mark_span(symbol, label)

    return _LEGACY_IP_MARK.sub(repl, html)


def replace_emoji(html: str, report) -> str:
    """把 html 中的 emoji 按策略替换，返回新html 并记录报告。

    报告条目形如：
      emoji→svg: ⚠️ → #i-alert-triangle (warn)
      emoji→kept: ▲ (ADR-003 方向冗余编码，保留)
      emoji→svg: ♟ → #i-chess-pawn（IP 标识升级 SVG，ip-mark 包裹保留：股市棋手）
      needs-manual-review: 未映射 emoji：不在 IP 标识白名单，疑功能图标位……
    """
    # 先把已处理过的片段保护起来（幂等：二次运行不再重复处理）
    # CSS/JS 源码块同样保护：内容字符串里的符号（如 content:"➔"）不是
    # 文本节点 emoji，替换它会损坏样式表/脚本（2026-10-15 实测该类数据存在）
    protected: list[str] = []

    def stash(m: re.Match) -> str:
        protected.append(m.group(0))
        return f"\x00P{len(protected) - 1}\x00"

    work = _STYLE_BLOCK.sub(stash, html)
    work = _SCRIPT_BLOCK.sub(stash, work)
    # 旧形态 ip-mark 先升级（PM-07）：升级产物是新形态，才会被下面的
    # stash 白名单正确豁免；若先 stash，旧形态连升级的机会都没有。
    work = _upgrade_legacy_ip_marks(work, report)
    work = _IP_MARK_SPAN.sub(stash, work)

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
            # K-1：IP 标识白名单是唯一合法保留路径。PM-07 起保留的是
            # 「包裹机制 + 文字语义」，图形本体升级为 SVG symbol。
            # 白名单外的 emoji 走 K-2，不再搭这条便车。
            symbol, label = M.IP_MARK_SYMBOL[M.strip_variation(token)]
            report.add("emoji", f"{_escape(token)} → #i-{symbol}"
                               f"（IP 标识：{label}）")
            return _ip_mark_span(symbol, label)

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