#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""site_feed.py — RSS 2.0 条目级 feed（产品债 P-2 的落点）

为什么单独成模块：feed 从「日期级」重构为「条目级」后逻辑量翻倍
（每条目：标题/链接/guid/描述/时间五要素 + 降级态防护），site_pages.py
已超 300 行硬上限，独立成文件；site_pages.feed() 保留薄委托（build_site
调用点不变）。依赖只向下：site_feed → site_content。

产品契约（BACKLOG-MASTER P-2，2026-10-17 用户实测）：
  · 订阅者要拿到「今天该做什么」——每个任务条目一个 <item>，
    标题 = 「任务名 · 日期」，description = 该条目契约化 conclusion；
  · 降级态必须带降级文案，绝不带评级 / Σ 数值（PC-5 的机器消费侧同守：
    entries.json / feed.json 会被第三方直接消费）；
  · guid 用「日期/slug」稳定标识（重播不漂移）；link 用详情页相对 URL
    （feed 位于 docs/ 根，相对解析即详情页，且不随 --base-url 漂移）；
  · pubDate 取「日期当天 00:00 +0800」固定值，禁用当前时刻（发布幂等铁律）。
"""
from __future__ import annotations

import re
from datetime import date as _date

import site_content as C

# RFC 822 要求英文星期/月份名。strftime 的 %a/%b 随平台 locale 变
# （中文环境输出「周五」直接破坏 RSS 合规且字节不稳定）——固定名表。
_DOW = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# 发布幂等：固定 +0800（UTC+8，数据时点所在时区），不用当前时刻、不用 UTC 转换
_PUB_TZ = "+0800"
# 降级态兜底文案：与 publish_to_github.py:427（entries.json 的生产侧）同源。
# 仅在 conclusion 缺失时启用；启用即替换，绝不与可能残留的方向值拼接。
_DEGRADED_TEXT = ("数据源降级 · 本轮结论不适用｜"
                  "取数非实时（详见正文数据源说明），标准动作暂不执行")
# 降级态方向值残留模式：Σ 带数字 / 五档评级 + 间隔号（PC-5 机检）
_DIRECTION_RE = re.compile(r"Σ[+\-−]?\d|(?:进攻|均衡|信号矛盾|防守|回避)\s*·")


def _pub_date(date_str: str) -> str:
    """日期 → RFC 822 固定值（当天 00:00 +0800）。非法日期回退纪元值，
    不静默丢条目（丢条目 = 订阅者少看一天，比时间戳难看更糟）。"""
    try:
        y, m, d = (int(x) for x in date_str.split("-"))
        wd = _date(y, m, d).weekday()
        return f"{_DOW[wd]}, {d:02d} {_MON[m - 1]} {y} 00:00:00 {_PUB_TZ}"
    except (ValueError, TypeError):
        return f"Mon, 01 Jan 1970 00:00:00 {_PUB_TZ}"


def _description(e: dict) -> str:
    """条目描述：优先契约化 conclusion；非降级态缺失才回落 summary / 任务说明。

    降级态双保险：① conclusion 缺失 → 用降级兜底文案；② conclusion 命中
    方向值模式（数据层被污染的极端情况）→ 同样替换。降级态绝不外溢评级/Σ。
    """
    degraded = bool(e.get("degraded"))
    text = e.get("conclusion") or ""
    if degraded:
        if not text.strip() or _DIRECTION_RE.search(text):
            text = _DEGRADED_TEXT
    else:
        if not text.strip():
            slug = e.get("slug", "")
            blurb = C.TASK_META.get(slug, ("", "", "", ""))[2]
            text = e.get("summary") or blurb
    # AI 生成标识随内容走（订阅页明示的合规要求：阅读器里也看得见）
    return f"{text}。{C.I18N['ai_notice']}"


def _item(date: str, e: dict) -> str:
    """单个 <item>：标题（任务名 · 日期）/ 相对链接 / 稳定 guid / 描述 / 固定 pubDate。"""
    slug = e.get("slug", "")
    name, _t, _b, _i = C.TASK_META.get(slug, (e.get("name") or slug,))
    html = e.get("html")
    link = f"daily/{date}/{html}" if html else f"daily/{date}/"
    guid = f"{date}/{slug}"
    return f"""  <item>
    <title>{C.esc(name)} · {C.esc(date)}</title>
    <link>{C.esc(link)}</link>
    <guid isPermaLink="false">{C.esc(guid)}</guid>
    <description>{C.esc(_description(e))}</description>
    <pubDate>{_pub_date(date)}</pubDate>
  </item>"""


def feed(metas: list[dict], base_url: str) -> str:
    """RSS 2.0 条目级：每个任务条目一个 <item>，channel 级信息原样保留。

    base_url 只用于 channel 的 <link>（站点地址）；条目链接一律相对
    （feed 与被链页面同站同根，相对解析稳定且不随部署域名漂移）。
    """
    items: list[str] = []
    for m in metas:
        date = m.get("date", "")
        for e in sorted(m.get("entries", []), key=lambda x: x.get("time") or "99:99"):
            items.append(_item(date, e))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{C.esc(C.I18N['site_title'])}</title>
  <link>{C.esc(base_url)}</link>
  <description>数据驱动的 A 股/基金每日研判档案 / Data-driven daily research archive</description>
  <language>zh-CN</language>
{chr(10).join(items)}
</channel>
</rss>
"""
