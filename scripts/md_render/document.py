#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""md_render.document — 块序列 → 详情页 HTML（组装层 + 章节视觉映射）

单一职责：把 blocks.parse_blocks 的块序列渲染成正文 HTML（render_md），并组装
整页骨架（build_page，FRAMEWORK-DESIGN §2.5 输出契约）。

## 章节视觉映射（§2.4，只包容器不改文字）
    「结论卡 / 核心决策(卡)」章节 → <div class="verdict-card">
    「免责声明」章节 / 引用      → <div class="footer-note">
    四态台账词                  → <span class="tag"> 状态徽章（inline 层）
    表格                        → <div class="tbl-wrap"><table class="tbl">
    评级全缺                    → <p class="gap-note"><span class="tag gap">（诚实降级）

类名纪律（C-14 门禁）：全部类名要么 detail-frame.css 已收录（verdict-card /
footer-note / gap-note / tag / gap / tbl-wrap / ic-wrap / up / down / warn），
要么是 A-9 主动施加的 tbl —— 框架类表里的连字符复合类（如 tag-gap）会撞
frame_pass 的 C-14 未登记门禁（构建失败），故缺口徽章用 `.tag gap` 双类
（detail-frame.css §4 的 `.doc .tag.gap` 正是它的再皮肤规则）。

## 标题层级（与 sanitizer heading_pass 的 LEVEL_MAP 对齐）
    md h1 → h3 / md h2 → h4 / md h3 → h4，统一预置 data-sb-h="rendered"
    一次性标记 —— 渲染产物再过 sanitize 时标题层零改动（固定点）。
    md H1 文字按 §3.1 标题铁律清洗（去 emoji、剥破折号副标题）；h2+ 仅清洗。
    规范标题（meta.render_title）由 build_page 注入为首个 h3，frame_pass
    提升为 h1.doc-title；md 自带 H1 降级为章节头保留（正文无损）。

样式策略：渲染器**不内联 CSS** —— 全部经类名引用 detail-frame.css（frame_pass
注入，单一 Token 源）；GFM 表格对齐只映射框架已有原语（右对齐列 → .num），
无对应原语的对齐（居中）降级为默认（文字不丢）。输出零 <script>、零渐变、
零裸色值。幂等：无墙钟无随机。
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
from . import inline as I                       # noqa: E402  行内渲染（含 esc）
from .meta import (_DASH_SUFFIX_RE, _clean_title, _TITLE_EMOJI_RE,  # noqa: E402
                   render_title)

# md 标题层级 → 框架层级（与 sanitizer.heading_pass.LEVEL_MAP 对齐）
_HEADING_TAG = {1: "3", 2: "4", 3: "4"}
_HEADING_MARK = ' data-sb-h="rendered"'

# 章节视觉映射关键词（§2.4）：匹配时先剥 md 记号与 emoji，防 `## **结论卡**` 漏配
_VERDICT_RE = re.compile(r"结论卡|核心决策")
_DISCLAIMER_RE = re.compile(r"免责声明")

_SITE_SUFFIX = " — 每日市场脉搏"
_GAP_NOTE = ("数据缺口：front-matter / 正文元信息 / market_data.json "
             "均未提供评级标注，本页不编造评级。")


def _plain(text: str) -> str:
    """关键词匹配用：剥 md 记号与 emoji（只用于判定，不回写正文）。"""
    return EMOJI_PATTERN.sub("", re.sub(r"[*_`#>-]", "", text))


def _render_heading(b: dict, log: list[str]) -> str:
    lv = b["level"]
    text = _clean_title(b["text"])
    if lv == 1 and _DASH_SUFFIX_RE.search(text):
        # §3.1 标题铁律：H1 禁破折号副标题（如「— daily-decision-engine v1.3」）
        text = _DASH_SUFFIX_RE.sub("", text)
        log.append("H1 破折号副标题按标题铁律剥离（规范标题已由渲染器注入）")
    if _TITLE_EMOJI_RE.search(b["text"]):
        log.append("标题剥离装饰 emoji（语义由文字承载）")
    if lv in _HEADING_TAG:
        tag = _HEADING_TAG[lv]
        # inline 而非裸 esc：标题内数学记号（`$-0.12\%$`）须按 _math_text 转写，
        # 否则 $ 壳与 \cmd 残留进正文（正文无损口径要求同规则转写）
        return f"<h{tag}{_HEADING_MARK}>{I.inline(text, log=log)}</h{tag}>"
    return f"<h{lv}>{I.inline(text, log=log)}</h{lv}>"


def _render_table(t: dict, log: list[str]) -> str:
    aligns = t["align"]

    def cell(tag: str, text: str, idx: int) -> str:
        a = aligns[idx] if idx < len(aligns) else None
        # 对齐走框架原生机制：右对齐列 → .num（site_blocks.css `.tbl .num` 已定义
        # text-align:right + 等宽数字形制）。中/左对齐不设属性——渲染器零内联
        # CSS（§2.5 样式策略），detail-frame.css 无居中原语，居中列降级为默认
        # 左对齐（纯观感，文字 100% 保留）。
        cls = ' class="num"' if a == "right" else ""
        return f"<{tag}{cls}>{I.inline(text, log=log)}</{tag}>"

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


def render_body(blks: list[dict], log: list[str]) -> str:
    """块序列 → 正文 HTML（不含规范标题与缺口标记，那是 build_page 的职责）。

    **首个 md H1 剥离（2026-10-16）**：build_page 已注入规范标题
    「<任务名> · YYYY-MM-DD（周X）<阶段>」，若再把上游 md 自带 H1 渲染成
    h3，页面上会出现两个标题（用户实锤「风格不一致」的一种表现：有的页
    标题规范、有的页多一行旧标题）。语义已由规范标题承载，故剥离首个 H1；
    第二个及以后的 H1（子章节）保留，md 正文一字不删。
    """
    parts: list[str] = []
    i = 0
    stripped_first_h1 = False
    while i < len(blks):
        b = blks[i]
        if b["type"] == "heading" and b["level"] == 1 and not stripped_first_h1:
            stripped_first_h1 = True
            log.append("首个 md H1 已剥离（规范标题由 build_page 注入）")
            i += 1
            continue
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


def render_md(md_text: str, log: list[str] | None = None) -> str:
    """md 全文 → 正文 HTML（纯函数：同输入必得同字节）。"""
    log = log if log is not None else []
    return render_body(B.parse_blocks(md_text), log)


def build_page(slug: str, date: str, meta: dict, body: str) -> str:
    """正文 HTML → 整页（§2.5 骨架：规范标题 h3 + 缺口标记 + doctype/head/body）。"""
    meta = meta or {}
    title = render_title(slug, date, meta.get("stage"))
    parts = [f'<h3{_HEADING_MARK}>{I.esc(title)}</h3>']
    if meta.get("rating") is None:
        # 诚实降级（§2.3）：评级全缺 → 数据缺口徽章，禁编造评级
        parts.append(f'<p class="gap-note"><span class="tag gap">'
                     f'{T.icon("minus")}评级未标注</span>{_GAP_NOTE}</p>')
    return (f'<!doctype html>\n<html lang="zh-CN">\n<head>\n'
            f'<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{I.esc(title)}{_SITE_SUFFIX}</title>\n"
            f"</head>\n<body data-sb-h>\n"
            + "\n".join(parts) + "\n" + body + "\n</body>\n</html>\n")
