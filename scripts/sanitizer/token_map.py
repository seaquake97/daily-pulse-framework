#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""token_map.py — 硬编码色值/ 间距 → design-token 变量映射（数据层）

单一职责：提供「这个色值该换成哪个 Token」的查表。不做替换（替换在 style_pass.py）。

## 为什么需要它
上游正文用 Tailwind 语义色（slate-900 / red-600 / amber-50...）与裸 hex，
与站点框架的 Apple Token 体系（--fg / --surface / --accent...）是两套语言，
渲染出来是「两个产品拼在一个页面上」。本模块把上游色值收敛到 Token，
不改任何可见文本 —— 换的是呈现语言，不是内容。

## 映射原则（按优先级，先命中先用）
  1. 精确 hex 命中 —— 上游高频色值逐个对齐到语义最接近的 Token；
  2. Tailwind 类名色板 —— bg-slate-800 / text-red-600 这类按色板归族；
  3. 兜底：未知色值**不猜**，原样保留并在报告中记录（宁可不换，不可换错）。

第3 条是关键：把一个陌生色值硬映射到某个 Token 是「沉默逻辑错误」的典型
形态 —— 页面照常渲染，但语义色错了，没人发现。记录下来让人判断，而不是猜。

## 禁硬编码（P0-3）
Token 体系里除 #fff / #000 外的裸 hex 都不得出现在产出里。本模块输出的
一律是 var(--token)，色值本身只存在于这张表内（构建期，不进产物）。
"""
from __future__ import annotations

# ---- 1. 精确 hex → Token ----
# 上游 2026-10-14 三份产物的实测色值全集（63 + 18 + 8 个 distinct）。
# 值一律小写（比较前统一 lower），避免 #FFF 与 #fff 变成两条记录。
HEX_TO_TOKEN: dict[str, str] = {
    # —— 中性 / 文字 ——
    "#0f172a": "--fg",            # slate-900 近黑（正文主色）
    "#1e293b": "--fg",            # slate-800
    "#111827": "--fg",
    "#1f2937": "--fg",
    "#0d0d0e": "--fg",
    "#18181b": "--fg",
    "#1c1917": "--fg",
    "#1a0000": "--fg",
    "#330505": "--fg",
    "#4d0a0a": "--fg",
    "#451a1a": "--fg",
    "#1f0a0a": "--fg",
    "#120924": "--fg",
    "#241442": "--fg",
    "#170a28": "--fg",
    "#2d1a45": "--fg",
    "#3b1f66": "--fg",
    "#022c22": "--fg",
    "#143823": "--fg",
    "#0b1f13": "--fg",
    "#0b1120": "--fg",
    "#0f766e": "--fg",
    "#362a19": "--fg",
    "#44403c": "--fg",
    "#1c1c1e": "--fg",
    "#334155": "--fg",

    # slate-700/600/500/400/300 → 次级与弱化文字
    "#475569": "--fg-2",
    "#64748b": "--fg-3",
    "#6b7280": "--fg-3",
    "#78716c": "--fg-3",
    "#94a3b8": "--fg-3",
    "#9ca3af": "--fg-3",
    "#d1d5db": "--border",

    # —— 表面 / 背景 ——
    "#ffffff": "--surface",       # 白（唯一允许的例外色，仍走 Token 更一致）
    "#f8fafc": "--surface-alt",
    "#f1f5f9": "--surface-sunken",
    "#f5f5f7": "--surface-alt",
    "#f3f4f6": "--surface-alt",
    "#fafaf9": "--surface-alt",
    "#fafafa": "--surface-alt",
    "#faf9f6": "--surface-alt",
    "#f2f2f7": "--surface-alt",
    "#faf7f0": "--surface-alt",
    "#f9fafb": "--surface-alt",
    "#fbfbfd": "--surface-alt",
    "#faf5f0": "--surface-alt",
    "#fdf6ec": "--surface-alt",
    "#f7f7f5": "--surface-alt",
    # 2026-10-15 stock-review.html 实测新增（门禁 B-4：声明级 hex 收敛）。
    # 设计师点名存活样本：.expert-badge 的浅蓝 tint 底 + 蓝字。
    "#e0f2fe": "--surface-alt",   # sky-100 浅蓝淡化底：弱化底色，收敛到浅表面
    "#0369a1": "--accent",        # sky-700 蓝字：强调色族（与 #3b82f6 同族）

    # —— 描边 / 分隔 ——
    "#e2e8f0": "--border",
    "#cbd5e1": "--border",
    "#e5e7eb": "--border",
    "#e7e5e4": "--border",
    "#e8e8ed": "--border-soft",
    "#d2d2d7": "--border",

    # —— 语义色：红涨绿跌（A 股口径）——
    "#ef4444": "--quote-up",
    "#dc2626": "--quote-up",
    "#b91c1c": "--quote-up",
    "#f87171": "--quote-up",
    "#e30000": "--quote-up",
    "#10b981": "--quote-down",
    "#16a34a": "--quote-down",
    "#15803d": "--quote-down",
    "#4ade80": "--quote-down",
    "#008009": "--quote-down",

    # —— 警示 / 强调 ——
    "#f59e0b": "--warn",
    "#d97706": "--warn",
    "#b45309": "--warn",
    "#fbbf24": "--warn",
    "#c93400": "--warn",
    "#3b82f6": "--accent",
    "#0071e3": "--accent",
    "#2997ff": "--accent",
    "#8b5cf6": "--accent",       # violet：上游当强调色用，收敛到交互蓝
    "#6366f1": "--accent",       # indigo：同上

    # —— 弱化底色（chip/badge 背景）——
    "#fef2f2": "--rating-offensive-wash",
    "#fee2e2": "--rating-offensive-wash",
    "#fecaca": "--rating-offensive-wash",
    "#fca5a5": "--rating-offensive-wash",
    "#fffbeb": "--rating-balanced-wash",
    "#fef3c7": "--rating-balanced-wash",
    "#fde68a": "--rating-balanced-wash",
    "#f0fdf4": "--rating-defensive-wash",
    "#dcfce7": "--rating-defensive-wash",
    "#064e3b": "--rating-defensive-fg",
    "#1e3a8a": "--rating-conflict-fg",
    "#92400e": "--warn",
    "#78350f": "--warn",
    "#57534e": "--fg-3",
    "#292524": "--fg-2",
    "#0c0a09": "--fg",
}

# ---- 2. Tailwind 色板 → Token 语义族 ----
# 按「色板名 → 族」归类，再由族决定 Token。这样新增 shade（如 slate-950）
# 无需逐个登记，也不会漏映射。
TAILWIND_PALETTE_FAMILY: dict[str, str] = {
    "slate": "neutral", "gray": "neutral", "zinc": "neutral",
    "stone": "neutral", "neutral": "neutral",
    "red": "up", "rose": "up", "orange": "warn",
    "amber": "warn", "yellow": "warn", "lime": "down",
    "green": "down", "emerald": "down", "teal": "down",
    "cyan": "accent", "sky": "accent", "blue": "accent",
    "indigo": "accent", "violet": "accent",
    "fuchsia": "accent", "pink": "up",
}

FAMILY_TO_TOKEN: dict[str, str] = {
    "neutral": "--fg-3",
    "up": "--quote-up",
    "down": "--quote-down",
    "warn": "--warn",
    "accent": "--accent",
}

# 同一族在不同用途（文字 / 背景 / 描边）下的 Token 差异。
# 只在 Tailwind 类名映射时使用；精确 hex 走HEX_TO_TOKEN。
FAMILY_ROLE_TOKEN: dict[str, dict[str, str]] = {
    "neutral": {"text": "--fg-2", "bg": "--surface-alt", "border": "--border"},
    "up": {"text": "--quote-up", "bg": "--rating-offensive-wash", "border": "--border"},
    "down": {"text": "--quote-down", "bg": "--rating-defensive-wash", "border": "--border"},
    "warn": {"text": "--warn", "bg": "--rating-balanced-wash", "border": "--border"},
    "accent": {"text": "--accent", "bg": "--surface-alt", "border": "--border"},
}

# 说明：带透明度后缀的底色类（bg-amber-400/20）按「有透明度 = 弱化底色」
# 处理，统一收敛到 --surface-alt；透明度层级差异在视觉上远小于色相差异，
# 保留它会让弱化层级与语义层级继续分裂。
ALPHA_SUFFIX_BG_TOKEN = "--surface-alt"


# ---- 角色感知（role-aware）----
# 为什么不能一张平表：同一个色值在不同 CSS 属性里语义完全不同
#     color: #FFFFFF      → 深色封面上的「文字」→ 前景 Token（--fg）
#     background: #FFFFFF →「白色表面」        → 表面 Token（--surface）
# 若用平表把 #fff 统一映射到 --surface，浅色模式下就变成「白底白字」——
# 文字彻底消失，而页面看起来「正常」。这是典型的沉默逻辑错误。
# 因此 token_for_hex 必须知道角色（text / bg / border）。
#
# 角色覆写：仅在「同一色值跨角色语义不同」时声明，其余走 HEX_TO_TOKEN。
ROLE_OVERRIDE: dict[str, dict[str, str]] = {
    # 纯白 / 纯黑：文字与表面必须分开
    "#ffffff": {"text": "--fg", "bg": "--surface"},
    "#fff": {"text": "--fg", "bg": "--surface"},
    "#000000": {"text": "--fg", "bg": "--surface-sunken"},
    "#000": {"text": "--fg", "bg": "--surface-sunken"},
}

# ---- 深底浅字（B-3，2026-10-15 门禁实锤）----
# 文字角色且原值亮度 > 0.75 → --fg-on-inverse，不再走 ROLE_OVERRIDE 的 --fg。
# 根因：深色封面（渐变被 gradient_pass 收敛成 --surface-inverse）上的浅色
# 文字（color:#fff）曾与背景双双落 --fg → fg-on-fg 不可见文本。
# design-tokens.css 成对定义了 --surface-inverse / --fg-on-inverse
# （浅色 #1D1D1F × #F5F5F7，16.83:1；深色模式 #2C2C2E × #F5F5F7），
# 这里消费前景一侧。该规则优先于 ROLE_OVERRIDE：白字在深底上永远是
# 「反色文字」，在浅底上写白字本身即上游缺陷，不构成反例。
_INVERSE_TEXT_MIN_LUM = 0.75

_HEXDIGITS = frozenset("0123456789abcdef")


def hex_luminance(hex_value: str) -> float | None:
    """hex 的相对亮度（0=黑 1=白）。无法解析返回 None。

    单一实现：gradient_pass 的色标亮度与本模块的深底浅字判据共用，
    避免两处公式漂移。接受 3/4/6/8 位（#abc / #abcd / #aabbcc / #aabbccdd）。
    """
    h = hex_value.strip().lstrip("#").lower()
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    if len(h) not in (6, 8) or any(c not in _HEXDIGITS for c in h):
        return None
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def token_for_hex(hex_value: str, role: str = "bg") -> str | None:
    """色值 → Token。未命中返回 None（调用方保留原值并记录）。

    role ∈ {text, bg, border}，决定角色覆写表是否生效。
    """
    key = hex_value.strip().lower()
    if role == "text":
        # 深底浅字：亮度 > 0.75 的浅色文字 → --fg-on-inverse（见上方注释）
        lum = hex_luminance(key)
        if lum is not None and lum > _INVERSE_TEXT_MIN_LUM:
            return "--fg-on-inverse"
    override = ROLE_OVERRIDE.get(key)
    if override and role in override:
        tok = override[role]
    else:
        tok = HEX_TO_TOKEN.get(key)
    # 铁律：--rating-*-wash 只作背景，禁作文字色。文字角色命中 wash 族时
    # 不猜、不静默换错，返回 None 让调用方记 unmapped-color 显式报告。
    if role == "text" and tok and tok.endswith("-wash"):
        return None
    return tok


def token_for_tailwind(utility: str, role: str = "text") -> str | None:
    """Tailwind 工具类 → Token。

    utility 形如 "text-slate-800" / "bg-red-500" / "border-amber-200"；
    role 由前缀决定（text- / bg- / border-），传错也不会崩，只是取错族。
    """
    parts = utility.split("-")
    if len(parts) < 2:
        return None
    prefix, palette = parts[0], parts[1]
    if palette not in TAILWIND_PALETTE_FAMILY:
        return None
    family = TAILWIND_PALETTE_FAMILY[palette]
    role = prefix if prefix in ("text", "bg", "border") else role
    return FAMILY_ROLE_TOKEN[family].get(role) or FAMILY_TOKEN[family]


# ---- 3. 间距 → Token ----
# 上游 Tailwind 的 rem 间距。站点 Token 已有 --space-1..8（见 blocks 层），
# 对不上的保留原值（布局改动风险高于收益，不猜）。
SPACING_TO_TOKEN: dict[str, str] = {
    "0.125rem": "--space-1",
    "0.25rem": "--space-1",
    "0.375rem": "--space-2",
    "0.5rem": "--space-2",
    "0.75rem": "--space-3",
    "1rem": "--space-4",
    "1.5rem": "--space-6",
    "2rem": "--space-8",
}