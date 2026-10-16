#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""style_pass.py — 内联样式与<style> 块的Token 收敛（变换层）

单一职责：把正文里的硬编码色值/间距换成 design-token 变量。
依赖方向：向下依赖 token_map。

## 这是「换皮」不是「脱敏」
本模块**只改CSS 表达方式，一个可见字符都不删**。上游正文该说什么还说什么，
只是把`style="background:#EF4444"` 改写成 `style="background:var(--quote-up)"`。
与被移除的脱敏层的区别：脱敏删内容，本模块不删。

## 处理范围
  · style="..." 属性里的 color / background-color / border-color / fill / stroke
  · <style> 块内 CSS 声明里的同类属性（含 border 系列简写）
  · <style> 块内 :root/选择器里的**自定义属性声明**（--up/--ink/--line 等
    上游私有调色板，按属性名推断语义角色收敛，见 map_custom_properties）
  · 裸 hex 与 rgb()/rgba() 两种写法

## 角色语义（B-3 后完整版）
同一个 #FFFFFF：在 color: 里是「深底上的浅色文字」→ --fg-on-inverse；
在 background: 里是「白色表面」→ --surface。渐变收敛出的深色区块同理：
背景落 --surface-inverse，其上文字落 --fg-on-inverse（token_map 的
深底浅字规则）。不区分 role 会把浅色文字映射成表面 token —— 浅色模式下
文字直接消失，而页面看起来「正常」，是最典型的沉默逻辑错误。

## 未知色值不猜
映射不到的色值原样保留，并在报告里记一条 unmapped-color —— 让门禁能看见
「这里还有 3 个没收敛的色值」，而不是悄悄放过或猜一个错的。
"""
from __future__ import annotations

import re
from functools import lru_cache

from . import token_map as TM

# 需要收敛的 CSS 属性（只动颜色类属性，布局属性一律不碰）
# 负向后视 (?<![-\w])：属性名不能是自定义属性名的后缀——否则
# `--focus-ring-color: var(--x)` 会被切成 prop="color" 的假声明
# （2026-10-15 token 注入引入更多自定义属性后必须堵住，见 token_pass）。
# border 系列简写（2026-10-15 B-4 补）：`border-bottom: 2px solid #f1f5f9`
# 曾因简写不在表内而裸 hex 存活；简写值里的色标字面量同样按角色收敛。
# 长名优先于简写排列（alternation 虽可回溯，长名在前少一次回溯）。
_COLOR_PROPS = (
    "color", "background-color", "background", "border-color",
    "border-top-color", "border-bottom-color", "border-left-color",
    "border-right-color", "fill", "stroke", "outline-color",
    "border", "border-top", "border-right", "border-bottom", "border-left",
)

# 文本类属性：用「前景」Token 语义（#fff 是深底上的文字，不是背景）
_TEXTUAL_PROPS = frozenset({"color", "fill", "stroke"})
# 背景类属性：用「表面」Token 语义
_SURFACE_PROPS = frozenset({"background", "background-color"})

_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_FUNC_COLOR = re.compile(r"rgba?\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*"
                         r"(?:,\s*[\d.]+\s*)?\)", re.I)


def _map_color(literal: str, role: str) -> str | None:
    """一个色值字面量 → var(--token)；未映射返回 None。

    role 必须是 text / bg / border —— 这是**语义正确性的关键**：
    同一个 #FFFFFF，在 color: 里是「深底上的文字」，在 background: 里是「白色表面」。
    不区分 role 会把 color:#FFFFFF 映射成 var(--surface)（浅色模式下白底白字，
    文字直接消失）—— 这类沉默错误正是本任务最需要防的。
    """
    if literal.startswith("#"):
        return TM.token_for_hex(literal, role=role)
    return None


def _replace_in_declaration(value: str, role: str = "bg") -> tuple[str, list[str]]:
    """替换一个声明值里的色值字面量，返回 (新值, 未映射清单)。"""
    unmapped: list[str] = []

    def hex_repl(m: re.Match) -> str:
        lit = m.group(0)
        tok = _map_color(lit, role)
        if tok:
            return f"var({tok})"
        unmapped.append(lit)
        return lit

    new = _HEX.sub(hex_repl, value)

    def func_repl(m: re.Match) -> str:
        lit = m.group(0)
        # 带 alpha 的色值不映射：Token 不承载透明度，映射会丢掉 alpha 语义
        # （例：box-shadow 的 rgba(0,0,0,.15) 变成不透明色，阴影变成脏块）。
        nums = re.findall(r"[\d.]+", lit)
        if len(nums) >= 4 and float(nums[3]) < 1.0:
            unmapped.append(lit)
            return lit
        hexish = _rgb_to_hex(lit)
        tok = TM.token_for_hex(hexish, role=role) if hexish else None
        if tok:
            return f"var({tok})"
        unmapped.append(lit)
        return lit

    new = _FUNC_COLOR.sub(func_repl, new)
    return new, unmapped


def _rgb_to_hex(lit: str) -> str | None:
    """rgb()/rgba() → #rrggbb（忽略 alpha：Token 已承载透明度层级）。"""
    nums = re.findall(r"[\d.]+", lit)
    if len(nums) < 3:
        return None
    try:
        r, g, b = (max(0, min(255, int(float(n)))) for n in nums[:3])
    except ValueError:
        return None
    return f"#{r:02x}{g:02x}{b:02x}"


def _role_of(prop: str) -> str:
    """CSS 属性 → 语义角色（text / bg / border）。"""
    p = prop.lower()
    if p in _TEXTUAL_PROPS:
        return "text"
    if p in _SURFACE_PROPS:
        return "bg"
    return "border"


_DECL = re.compile(
    r"(?<![-\w])(?P<prop>" + "|".join(_COLOR_PROPS) + r")\s*:\s*(?P<val>[^;{}]+)",
    re.I)

# ---- 自定义属性（上游私有调色板）收敛（B-4）----
# 上游详情页自带一套 :root（--up/--down/--ink/--sub/--card/--line/--defend*），
# 裸 hex 原样存活即违反 P0「产出无裸 hex」。按属性名推断语义角色后收敛：
#   border/line/ring → 描边 token；bg/surface/card/wash → 背景 token；
#   fg/text/ink/sub → 文字 token；无法归类 → text（上游调色板以前景/
#   行情色为主，text 是安全默认）。色值映射本身仍走 token_for_hex，
#   未知色值保留原值 + unmapped-color 报告，与声明级同一纪律。
_CP_DECL = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;{}]+)", re.I)
_VAR_REF_RE = re.compile(r"var\((--[a-z0-9-]+)")
_CP_BORDER_HINTS = ("border", "line", "ring", "sep", "hairline", "divider")
_CP_BG_HINTS = ("bg", "surface", "card", "panel", "wash", "tint", "canvas")
_CP_TEXT_HINTS = ("fg", "text", "ink", "sub", "muted", "title")


def _cp_role(name: str) -> str:
    """自定义属性名 → 语义角色（border / bg / text）。"""
    n = name.lower()
    if any(h in n for h in _CP_BORDER_HINTS):
        return "border"
    if any(h in n for h in _CP_BG_HINTS):
        return "bg"
    return "text"


@lru_cache(maxsize=1)
def _design_token_refs() -> dict[str, frozenset[str]]:
    """token 名 → 其 design-tokens 定义值里直接引用的 token 集合。

    延迟 import site_theme —— style_pass 只向下依赖 token_map，表现层
    引用延迟到调用期（与 icon_pass / token_pass 同一纪律）。不可读时退化
    为空表，此时仅靠「目标 token ≠ 属性名」防自环。
    """
    try:
        import site_theme as T
        light, dark = T.token_palette()
    except Exception:
        return {}
    refs: dict[str, frozenset[str]] = {}
    for name in set(light) | set(dark):
        found: set[str] = set()
        for v in (light.get(name), dark.get(name)):
            if v:
                found |= set(_VAR_REF_RE.findall(v))
        refs[name] = frozenset(found)
    return refs


def _definition_reaches(start: str, target: str) -> bool:
    """start 的定义（沿 design-tokens 引用链）是否能到达 target。

    用于自定义属性收敛的循环判定：属性名 N 收敛成 var(T) 后，token_pass
    会为 T 补 design-tokens 定义；若 T 的定义链能走到 N，则
    N→T→…→N 成环，双方计算值俱废（页面静默丢色）。
    """
    refs = _design_token_refs()
    seen: set[str] = set()
    frontier = [start]
    while frontier:
        n = frontier.pop()
        if n == target:
            return True
        if n in seen:
            continue
        seen.add(n)
        frontier.extend(refs.get(n, ()))
    return False


def map_custom_properties(css: str, report, where: str) -> str:
    """收敛 <style> 块里的自定义属性声明（上游私有调色板 → design token）。

    显式跳过（均有据，不是遗漏）：
      · 值里已含 var( —— 已收敛，幂等；
      · 目标 token 与属性名同名 —— 会造出 `--fg: var(--fg)` 自环；
      · 目标 token 的定义链能到达属性名 —— 会与 token_pass 补的定义互环
        （上游若定义 --ap-ink 且收敛到 --fg，token_pass 补的
        --fg: var(--ap-ink) 与之成环）。
    注意第二种环是**精确判定**而非「属性名是 design token 名就跳过」：
    上游 --bg: #f8fafc 与站点 --bg 同名但收敛目标 --surface-alt 的定义链
    到不了 --bg，应当收敛（2026-10-15 实测：过度保守曾把 --bg 留下）。
    两种环都保留原值并在报告留痕，绝不静默。
    """
    def repl(m: re.Match) -> str:
        name, val = m.group(1), m.group(2)
        if "var(" in val:
            return m.group(0)                      # 已收敛，幂等跳过
        new, unmapped = _replace_in_declaration(val, role=_cp_role(name))
        for u in unmapped:
            report.add("unmapped-color", f"{where}: {name} 的值 {u}")
        if new == val:
            return m.group(0)                      # 无色值可收敛：原样返回
        cyclic = [t for t in _VAR_REF_RE.findall(new)
                  if t == name or _definition_reaches(t, name)]
        if cyclic:
            report.add("style",
                       f"{where}: 自定义属性 {name} 收敛目标 {cyclic[0]} 会与 "
                       "design token 定义互环，保留原值（显式留痕，非静默）")
            return m.group(0)
        report.add("style",
                   f"{where}: 自定义属性 {name} → {new.strip()[:60]}")
        return f"{name}: {new}"

    return _CP_DECL.sub(repl, css)


def map_css(css: str, report, where: str) -> str:
    """收敛一段 CSS 里的颜色声明。"""

    def repl(m: re.Match) -> str:
        val = m.group("val")
        if "var(" in val:
            return m.group(0)          # 已收敛，幂等跳过
        new, unmapped = _replace_in_declaration(val, role=_role_of(m.group("prop")))
        if new != val:
            report.add("style",
                       f"{where}: {m.group('prop')} → {new.strip()[:70]}")
        for u in unmapped:
            report.add("unmapped-color", f"{where}: {u}")
        # 无改动必须原样返回：下面的重建会把冒号间距规整为 "prop: val"，
        # 对 stroke:currentColor 这类本就没色的声明构成字节改动，
        # 直接破坏「二次运行字节一致」的幂等铁律（2026-10-14 实测踩中）。
        return f"{m.group('prop')}: {new}" if new != val else m.group(0)

    return _DECL.sub(repl, css)


_STYLE_BLOCK = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.S | re.I)


def map_inline_styles(html: str, report) -> str:
    """处理 style="..." 属性与 <style> 块。"""

    def attr_repl(m: re.Match) -> str:
        attr = m.group(1)
        if "var(" in attr:
            return m.group(0)
        #内联 style 属性可能同时含 background 与 color，按出现顺序分段处理过于脆弱；
        # 统一按 bg 角色处理 —— 内联样式里 90% 是背景/边框色，
        # 且剩余的未映射色值会被记录下来供人工确认，不会静默改错。
        new, unmapped = _replace_in_declaration(attr, role="bg")
        if new != attr:
            report.add("style", f"style属性 → {new.strip()[:70]}")
        for u in unmapped:
            report.add("unmapped-color", f"style属性: {u}")
        # 同上：无改动原样返回，保住属性内冒号间距的字节幂等
        return f'style="{new}"' if new != attr else m.group(0)

    html = re.sub(r'style="([^"]*)"', attr_repl, html)

    def block_repl(m: re.Match) -> str:
        css = map_css(m.group(2), report, "<style>")
        # 自定义属性收敛只处理上游 <style>。注入块（tailwind-static /
        # detail-tokens / icon-subsprite）是消毒器自家产物：其 --tw-* 与
        # --ap-* 原语值（如 --ap-ink:#1d1d1f）是 palette 定义本身，
        # 收敛它们会把原语改成 var() 循环，也会污染预编译工具类。
        if "data-origin=" not in m.group(1):
            css = map_custom_properties(css, report, "<style>")
        return m.group(1) + css + m.group(3)

    return _STYLE_BLOCK.sub(block_repl, html)