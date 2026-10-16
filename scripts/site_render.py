#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""site_render.py — 站点渲染层（DOM 组装，只依赖 site_content / site_theme）

职责边界：
  · 组装页面骨架：<head> / 导航 / 页脚 / 时间线 / 各页面；
  · 不读文件、不做数据判断（评级/时点/缺口语义全在 site_content）；
  · 不定义样式（样式全在 site_components.css + design-tokens.css）。

视觉基准：apple-prototype.html。零 JS、零外链、零渐变、零 emoji。
"""
from __future__ import annotations

import site_content as C
import site_theme as T


# ---------------------------------------------------------------------------
# 骨架
# ---------------------------------------------------------------------------
def _nav(depth: str, current: str) -> str:
    items = []
    for key, label, href, optional in C.NAV_ITEMS:
        cur = ' aria-current="page"' if key == current else ""
        opt = " data-optional" if optional else ""
        # 中英双段：≤640px 隐藏英文段（.nav-en），窄屏导航不横向溢出
        zh, sep, en = label.partition(" / ")
        items.append(f'<a href="{depth}{href}"{cur}{opt}>'
                     f'<span class="nav-zh">{C.esc(zh)}</span>'
                     f'{f"<span class=\"nav-en\">{C.esc(sep + en)}</span>" if en else ""}</a>')
    # RSS 入口指向订阅页（说明 + 地址 + 阅读器指引），不再把读者直接扔进裸 XML
    items.append(f'<a href="{depth}subscribe/">{T.icon("rss")}<span class="sr">RSS 订阅</span></a>')
    return "\n".join(items)


def nav_block(depth: str, current: str) -> str:
    """完整导航块（<nav> 容器 + 品牌 + 链接），供静态页注入复用。

    shell() 内部用的是同一组片段；静态页（如方法论）改注入本函数而非自己
    写死导航 —— 2026-10-16 前方法论页导航写死漂移出 href="../feed.xml"，
    右上角订阅入口直达裸 XML（用户实锤）。导航必须单一生产者。
    """
    return (f'<nav class="nav" aria-label="全局导航">\n  <div class="nav-in">\n'
            f'    <a class="nav-brand" href="{depth}index.html">'
            f'{T.icon("line-chart", extra_class="mark")}每日市场脉搏</a>\n'
            f'    <div class="nav-links">\n{_nav(depth, current)}\n'
            f'    </div>\n  </div>\n</nav>')


def _footer(depth: str, extra_legal: str = "") -> str:
    """站点页脚。栏目标题用 h4 不用 h3：frame 铬件注入晚于 sanitize，无 data-sb-h
    标记的 h3 会被 heading_pass 降级成 h4（页面再消毒时字节漂移）；h4 不在其
    LEVEL_MAP 内，原样稳定（选择器同步见 site_blocks.css .foot-col h4）。"""
    link = lambda href, label, ico="": (  # noqa: E731 - 局部渲染助手，保持单行可读
        f'<li><a href="{depth}{href}">{T.icon(ico) if ico else ""}{C.esc(label)}</a></li>')
    return f"""<footer class="foot">
  <div class="foot-in">
    <div class="foot-top">
      <div class="foot-brand">
        <a class="nav-brand" href="{depth}index.html">{T.icon("line-chart", extra_class="mark")}每日市场脉搏</a>
        <p class="t-footnote">每交易日的判断轨迹存档。结论由 daily-decision-engine 确定性计算，同数据必得同结论。</p>
      </div>
      <nav class="foot-cols" aria-label="页脚导航">
        <div class="foot-col">
          <h4>归档</h4>
          <ul>{link("index.html", "全部归档")}{link("weekly/", "周报")}{link("monthly/", "月报")}</ul>
        </div>
        <div class="foot-col">
          <h4>关于</h4>
          <ul>{link("methodology/", "研判方法论")}{link("subscribe/", "订阅更新", "rss")}</ul>
        </div>
        <div class="foot-col">
          <h4>来源</h4>
          <ul>{link("methodology/", "腾讯自选股 MCP", "database")}{link("methodology/", "daily-decision-engine", "git-branch")}</ul>
        </div>
      </nav>
    </div>
    <div class="foot-legal">
      <p class="foot-ai">{T.icon("alert")}{C.esc(C.I18N["ai_notice"])}</p>
      <p class="foot-pub">{T.icon("shield")}{C.esc(C.I18N["publisher_note"])}</p>
      <p>{C.esc(C.I18N["disclaimer_zh"])}</p>
      <p>{C.esc(C.I18N["disclaimer_en"])}</p>
      <p>数据来源：腾讯自选股 MCP 实时采集 · 信号评分由 daily-decision-engine 确定性计算</p>{extra_legal}
    </div>
  </div>
</footer>"""


def shell(title: str, desc: str, depth: str, body: str, current: str = "") -> str:
    """整页外壳：Token 注入 + 图标 sprite + 跳到主内容 + 两级导航 + 页脚。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<link rel="alternate" type="application/rss+xml" title="每日市场脉搏 · Daily Market Pulse" href="{depth}feed.xml">
<title>{C.esc(title)}</title>
<meta name="description" content="{C.esc(desc)}">
<meta property="og:title" content="{C.esc(title)}">
<meta property="og:description" content="{C.esc(desc)}">
<meta property="og:type" content="website">
<meta name="generator" content="daily-decision-engine">
<style>{T.inject_tokens()}</style>
</head>
<body>
{T.icon_sprite()}
<a class="skip-link" href="#main">跳到主要内容</a>
<nav class="nav" aria-label="全局导航">
  <div class="nav-in">
    <a class="nav-brand" href="{depth}index.html">{T.icon("line-chart", extra_class="mark")}每日市场脉搏</a>
    <div class="nav-links">
{_nav(depth, current)}
    </div>
  </div>
</nav>
<main id="main" class="frame">
  <div class="shell">
{body}
  </div>
</main>
{_footer(depth)}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 组件片段
# ---------------------------------------------------------------------------
def rating_badge(rating: str | None, size: str = "") -> str:
    """评级徽章：颜色 + SVG 图标 + 箭头 + 文字，四重编码。"""
    variant, arrow, ico = C.rating_of(rating)
    # f-string 条件表达式：lg 分支曾因字符串拼接优先级产出 `rating-lg defensive`
    #（variant 缺 rating- 前缀，徽章样式实际不生效）——条件表达式两侧独立求值
    cls = (f"rating rating-lg rating-{variant}" if size == "lg"
           else f"rating rating-{variant}")
    return (f'<span class="{cls}">{T.icon(ico)}'
            f'<span class="arrow">{arrow}</span>{C.esc(rating)}</span>')


def sigma_badge(sigma) -> str:
    """Σ 值。None → 空串（调用方改渲染 tag gap 双类，绝不显示 0.000）。"""
    txt = C.sigma_txt(sigma)
    return "" if not txt else f'<span class="tl-sigma">{T.icon("sigma")}{C.esc(txt)}</span>'


def stage_chip(stage: str | None) -> str:
    zh, en, variant, ico = C.stage_of(stage)
    return f'<span class="chip {variant}">{T.icon(ico)}{C.esc(zh)} / {C.esc(en)}</span>'


# ---------------------------------------------------------------------------
# 详情页阅读框架片段（frame_pass 注入用；detail-frame-spec v1.1 §2/§3）
# 与框架页片段同 Token 同组件类——站点铬件只有一套，不因页面类型分裂。
# ---------------------------------------------------------------------------
def detail_nav(date: str, depth: str = "../../") -> str:
    """§3.1 slim 导航：复用 .nav 全套类；品牌 + 返回当日时间线 + 方法论 + RSS。
    次要链接带 data-optional（框架 @media ≤640px 隐藏），移动端只留品牌+返回。
    date 仅作调用契约（日期由 detail_crumb 承载）——导航里重复日期会在
    320px 窄屏把「返回」链接挤出可视区（探针实测 right=328 > 320）。"""
    return (f'<nav class="nav" aria-label="全局导航">\n  <div class="nav-in">\n'
            f'    <a class="nav-brand" href="{depth}index.html">'
            f'{T.icon("line-chart", extra_class="mark")}每日市场脉搏</a>\n'
            f'    <div class="nav-links">\n'
            f'      <a class="df-back" href="index.html">{T.icon("arrow-left")}'
            f'返回时间线</a>\n'
            f'      <a href="{depth}methodology/" data-optional>方法论 / Method</a>\n'
            f'      <a href="{depth}subscribe/" data-optional>{T.icon("rss")}'
            f'<span class="sr">RSS 订阅</span></a>\n'
            f'    </div>\n  </div>\n</nav>')


def detail_crumb(date: str, name: str, depth: str = "../../") -> str:
    """§3.2 面包屑三段：全部归档 / 日期 / 当前任务名（aria-current）。"""
    return (f'<nav class="crumb" aria-label="面包屑">'
            f'<a href="{depth}index.html">{T.icon("chevron-right")}全部归档</a>'
            f'<span class="sep" aria-hidden="true">/</span>'
            f'<a href="index.html">{C.esc(date)}</a>'
            f'<span class="sep" aria-hidden="true">/</span>'
            f'<span aria-current="page">{C.esc(name)}</span></nav>')


def detail_meta(entry: dict) -> str:
    """§3.4 元信息行：字段与时间线条目 meta 区完全同源（entries.json 同一记录）。"""
    parts = [f'<span class="df-time">{T.icon("clock")}调度 '
             f'<b>{C.esc(entry.get("time") or "")}</b></span>']
    sched, run = entry.get("time") or "", entry.get("run_time") or ""
    if run and run[:5] != sched:               # 承诺 vs 事实，延迟本身是内容
        parts.append(f'<span class="df-time">{T.icon("timer")}生成 '
                     f'<b>{C.esc(run)}</b></span>')
    if entry.get("stage"):
        parts.append(stage_chip(entry["stage"]))
    if entry.get("rating") is not None:
        parts.append(rating_badge(entry["rating"]))
    if entry.get("sigma") is None:             # P0：缺口显式呈现，严禁 0.000 兜底
        parts.append(f'<span class="tag gap">{T.icon("alert")}Σ 数据缺口</span>')
    else:
        parts.append(sigma_badge(entry["sigma"]))
    if entry.get("comparable") is False:
        parts.append(f'<span class="tag tag-warn">{T.icon("alert")}'
                     f'{C.I18N["caliber_tag"]}</span>')
    return '<div class="doc-meta">' + "".join(parts) + "</div>"


def detail_footer(depth: str, entry: dict | None, date: str) -> str:
    """§3.6 站点页脚（与框架页同源同 Token）+ 详情页「本页信息」行。

    本页信息只取 entries.json / 路径字段，不取墙钟——守住发布幂等铁律。
    """
    segs = [f"数据日期 {date}"]
    if entry:
        run = entry.get("run_time") or ""
        if run:
            segs.append(f"生成时点 {run[:5]}")
        if entry.get("stage"):
            segs.append(f"数据时点 {C.stage_of(entry['stage'])[0]}")
    segs.append("报告由 AI 生成")
    return _footer(depth, f"<p>本页信息：{' · '.join(segs)}</p>")


def timeline(m: dict, depth: str) -> str:
    """当日时间线：调度时点 / 真实生成时刻 / 任务名 / 真实标题 / 摘要 / 徽章 / Σ / 时点。"""
    entries = sorted(m.get("entries", []), key=lambda e: e.get("time") or "99:99")
    if not entries:
        return ('  <div class="empty">'
                f'{T.icon("inbox", "ic-24")}'
                '<h3>本期无分项产出记录</h3>'
                '<p>该交易日的任务产出尚未入库 —— 空数据不做补零，避免生成虚假结论。</p>'
                '<div class="btn-row" style="justify-content:center">'
                f'<a class="btn btn-quiet" href="{depth}subscribe/">{T.icon("rss")}订阅更新</a>'
                '</div></div>')

    rows = []
    date = m.get("date", "")
    for e in entries:
        slug = e.get("slug", "")
        name, default_time, blurb, ico = C.TASK_META.get(slug, (slug, "—", "", "file-text"))
        sched = e.get("time") or default_time
        title = e.get("title") or name
        rating, sigma = e.get("rating"), e.get("sigma")
        html = e.get("html")
        # 摘要走结论先行契约（一致性契约 C-2）：评级·Σ ｜ 标准动作 ｜ 关键事实。
        # 老 entries.json 无 conclusion 字段时回落 blurb，向后兼容。
        conclusion = e.get("conclusion")
        summary = conclusion if conclusion else (e.get("summary") or blurb)

        # 调度时点是承诺，生成时刻是事实；两者都显示，延迟本身是内容
        run = e.get("run_time") or ""
        run_cell = (f'<span class="tl-run">{T.icon("timer")}生成 {C.esc(run)}</span>'
                    if run and run[:5] != sched else "")

        # 链接文案 = 报告真实标题。无 html 时不点，挂 chip-pending 如实说明状态
        if html:
            head = (f'<a href="{depth}daily/{C.esc(date)}/{C.esc(slug)}.html">'
                    f'{C.esc(title)}<span class="go">{T.icon("arrow-right")}</span></a>')
        else:
            head = f'<span>{C.esc(title)}</span>'

        # P0：Σ / 评级缺失必须显式呈现为缺口，严禁回落 0.000 或借用他任务数值
        if sigma is None:
            quality = [f'<span class="tag gap">{T.icon("alert")}Σ 数据缺口</span>']
        else:
            quality = [sigma_badge(sigma)]
        if rating is None:
            quality.append(f'<span class="tag gap">{T.icon("minus")}评级未标注</span>')
        # 宽度口径不同 → Σ 不可跨时点比较，明确标注避免误读
        if not e.get("comparable", True):
            quality.append(f'<span class="tag tag-warn">{T.icon("alert")}{C.I18N["caliber_tag"]}</span>')

        meta = [stage_chip(e.get("stage") or m.get("data_stage"))]
        if not html:
            meta.append(f'<span class="chip chip-pending">{T.icon("file-text")}网页版待补齐</span>')
        if e.get("degraded"):
            # 数据源降级/缺口如实标出——不让降级产出看起来与正常产出一样
            meta.append(f'<span class="tag gap">{T.icon("alert-triangle")}数据源降级</span>')
        if rating is not None:
            meta.insert(0, rating_badge(rating))

        rows.append(f"""    <li class="tl-item" data-time="{C.esc(sched)}" data-slug="{C.esc(slug)}">
      <div class="tl-time">
        <span class="tl-sched"><span class="dot"></span>{C.esc(sched)}</span>
        {run_cell}
      </div>
      <div class="tl-body">
        <p class="tl-kicker">{T.icon(ico)}{C.esc(name)}</p>
        <h3 class="tl-title">{head}</h3>
        <p class="tl-sum">{C.conclusion_html(summary, T.icon) if conclusion
           else C.summary_html(summary, T.icon)}</p>
      </div>
      <div class="tl-meta">
        {"".join(meta)}
        {"".join(quality)}
      </div>
    </li>""")
    return "\n".join(rows)


def issue_block(m: dict, depth: str) -> str:
    """日期分组：日期 + 星期 + 当日评级 + Σ + 该日时间线。"""
    date = m.get("date", "")
    zh, en = C.dow_label(date)
    rating, sigma = m.get("rating"), m.get("sigma")
    sig = C.sigma_txt(sigma)
    sig_cell = (f'<span class="tl-sigma">{T.icon("sigma")}{C.esc(sig)}</span>' if sig
                else f'<span class="tag gap">{T.icon("alert")}Σ 数据缺口</span>')
    return f"""  <article class="issue dp-card" data-date="{C.esc(date)}" data-rating="{C.esc(rating or "")}" data-sigma="{C.sigma_raw(sigma)}">
    <div class="issue-head">
      <time class="issue-date" datetime="{C.esc(date)}">{C.esc(date)}</time>
      <span class="issue-dow">{C.esc(zh)} · {C.esc(en)}</span>
      <span class="spacer"></span>
      <span class="issue-summary">{rating_badge(rating, "lg") if rating else ""}{sig_cell}</span>
    </div>
    <ul class="tl">
{timeline(m, depth)}
    </ul>
  </article>"""


def kpi_row(items: list[tuple[str, str, str]]) -> str:
    """指标卡：hairline 分隔，数字等宽。items = [(图标键, 标签, 值HTML)]"""
    cells = "".join(
        f'<div class="kpi"><dt>{T.icon(ico)}{C.esc(label)}</dt><dd>{val}</dd></div>'
        for ico, label, val in items)
    return f'<dl class="kpi-row">{cells}</dl>'


def archive_strip(items: list[tuple[str, str]]) -> str:
    """首页归档数据条：真实统计，不是空洞 Hero。"""
    cells = "".join(f'<div><dt>{C.esc(k)}</dt><dd>{v}</dd></div>' for k, v in items)
    return f'<dl class="archive-strip">{cells}</dl>'