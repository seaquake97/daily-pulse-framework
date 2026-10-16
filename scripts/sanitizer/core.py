#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""core.py — 正文消毒编排（sanitizer 包的编排层）

单一职责：按固定顺序调用各变换层，产出 (净化后 HTML, 审计报告)。

## 执行顺序（顺序本身是设计约束）
    1. scripts   —— 先摘 JS。理由：script 里可能内联着数据（如 Chart.js 配置），
                    先处理样式会打乱后续定位；且 JS 移除后 HTML 更小，后续正则更快。
    2. gradient  —— 再统一 CSS 里的渐变。
    3. style     —— 然后把剩余色值收敛到 Token（此时渐变已变 var()，不会被二次处理）。
    4. emoji     —— 最后处理文本节点里的 emoji。
    5. heading   —— 收尾对齐标题层级。
    6. icon      —— 补全图标引用闭环：按需 symbol 子集 + 图标 CSS。
                    必须放最后：它注入的 <symbol>/<style> 不应被前面的正则二次处理，
                    且注入决策依赖前面各 pass 的产物（emoji→SVG 后的真实引用集）。
    7. token     —— 补全被引用但未定义的 design token（悬空 var 会让属性回退
                    unset，颜色 fidelity 丢失）。放 icon 之后：所见引用集是终态，
                    且与 icon 注入互不干扰（icon CSS 用字面 px，不产生 token 引用）。

先emoji 后 script 也可以，但那样 script 内的 emoji（若有）会漏过emoji 检查，
产生「产出里还有 emoji」的门禁缺口。当前顺序不留这种缺口。

## 铁律：绝不删正文内容
每一层都只改呈现载体（CSS 声明 / 标签名 / 字符→SVG），不改可见文本。
唯一的「删除」是 <script> 与 <canvas> 元素本身，而 script 的内容在删除前
已被验证「在别处有冗余静态文本」或被明确降级为静态标记（见 script_pass）。
测试用「净化前后可见文本字符集包含关系」守住这条线。
"""
from __future__ import annotations

from pathlib import Path

from . import (emoji_inline, gradient_pass, heading_pass, icon_pass,  # noqa: F401
               script_pass, style_pass, token_pass)
from .report import SanitizeReport

# 预编译工具类 CSS 的默认位置（由 build_body_css.py 生成并随仓库提交）
DEFAULT_UTILITIES = Path(__file__).resolve().parent.parent / "assets" / "body-utilities.css"


def load_utilities_css(path: Path | str | None = None) -> str | None:
    """读取预编译工具类 CSS；不存在返回 None（调用方据此保留 Tailwind CDN）。"""
    p = Path(path) if path else DEFAULT_UTILITIES
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8").strip()
    return text or None


def sanitize_html(html: str, source: str = "",
                  utilities_css: str | None = None) -> tuple[str, SanitizeReport]:
    """净化一篇正文 HTML，返回 (新 HTML, 审计报告)。

    参数
      html          上游正文原文
      source        来源标识（写进报告，便于回溯是哪份产物）
      utilities_css 预编译的 Tailwind 工具类 CSS；None 表示不处理 Tailwind CDN
    """
    report = SanitizeReport(source=source)
    out = html
    out = script_pass.handle_scripts(out, report, utilities_css=utilities_css)
    out = gradient_pass.strip_gradients(out, report)
    out = style_pass.map_inline_styles(out, report)
    out = emoji_inline.replace_emoji(out, report)
    out = heading_pass.align_headings(out, report)
    out = icon_pass.inject_icon_support(out, report)
    out = token_pass.inject_missing_tokens(out, report)
    return out, report


def visible_text(html: str) -> str:
    """抽取可见文本（测试断言「内容零丢失」的基准）。

    剔除：标签、<script>/<style> 内容、注释、SVG 内部（图标不是内容）。
    这是「读者实际能读到的文字」的近似定义。
    """
    import re
    text = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<svg\b.*?</svg>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()