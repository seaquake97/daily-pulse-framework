#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""md_render.document — 块序列 → 详情页 HTML（组装层 + 章节视觉映射）

单一职责：把 blocks.parse_blocks 的块序列渲染成整页 HTML（FRAMEWORK-DESIGN
§2.5 输出契约），并执行章节视觉映射（§2.4，只包容器不改文字）：
    「结论卡 / 核心决策(卡)」章节 → <div class="verdict-card">
    「免责声明」章节 / 引用      → <div class="footer-note">
    四态台账词                  → <span class="tag"> 状态徽章（inline 层）
    表格                        → <div class="tbl-wrap"><table class="tbl">
    评级全缺                    → <p class="gap-note"> 数据缺口（诚实降级，禁编造）

标题层级与 sanitizer heading_pass 的 LEVEL_MAP 对齐（h1→h3 / h2→h4 / h3→h4），
并预置 data-sb-h 一次性标记 —— 渲染产物再过 sanitize 时标题层零改动（固定点）。
规范标题（meta.canonical_title）作为首个 h3 注入正文，frame_pass 会把它提升为
h1.doc-title；md 自带 H1 按 LEVEL_MAP 降级为章节头保留（正文无损）。

样式策略：渲染器**不内联 CSS** —— 全部经类名引用 detail-frame.css（frame_pass
注入，单一 Token 源）。输出零 <script>、零渐变、零裸色值。幂等：无墙钟无随机。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

import site_theme as T                          # noqa: E402  锁定图标表
from sanitizer.emoji_inline import EMOJI_PATTERN  # noqa: E402  关键词剥离 emoji 用

from . import blocks as B                       # noqa: E402  块解析
from . import inline as I                       # noqa: E402  行内渲染
from .meta import Meta, canonical_title, extract_meta, resolve_stage  # noqa: E402,F401

# md 标题层级 → 框架层级（与 sanitizer.heading_pass.LEVEL_MAP 对齐）+ 一次性标记
_HEADING_MAP = {1: ("3", "1->3"), 2: ("4", "2->4"), 3: ("4", "3->4")}

# 章节视觉映射关键词（§2.4）：匹配时先剥 md 记号与 emoji，防 `## **结论卡**` 漏配
_VERDICT_RE = re.compile(r"结论卡|核心决策")
_DISCLAIMER_RE = re.compile(r"免责声明")

_SITE_SUFFIX = " — 每日市场脉搏"
_GAP_NOTE = ("数据缺口：front-matter / 正文元信息 / market_data.json 均未提供"
             "评级标注 —— 本页不编造评级。")


def _plain(text: str) -> str:
    """关键词匹配用：剥 md 记号与 emoji（只用于判定，不回写正文）。"""
    return EMOJI_PATTERN.sub("", re.sub(r"[*_`#>-]", "", text))


def _render_heading(b: dict, log: list[str]) -> str:
    lv = b["level"]
    text = I.inline(b["text"], log=log)
    if lv in _HEADING_MAP:
        tag, mark = _HEADING_MAP[lv]
        return f'<h{tag} data-sb-h="{mark}">{text}</h{tag}>'
    return f"<h{lv}>{text}</h{lv}>"


def _render_table(t: dict, log: list[str]) -> str:
    aligns = t["align"]

    def cell(tag: str, text: str, idx: int) -> str:
        a = aligns[idx] if idx < len(aligns) else None
        style = f' style="text-align:{a}"' if a else ""
        return f"<{tag}{style}>{I.inline(text, log=log)}</{tag}>"

    ths = "".join(cell("th", c, i) for i, c in enumerate(t["header"]))
    trs = "".join(f"<tr>{''.join(cell('td', c, i) for i, c in enumerate(row))}</tr>"
                  for row in t["rows"])
    return (f'<div class="tbl-wrap"><table class="tbl">'
            f"<thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>")


def _render_list(items: list[dict], log: list[str]) -> str:
    """嵌套列表：缩进进栈出栈；任务列表项前置 check/ban 徽章（SVG symbol 引用）。"""
    parts: list[str] = []
    stack: list[list] = []                      # [indent, tag, li_open]
    for it in items:
        tag = "ol" if it["ordered"] else "ul"
        while stack and stack[-1][0] >= it["indent"]:
            top = stack.pop()
            if top[2]:
                parts.append("</li>")
            parts.append(f"</{top[1]}>")
        if stack and stack[-1][0] < it["indent"]:        # 更深：嵌套进未闭合的 li
            parts.append(f"<{tag}>")
            stack.append([it["indent"], tag, False])
        else:                                           # 同级/首个：关旧 li 开新 li
            if stack:
                if stack[-1][2]:
                    parts.append("</li>")
                    stack[-1][2] = False
                if stack[-1][1] != tag:
                    parts.append(f"</{stack[-1][1]}>")
                    stack[-1][1] = tag
                    parts.append(f"<{tag}>")
            else:
                parts.append(f"<{tag}>")
                stack.append([it["indent"], tag, False])
        content = I.inline(it["text"], log=log)
        if it["task"] is not None:
            content = (f'<span class="tag">{T.icon("check" if it["task"] else "ban")}'
                       f"</span>") + content
        parts.append(f"<li>{content}")
        stack[-1][2] = True
    while stack:
        top = stack.pop()
        if top[2]:
            parts.append("</li>")
        parts.append(f"</{top[1]}>")
    return "".join(parts)


def _render_image(im: dict) -> str:
    if not I.safe_url(im["src"]):
        return f"<p>{I.esc(im['src'])}</p>"
    img = f'<img src="{I.esc(im["src"])}" alt="{I.esc(im["alt"])}">'
    cap = f"<figcaption>{I.esc(im['alt'])}</figcaption>" if im["alt"] else ""
    return f"<figure>{img}{cap}</figure>"


def render_block(b: dict, log: list[str]) -> str:
    """单块 → HTML。文字一律过 inline（转义 + 行内语法 + emoji 处置）。"""
    kind = b["type"]
    if kind == "heading":
        return _render_heading(b, log)
    if kind == "para":
        return f"<p>{I.inline(b['text'], log=log)}</p>"
    if kind == "hr":
        return "<hr>"
    if kind == "html":
        return b["text"]                        # HTML 注释 verbatim
    if kind == "code":
        return f"<pre><code>{I.convert_emoji(I.esc(b['text']), log)}</code></pre>"
    if kind == "table":
        return _render_table(b, log)
    if kind == "list":
        return _render_list(b["items"], log)
    if kind == "image":
        return _render_image(b)
    if kind == "quote":
        inner = "".join(render_block(x, log) for x in b["blocks"])
        if _DISCLAIMER_RE.search(_plain(b["text"])):
            return f'<div class="footer-note">{inner}</div>'
        return f"<blockquote>{inner}</blockquote>"
    raise ValueError(f"未知块类型: {kind}")


def _section_end(blks: list[dict], start: int) -> int:
    """章节内容终点：下一个 h2（或 EOF）；后随标题的分隔线不算章节内容。"""
    j = start
    while j < len(blks):
        b = blks[j]
        if b["type"] == "heading" and b["level"] <= 2:
            break
        if (b["type"] == "hr" and j + 1 < len(blks)
                and blks[j + 1]["type"] == "heading" and blks[j + 1]["level"] <= 2):
            break
        j += 1
    return j


def render_body(blks: list[dict], meta: Meta, title: str, log: list[str]) -> str:
    """块序列 → 正文 HTML。规范标题为首个 h3；评级全缺时出 gap-note。"""
    parts = [f'<h3 data-sb-h="1->3">{I.esc(title)}</h3>']
    if meta.rating is None:
        parts.append(f'<p class="gap-note">{_GAP_NOTE}</p>')
    i = 0
    while i < len(blks):
        b = blks[i]
        if b["type"] == "heading" and b["level"] == 2:
            plain = _plain(b["text"])
            end = _section_end(blks, i + 1)
            content = "".join(render_block(x, log) for x in blks[i + 1:end])
            head = render_block(b, log)
            if _VERDICT_RE.search(plain):
                parts.append(f'{head}<div class="verdict-card">{content}</div>')
            elif _DISCLAIMER_RE.search(plain):
                parts.append(f'{head}<div class="footer-note">{content}</div>')
            else:
                parts.append(head + content)
            i = end
            continue
        parts.append(render_block(b, log))
        i += 1
    return "\n".join(parts)


def render_page(md_text: str, slug: str, date: str,
                market_data: dict | None = None) -> tuple[str, Meta, list[str]]:
    """md 全文 → (整页 HTML, meta, 处置留痕)。纯函数：同输入必得同字节。"""
    meta = extract_meta(md_text, market_data)
    title = canonical_title(slug, date)
    log: list[str] = []
    body = render_body(B.parse_blocks(md_text), meta, title, log)
    html = (f"<!doctype html>\n<html lang=\"zh-CN\">\n<head>\n"
            f'<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{I.esc(title)}{_SITE_SUFFIX}</title>\n"
            f"</head>\n<body data-sb-h>\n{body}\n</body>\n</html>\n")
    return html, meta, log


def stage_label_for(meta: Meta, slug: str) -> str:
    """解析后的数据时点（含 SLUG_STAGE 兜底）—— CLI 日志与校验用。"""
    return resolve_stage(meta, slug)
