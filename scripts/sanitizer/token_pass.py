#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""token_pass.py — 详情页缺失 Token 注入（sanitizer 包的末道变换层）

单一职责：把「被引用但未定义」的 design token 补进详情页，让 style_pass
收敛出来的 var(--x) 引用全部有着落——悬空 var 的计算值是不可用值，
属性回退 unset，颜色 fidelity 实际丢失（不是理论风险）。

## 根因（2026-10-15 团队实测实锤）
style_pass 把硬编码色值改写成 var(--token)，但上游详情页只自带一套私有
:root（--up/--down/--ink/--sub...），不携带站点 Token 层。实测
stock-review.html 消毒后 14 个 var 引用 vs 11 个 :root 定义，悬空
--fg / --fg-3 / --surface-alt。

## 深浅双套（不可只注入浅色）
design-tokens.css 的 token 在 prefers-color-scheme 下有深浅两值。只注入
浅色等于让深色模式用户看到「属性未设置」。注入形态复刻规范源结构：
    :root{ ...浅色... }
    @media (prefers-color-scheme: dark){
      :root:not([data-theme="light"]){ ...深色... } }
手动钩子 :root[data-theme="dark"] 不注入——详情页零 JS、无主题切换器，
注入即是死代码。规范源里只存在于深色块的 token（如有）只注深色。

## 只补缺口，不覆盖
页面已定义的 token 一律不碰（CSS 中级联后者胜，新 :root 会覆盖页面原值，
那是换皮变篡改）。注入值自身若再引用其他 token（--fg → var(--ap-ink)），
沿引用链递归进闭包——否则只是把悬空往下传一层。

## 幂等（硬约束）
「无缺口即整段不动」：被引用但未定义的 token 集合为空时直接返回原文，
二次运行字节不变。注入块带标记 <!-- detail-tokens:v1 --> 便于回溯。

## 已注入页面也要补缺口（B-8 配套，2026-10-15 门禁实测）
旧实现见 MARKER 即整段跳过。但历史产物再次消毒时，新规则可能引入**新**
引用（如 B-3 的深底浅字规则把 color:#fff 改写成 var(--fg-on-inverse)），
整段跳过会让新引用悬空 —— 「代码新于产物」的陈旧路径改头换面复活。
现在：MARKER 存在但仍有缺口时，补一个**补充注入块**（只含缺口 token，
带同一 MARKER 便于回溯），而不是跳过。补充块与既有块 token 集合不相交
（缺口 = 全页未定义），无级联冲突；下一次运行无缺口 → 不动 → 字节幂等。
"""
from __future__ import annotations

import re

from .html_utils import inject_before

# 注入标记：二次运行检测到即跳过（幂等的唯一依据）
MARKER = "<!-- detail-tokens:v1 -->"

_VAR_REF = re.compile(r"var\((--[a-z0-9-]+)")
# 页面里的 token 定义（任意位置：:root / @media 内 / 兜底定义都算）
_TOKEN_DEF = re.compile(r"(--[a-z0-9-]+)\s*:")
# CSS 注释（引用检测前剥离，见 referenced_tokens docstring）
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def referenced_tokens(html: str) -> set[str]:
    """产物中被 var(--x) 引用的 token 名集合。

    先剥离 /* */ 注释再扫描：注释里的示例文本不是真实引用 ——
    detail-frame.css 的规范注释含「一律 var(--token) 引用」字样，计入
    会造出幻影引用 --token：design-tokens.css 没有该定义故不会注入，
    却以 unmapped-token 条目污染消毒报告（2026-10-15 实测，腐败页
    stock-review.html 里 3 处）。只在引用检测路径剥离，注入产物
    （注入块无注释）不受影响。
    """
    return set(_VAR_REF.findall(_CSS_COMMENT.sub("", html)))


def defined_tokens(html: str) -> set[str]:
    """产物中已定义（有着落）的 token 名集合。"""
    return set(_TOKEN_DEF.findall(html))


def _closure(missing: set[str], defined: set[str],
             light: dict[str, str], dark: dict[str, str]
             ) -> tuple[dict[str, tuple[str | None, str | None]], list[str]]:
    """从 missing 出发沿「注入值的引用」走到闭包。

    返回 (注入表, 无法注入的清空)。注入表 name → (浅色值或 None, 深色值或 None)。
    seen 集合保证每个 token 只处理一次（否则会重复进 unmapped）。
    """
    inject: dict[str, tuple[str | None, str | None]] = {}
    unmapped: list[str] = []
    seen: set[str] = set()
    frontier = list(missing - defined)
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        if name in defined:
            continue
        lv, dv = light.get(name), dark.get(name)
        if lv is None and dv is None:
            unmapped.append(name)          # 规范源也没有：悬空且无法补
            continue
        inject[name] = (lv, dv)
        for v in (lv, dv):
            if v:
                frontier.extend(r for r in _VAR_REF.findall(v) if r not in seen)
    return inject, sorted(unmapped)


def _inject_block(inject: dict[str, tuple[str | None, str | None]]) -> str:
    """按规范源结构生成注入块（浅色 :root + 深色 @media），sorted 保字节确定。"""
    light_css = "".join(f"{n}:{lv};" for n, (lv, _) in sorted(inject.items()) if lv)
    dark_css = "".join(f"{n}:{dv};" for n, (_, dv) in sorted(inject.items()) if dv)
    block = MARKER + '<style data-origin="detail-tokens">'
    if light_css:
        block += f":root{{{light_css}}}"
    if dark_css:
        block += ('@media (prefers-color-scheme: dark){'
                  f':root:not([data-theme="light"]){{{dark_css}}}}}')
    return block + "</style>"


def inject_missing_tokens(html: str, report) -> str:
    """补全被引用但未定义的 token。幂等由「无缺口即不动」保证。"""
    missing = referenced_tokens(html) - defined_tokens(html)
    if not missing:
        return html                                  # 无悬空：什么都不加
    import site_theme as T
    light, dark = T.token_palette()
    inject, unmapped = _closure(missing, defined_tokens(html), light, dark)
    for name in unmapped:
        # 规范源也没有的 token：显式记录，绝不静默留着悬空
        report.add("unmapped-token",
                   f"{name} 被引用但 design-tokens.css 无定义，无法注入（保持悬空）")
    if not inject:
        return html
    block = _inject_block(inject)
    if MARKER in html:
        # 已注入过的页面（历史产物再次消毒）：只补缺口，不重注、不覆盖。
        # 补充块带同一 MARKER 便于回溯；token 集合与既有块不相交。
        block = MARKER + block
    out = inject_before(html, r"</head\s*>", block, "head")
    report.add("token",
               f"注入缺失 Token {len(inject)} 个: {', '.join(sorted(inject))}")
    return out
