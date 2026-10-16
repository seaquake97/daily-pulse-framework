#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""html_utils.py — sanitizer 包的 HTML 注入原语（基础设施层，零依赖）

单一职责：把注入块（CSS / SVG defs / 幂等标记）插到 HTML 的约定位置，
并处理「目标标签缺失」的兜底。被 icon_pass / token_pass 共用——
两个 pass 的注入位置纪律必须一致（CSS 进 </head> 前，defs 进 </body> 前），
原语只有一份，避免两边各写一套、日后跑偏。
"""
from __future__ import annotations

import re


def inject_before(html: str, pattern: str, block: str, fallback: str) -> str:
    """把 block 插到 pattern 首个匹配之前；无匹配时按 fallback 放到头/尾。

    fallback="head"：插到文档最前（片段场景：无 </head> 时样式仍生效）；
    fallback="tail"：插到文档末尾（片段场景：无 </body> 时 defs 仍生效）。

    完整文档必有 </head>/</body>，兜底只服务于单元测试里的 HTML 片段。
    """
    m = re.search(pattern, html, re.I)
    if m:
        return html[:m.start()] + block + html[m.start():]
    return (block + html) if fallback == "head" else (html + block)
