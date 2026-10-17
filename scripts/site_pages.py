#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""site_pages.py — 页面层（整页组合 + sitemap；feed 实现在 site_feed.py）

只做「把 site_render 的片段组装成整页」，不引入新的样式或数据判断。
依赖方向：site_pages → site_render / site_today / site_feed → site_content → site_theme（只向下）。
"""
from __future__ import annotations

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


# ---------------------------------------------------------------------------
# 订阅页
# ---------------------------------------------------------------------------
def subscribe(metas: list[dict], base_url: str) -> str:
    """订阅页：RSS 的产品化落点——地址 + 阅读器三步 + 订阅流内容说明。零 JS。

    为什么不做成裸 feed.xml 直出：读者点进来看到 XML 源码没有任何引导，
    订阅转化率为零。本页给人看，feed.xml 给阅读器读，两者分工。
    """
    feed_url = f"{base_url}feed.xml"
    latest = metas[0].get("date", "") if metas else ""
    docs = sum(len(m.get("entries", [])) for m in metas)
    task_rows = "".join(
        f'<tr><th scope="row" class="rowkey">{C.esc(name)}</th>'
        f'<td class="num">{C.esc(time)}</td>'
        f'<td>{C.esc(blurb)}</td></tr>'
        for name, time, blurb, _ico in C.TASK_META.values())
    body = f"""  <header class="page-head">
    <p class="eyebrow t-footnote">{T.icon("rss")}订阅 / Subscribe</p>
    <h1 class="t-title1">订阅每日更新</h1>
    <p class="lede t-callout">每个交易时点的研判归档后即可订阅。无需注册、免费、全文送达。</p>
    <p class="lede-en t-subhead">Subscribe to every trading-session verdict — no account, no cost, full text.</p>
    <p class="meta">{T.icon("calendar")}每交易日更新 · 已归档 {len(metas)} 期 / {docs} 篇{(' · 最近一期 ' + C.esc(latest)) if latest else ''}</p>
  </header>
  <section aria-labelledby="sec-url">
    <div class="sec-head">
      <h2 class="t-title3" id="sec-url">订阅地址</h2>
      <span class="spacer"></span>
      <span class="aside">{T.icon("rss")}RSS 2.0 · 全文</span>
    </div>
    <p class="sub-lede t-callout">在任意 RSS 阅读器中选择「添加订阅」，粘贴以下地址即可。使用支持 RSS 的浏览器访问本站时，地址栏的订阅图标也可一键添加。</p>
    <code class="sub-url">{C.esc(feed_url)}</code>
    <p class="sub-hint t-footnote">{T.icon("lightbulb")}订阅内容为研判全文，不是摘要——阅读器里即可读完，无需再点回网站。</p>
    <p class="sub-legal t-footnote">{T.icon("alert")}{C.esc(C.I18N["ai_notice"])}
      {C.esc(C.I18N["publisher_note"])}</p>
  </section>
  <section aria-labelledby="sec-how" style="margin-top:var(--space-16)">
    <div class="sec-head">
      <h2 class="t-title3" id="sec-how">三步完成订阅</h2>
      <span class="spacer"></span>
      <span class="aside">{T.icon("clock")}约一分钟</span>
    </div>
    <ol class="sub-steps">
      <li><b>复制订阅地址</b>——全选上方地址复制，或手动抄录。</li>
      <li><b>打开 RSS 阅读器</b>——Feedly、Inoreader、Reeder、NetNewsWire 等均可，浏览器亦可。</li>
      <li><b>添加订阅源</b>——粘贴地址并确认。之后每个交易时点的新研判会自动送达。</li>
    </ol>
  </section>
  <section aria-labelledby="sec-what" style="margin-top:var(--space-16)">
    <div class="sec-head">
      <h2 class="t-title3" id="sec-what">订阅流里每篇是什么</h2>
      <span class="spacer"></span>
      <span class="aside">{T.icon("timer")}每交易时点调度</span>
    </div>
    <div class="tbl-wrap">
      <table class="tbl">
        <caption>各任务产出按调度时点排序，全部进入同一订阅流</caption>
        <thead><tr>
          <th scope="col">任务</th><th scope="col" class="num">时点</th><th scope="col">内容</th>
        </tr></thead>
        <tbody>{task_rows}</tbody>
      </table>
    </div>
    <div class="btn-row" style="margin-top:var(--space-8)">
      <a class="btn btn-quiet" href="../index.html">{T.icon("archive")}浏览全部归档</a>
      <a class="btn btn-quiet" href="../methodology/">{T.icon("book")}研判方法论</a>
    </div>
  </section>"""
    # depth="../"：本页在 docs/subscribe/ 子目录，用 "./" 会让导航的
    # index.html 解析成 /subscribe/index.html（本页自己）、methodology/
    # 解析成 /subscribe/methodology/（404）——用户实锤「进订阅页后哪都点不动」
    return R.shell("订阅更新 · Subscribe | 每日市场脉搏",
                   "订阅每日市场脉搏：每交易时点的 A 股 / 基金研判全文 RSS，无需注册、免费。",
                   "../", body, "subscribe")


# ---------------------------------------------------------------------------
# 日期页
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 周 / 月归档页
# ---------------------------------------------------------------------------
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
    body = f"""  {_crumb(depth, crumb_tail)}
  <header class="page-head" style="padding-top:var(--space-6)">
    <h1 class="t-title1">{C.esc(title)}</h1>
    <p class="lede t-callout">{C.esc(subtitle)}</p>
    <p class="meta">{T.icon("layers")}{len(metas)} 期 · {docs} 篇产出</p>
  </header>
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


# ---------------------------------------------------------------------------
# feed.xml / sitemap.xml
# ---------------------------------------------------------------------------
def feed(metas: list[dict], base_url: str) -> str:
    """RSS 2.0 条目级（P-2）。实现迁至 site_feed.py（单文件 ≤300 行纪律），
    此处保留委托：build_site.py 的调用点与 SITE_FILE 协议不变。"""
    import site_feed
    return site_feed.feed(metas, base_url)


def json_feed(metas: list[dict], base_url: str) -> str:
    """JSON Feed（ARCH-R6-MINIPROGRAM §3.1）：小程序 / PWA 的机器可读数据源。

    与 RSS 的分工：feed.xml 给人看（订阅器），feed.json 给机器读（客户端）。
    数据全部来自 entries.json（发布层唯一时间线事实源），零编造。

    设计取舍（待架构师评审）：**不含 detail 页数组**——详情内容量大且已是
    静态 HTML，客户端按需拉页面即可；JSON 只承载「列表 + 结论」这一层，
    避免同一份内容维护两遍（双份即漂移）。
    """
    import json

    def entry_json(e: dict) -> dict:
        # 降级态不得输出方向值（架构师 A-04）：客户端会二次解读 rating/sigma，
        # 若此处仍带「进攻 +0.510」，第三方应用会拿着不可信数据算出动作。
        degraded = bool(e.get("degraded"))
        gap = degraded or e.get("sigma") is None
        return {
            "slug": e.get("slug"),
            "name": e.get("name"),
            "time": e.get("time"),
            "runTime": e.get("run_time"),
            "title": e.get("title"),
            "conclusion": e.get("conclusion"),
            "rating": None if degraded else e.get("rating"),
            "sigma": None if degraded else e.get("sigma"),
            "stage": e.get("stage"),
            "degraded": degraded,
            "dataGap": gap,
            "comparable": False if degraded else bool(e.get("comparable", False)),
            "url": f"{base_url}daily/{e.get('_date', '')}/{e.get('slug')}.html"
                   if e.get("html") else None,
        }

    days = []
    for m in metas:
        date = m.get("date", "")
        entries = [dict(e, _date=date) for e in m.get("entries", [])]
        days.append({
            "date": date,
            "title": m.get("title_zh"),
            "summary": m.get("summary_zh"),
            "rating": m.get("rating"),
            "sigma": m.get("sigma"),
            "stage": m.get("data_stage"),
            "entryCount": len(entries),
            "url": f"{base_url}daily/{date}/",
            "entries": [entry_json(e) for e in entries],
        })

    payload = {
        "version": "1.0",
        "generator": "daily-decision-engine",
        "site": {"title": C.I18N["site_title"], "url": base_url},
        "disclaimer": C.I18N["disclaimer_zh"],
        "ratingScale": ["进攻", "均衡", "信号矛盾", "防守", "回避"],
        "stageScale": [{"key": k, "label": v[0], "labelEn": v[1]}
                       for k, v in C.STAGE_MAP.items()],
        "days": days,
    }
    return json.dumps(payload, ensure_ascii=False, indent=1) + "\n"


def sitemap(metas: list[dict], base_url: str, extras: list[str]) -> str:
    urls = [base_url] + [f"{base_url}daily/{m.get('date', '')}/" for m in metas]
    urls += [base_url + e for e in extras]
    lines = "\n".join(f"  <url><loc>{C.esc(u)}</loc></url>" for u in urls)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{lines}
</urlset>
"""