"""sanitizer — 发布层正文消毒包。

职责：把上游任务产出的研判正文 HTML 转换为与站点框架同风格（Apple Token 体系），
**只改呈现，不改内容语义**。

分层（依赖只向下）：
    core          编排层：按固定顺序调用各变换层
    ├── script_pass     <script> 移除 + 图表静态化
    ├── gradient_pass   渐变消除
    ├── style_pass      内联样式/色值 → Token
    ├── emoji_inline    emoji → 内联 SVG
    ├── heading_pass    标题层级对齐
    ├── icon_pass       图标引用闭环（按需 symbol 子集 + 图标 CSS）
    └── token_pass      缺失 Token 注入（悬空 var 补全，深浅双套）
    数据层：emoji_map（emoji 语义表）、token_map（色值→Token 表）
    基础设施：report（审计报告）、html_utils（注入原语）
    发布护栏：freshness（代码时点 vs 产物时点，供 publish 层调用）

公共 API：
    sanitize_html(html, source, utilities_css) -> (html, report)
    visible_text(html) -> str          # 测试断言「内容零丢失」的基准
    load_utilities_css(path) -> str | None
"""

from .core import load_utilities_css, sanitize_html, visible_text
from .report import Change, SanitizeReport

__all__ = [
    "sanitize_html",
    "visible_text",
    "load_utilities_css",
    "SanitizeReport",
    "Change",
]