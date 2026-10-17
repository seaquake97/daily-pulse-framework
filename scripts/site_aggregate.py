#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""site_aggregate.py — 周/月归档页真聚合（产品债 P-4 / 框架债 F-3 的落点）

周报/月报原是全量日数据的两个标签壳（实测文本相似度 0.9937，仅标题词不同），
导航入口给人「有周月维度」的假象。本模块按周期粒度实算聚合指标并渲染
「本周聚合 / 本月聚合」区块，由 site_pages.group() 调用；原有全量日轨迹表保留，聚合是新增不是替换。

口径（全部由周期内各日期 meta.json + entries.json 实算，禁止写死）：
  · 评级迁移次数：相邻交易日按日期升序比对 rating，档位变化计 1 次，
    rating 为 None 的日期跳过且不计迁移；
  · Σ 变化方向：周期内首个有效 Σ → 最近一个有效 Σ 的差值符号与数值；
  · 防守天数：rating ∈ {防守, 回避} 的日期数，信号矛盾单列；
  · 产出条目数：entries 总数；
  · 无评级/无数据的维度呈现「数据缺口」，绝不编造（0 是事实，不是缺口）；
  · 存在 comparable=false 时加一行口径提示（复用 .tag gap / .tag-warn 视觉）。
依赖只向下：site_aggregate → site_content / site_render / site_theme。
"""
from __future__ import annotations

import site_content as C
import site_render as R
import site_theme as T

_DEFENSIVE = ("防守", "回避")
_CONFLICT = "信号矛盾"
_GAP = '<span class="flat">数据缺口</span>'


def compute(metas: list[dict]) -> dict:
    """实算周期聚合指标（纯计算，不碰 DOM）。返回审计链，渲染层不编造。

    Σ 有效性判定复用 C.sigma_txt 的真值——与页面显示同一把尺，
    杜绝「聚合算得出来、页面显示数据缺口」的静默分裂。
    """
    days = sorted((m for m in metas if m.get("date")), key=lambda m: m["date"])
    rated = [(m["date"], m["rating"]) for m in days if m.get("rating")]
    moves = [(a[0], b[0]) for a, b in zip(rated, rated[1:]) if a[1] != b[1]]
    sigmas = [(m["date"], m["sigma"]) for m in days if C.sigma_txt(m.get("sigma"))]
    return {
        "days": days, "rated": rated, "moves": moves,
        # 不足 2 个有效评级 → 无可比对相邻对，迁移次数无数据（不是 0）
        "migrations": len(moves) if len(rated) >= 2 else None,
        "sigmas": sigmas,
        "delta": round(sigmas[-1][1] - sigmas[0][1], 3) if len(sigmas) >= 2 else None,
        # 全周期无评级 → 防守/矛盾天数无数据；有评级时 0 是事实
        "defensive": sum(1 for _, r in rated if r in _DEFENSIVE) if rated else None,
        "conflict": sum(1 for _, r in rated if r == _CONFLICT) if rated else None,
        "entries": sum(len(m.get("entries") or []) for m in days),
        "incomparable": sum(1 for m in days for e in (m.get("entries") or [])
                            if e.get("comparable") is False),
    }


def _cell(n: int | None, unit: str) -> str:
    """计数指标单元格：None（无数据）→ 数据缺口；数字一律 tabular-nums。"""
    return (f'<span class="num">{n}</span><span class="u">{unit}</span>'
            if n is not None else _GAP)


def _contrib_rows(agg: dict) -> str:
    """逐日贡献审计表行：迁移判定、Σ 值、产出与口径受限计数全部实算。"""
    rated_dates = {d for d, _ in agg["rated"]}
    first_rated = agg["rated"][0][0] if agg["rated"] else ""
    move_cur = {cur for _, cur in agg["moves"]}
    rows = []
    for m in agg["days"]:
        date, rating = m.get("date", ""), m.get("rating")
        entries = m.get("entries") or []
        moved = ("跳过" if date not in rated_dates else
                 "—" if date == first_rated else
                 "是" if date in move_cur else "否")
        zh, _en = C.dow_label(date)
        badge = R.rating_badge(rating) if rating else '<span class="flat">未标注</span>'
        rows.append(
            f'<tr><th scope="row" class="rowkey num">{C.esc(date)}'
            f'<span class="rowkey-zh">{C.esc(zh)}</span></th>'
            f'<td>{badge}</td>'
            f'<td class="num">{C.sigma_txt(m.get("sigma")) or "—"}</td>'
            f'<td class="num">{len(entries)}</td>'
            f'<td class="num">{sum(1 for e in entries if e.get("comparable") is False)}</td>'
            f'<td class="num">{moved}</td></tr>')
    return "".join(rows)


def _notes(agg: dict, scope: str, d, word: str) -> list[str]:
    """口径提示行：Σ 变化首末链 + 评级覆盖链（有/无评级日期全部列出）。"""
    if len(agg["sigmas"]) >= 2:
        (d0, s0), (d1, s1) = agg["sigmas"][0], agg["sigmas"][-1]
        head = (f"Σ 变化口径：{d0}（{C.sigma_txt(s0)}）→ {d1}（{C.sigma_txt(s1)}）= {d:+.3f}（{word}）")
    else:
        head = ("Σ 变化口径：本周期无有效 Σ，方向不可计算" if not agg["sigmas"]
                else f"Σ 变化口径：仅 1 个有效 Σ（{agg['sigmas'][0][0]}），方向不可计算")
    unrated = [m["date"] for m in agg["days"] if not m.get("rating")]
    rated_txt = " · ".join(f"{d0} {r}" for d0, r in agg["rated"]) or "无"
    tail = (f"{scope}共 {len(agg['days'])} 个交易日：{len(agg['rated'])} 个有评级"
            f"（{rated_txt}），{len(unrated)} 个无评级（{' · '.join(unrated) or '无'}），"
            f"无评级日期跳过且不计迁移")
    return [head, tail]


def section(metas: list[dict], granularity: str) -> str:
    """渲染聚合区块。granularity ∈ {week, month}：同一套函数，粒度参数区分周/月。"""
    agg = compute(metas)
    scope = "本周" if granularity == "week" else "本月"
    d = agg["delta"]
    # None 先行：条件表达式右结合，先判空再比值，避免 None > 0 静默崩溃
    word = "" if d is None else ("上升" if d > 0 else "下降" if d < 0 else "持平")
    d_ico = {"上升": "trending-up", "下降": "trending-down"}.get(word, "minus")
    direction = (f'<span class="num">{d:+.3f}</span><span class="u">{word}</span>' if d is not None else _GAP)

    kpis = R.kpi_row([
        ("repeat", f"{scope}评级迁移次数", _cell(agg["migrations"], "次")),
        (d_ico, f"{scope}Σ 变化方向", direction),
        ("shield", f"{scope}防守天数", _cell(agg["defensive"], "天")),
        ("shuffle", f"{scope}信号矛盾天数", _cell(agg["conflict"], "天")),
        ("inbox", f"{scope}产出条目数", _cell(agg["entries"], "项")),
    ])
    # 口径提示行用普通段落而非 .sec-note（flex）：tag-warn 徽章 + 后续文本必须在
    # 窄屏换行到徽章下方，flex 行会撑出页面横滚（320px 实测 345 > 320）。
    note_style = 'margin-top:var(--space-3);max-width:var(--container-prose)'
    note_html = "".join(
        f'    <p class="t-footnote" style="{note_style}">{T.icon("scale")}{n}。</p>\n'
        for n in _notes(agg, scope, d, word))
    warn = ""
    if agg["incomparable"]:
        warn = (f'    <p class="t-footnote" style="{note_style}">'
                f'<span class="tag tag-warn">{T.icon("alert")}{C.I18N["caliber_tag"]}</span>'
                f' {scope} {agg["entries"]} 条产出中 {agg["incomparable"]} 条 '
                f'comparable=false，聚合值按原始记录汇总，横向可比性受限。</p>\n')
    table = f"""    <div class="tbl-wrap">
      <table class="tbl">
        <caption>逐日贡献审计：迁移按相邻交易日比对，无评级日期跳过且不计迁移</caption>
        <thead><tr>
          <th scope="col">交易日</th><th scope="col">Σ 评级</th>
          <th scope="col" class="num">Σ 值</th><th scope="col" class="num">产出</th>
          <th scope="col" class="num">口径受限</th><th scope="col" class="num">评级迁移</th>
        </tr></thead>
        <tbody>{_contrib_rows(agg)}</tbody>
      </table>
    </div>"""

    return (f'  <section aria-labelledby="sec-agg">\n'
            f'    <div class="sec-head">\n'
            f'      <h2 class="t-title3" id="sec-agg">{scope}聚合</h2>\n'
            f'      <span class="spacer"></span>\n'
            f'      <span class="aside">{T.icon("scale")}指标由{scope} '
            f'{len(agg["days"])} 个交易日实算</span>\n'
            f'    </div>\n    {kpis}\n{note_html}{warn}{table}'
            f'  </section>')
