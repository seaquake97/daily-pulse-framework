#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""md_render.inline — 行内 Markdown → HTML（表现层，纯函数 + 基础设施依赖）

单一职责：把一行/一段 md 行内语法转成 HTML 片段。依赖只向下：
site_theme（锁定图标表）与 sanitizer 的数据层 emoji_map（emoji→SVG 语义表，
设计师门禁锁定，复制必漂移）——不依赖 sanitizer 的编排层。

渲染清单（FRAMEWORK-DESIGN §2.4 实测裁剪 + 任务书契约）：粗体/斜体/删除线/
行内代码/链接/图片/任务列表徽章/四态台账徽章/emoji/数学记号转写。

数学记号（存量 14:30 md 实测存在 `$$\Sigma…$$`、`$|\Sigma|<0.15$`，v2.0 契约
补正）：`$…$`/`$$…$$` 整体经 _math_text 转写为可读文本（\Sigma→Σ、\text{X}→X、
\quad→空格、$ 剥离）——内容不丢，只是换载体；不是数学渲染，零 JS 零外部库。

emoji 处置策略（与 site_content.summary_html 同口径）：
  · emoji_map 命中 → <span class="ic-wrap">{SVG}</span>（信息不丢，只换载体）；
  · IP 标识白名单 → ip-mark 包裹保留（sanitizer K-1 唯一合法保留路径）；
  · 其余装饰性 emoji → 剥离并记入 log（语义已由文字承载；P0 禁 emoji 作图标，
    剥离必须留痕，不静默删字符）。
四态台账（TRIGGERED/NOT_TRIGGERED/UNEVALUABLE/MISSED_NEUTRAL）在行内代码或
普通文本中出现 → 状态徽章（文字保留在徽章内）；围栏代码块内不转（verbatim）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

import site_theme as T                          # noqa: E402  锁定图标表
from sanitizer import emoji_map as EM           # noqa: E402  emoji→SVG 语义表（数据层）
from sanitizer.emoji_inline import EMOJI_PATTERN  # noqa: E402  与 sanitizer 同口径

# 行内原样放行的裸 HTML 标签白名单（存量 md 实测只用 <br>，其余一律转义）
_RAW_TAG_RE = re.compile(r"<br\s*/?>", re.I)

_IMG_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
_LINK_RE = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<href>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
_CODE_RE = re.compile(r"`([^`\n]+)`")
_MATH_RE = re.compile(r"\$+([^$]+)\$+")
_BOLD_RE = re.compile(r"\*\*(?P<t>(?:[^*]|\*(?!\*))+?)\*\*|__(?P<u>(?:[^_]|_(?!_))+?)__")
_DEL_RE = re.compile(r"~~(?P<t>[^~\n]+?)~~")
_EM_STAR_RE = re.compile(r"(?<!\*)\*(?!\s)(?P<t>[^*\n]+?)(?<!\s)\*(?!\*)")
_EM_US_RE = re.compile(r"(?<![\w_])_(?!\s)(?P<t>[^_\n]+?)(?<!\s)_(?![\w_])")

# 四态台账 → 状态徽章（图标取自锁定 symbol 表，文字保留在徽章内）
_LEDGER_ICON = {"TRIGGERED": "check", "NOT_TRIGGERED": "x",
                "UNEVALUABLE": "alert", "MISSED_NEUTRAL": "alert-triangle"}
_STATE_RE = re.compile(r"\b(" + "|".join(_LEDGER_ICON) + r")\b")

# 链接/图片目标安全闸门：禁 javascript:/vbscript:/data:，命中即中性化为 href="#"
_UNSAFE_URL_RE = re.compile(r"^\s*(?:javascript|vbscript|data)\s*:", re.I)

# ---- 数学记号转写（内容保留，只换载体；与 test_render_md 的 _math_text 同一份）----
_MATH_WRAPPER_RE = re.compile(
    r"\\(?:text|mathrm|mathbf|mathit|mathsf|operatorname)\{([^{}]*)\}")
_MATH_GREEK = {"Sigma": "Σ", "sigma": "σ", "Delta": "Δ", "delta": "δ",
               "mu": "μ", "rho": "ρ", "theta": "θ", "lambda": "λ",
               "pi": "π", "omega": "ω", "alpha": "α", "beta": "β"}
_MATH_SPACE_CMD = frozenset({"quad", "qquad", ";", ",", ":", "!", " "})
_MATH_DROP_CMD = frozenset({"left", "right", "displaystyle", "limits"})


def esc(s) -> str:
    """HTML 文本转义（与 site_content.esc 同口径）。"""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def _math_text(s: str) -> str:
    r"""LaTeX 风味数学串 → 可读文本：\Sigma→Σ、\text{X}→X、\quad→空格、
    \left/\right 与未识别的 \cmd 剥除、$ 与花括号剥除。内容不丢。"""
    s = _MATH_WRAPPER_RE.sub(r"\1", s)

    def _cmd(m: re.Match) -> str:
        name = m.group(1)
        if name in _MATH_GREEK:
            return _MATH_GREEK[name]
        if name in _MATH_SPACE_CMD:
            return " "
        if name in _MATH_DROP_CMD:
            return ""
        return ""

    s = re.sub(r"\\([A-Za-z]+)", _cmd, s)
    s = re.sub(r"\\ ", " ", s)
    for a, b in (("\\%", "%"), ("\\&", "&"), ("\\_", "_"),
                 ("\\#", "#"), ("\\$", "$")):
        s = s.replace(a, b)
    return s.replace("{", "").replace("}", "")


def _icon_span(symbol: str, cls: str = "") -> str:
    inner = T.icon(symbol)
    return (f'<span class="ic-wrap {cls}">{inner}</span>' if cls
            else f'<span class="ic-wrap">{inner}</span>')


def _emoji_repl(m: re.Match, log: list[str] | None) -> str:
    """emoji → SVG / IP 保留 / 装饰剥离（留痕）。与 sanitizer emoji_inline 输出同形，
    保证渲染产物再过 sanitize 时 emoji 层是零改动（固定点的一部分）。"""
    tok = m.group(1)
    hit = EM.lookup(tok)
    if hit:
        symbol, cls = hit
        return _icon_span(symbol, cls)
    if EM.is_ip_mark(tok):
        return (f'<span class="ip-mark" title="{esc(tok)}" '
                f'aria-label="{esc(tok)}" role="img">{tok}</span>')
    if log is not None:                       # 装饰性剥离：留痕，不静默
        log.append(f"剥离装饰 emoji U+{ord(tok[0]):04X}（语义由文字承载）")
    return ""


def convert_emoji(text: str, log: list[str] | None = None) -> str:
    """对一段（已转义的）文本做 emoji 处置。"""
    return EMOJI_PATTERN.sub(lambda m: _emoji_repl(m, log), text)


def _state_badge(state: str) -> str:
    return f'<span class="tag">{T.icon(_LEDGER_ICON[state])}{state}</span>'


def safe_url(url: str) -> bool:
    """链接/图片目标安全闸门：禁 javascript:/vbscript:/data:，其余放行。"""
    return not _UNSAFE_URL_RE.match(url)


def _render_img(m: re.Match) -> str:
    src, alt = m.group("src"), m.group("alt")
    if not safe_url(src):
        return esc(m.group(0))
    return f'<img src="{esc(src)}" alt="{esc(alt)}">'


def _render_link(m: re.Match) -> str:
    href, text = m.group("href"), m.group("text")
    if not safe_url(href):
        return f'<a href="#">{esc(text)}</a>'      # 危险目标中性化，文本保留
    return f'<a href="{esc(href)}">{esc(text)}</a>'


def _render_code(m: re.Match, state_badge: bool) -> str:
    """行内代码。内容是四态台账词时升级为状态徽章（文字不丢）；否则 <code>。"""
    content = m.group(1).strip()
    if state_badge and content in _LEDGER_ICON:
        return _state_badge(content)
    return f"<code>{convert_emoji(esc(content))}</code>"


def inline(text: str, state_badge: bool = True, log: list[str] | None = None) -> str:
    """行内渲染主入口。state_badge=False 时四态词保持普通文本（围栏代码块场景）。"""
    store: list[str] = []

    def keep(html: str) -> str:
        store.append(html)
        return f"\x00{len(store) - 1}\x00"

    work = _RAW_TAG_RE.sub(lambda m: keep(m.group(0)), text)
    work = _IMG_RE.sub(lambda m: keep(_render_img(m)), work)
    work = _LINK_RE.sub(lambda m: keep(_render_link(m)), work)
    work = _CODE_RE.sub(lambda m: keep(_render_code(m, state_badge)), work)
    work = _MATH_RE.sub(lambda m: _math_text(m.group(1)), work)
    work = esc(work)
    work = _BOLD_RE.sub(lambda m: f"<b>{m.group('t') or m.group('u')}</b>", work)
    work = _DEL_RE.sub(lambda m: f"<del>{m.group('t')}</del>", work)
    work = _EM_STAR_RE.sub(lambda m: f"<i>{m.group('t')}</i>", work)
    work = _EM_US_RE.sub(lambda m: f"<i>{m.group('t')}</i>", work)
    if state_badge:
        work = _STATE_RE.sub(lambda m: _state_badge(m.group(1)), work)
    work = convert_emoji(work, log)
    for i, frag in enumerate(store):
        work = work.replace(f"\x00{i}\x00", frag)
    return work
