#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""site_pages.py — 页面层（整页组合 + sitemap；feed 实现在 site_feed.py）

只做「把 site_render 的片段组装成整页」，不引入新的样式或数据判断。
依赖方向：site_pages → site_render / site_today / site_feed / site_aggregate → site_content → site_theme（只向下）。
"""
from __future__ import annotations

import site_aggregate as AG
import site_content as C
import site_render as R
import site_theme as T
import site_today as TD


def _crumb(depth: str, tail: str) -> str:
    return (f'<nav class="crumb" aria-label="面包屑">'
            f'<a href="{depth}index.html">{T.icon("chevron-right")}全部归档</a>'
            f'<span class="sep" aria-hidden="true">/</span>'
            f'<span aria-current="page">{C.esc(tail)}</span></nav>')


# ---------------------------------------------------------------------------
# 首页
# ---------------------------------------------------------------------------
def home(metas: list[dict]) -> str:
    last = metas[0] if metas else {}
    date = last.get("date", "")
    zh, en = C.dow_label(date)
    rating, sigma = last.get("rating"), last.get("sigma")
    docs = sum(len(m.get("entries", [])) for m in metas)
    sig = C.sigma_txt(sigma)

    strip = R.archive_strip([
        ("已归档交易日", f'{len(metas)}<span class="u">期</span>'),
        ("研判产出", f'{docs}<span class="u">篇</span>'),
        ("最近一期 Σ 评级", R.rating_badge(rating) if rating
         else f'<span class="txt">未标注</span>'),
        ("最近一期 Σ 值", f'{C.esc(sig)}' if sig
         else f'<span class="txt">数据缺口</span>'),
        ("数据源", '<span class="txt">腾讯自选股 MCP</span>'),
    ])

    issues = "\n".join(R.issue_block(m, "./", default_open=(i == 0)) for i, m in enumerate(metas)) or (
        f'  <div class="empty">{T.icon("inbox", "ic-24")}'
        '<h3>暂无归档数据</h3><p>尚无已入库的交易日。空数据不做补零，避免生成虚假结论。</p>'
        f'<div class="btn-row" style="justify-content:center">'
        f'<a class="btn btn-quiet" href="methodology/">{T.icon("book")}查看研判方法论</a>'
        f'<a class="btn btn-quiet" href="subscribe/">{T.icon("rss")}订阅更新</a>'
        '</div></div>')

    body = f"""  <header class="page-head">
    <p class="eyebrow t-footnote">{T.icon("target")}数据驱动的 A 股 / 基金每日研判档案</p>
    <h1 class="t-title1">每交易日的判断，<br>留一条可回溯的轨迹。</h1>
    <p class="lede t-callout">同一份数据必然得出同一结论。结论可复现、可审计 —— 这里存的不是行情，是判断本身。</p>
    <p class="lede-en t-subhead">Same data always yields the same verdict. Verdicts are reproducible and auditable — this archive stores judgments, not quotes.</p>
    <p class="meta">{T.icon("clock")}{len(metas)} 期归档
      {f'· 最近更新 {C.esc(date)}（{C.esc(zh)} · {C.esc(en)}）' if date else ''}</p>
  </header>
  {strip}
{TD.today_section(metas, "./")}
  <section aria-labelledby="sec-timeline" style="margin-top:var(--space-16)">
    <div class="sec-head">
      <h2 class="t-title2" id="sec-timeline">判断轨迹</h2>
      <span class="spacer"></span>
      <span class="aside">{T.icon("timer")}每交易时点调度 · 按调度时点排序</span>
    </div>
    <p class="sec-note t-footnote">{T.icon("scale")}{C.esc(C.I18N["caliber_note"])}</p>
{issues}
  </section>"""
    return R.shell(C.I18N["site_title"],
                   "数据驱动的 A 股/基金每日研判档案 · Data-driven daily A-share & fund research archive",
                   "./", body, "index")


# 订阅页 / JSON Feed 薄委托（实现已外迁，build_site 调用点与 SITE_FILE 协议不变）
def subscribe(metas: list[dict], base_url: str) -> str:
    """订阅页实现迁至 site_subscribe.py（单文件 ≤300 行纪律）。"""
    import site_subscribe
    return site_subscribe.subscribe(metas, base_url)


def json_feed(metas: list[dict], base_url: str) -> str:
    """JSON Feed 实现迁至 site_feed.py（与 feed.xml 同属机器可读馈送）。"""
    import site_feed
    return site_feed.json_feed(metas, base_url)


# 日期页
def _verdict_overview(entries: list[dict]) -> str:
    """当日结论速览：按时点分组横排 Σ，让「同口径可比、跨口径不可比」结构可见。

    产品判断（2026-10-16，用户实锤「一眼看不出结论」的延伸）：五个任务的
    Σ 落在竞价/盘中/收盘三个不同数据时点上，纵向排成时间线会诱导读者把
    +0.510（竞价）与 -0.011（尾盘）直接相比——而这是口径陷阱。本块把
    同时点的任务并排、时点之间显式分组，既给"当日结论一览"，又不制造
    虚假可比性。数字全部来自 entries.json，无任何编造。
    """
    groups: dict[str, list[dict]] = {}
    for e in entries:
        stage = e.get("stage") or "close"
        groups.setdefault(stage, []).append(e)
    order = [s for s in ("pre_open", "intraday", "close") if s in groups]
    order += [s for s in groups if s not in order]
    blocks = []
    for stage in order:
        zh, en, variant, ico = C.stage_of(stage)
        cells = []
        for e in groups[stage]:
            name = C.TASK_META.get(e.get("slug", ""), (e.get("slug", ""),))[0]
            sig = C.sigma_txt(e.get("sigma"))
            rating = e.get("rating")
            badge = (R.rating_badge(rating) if rating
                     else f'<span class="tag gap">{T.icon("minus")}未标注</span>')
            sig_cell = (f'<span class="tl-sigma">{T.icon("sigma")}{C.esc(sig)}</span>'
                        if sig else f'<span class="tag gap">{T.icon("alert")}Σ 数据缺口</span>')
            cells.append(f'<div class="ov-cell"><p class="ov-name">{C.esc(name)}</p>'
                         f'<p class="ov-badges">{badge}{sig_cell}</p></div>')
        blocks.append(f"""    <div class="ov-group">
      <p class="ov-stage"><span class="chip {variant}">{T.icon(ico)}{C.esc(zh)} / {C.esc(en)}</span>
        <span class="ov-note">同时点任务可比</span></p>
      <div class="ov-cells">{''.join(cells)}</div>
    </div>""")
    if len(groups) > 1:
        blocks.append(
            '    <p class="ov-caution">' + T.icon("alert") +
            '各时点数据口径不同（竞价快照 / 盘中实时 / 收盘定格），'
            'Σ 跨时点不可直接比较，请以同时点内的对比为准。</p>')
    return "".join(blocks)


def day(m: dict) -> str:
    date = m.get("date", "")
    zh, en = C.dow_label(date)
    entries = m.get("entries", [])
    stage_zh, stage_en, _, stage_ico = C.stage_of(m.get("data_stage"))
    rating, sigma = m.get("rating"), m.get("sigma")
    sig = C.sigma_txt(sigma)
    gap_n = sum(1 for e in entries if e.get("sigma") is None)
    warn_n = sum(1 for e in entries if not e.get("comparable", True))

    kpis = R.kpi_row([
        ("sigma", "Σ 综合评分", f'<span class="num">{C.esc(sig)}</span>' if sig
         else '<span class="flat">数据缺口</span>'),
        ("scale", "Σ 评级", R.rating_badge(rating) if rating else '<span class="flat">未标注</span>'),
        (stage_ico, "数据时点", f'<span class="num" style="font-family:var(--font-text)">'
                                f'{C.esc(stage_zh)}</span>'),
        ("inbox", "产出条目", f'<span class="num">{len(entries)}</span><span class="u">项</span>'),
        ("alert", "Σ 数据缺口", f'<span class="num">{gap_n}</span><span class="u">项</span>'),
        ("alert", "口径待标注", f'<span class="num">{warn_n}</span><span class="u">项</span>'),
    ])

    body = f"""  {_crumb("../../", date)}
  <header class="page-head" style="padding-top:var(--space-6)">
    <p class="eyebrow t-footnote">{T.icon("calendar")}交易日 · {C.esc(zh)}</p>
    <h1 class="t-title1 num">{C.esc(date)}<span class="sub">{C.esc(zh)} · {C.esc(en)}</span></h1>
    <p class="lede t-callout">{C.esc(m.get("summary_zh", ""))}</p>
    <p class="lede-en t-subhead">{C.esc(m.get("summary_en", ""))}</p>
  </header>
  {kpis}
  <section aria-labelledby="sec-ov" style="margin-top:var(--space-12)">
    <div class="sec-head">
      <h2 class="t-title3" id="sec-ov">当日结论速览</h2>
      <span class="spacer"></span>
      <span class="aside">{T.icon("scale")}按时点分组 · 同时点内可比</span>
    </div>
    {_verdict_overview(entries)}
  </section>
  <section aria-labelledby="sec-day-tl" style="margin-top:var(--space-12)">
    <div class="sec-head">
      <h2 class="t-title3" id="sec-day-tl">当日产出时间线</h2>
      <span class="spacer"></span>
      <span class="aside">{T.icon("timer")}调度时点 → 实际生成时刻</span>
    </div>
    <p class="sec-note t-footnote">{T.icon("scale")}{C.esc(C.I18N["caliber_note"])}</p>
    <ul class="tl">
{R.timeline(m, "../../")}
    </ul>
  </section>"""
    return R.shell(f"{date} 每日市场脉搏 · Daily Market Pulse",
                   m.get("summary_zh", ""), "../../", body)


# 周 / 月归档页（总览索引 + 周期页；周期聚合在 site_aggregate.py）
def _trajectory_table(metas: list[dict]) -> str:
    """评级轨迹总览：全部来自 meta.json 真实值，无任何虚构数字。"""
    rows = []
    for m in metas:
        date = m.get("date", "")
        zh, _en = C.dow_label(date)
        rating, sigma = m.get("rating"), m.get("sigma")
        sig = C.sigma_txt(sigma)
        badge = R.rating_badge(rating) if rating else '<span class="flat">未标注</span>'
        sig_cell = C.esc(sig) if sig else "—"
        rows.append(
            f'<tr><th scope="row" class="rowkey num">{C.esc(date)}'
            f'<span class="rowkey-zh">{C.esc(zh)}</span></th>'
            f'<td>{badge}</td>'
            f'<td class="num">{sig_cell}</td>'
            f'<td class="num">{len(m.get("entries", []))}</td>'
            f'<td class="num">{C.esc(C.stage_of(m.get("data_stage"))[0])}</td></tr>')
    return f"""    <div class="tbl-wrap">
      <table class="tbl">
        <caption>按交易日汇总的 Σ 评级与 Σ 值，全部取自 meta.json 原始记录</caption>
        <thead><tr>
          <th scope="col">交易日</th><th scope="col">Σ 评级</th>
          <th scope="col" class="num">Σ 值</th><th scope="col" class="num">产出</th>
          <th scope="col">数据时点</th>
        </tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </div>"""


def archive_index(kind: str, groups: list[tuple[str, str]]) -> str:
    """周报 / 月报总览页（PM 缺陷 P0-1：导航指向 weekly/ 但该页从未生成 → 线上 404）。

    产品判断：导航里既然有「周报 / 月报」两个入口，就得真的有这两个页面。
    早前只生成 `weekly/<YYYY-Www>/` 具体周页，却让导航指向 `weekly/`，
    结果 5 个页面 × 2 入口 = 全站 80 处死链、线上 404。
    与其把导航入口撤掉（信息更少），不如补齐总览页——它是「有哪些周报可读」
    的索引页，本身就该存在。
    """
    zh, en = (("周报", "Weekly") if kind == "weekly" else ("月报", "Monthly"))
    rows = "".join(
        f'    <li><a href="./{key}/">{C.esc(label)}</a></li>' for key, label in groups)
    body = f"""  <header class="page-head">
    <p class="eyebrow t-footnote">{T.icon("archive")}{C.esc(zh)} / {C.esc(en)}</p>
    <h1 class="t-title1">{C.esc(zh)}归档</h1>
    <p class="lede">按{zh[:-1] if zh.endswith('报') else zh}期浏览全部历史研判，共 {len(groups)} 期。</p>
  </header>
  <section aria-labelledby="sec-list">
    <div class="sec-head">
      <h2 class="t-title3" id="sec-list">全部{zh}期</h2>
      <span class="spacer"></span>
      <span class="aside">{T.icon("calendar")}最近在前</span>
    </div>
    <ul class="archive-list">
{rows}
    </ul>
  </section>"""
    current = "weekly" if kind == "weekly" else "monthly"
    # depth="../"：本页在 docs/weekly/（或 monthly/）子目录，
    # 用 "" 会让导航的 index.html 解析成 /weekly/index.html（本页自己）。
    return R.shell(f"{zh}归档 · 每日市场脉搏",
                   f"按期浏览全部{en}归档，共 {len(groups)} 期。",
                   "../", body, current)


def group(title: str, subtitle: str, metas: list[dict], depth: str, current: str,
          crumb_tail: str) -> str:
    docs = sum(len(m.get("entries", [])) for m in metas)
    issues = "\n".join(R.issue_block(m, depth, default_open=(i == 0)) for i, m in enumerate(metas)) or (
        f'  <div class="empty">{T.icon("inbox", "ic-24")}<h3>暂无归档数据</h3>'
        '<p>该区间尚无已入库的交易日。</p></div>')
    # 周/月真聚合（P-4/F-3）：同一套渲染函数，粒度参数区分周/月；
    # 置于页头之后、评级轨迹总览之前——先给周期结论，再给逐日明细。
    aggregate = AG.section(metas, "week" if current == "weekly" else "month")
    body = f"""  {_crumb(depth, crumb_tail)}
  <header class="page-head" style="padding-top:var(--space-6)">
    <h1 class="t-title1">{C.esc(title)}</h1>
    <p class="lede t-callout">{C.esc(subtitle)}</p>
    <p class="meta">{T.icon("layers")}{len(metas)} 期 · {docs} 篇产出</p>
  </header>
{aggregate}
  <section aria-labelledby="sec-traj">
    <div class="sec-head">
      <h2 class="t-title3" id="sec-traj">评级轨迹总览</h2>
      <span class="spacer"></span>
      <span class="aside">全部数字等宽对齐，Σ 值不跨口径直接比较</span>
    </div>
{_trajectory_table(metas)}
  </section>
  <section aria-labelledby="sec-tl" style="margin-top:var(--space-16)">
    <div class="sec-head"><h2 class="t-title3" id="sec-tl">逐日判断轨迹</h2></div>
{issues}
  </section>"""
    return R.shell(f"{title} · 每日市场脉搏", subtitle, depth, body, current)


# feed.xml / sitemap.xml（均为薄委托或纯组装）
def feed(metas: list[dict], base_url: str) -> str:
    """RSS 2.0 条目级（P-2）。实现迁至 site_feed.py（单文件 ≤300 行纪律），
    此处保留委托：build_site.py 的调用点与 SITE_FILE 协议不变。"""
    import site_feed
    return site_feed.feed(metas, base_url)


def sitemap(metas: list[dict], base_url: str, extras: list[str]) -> str:
    urls = [base_url] + [f"{base_url}daily/{m.get('date', '')}/" for m in metas]
    urls += [base_url + e for e in extras]
    lines = "\n".join(f"  <url><loc>{C.esc(u)}</loc></url>" for u in urls)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{lines}
</urlset>
"""