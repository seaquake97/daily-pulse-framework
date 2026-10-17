#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""site_today.py — 首页「今日研判」区块（产品债 P-1 的落点）

为什么单独成模块（而非塞进 site_render / site_pages）：那两个文件已逼近
「Python 单文件 ≤300 行」硬上限，本区块是自包含的仪表盘片段（领域判断全在
site_content），独立成文件让两个既有文件的增量各 ≤10 行。依赖方向与
site_render 同级：site_today → site_content / site_render / site_theme（只向下）。

产品契约（BACKLOG-MASTER P-1，2026-10-17 用户实测）：
  · 首页必须回答「今天该做什么」——展示**最近一个有产出的交易日**的全部条目，
    每条 = 任务名 + 时点 + 评级徽章 + Σ 值 + 结论摘要 + 详情页链接；
  · 结论摘要一律直接用 entries.json 已契约化的 conclusion 字段（三段式，
    PC-2），不在本层拼文案；
  · 降级条目（degraded=true）不渲染评级徽章与可执行动作（PC-5 / PC-24），
    徽章层中性化；Σ 为 None 显示「—」，严禁格式化 0.000（PC-12）；
  · 排版：桌面容器内纵排、移动端 390px 单列不溢出（零 JS，纯原生语义）。
"""
from __future__ import annotations

import site_content as C
import site_render as R
import site_theme as T


def _entry_row(e: dict, date: str, depth: str) -> str:
    """单条目行：时点 + 任务名（链接）+ 状态徽章 + Σ + 结论三段式。"""
    slug = e.get("slug", "")
    name, default_time, blurb, _ico = C.TASK_META.get(slug, (slug, "—", "", "file-text"))
    sched = e.get("time") or default_time
    rating, sigma = e.get("rating"), e.get("sigma")
    degraded = bool(e.get("degraded"))

    # 单一状态药丸原则（与时间线同范式）：降级优先 → 评级 → 数据缺口，
    # 绝不堆叠同义标签。降级态不出现 rating-* 徽章（PC-5 的页面层守护）。
    if degraded:
        badge = f'<span class="tag tag-degraded">{T.icon("alert-triangle")}数据降级</span>'
    elif rating is not None:
        badge = R.rating_badge(rating)
    else:
        badge = f'<span class="tag gap">{T.icon("minus")}数据缺口</span>'

    # Σ：None → 「—」（PC-12：禁 0.000 兜底；降级态 sigma 已在数据层置 null）
    sigma_cell = (R.sigma_badge(sigma) if C.sigma_txt(sigma)
                  else '<span class="tl-sigma">—</span>')

    # 结论摘要：直接用契约化 conclusion 三段式；缺失才回落 summary / 任务说明
    conclusion = e.get("conclusion")
    summary = conclusion if conclusion else (e.get("summary") or blurb)
    sum_html = (C.conclusion_html(summary, T.icon) if conclusion
                else C.summary_html(summary, T.icon))

    html = e.get("html")
    if html:
        title = (f'<a href="{depth}daily/{C.esc(date)}/{C.esc(html)}">'
                 f'{C.esc(name)}<span class="go">{T.icon("arrow-right")}</span></a>')
    else:
        title = f'<span>{C.esc(name)}</span>'
    # 无详情页不造死链：挂「待补齐」芯片（与时间线同范式），绝不给 404
    pending = (f'<span class="chip chip-pending">{T.icon("file-text")}待补齐</span>'
               if not html else "")

    return f"""    <li class="today-item">
      <div class="today-head">
        <span class="today-time">{C.esc(sched)}</span>
        <h3 class="tl-title">{title}</h3>
        <span class="today-badges">{badge}{sigma_cell}{pending}</span>
      </div>
      <p class="tl-sum">{sum_html}</p>
    </li>"""


def today_section(metas: list[dict], depth: str = "./") -> str:
    """今日研判 section：最近一个有产出的交易日的全部条目纵排。

    无任何有产出的日期时返回空串——首页退化为纯归档，不渲染空区块
    （空数据不做补零，避免生成虚假结论）。
    """
    latest = next((m for m in metas if m.get("entries")), None)
    if not latest:
        return ""
    date = latest.get("date", "")
    zh, en = C.dow_label(date)
    entries = sorted(latest.get("entries", []), key=lambda e: e.get("time") or "99:99")
    stage_zh = C.stage_of(latest.get("data_stage"))[0]
    rows = "\n".join(_entry_row(e, date, depth) for e in entries)
    return f"""  <section aria-labelledby="sec-today" style="margin-top:var(--space-16)">
    <div class="sec-head">
      <h2 class="t-title2" id="sec-today">今日研判</h2>
      <span class="spacer"></span>
      <span class="aside">{T.icon("calendar")}{C.esc(date)} {C.esc(zh)} · {len(entries)} 项产出 · {C.esc(stage_zh)}</span>
    </div>
    <p class="sec-note t-footnote">{T.icon("scale")}{C.esc(C.I18N["caliber_note"])}</p>
    <ol class="today-list">
{rows}
    </ol>
    <div class="btn-row" style="margin-top:var(--space-6)">
      <a class="btn btn-quiet" href="{depth}daily/{C.esc(date)}/">查看当日全部产出{T.icon("arrow-right")}</a>
    </div>
  </section>"""
