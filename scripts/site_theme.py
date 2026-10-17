#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""site_theme.py — 站点主题层（表现层基础设施，纯静态、零 JS）

单一职责，只做四件事：
  1. 生成期一次性读取 design-tokens.css，解析为 dict（TOKENS），并做关键 Token 存在性校验；
  2. 提供 inject_tokens(css=None)：把 Token 层 + 组件层 CSS 注入产出 HTML 的 <style>；
  3. 提供锁定的 Lucide 描边 SVG symbol sprite 与 icon() 帮助函数（16/20/24 三档）；
  4. 提供 emoji → SVG 语义替换表（ADR-003：只锁语义键，不锁实现）。

依赖只向下：design-tokens.css / site_components.css / site_blocks.css 三个静态资源 + 标准库。
本模块不含业务规则、不 import 渲染层（禁止反向依赖）。
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).resolve().parent
TOKENS_CSS_PATH = _HERE.parent / "design-tokens.css"
COMPONENTS_CSS_PATH = _HERE / "site_components.css"
BLOCKS_CSS_PATH = _HERE / "site_blocks.css"
FRAME_CSS_PATH = _HERE.parent / "detail-frame.css"

# 关键 Token 清单：设计师改名即在构建期报错，而不是静默产出无样式页面（沉默失效防线）
REQUIRED_TOKENS = (
    "--bg", "--fg", "--fg-2", "--fg-3", "--border", "--separator", "--accent", "--link",
    "--container-max", "--container-prose", "--fs-body", "--tracking-body", "--nav-h",
    "--nav-blur", "--tl-gutter", "--radius-md", "--badge-radius", "--chip-radius",
    "--rating-defensive-bg", "--quote-up", "--quote-down", "--icon-stroke",
    # 详情页反色面（上游深渐变封面/hero 的落点，B-2 事故后入列）
    "--surface-inverse", "--fg-on-inverse",
)

_VAR_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;{}]+);", re.I)


@lru_cache(maxsize=1)
def load_tokens(path: str | None = None) -> dict[str, str]:
    """解析 design-tokens.css 的全部 CSS 变量为 dict（生成期读一次，结果缓存）。

    同名变量以文件中最后一次声明为准（深色模式块覆盖基础块）—— 仅供构建期自检与
    外部工具查询使用；页面渲染一律走浏览器端的 var(--token)，不在 Python 里硬编码颜色。
    """
    p = Path(path) if path else TOKENS_CSS_PATH
    if not p.exists():
        raise FileNotFoundError(f"设计 Token 文件缺失：{p}")
    text = p.read_text(encoding="utf-8")
    return {m.group(1): m.group(2).strip() for m in _VAR_RE.finditer(text)}


def require_tokens(tokens: dict[str, str]) -> None:
    """关键 Token 缺失即构建失败——避免产出「看起来正常其实没样式」的静默页面。"""
    missing = [t for t in REQUIRED_TOKENS if t not in tokens]
    if missing:
        raise KeyError(f"design-tokens.css 缺少关键 Token：{', '.join(missing)}")


@lru_cache(maxsize=1)
def tokens_css() -> str:
    """Token 层 CSS 原文（整文件内联，产出站点零外部请求）。"""
    return TOKENS_CSS_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def components_css() -> str:
    """通用骨架层 CSS：reset / 排版基元 / 图标 / 导航 / 容器 / 页头。"""
    return COMPONENTS_CSS_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def blocks_css() -> str:
    """业务组件层 CSS：时间线 / 徽章 / 芯片 / 表格 / 页脚 / 响应式。"""
    return BLOCKS_CSS_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def detail_frame_css() -> str:
    """详情页阅读框架扩展层 CSS（detail-frame.css，frame_pass 经 inject_tokens 注入）。

    与前三层同属「站点静态 CSS 资产」：路径知识留在 theme 层，frame_pass 不感知
    文件位置。铁律随文件自身声明：零颜色字面量、零 gradient、零弹跳缓动。
    """
    return FRAME_CSS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 结构化 Token 解析：浅色 / 深色两套取值（供详情页按需注入缺失 token）
# ---------------------------------------------------------------------------
_DECL_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+)", re.I)
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_BRACE_RE = re.compile(r"[{}]")


def _iter_css_blocks(text: str, media: str | None = None, skipped: bool = False):
    """产出 (外层 @media 条件或 None, 选择器, 声明体)。

    @media 的条件向下传递；其余 at-rule（@supports / prefers-reduced-motion）
    内部的块标记 skipped——它们是渐进增强，不属于基准调色板。
    """
    pos = 0
    while True:
        m = _BRACE_RE.search(text, pos)
        if not m:
            return
        if m.group(0) != "{":
            pos = m.end()
            continue
        # 头部先剥注释：design-tokens.css 的每个块前都有大段说明注释，
        # 不剥的话选择器变成 "/* ... */ :root"，精确匹配全失败
        header = _CSS_COMMENT_RE.sub(" ", text[pos:m.start()])
        header = re.sub(r"\s+", " ", header).strip()
        body_start = m.end()
        depth, j = 1, body_start
        while j < len(text) and depth:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[body_start:j - 1]
        if header.startswith("@"):
            if header.startswith("@media"):
                yield from _iter_css_blocks(body, media=header)
            else:
                yield from _iter_css_blocks(body, media=media, skipped=True)
        elif not skipped:
            yield media, header, body
        pos = j


def _declarations(body: str) -> dict[str, str]:
    """一段 CSS 声明体 → {token 名: 取值}（剥注释、去首尾空白）。"""
    return {name: _CSS_COMMENT_RE.sub("", val).strip()
            for name, val in _DECL_RE.findall(body)}


@lru_cache(maxsize=1)
def token_palette() -> tuple[dict[str, str], dict[str, str]]:
    """design-tokens.css 的结构化解析：(浅色值, 深色值)。

    浅色 = 顶层 :root 块（同文件后者覆盖前者）；深色 = @media
    (prefers-color-scheme: dark) 内 :root 块的覆盖。
    手动钩子 :root[data-theme="dark"] 不计入——它只是同一套深色值的
    另一入口（详情页零 JS，无主题切换器）。

    与 load_tokens() 的分工：后者是「最后一次声明胜出」的扁平查询（自检用），
    前者保留深浅结构（注入用）。混用会让深色模式丢值。
    """
    text = TOKENS_CSS_PATH.read_text(encoding="utf-8")
    light: dict[str, str] = {}
    dark: dict[str, str] = {}
    for media, sel, body in _iter_css_blocks(text):
        if media is None and sel == ":root":
            light.update(_declarations(body))
        elif media and "prefers-color-scheme: dark" in media and sel.startswith(":root"):
            dark.update(_declarations(body))
    return light, dark


def inject_tokens(css: str | None = None) -> str:
    """产出 HTML <style> 的完整内容 = Token 层 + 骨架层 + 组件层（+ 可选页面级补充）。

    css 为 None 时只注入三层；传入字符串时追加在最后，可覆盖组件层默认值。
    """
    parts = [tokens_css(), components_css(), blocks_css()]
    if css:
        parts.append(css)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 图标层：Lucide 描边 SVG（viewBox 24 / stroke 1.75 / round cap-join / fill none）
# 全站唯一样式，禁止混用第二套图标库（APPLE-DESIGN-SPEC §8）。
# ---------------------------------------------------------------------------
SYMBOLS: dict[str, str] = {
    "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "alert": '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>'
             '<line x1="12" y1="16" x2="12.01" y2="16"/>',
    "alert-triangle": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0'
                      ' 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "archive": '<rect width="20" height="5" x="2" y="3" rx="1"/>'
               '<path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>',
    "arrow-down": '<line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/>',
    "arrow-left": '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
    "arrow-right": '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    "arrow-up": '<line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>',
    "award": '<circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/>',
    "ban": '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
    "bar-chart": '<line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/>'
                 '<line x1="6" y1="20" x2="6" y2="16"/>',
    "book": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>'
            '<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "calendar": '<rect width="18" height="18" x="3" y="4" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/>'
                '<line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    # 以下两枚是个人 IP / 专栏品牌标识（PM-07，2026-10-16 总监裁决）：原以
    # emoji 字符（U+265F 棋子 / U+1F35C 面碗）经 ip-mark 保留，违反团队
    # P0-1「禁止 emoji 作为功能图标」。裁决：品牌标识不删除、不降级，升级
    # 为锁定 symbol 表内的专用图形 —— 与全站同一 stroke 语言（viewBox 24 /
    # stroke-width 1.75 / round cap-join / fill none，由 .ic CSS 统一施加，
    # symbol 内只放几何路径）。语义由 ip-mark 的 title/aria-label 承载
    # （emoji_map.IP_MARK_SYMBOL），图形与文字分离，可访问性不降级。
    "chess-pawn": '<circle cx="12" cy="7" r="3"/>'
                  '<path d="M10.2 10.2c0 1.5-.7 2.2-1.6 3.4-.8 1.1-1.3 2-1.7 2.9h10.2'
                  'c-.4-.9-.9-1.8-1.7-2.9-.9-1.2-1.6-1.9-1.6-3.4"/>',
    "chevron-down": '<polyline points="6 9 12 15 18 9"/>',
    "chevron-right": '<polyline points="9 18 15 12 9 6"/>',
    "chevrons-down": '<polyline points="7 13 12 18 17 13"/><polyline points="7 6 12 11 17 6"/>',
    "chevrons-up": '<polyline points="17 11 12 6 7 11"/><polyline points="17 18 12 13 7 18"/>',
    "circle-dot": '<circle cx="12" cy="12" r="10"/><line x1="12" y1="12" x2="12.01" y2="12"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/>'
                '<path d="M3 12a9 3 0 0 0 18 0"/>',
    "eye": '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 '
           '-.696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
    "file": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/>'
            '<polyline points="14 2 14 8 20 8"/>',
    "file-text": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/>'
                 '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>'
                 '<line x1="16" y1="17" x2="8" y2="17"/>',
    "git-branch": '<line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/>'
                  '<circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><polyline points="12 7 12 12 15 14"/>',
    "inbox": '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>'
             '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 '
             '16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    "layers": '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 '
              '1 0 0 0 0-1.83z"/><path d="m6.08 9.5-3.5 1.6a1 1 0 0 0 0 1.81l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9a1 1 0 '
              '0 0 0-1.83L17.9 9.5"/><path d="m6.08 14.5-3.5 1.6a1 1 0 0 0 0 1.81l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9a1 1 '
              '0 0 0 0-1.83l-3.5-1.59"/>',
    "lightbulb": '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 '
                 '1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>',
    "line-chart": '<line x1="3" y1="3" x2="3" y2="21"/><line x1="3" y1="21" x2="21" y2="21"/>'
                  '<polyline points="7 16 11 10 15 13 20 6"/>',
    "minus": '<line x1="5" y1="12" x2="19" y2="12"/>',
    # 面碗（账号 IP 形象，PM-07）：碗沿 + 弧底 + 两缕蒸汽，描边语言同上。
    "noodle-bowl": '<path d="M9 9.2c-1.2-1-1.2-2.2 0-3.2 1.2-1 1.2-2.2 0-3.2"/>'
                   '<path d="M15 9.2c-1.2-1-1.2-2.2 0-3.2 1.2-1 1.2-2.2 0-3.2"/>'
                   '<path d="M4 11.5h16a8 8 0 0 1-16 0"/>',
    "radio": '<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2a6 6 0 0 1 0-8.5"/>'
             '<circle cx="12" cy="12" r="2"/><path d="M16.2 7.8a6 6 0 0 1 0 8.5"/>'
             '<path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>',
    "repeat": '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/>'
              '<path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    "rss": '<path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/>',
    "scale": '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/>'
             '<path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/>'
             '<path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 '
              '1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 '
              '1z"/>',
    "shuffle": '<path d="M2 18h1.4c1.3 0 2.5-.6 3.3-1.7l6.1-8.6c.7-1.1 2-1.7 3.3-1.7H22"/>'
               '<path d="m18 2 4 4-4 4"/><path d="M2 6h1.9c1.5 0 2.9.9 3.6 2.2"/>'
               '<path d="M22 18h-5.9c-1.3 0-2.6-.7-3.3-1.8l-.5-.8"/><path d="m18 14 4 4-4 4"/>',
    "sigma": '<path d="M18 7V5a1 1 0 0 0-1-1H6.5a.5.5 0 0 0-.4.8l4.5 6a2 2 0 0 1 0 2.4l-4.5 6a.5.5 0 0 '
             '0 .4.8H17a1 1 0 0 0 1-1v-2"/>',
    "star": '<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 '
            '1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 '
            '1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 '
            '0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 '
            '9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.123 0 0 0 1.597-1.16z"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "thumbs-up": '<path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1'
                 ' 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13'
                 ' 0 0 1 3 3.88Z"/>',
    "timer": '<line x1="10" x2="14" y1="2" y2="2"/><line x1="12" y1="14" x2="15" y2="11"/>'
             '<circle cx="12" cy="14" r="8"/>',
    "trending-down": '<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>',
    "trending-up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "x": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
}

# emoji → 语义图标（ADR-003）。只替换不删除：删除会丢失方向信息。
EMOJI_ICON_MAP: dict[str, tuple[str, str]] = {
    "\U0001F53A": ("arrow-up", "up"),          # 红色上三角
    "\U0001F53B": ("arrow-down", "down"),      # 红色下三角
    "\U0001F4C8": ("trending-up", "up"),       # 上升柱状图
    "\U0001F4C9": ("trending-down", "down"),  # 下降柱状图
    "\u2b06\ufe0f": ("arrow-up", "up"),        # 黑上箭头 + 变体选择符
    "\u2b07\ufe0f": ("arrow-down", "down"),  # 黑下箭头 + 变体选择符
    "\u2197": ("trending-up", "up"),           # 右上箭头
    "\u2198": ("trending-down", "down"),       # 右下箭头
}
# 兜底：无法映射到语义的装饰性 emoji 直接剥离（分段枚举，不误伤评级箭头）
EMOJI_STRIP_RE = re.compile(
    "[\U0001F300-\U0001F9FF\U0001FAFF"
    "\u2600-\u26bf\u2b00-\u2bff"
    "\ufe0f\u200d\u2b50]")


ICON_SIZES = {"ic": "", "ic-20": " ic-20", "ic-24": " ic-24"}


def icon(name: str, size: str = "ic", extra_class: str = "") -> str:
    """内联 <svg><use> 图标。size ∈ {ic(16), ic-20(20), ic-24(24)}。"""
    if name not in SYMBOLS:
        raise KeyError(f"图标 {name!r} 未在锁定 symbol 表中定义（禁止临时手绘第二套图标）")
    cls = ("ic" + ICON_SIZES[size] + (" " + extra_class if extra_class else "")).strip()
    return (f'<svg class="{cls}" aria-hidden="true" focusable="false">'
            f'<use href="#i-{name}"/></svg>')


def icon_sprite() -> str:
    """全站 SVG symbol sprite（一次内联，全页复用，零外部请求）。"""
    body = "".join(f'<symbol id="i-{k}" viewBox="0 0 24 24">{v}</symbol>'
                   for k, v in SYMBOLS.items())
    return ('<svg width="0" height="0" style="position:absolute" aria-hidden="true" '
            f'focusable="false"><defs>{body}</defs></svg>')