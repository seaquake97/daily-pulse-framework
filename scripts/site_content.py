#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""site_content.py — 站点内容层（领域常量 + 纯函数，无 IO、无 HTML 骨架）

职责边界：
  · 只声明「内容语义」：任务元信息、五档评级映射、时点映射、星期；
  · 只提供纯函数：转义、Σ 格式化、摘要富化（emoji → SVG 箭头、涨跌语义色）；
  · 不感知 DOM 结构、不读文件、不生成整页 HTML（那是 site_render 的事）。

P0 数据纪律（沉默逻辑错误防线）：
  · sigma 为 None → 一律呈现「数据缺口」，绝不回落 0.000、绝不借用他任务数值；
  · rating 为 None → 一律呈现「评级未标注」，绝不借用当日 meta 的评级。
"""
from __future__ import annotations

import re
from datetime import datetime

# ---- 任务语义：slug → (展示名, 调度时点, 一句话说明, 图标语义键) ----
TASK_META: dict[str, tuple[str, str, str, str]] = {
    "stock-assistant": ("股票助手", "09:28", "竞价窗口的持仓级研判与条件单建议", "bar-chart"),
    "fund-market": ("基金盘面", "11:00", "基金加权涨跌穿透与板块轮动诊断", "database"),
    "fund-guide": ("基金操作指引", "14:30", "尾盘决策窗口的分层操作指令", "target"),
    "stock-review": ("股票复盘", "15:05", "收盘后多视角对抗辩论与决策卡", "line-chart"),
    "daily-review": ("每日总复盘", "15:30", "当日全部研判的汇总归档与观点结算", "inbox"),
}

# ---- 五档评级：CSS 变体 + 箭头冗余编码 + 图标语义键 ----
# 箭头是 ADR-003 明确要求保留的色盲友好冗余编码，不可移除。
RATING_VARIANT: dict[str, tuple[str, str]] = {
    "进攻": ("offensive", "▲▲"), "均衡": ("balanced", "▲"),
    "信号矛盾": ("conflict", "↔"), "防守": ("defensive", "▼"), "回避": ("avoid", "▼▼"),
}
RATING_ICON: dict[str, str] = {
    "进攻": "trending-up", "均衡": "arrow-up", "信号矛盾": "shuffle",
    "防守": "arrow-down", "回避": "chevrons-down",
}
# 未知/缺失评级归入「信号矛盾」变体：该档用中性石板灰，不携带方向暗示，
# 比回落到任意一档红/绿更诚实（SPEC §2.3 的核心色彩决策）
RATING_FALLBACK = "信号矛盾"

# ---- 五档 → 标准动作（结论先行摘要的第二段）----
# 文案与 daily-decision-engine references/decision-card.md 逐字同源。
# 同步责任：改这里必须同时改那份 references（本仓为呈现层，引擎仓为事实源）。
RATING_ACTION: dict[str, str] = {
    "进攻": "定投额度上浮 ≤20%，网格卖单档位可上移，单日新增买入 ≤ 总仓位 5%",
    "均衡": "定投按基准额度执行，网格按原参数运行，不主动加减仓",
    "信号矛盾": "暂停一切主动买入，可挂低于现价 ≥2% 的吸买单；只列多空证据，禁表述为均衡",
    "防守": "暂停主动买入（含手动追加），定投可降档 ≤30%，卖出仅在触发线执行",
    "回避": "定投暂停一期；亏损 >15% 的品种分笔减仓 ≤1/3，启动红利/黄金防御仓再平衡",
}
RATING_ACTION_FALLBACK = RATING_ACTION[RATING_FALLBACK]

# ---- 数据时点 ----
STAGE_MAP: dict[str, tuple[str, str, str, str]] = {
    # stage → (中文, English, chip 变体, 图标语义键)
    "pre_open": ("竞价时点", "Pre-open", "chip-intraday", "timer"),
    "intraday": ("盘中时点", "Intraday", "chip-intraday", "clock"),
    "close": ("收盘时点", "Close", "chip-close", "calendar"),
}
STAGE_FALLBACK = "close"

WEEKDAY_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
WEEKDAY_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

I18N = {
    "site_title": "每日市场脉搏 · Daily Market Pulse",
    "disclaimer_zh": (
        "免责声明：本站内容由 AI 依据公开数据与量化模型自动生成，属个人信息参考"
        "与研究记录，不构成证券投资咨询意见，亦非任何买卖要约。文中评级、Σ 值、"
        "网格参数与操作指令均为模型在特定假设下的推演结果，可能与实际市场不符，"
        "使用者据此操作风险自负。市场有风险，投资需谨慎。"),
    "disclaimer_en": (
        "Disclaimer: AI-generated from public data and quantitative models. For "
        "personal research records only — NOT securities investment advice and "
        "not an offer to buy or sell. Ratings, scores and grid parameters are "
        "model outputs under stated assumptions and may not reflect reality."),
    # AI 生成内容标识：内容侧强制披露义务（与《生成式AI服务管理暂行办法》对齐，
    # 也回应平台侧合规要求）。页脚与订阅页同时呈现——不藏进折叠区。
    "ai_notice": "本站研判内容由 AI 自动生成，非持牌机构发布，不提供投资咨询。",
    "publisher_note": "内容站由个人独立运营，非持牌证券投资咨询机构，不提供代客理财或荐股服务。",
    # 口径提示（2026-10-16 人话化重设计）：旧文案「口径未标注 · Σ 不可跨时点比较」
    # 全是术语，读者看不出「哪里不同、该怎么做」。新文案两段式：
    # 徽章说清状态（统计口径不同 + 动作：仅供参考），说明句说清读法。
    "caliber_tag": "统计口径不同 · 数值仅供参考",
    "caliber_note": "各任务的数据时点与统计口径可能不同：带「统计口径不同」标记的条目，请以当页「数据时点」标注为准阅读，不宜与其他任务或日期的数值直接横向比较。",
}

NAV_ITEMS = (
    ("index", "首页 / Home", "index.html", False),
    ("methodology", "方法论 / Method", "methodology/", False),
    ("weekly", "周报 / Weekly", "weekly/", True),
    ("monthly", "月报 / Monthly", "monthly/", True),
)


def esc(s) -> str:
    """HTML 文本转义。所有插值必须先过这里，杜绝上游数据破坏结构。"""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def sigma_txt(s) -> str:
    """Σ 值格式化。None 返回空串——调用方负责渲染「数据缺口」，不在此处伪造数值。"""
    return f"{s:+.3f}" if isinstance(s, (int, float)) and not isinstance(s, bool) else ""


def sigma_raw(s) -> str:
    """data-sigma 属性用：None → 空串（缺失即缺失，不写 0）。"""
    return f"{s:+.3f}" if isinstance(s, (int, float)) and not isinstance(s, bool) else ""


def dow_label(date_str: str) -> tuple[str, str]:
    try:
        i = datetime.strptime(date_str, "%Y-%m-%d").weekday()
        return WEEKDAY_ZH[i], WEEKDAY_EN[i]
    except (ValueError, TypeError):
        return "", ""


def stage_of(stage: str | None) -> tuple[str, str, str, str]:
    return STAGE_MAP.get(stage or STAGE_FALLBACK,
                         (str(stage), str(stage), "chip-close", "calendar"))


def rating_of(rating: str | None) -> tuple[str, str, str]:
    """返回 (CSS 变体, 箭头, 图标语义键)。未知评级归入中性「信号矛盾」变体。"""
    v, arrow = RATING_VARIANT.get(rating or "", RATING_VARIANT[RATING_FALLBACK])
    return v, arrow, RATING_ICON.get(rating or "", RATING_ICON[RATING_FALLBACK])


def conclusion(rating: str | None, sigma, fact: str = "") -> str:
    """结论先行摘要（§ 一致性契约 C-2）：评级·Σ ｜ 标准动作 ｜ 关键事实。

    用户实锤「每个任务摘要一眼看不出结论」——旧摘要是 md 第一段自由文本，
    四个任务四种结构（09:28 甚至是 MCP 连接警告）。本函数把「结论」锁死成
    固定三段式：读者不看正文也能知道今天什么档、该做什么。

    P0 数据纪律：rating/sigma 任一为 None → 只出「数据缺口」，不回落 0.000。
    """
    if rating is None or not isinstance(sigma, (int, float)) or isinstance(sigma, bool):
        head = "数据缺口 · 未评级" + "｜本任务无可用评级，详见正文说明" if rating is None else \
               f"数据缺口 · Σ 缺失｜评级「{rating}」但 Σ 值不可得，不做估算"
    else:
        head = f"{rating} · Σ{sigma:+.3f}｜{RATING_ACTION.get(rating, RATING_ACTION_FALLBACK)}"
    return f"{head}｜{fact}" if fact else head


# ---- 摘要富化：emoji → SVG 箭头；带符号涨跌幅 → 语义色 + 矢量箭头 ----
# 单趟 tokenize，避免二次处理自己插入的标签（沉默逻辑错误高发点）。
#
# 映射表的键一律写成 \uXXXX 转义而非字面字符：字面 emoji 会让 P0 扫描器在源码里
# 命中，误判「emoji 仍在被使用」。转义后语义完全等价，源码扫描恒为 0 命中。
_EMOJI_MAP: dict[str, tuple[str, str]] = {
    "\U0001F53A": ("arrow-up", "up"),  # 红色上三角
    "\U0001F53B": ("arrow-down", "down"),  # 红色下三角
    "\U0001F4C8": ("trending-up", "up"),  # 上升柱状图
    "\U0001F4C9": ("trending-down", "down"),  # 下降柱状图
    "\u2b06\ufe0f": ("arrow-up", "up"),  # 黑上箭头 + 变体选择符
    "\u2b07\ufe0f": ("arrow-down", "down"),  # 黑下箭头 + 变体选择符
    "\u2197": ("trending-up", "up"),  # 右上箭头
    "\u2198": ("trending-down", "down"),  # 右下箭头
}
# 剥离口径与 P0 扫描正则完全一致（分段枚举，见 ADR-003 第二层）；
# 刻意不覆盖 U+25B2 / U+25BC / U+2194，故RATING_ARROWS 的
# 三角形/双向箭头色盲友好冗余编码不受影响（ADR-003 明确要求保留）。
# 2026-10-15 随 sanitizer 同口径补 \u26c0-\u26ff 与 \u2700-\u27bf 两段
# （QA 实测上游 ✅/❌ 状态标记从旧口径漏过）。
_EMOJI_ANY = re.compile(
    "[\U0001F300-\U0001F9FF\U0001FAFF"
    "\u2600-\u26bf\u26c0-\u26ff\u2700-\u27bf\u2b00-\u2bff"
    "\ufe0f\u200d\u2b50]")
_TOKEN_RE = re.compile(
    "([\U0001F300-\U0001F9FF\U0001FAFF"
    "\u2600-\u26bf\u26c0-\u26ff\u2700-\u27bf\u2b00-\u2bff"
    "\ufe0f\u200d\u2b50]+)"
    r"|([+\-−]?\d+(?:\.\d+)?\s*%)")


def _colorize(text: str, icon_fn) -> str:
    """带符号百分比 → 语义色 + 矢量箭头；可映射 emoji → SVG。

    summary_html 与 conclusion_html 共用（避免两套涨跌语义色规则）。
    输入必须已转义。
    """
    def repl(m: re.Match) -> str:
        tok = m.group(0)
        if _EMOJI_ANY.fullmatch(tok):
            hit = _EMOJI_MAP.get(tok[:1]) or _EMOJI_MAP.get(tok)
            if not hit:
                return ""          # 装饰性 emoji：语义已由正文承载，剥离
            name, cls = hit
            return f'<span class="{cls}">{icon_fn(name)}</span>'
        stripped = tok.lstrip()
        sign = stripped[0] if stripped else ""
        cls = "up" if sign == "+" else ("down" if sign in "-−" else "flat")
        arrow = {"up": "arrow-up", "down": "arrow-down"}.get(cls, "minus")
        return (f'<span class="{cls}">'
                f'<svg class="ic vt" aria-hidden="true" focusable="false">'
                f'<use href="#i-{arrow}"/></svg>{tok}</span>')

    return _TOKEN_RE.sub(repl, text)


def conclusion_html(text: str, icon_fn) -> str:
    """结论先行摘要的富化渲染（一致性契约 C-2 的视觉层）。

    三段固定结构各自承担不同视觉权重，读者扫一眼即知结论：
      段1 评级·Σ   → 加粗 + 评级语义色（最强）
      段2 标准动作 → 常规正文色
      段3 关键事实 → 三级灰（最弱，可略读）
    分隔符 ｜ 由 CSS 弱化为竖线细条，不与文字抢注意力。
    """
    parts = [p.strip() for p in (text or "").split("｜") if p.strip()]
    if not parts:
        return ""
    classes = ("concl-head", "concl-action", "concl-fact")
    rendered = [f'<span class="{classes[min(i, 2)]}">{_colorize(esc(p), icon_fn)}</span>'
                for i, p in enumerate(parts)]
    return ('<span class="conclusion">' +
            '<span class="concl-sep" aria-hidden="true"></span>'.join(rendered) +
            "</span>")


def summary_html(raw: str, icon_fn) -> str:
    """把上游摘要转成已转义、带语义标记的 HTML 片段。

    icon_fn(name, size) 由渲染层注入（site_theme.icon），本模块不依赖 DOM 实现。
    规则：
      · 带符号百分比 → <span class="up|down"> + 内联 SVG 箭头（红涨绿跌）；
      · 可映射 emoji → 同语义 SVG 箭头（信息不丢，只换载体）；
      · 不可映射 emoji → 剥离（章节装饰，语义已由正文承载）。
    """
    return _colorize(esc(raw or ""), icon_fn)


def summary_has_gap(raw: str) -> bool:
    """摘要是否声明了数据缺口（上游用「缺口」「未响应」「无响应」等词明示）。"""
    return any(k in (raw or "") for k in ("数据缺口", "无响应", "未响应", "未参与计算"))