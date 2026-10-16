#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_index.py — 聚合页生成器（GitHub Pages 首页）

扫描 _stage/docs/daily/<date>/meta.json，生成 _stage/docs/index.html：
  - 双语页头（中/英）
  - 日报卡片列表：日期 / 标题 / Σ 评级徽章 / 数据时点 / 链接（倒序，最新在前）
  - 五档评级色阶遵循 ui-design-spec.md：进攻=红 / 均衡=琥珀 / 信号矛盾=中性琥珀 /
    防守=蓝灰 / 回避=绿（中国市场惯例：红涨绿跌；评级色不与涨跌语义混淆）
  - 红涨绿跌仅用于行情数字；评级徽章用色相区分，不用红绿
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

RATING_COLORS = {
    "进攻": "#B91C1C",     # 深红（看多）
    "均衡": "#B45309",     # 琥珀
    "信号矛盾": "#475569",  # 中性灰（不给方向，避开红绿语义）
    "防守": "#15803D",     # 浅绿（看空梯度）
    "回避": "#166534",     # 深绿
}
# 方向箭头冗余编码（色盲友好，ui-design-spec §1.3）
RATING_ARROWS = {"进攻": "▲▲", "均衡": "▲", "信号矛盾": "↔", "防守": "▼", "回避": "▼▼"}
RATING_COLORS_EN = {
    "进攻": "#B91C1C", "均衡": "#B45309", "信号矛盾": "#78716C",
    "防守": "#1D4ED8", "回避": "#15803D",
}

I18N = {
    "site_title": ("每日市场脉搏 · Daily Market Pulse", "每日市场脉搏 · Daily Market Pulse"),
    "site_sub": ("数据驱动的 A 股/基金每日研判档案", "Data-driven daily research archive for A-shares & funds"),
    "latest": ("最新研判", "Latest Research"),
    "archive": ("历史归档", "Archive"),
    "rating": ("Σ 评级", "Sigma Rating"),
    "stage": ("数据时点", "Data Stage"),
    "read": ("阅读全文", "Read Full Report"),
    "no_data": ("暂无归档数据", "No archived reports yet"),
    "disclaimer": ("免责声明：本站内容基于公开数据与量化分析生成，仅供参考，不构成投资建议。市场有风险，投资需谨慎。",
                   "Disclaimer: Content is generated from public data and quantitative analysis, for reference only, not investment advice."),
    "source": ("数据来源：腾讯自选股 MCP（westock-mcp）实时采集 · 信号评分由 daily-decision-engine 代码计算",
               "Data source: Tencent Self-Selected MCP (westock-mcp) · Signals computed by daily-decision-engine"),
}


def load_metas(daily_dir: Path) -> list:
    metas = []
    for p in sorted(daily_dir.glob("*/meta.json"), reverse=True):
        try:
            metas.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"⚠️ meta.json 解析失败 {p}: {e}")
    return metas


def render(metas: list) -> str:
    cards = []
    for m in metas:
        rating = m.get("rating", "信号矛盾")
        sigma = m.get("sigma", 0)
        color = RATING_COLORS.get(rating, "#475569")
        arrow = RATING_ARROWS.get(rating, "↔")
        sigma_txt = f"{sigma:+.3f}" if isinstance(sigma, (int, float)) else str(sigma)
        stage = m.get("data_stage", "intraday")
        stage_map = {"pre_open": ("竞价时点", "Pre-open"), "intraday": ("盘中时点", "Intraday"),
                     "close": ("收盘时点", "Close")}
        stage_zh, stage_en = stage_map.get(stage, (stage, stage))
        tasks = "、".join(m.get("tasks", [])) or "—"
        cards.append(f"""
    <article class="dp-card" data-date="{m.get('date','')}" data-rating="{rating}" data-sigma="{sigma}">
      <div class="dp-card-head">
        <time class="dp-date">{m.get('date','')}</time>
        <span class="dp-rating" style="background:{color}">{arrow} {rating} · Σ {sigma_txt}</span>
        <span class="dp-stage">{stage_zh} / {stage_en}</span>
      </div>
      <h2 class="dp-title">{m.get('title_zh','')}</h2>
      <p class="dp-title-en">{m.get('title_en','')}</p>
      <p class="dp-summary">{m.get('summary_zh','')}</p>
      <p class="dp-tasks">覆盖任务 / Tasks: {tasks}</p>
      <a class="dp-link" href="./daily/{m.get('date','')}/">阅读全文 / Read Full Report →</a>
    </article>""")
    cards_html = "\n".join(cards) if cards else f'<p class="dp-empty">{I18N["no_data"][0]} / {I18N["no_data"][1]}</p>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{I18N['site_title'][0]}</title>
<style>
  :root {{ --ink:#1c1917; --sub:#57534e; --line:#e7e5e4; --bg:#fafaf9; --card:#ffffff; --amber:#d97706; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         background:var(--bg); color:var(--ink); font-size:15px; line-height:1.75; }}
  .wrap {{ max-width:880px; margin:0 auto; padding:32px 16px 48px; }}
  header.dp-head {{ border-bottom:2px solid var(--line); padding-bottom:20px; margin-bottom:24px; }}
  header.dp-head h1 {{ font-size:26px; font-weight:800; }}
  header.dp-head .sub {{ color:var(--sub); font-size:14px; margin-top:6px; }}
  .dp-card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:20px; margin-bottom:16px; }}
  .dp-card-head {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:10px; }}
  .dp-date {{ font-weight:800; font-size:15px; }}
  .dp-rating {{ color:#fff; font-size:12.5px; font-weight:700; padding:2px 10px; border-radius:6px; }}
  .dp-stage {{ font-size:12px; color:var(--sub); border:1px solid var(--line); padding:1px 8px; border-radius:5px; }}
  .dp-title {{ font-size:18px; font-weight:700; }}
  .dp-title-en {{ font-size:13.5px; color:var(--sub); margin:2px 0 8px; }}
  .dp-summary {{ font-size:14px; }}
  .dp-tasks {{ font-size:12.5px; color:var(--sub); margin-top:8px; }}
  .dp-link {{ display:inline-block; margin-top:10px; color:var(--amber); font-weight:700; text-decoration:none; font-size:14px; }}
  .dp-link:hover {{ text-decoration:underline; }}
  .dp-empty {{ color:var(--sub); padding:24px 0; }}
  nav.dp-nav {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:20px; }}
  nav.dp-nav a {{ font-size:13px; font-weight:600; color:var(--sub); text-decoration:none;
                  border:1px solid var(--line); background:var(--card); padding:4px 12px; border-radius:6px; }}
  nav.dp-nav a:hover {{ color:var(--amber); border-color:var(--amber); }}
  nav.dp-nav a.current {{ color:var(--amber); border-color:var(--amber); background:#fffbeb; }}
  footer.dp-foot {{ margin-top:32px; border-top:1px solid var(--line); padding-top:16px; font-size:12.5px; color:var(--sub); }}
  @media (max-width:600px) {{ header.dp-head h1 {{ font-size:22px; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="dp-head">
    <h1>{I18N['site_title'][0]}</h1>
    <p class="sub">{I18N['site_sub'][0]} / {I18N['site_sub'][1]}</p>
    <p class="sub">生成时间 / Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} · 共 {len(metas)} 期 / issues</p>
  </header>
  <nav class="dp-nav">
    <a class="current" href="./">首页 / Home</a>
    <a href="./methodology/">方法论 / Methodology</a>
    <a href="./weekly/">周报 / Weekly</a>
    <a href="./monthly/">月报 / Monthly</a>
    <a href="./feed.xml">订阅 / RSS</a>
  </nav>
  <main>
{cards_html}
  </main>
  <footer class="dp-foot">
    <p>{I18N['disclaimer'][0]}</p>
    <p>{I18N['disclaimer'][1]}</p>
    <p style="margin-top:6px">{I18N['source'][0]}</p>
    <p>{I18N['source'][1]}</p>
  </footer>
</div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="聚合页生成器")
    ap.add_argument("--daily-dir", required=True, help="docs/daily 目录（含 <date>/meta.json）")
    ap.add_argument("--out", required=True, help="输出 index.html 路径")
    args = ap.parse_args()

    daily = Path(args.daily_dir)
    if not daily.is_dir():
        print(f"❌ 目录不存在: {daily}")
        sys.exit(2)
    metas = load_metas(daily)
    html = render(metas)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"✅ 聚合页已生成: {out}（{len(metas)} 期日报）")
    sys.exit(0)


if __name__ == "__main__":
    main()
