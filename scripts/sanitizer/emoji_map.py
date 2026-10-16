#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""emoji_map.py — emoji 处置策略与语义映射表（sanitizer 包的数据层）

单一职责：决定「每个 emoji 变成什么」。不做任何正则替换 —— 替换逻辑在
emoji_inline.py（便于独立测试与分层）。

## 四种处置（穷举且互斥，无第五种）
  1. MAPPED      → 内联 SVG（site_theme 锁定的 Lucide symbol）
  2. PROTECTED   → 保留原字符（ADR-003 的色盲友好方向冗余编码，禁止剥离）
  3. IP_MARK     → 保留原字符 + ip-mark 包裹。**白名单制**：只有本文件
                   显式登记的 IP / 品牌标识可走此路（唯一合法保留路径）
  4. UNMAPPED    → needs-manual-review + 保守保留原字符（不包 ip-mark）。
                   包了 ip-mark 会被 P0 扫描器豁免，功能图标位 emoji
                   就此静默过闸（2026-10-15 设计师门禁实锤，见 B-5）

## 铁律：不静默删除，也不静默放行
  映射表覆盖不到的 emoji 一律显式处置（第 4 种），绝不悄悄包个 span 混进
  产出。「删除一个看不懂的 emoji」看起来干净，实则丢失上游语义，且违反本任务
  「sanitize 是换皮不是阉割」的核心约束；「悄悄保留」更糟 —— 它让 P0 闸门
  失去意义。宁可留一个 needs-manual-review 告警让人来判断，也不丢字符、
  不闭眼。测试用「可见文本字符集子集」守住内容线，用「未映射必报
  needs-manual-review」守住门禁线。

## ⚠️ 与 🍜 的设计决策（勿擅改）
  · U+26A0 警告符承载语义（风险提示），转 alert-triangle 并加 `warn` class
    继承所在容器的警示色 —— 可见性不降级，不是装饰性剥离。
  · U+1F35C 是个人 IP 形象（账号标识），**不是功能图标**。已核对原型站
    apple-prototype.html 的 36 个 i-* symbol，无面/餐/餐饮类图标；强行补一个
    等于手绘第二套图标库，违反 P0「全站唯一样式」。故按 IP_MARK 保留原字符，
    并加 title 说明，既守住 P0「禁止 emoji 作为功能图标」，也不丢品牌标识。

## 书写纪律
  键一律用 \\uXXXX 转义，不写字面 emoji —— 字面 emoji 会让 P0 扫描器在源码里
  命中，误判「emoji 仍在被使用」（与 site_content.py 同一纪律）。
  变体选择符 U+FE0F / 零宽连接符 U+200D 在查表前统一剥离，避免「⚠️」与「⚠」
  被当成两个 key。
"""
from __future__ import annotations

_VARIATION_SELECTORS = ("️", "‍")

# ---- 处置 1：语义映射表（可扩展）----
# (symbol, extra_class)；extra_class 用于继承容器语义色（up / down / warn）
EMOJI_TO_SYMBOL: dict[str, tuple[str, str]] = {
    # 方向 / 涨跌（与 site_content 已锁定的映射保持全站一致）
    "\U0001F53A": ("arrow-up", "up"),                # 红色上三角
    "\U0001F53B": ("arrow-down", "down"),            # 红色下三角
    "\U0001F4C8": ("trending-up", "up"),             # 上升柱状图
    "\U0001F4C9": ("trending-down", "down"),         # 下降柱状图
    "⬆️": ("arrow-up", "up"),                  # 黑上箭头 + 变体
    "⬇️": ("arrow-down", "down"),                # 黑下箭头 + 变体
    "↗": ("trending-up", "up"),                   # 右上箭头
    "↘": ("trending-down", "down"),               # 右下箭头

    # 语义标记（覆盖 2026-10-14 三份真实产出的实测全集）
    "\U0001F3AF": ("target", ""),                    # 目标
    "⚠": ("alert-triangle", "warn"),           # 警告：承载语义，保留
    "\U0001F4C5": ("calendar", ""),                   # 日历 / 数据日期
    "\U0001F464": ("user", ""),                       # 人物 / 投资者
    "\U0001F3C6": ("award", ""),                      # 奖杯 / 重仓榜
    "\U0001F4A1": ("lightbulb", ""),                  # 灯泡 / 提示
    "\U0001F6D1": ("ban", ""),                        # 禁止 / 否决
    "\U0001F4CA": ("bar-chart", ""),                  # 柱状图 / 多空统计
    # 状态标记（2026-10-15 QA P0 返工）：stock-review.html 待验证信号表用
    # ✅ TRIGGERED / ❌ NOT_TRIGGERED 标注条件单命中状态——功能图标位，
    # 原样字符即违反 P0。符号语义与 up/down 涨跌语境一致（命中=多头生效）。
    "\u2705": ("check", "up"),                        # 成功勾选：TRIGGERED
    "\u274c": ("ban", "down"),                        # 失败叉号：NOT_TRIGGERED

    # CTA 区的功能符号（点赞 / 关注 / 转发 / 在看）。
    # 原文同句已有「点赞」「关注」等文字，图形语义重复 —— 但仍转 SVG 而非删除：
    # 删除会丢字符（违反内容零丢失），转 SVG 则信息完整且风格统一。
    "\U0001F44D": ("check", ""),                      # 点赞 → 勾选
    "⭐": ("star", ""),                         # 关注 → 星标
    "\U0001F501": ("repeat", ""),                        # 转发 → 循环
    "\U0001F440": ("eye", ""),                           # 在看 → 眼睛

    # 2026-10-13 历史产出实测新增（B-5 收紧后由 needs-manual-review 转正）。
    # 全部是功能图标位（维度标签 / meta-chip），按 P0 必须转 SVG；符号从
    # 锁定表（site_theme.SYMBOLS）内选最接近者，不新增图标。
    # 含判断成分的三处（🏔/⚡/🔧）已在交付报告中标为 advisory 待设计师复核。
    "\u2696": ("scale", ""),                 # ⚖️ 均衡维度（天平）
    "\U0001F30A": ("layers", ""),            # 🌊 产业维度（分层结构）
    "\U0001F4E1": ("radio", ""),             # 📡 信号维度（信号塔）
    "\U0001F9EE": ("sigma", ""),             # 🧮 估值维度（Σ 估值符号）
    "\U0001F3D4": ("chevrons-down", ""),     # 🏔️ 逆向维度·坤候底（双下=候底）
    "\U0001F52C": ("file-text", ""),         # 🔬 财报维度（财报文档）
    "\u26a1": ("activity", ""),              # ⚡ 短线维度（脉冲活跃）
    "\U0001F550": ("clock", ""),             # 🕐 生成时间
    "\U0001F527": ("alert-triangle", ""),    # 🔧 定时故障补跑（异常处理）
    "\U0001F465": ("user", ""),              # 👥 投研专家团（锁定表无 users）

    # 2026-10-16 涨跌停统计三元组（fund-guide 市场宽度清单实测）：
    # ➖ 平盘 / 🔥 涨停 / ❄️ 跌停——内容位 emoji 修饰统计项名，属功能图标位。
    # 语义与全站红涨绿跌口径一致：涨停=up 红、跌停=down 绿、平盘=minus 灰。
    "\u2796": ("minus", ""),                 # ➖ 平盘家数（横盘）
    "\U0001F525": ("trending-up", "up"),     # 🔥 涨停板数（加热=上行）
    "\u2744": ("trending-down", "down"),     # ❄️ 跌停板数（冷凝=下行）
}

# ---- 处置 2：个人 IP / 品牌标识（保留原字符）----
IP_MARK_EMOJI = frozenset({
    "\U0001F35C",   # 热气面碗：个人 IP 形象
    "♟",             # 黑色棋子：专栏标识
})

# ---- 处置 3：ADR-003 色盲友好方向冗余编码（保留原字符，禁止剥离）----
PROTECTED_ARROWS = frozenset({"▲", "▼", "↔", "▲▲", "▼▼"})


def strip_variation(text: str) -> str:
    """剥离变体选择符与零宽连接符，返回可查表的裸字符。"""
    for ch in _VARIATION_SELECTORS:
        text = text.replace(ch, "")
    return text


_IP_BARE = frozenset(strip_variation(c) for c in IP_MARK_EMOJI)


def lookup(emoji: str) -> tuple[str, str] | None:
    """查 SVG 映射表。未命中返回 None（交由调用方走保留策略）。"""
    if emoji in EMOJI_TO_SYMBOL:
        return EMOJI_TO_SYMBOL[emoji]
    return EMOJI_TO_SYMBOL.get(strip_variation(emoji))


def is_ip_mark(emoji: str) -> bool:
    """是否个人 IP / 品牌标识（K-1 白名单：唯一合法保留路径）。

    白名单外的未映射 emoji 不走保留 + ip-mark，走 needs-manual-review
    （见 emoji_inline K-2）——ip-mark 是 P0 扫描器豁免范围，不能让
    未登记字符搭这条便车静默过闸。
    """
    return strip_variation(emoji) in _IP_BARE


def is_protected(emoji: str) -> bool:
    """是否受保护的方向冗余编码（ADR-003：禁止剥离）。"""
    return emoji in PROTECTED_ARROWS


def mapped_symbols() -> set[str]:
    """映射表引用到的全部 symbol 名（供 verify_symbols 校验）。"""
    return {sym for sym, _ in EMOJI_TO_SYMBOL.values()}


def verify_symbols(known: set[str]) -> list[str]:
    """返回映射表里尚未在 site_theme.SYMBOLS 定义的 symbol 名。

    构建期防线：映射表与图标表不同步时立即失败，而不是等渲染某页才 KeyError
    （把沉默失效前置为显式报错）。
    """
    return sorted(mapped_symbols() - set(known))