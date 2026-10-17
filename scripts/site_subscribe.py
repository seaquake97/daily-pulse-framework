#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""site_subscribe.py — 订阅页（RSS 的产品化落点，产品债 P-2 的页面侧）

为什么单独成模块：订阅页是「给人看的 RSS 说明页」（地址 + 阅读器三步 +
订阅流内容说明），与站点结构页（site_pages）职责不同；2026-10-17 随
P-4 聚合改造一并迁出 site_pages.py（单文件 ≤300 行纪律），
site_pages.subscribe() 保留薄委托（build_site 调用点不变）。

为什么不做成裸 feed.xml 直出：读者点进来看到 XML 源码没有任何引导，
订阅转化率为零。本页给人看，feed.xml 给阅读器读，两者分工。

依赖只向下：site_subscribe → site_content / site_render / site_theme。
"""
from __future__ import annotations

import site_content as C
import site_render as R
import site_theme as T


def subscribe(metas: list[dict], base_url: str) -> str:
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
