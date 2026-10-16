#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""heading_pass.py — 章节层级对齐（变换层）

单一职责：把正文的 h1/h2/h3 映射到站点框架的 h3/h4 语义，**不改标题文字**。

## 为什么需要
站点框架（site_render.py）用h3 承载报告标题、h4 承载章节；上游正文用
h1（报告标题）+ h2（章节）。两者混在同一个文档流里时，目录树、读屏器、
以及站点自己的 CSS 选择器（.t-title3 / .t-title4）会全部错位 ——
读者看到的是「一个页面里标题层级从 h1 跳到 h4」。

## 映射规则（只动层级，不动文字）
    h1 → h3   报告标题（对齐框架的报告标题级）
    h2 → h4   章节
    h3 → h4   子章节（与 h2 同级：正文里的 h3 是 h2 的子标题，
                        框架里章节与其子节都用 h4，不新增层级）
    h4 及以下 → 保持不变（更细的层级框架未使用，不强行提升）

## 铁律：不动标题文字
标题文本由 CONTENT-SPEC 契约管辖（章节命名、编号体系、措辞），
本模块只改标签名。改写标题会与内容契约打架，且属于「删改内容」。

## 幂等性
映射后的标签（h3/h4）不在映射源列表（h1/h2）里，因此二次运行不产生变化。
但 h3 → h4 是有方向的：若不区分「原生 h3」与「由 h1/h2 转来的 h4」，
二次运行会把原生 h3 也降级。故用一次性标记 data-sb-h 记录已处理，
带标记的元素直接跳过 —— 幂等由标记保证，不靠「转一次就不像了」的巧合。
"""
from __future__ import annotations

import re

# 原生层级 → 目标层级
LEVEL_MAP = {"1": "3", "2": "4", "3": "4"}

_HEADING_RE = re.compile(r"<h(?P<level>[1-6])(?P<attrs>[^>]*)>(?P<body>.*?)</h(?P=level)>",
                         re.S | re.I)
_DONE_ATTR = "data-sb-h"


def _already_done(attrs: str) -> bool:
    return _DONE_ATTR in attrs


def align_headings(html: str, report) -> str:
    """把正文标题层级对齐到框架语义。"""

    def repl(m: re.Match) -> str:
        level = m.group("level")
        attrs = m.group("attrs")
        body = m.group("body")
        if _already_done(attrs):
            return m.group(0)                    # 幂等：已处理过，原样返回
        target = LEVEL_MAP.get(level)
        if not target:
            return m.group(0)                    # h4/h5/h6 不动
        # 加标记：记录「已按正文规则对齐过」，防止二次运行再次降级
        new_attrs = attrs.rstrip()
        sep = "" if new_attrs.endswith("/") else ""
        new_attrs = f'{new_attrs} {_DONE_ATTR}="{level}->{target}"{sep}'
        title = re.sub(r"<[^>]+>", "", body).strip()[:30]
        report.add("heading", f"h{level} → h{target}（{title}）")
        return f"<h{target}{new_attrs}>{body}</h{target}>"

    return _HEADING_RE.sub(repl, html)


def heading_profile(html: str) -> dict[str, int]:
    """统计各层级标题数量（测试与门禁用）。"""
    out: dict[str, int] = {}
    for m in _HEADING_RE.finditer(html):
        lv = m.group("level")
        out[lv] = out.get(lv, 0) + 1
    return out