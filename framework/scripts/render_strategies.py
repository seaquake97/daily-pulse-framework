#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""render_strategies.py — 声明式策略库 → 静态页 HTML 片段（纯标准库，零第三方依赖）

## 定位（消费层，不改数据层）

  数据的一侧在 framework/scripts/strategies.py（加载 + Schema 校验），本模块只做
  呈现：把 framework/config/strategies/*.yaml 渲染成可直接嵌进静态页的 HTML
  片段。CI 已有 strategies.py 作为配置门禁，因此本模块的容错取向是
  「缺策略就少一块，不挂构建」——差 YAML 由门禁拦，渲染层不二次判死。

## 三条硬约束

  1. **字节确定性**：类别按 CATEGORY_ORDER 固定枚举排序、组内按 name 字典序，
     不用 dict 遍历顺序、不掺运行时刻时间戳。否则同输入不同输出，构建不幂等。
  2. **零颜色字面量**：CSS 全部走 var(--token)，深浅色由 Token 层覆写，
     遵循既有D-1 纪律（深色换算 surface，不靠阴影）。
  3. **团队 P0-1**：不产出任何 emoji。文案已由 strategies 门禁卡到缺失即报错，
     本侧只做 html.escape，不发明图标——语义由中文标签承载。

## 用法

    python3 render_strategies.py                      # 片段 → stdout
    python3 render_strategies.py --out _stage/strat.html
    python3 render_strategies.py --css                # 配套样式表 → stdout
    python3 render_strategies.py --dir <其他策略目录>

## 退出码

  0  正常（含「目录缺失/无策略 → 空片段」的降级路径）
  1  写文件失败
"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from strategies import StrategyError, load_all_strategies  # noqa: E402

DEFAULT_STRATEGY_DIR = _HERE.parent / "config" / "strategies"

# 锚点（注入对）：单锚点会被替换掉，二次注入失联，故升级为「开始/结束」成对联锚
BEGIN_MARK = "<!--__STRATEGIES__-->"
END_MARK = "<!--/__STRATEGIES__-->"

# 卡片样式标记：与 frame_pass.STYLE_ORIGIN 同一套防腐标记约定
STYLE_ORIGIN = 'data-origin="strategies"'

# 类别顺序 = 构建锚：战略 → 执行 → 防御，不可改成字典序（会打乱阅读逻辑）
CATEGORY_ORDER = ("strategic", "execution", "defensive")
CATEGORY_LABEL = {"strategic": "战略", "execution": "执行", "defensive": "防御"}
# 分组小标题用完整词组（徽章用上面的单字，两处语义同源但粒度不同）
CATEGORY_GROUP_LABEL = {"strategic": "战略配置", "execution": "执行战术",
                        "defensive": "防御底仓"}

# 数值字段 → 展示名：比率统一折算百分数，口径集中在这张表，避免各处各写一套
NUMERIC_FIELDS = (("step_ratio_default", "默认步长"),)
LIST_FIELDS = (("execution_levels", "委托档位"),)


# --------------------------------------------------------------- 工具
def esc(value) -> str:
    """HTML 转义（含引号），供文本与属性值共用。"""
    return html.escape(str(value), quote=True)


def fmt_percent(value) -> str:
    """比率 → 百分数文本：0.025 → 2.5%，0.02 → 2%，0.0 → 0%。

    两位小数后剥零：既不显示 2.5000%（浮点噪声），也不把 2.00% 砍成 2%（信息无损）。
    非数值原样返回，交给上层转义。
    """
    try:
        num = float(value) * 100.0
    except (TypeError, ValueError):
        return str(value)
    text = f"{num:.2f}".rstrip("0").rstrip(".")
    return (text or "0") + "%"


def order_key(item: dict) -> tuple:
    """排序键：(类别序号, name)。未知类别落到末尾，仍按 name 稳定排序。"""
    cat = str(item.get("category", ""))
    name = str(item.get("name", ""))
    rank = CATEGORY_ORDER.index(cat) if cat in CATEGORY_ORDER else len(CATEGORY_ORDER)
    return (rank, name)


# --------------------------------------------------------------- 样式层
def strategy_css() -> str:
    """策略区块样式表（Token 化 / 零颜色字面量 / 深色换面不投影）。

    单独输出而非内联进片段：<style> 只应落在 <head>，片段本身保持纯净 HTML，
    便于注入任意页面。由 inject_strategies.py 负责搬运。
    """
    return """
.strat-group + .strat-group{ margin-top:var(--space-6); }
.strat-group-label{ font-size:var(--fs-caption1); letter-spacing:var(--tracking-caption);
  color:var(--fg-3); margin-bottom:var(--space-2); }
.strat-card{ border:1px solid var(--border-soft); border-radius:var(--radius-sm);
  background:var(--surface-alt); padding:var(--space-4) var(--space-5);
  corner-shape:var(--corner-shape,squircle); }
.strat-card + .strat-card{ margin-top:var(--space-4); }
.strat-head{ display:flex; align-items:baseline; gap:var(--space-3); flex-wrap:wrap; }
.strat-card .strat-title{ margin:0; font-family:var(--font-display);
  font-size:var(--fs-title4); line-height:var(--lh-title4);
  letter-spacing:var(--tracking-title4); font-weight:var(--fw-semibold); color:var(--fg); }
.strat-cat{ flex:0 0 auto; }
.strat-cat-strategic{ background:transparent; color:var(--accent); border-color:var(--accent); }
.strat-cat-execution{ background:transparent; color:var(--link); border-color:var(--link); }
.strat-cat-defensive{ background:var(--rating-defensive-bg); color:var(--rating-defensive-fg);
  border-color:var(--rating-defensive-ring); }
.strat-desc{ margin:var(--space-2) 0 0; font-size:var(--fs-callout);
  line-height:var(--lh-callout); color:var(--fg-2); max-width:70ch; }
.strat-facts{ display:flex; flex-wrap:wrap; gap:var(--space-2) var(--space-5);
  margin:var(--space-3) 0 0; }
.strat-fact{ display:flex; align-items:baseline; gap:6px; }
.strat-fact dt{ font-size:var(--fs-caption1); letter-spacing:var(--tracking-caption); color:var(--fg-3); }
.strat-fact dd{ margin:0; font-family:var(--font-mono); font-variant-numeric:var(--numeric);
  font-size:var(--fs-footnote); color:var(--fg); }
.strat-block{ margin-top:var(--space-4); }
.strat-card .strat-h{ margin:0 0 var(--space-2); font-size:var(--fs-caption1);
  letter-spacing:var(--tracking-caption); font-weight:var(--fw-semibold); color:var(--fg-2); }
.strat-card .strat-list{ margin:0; padding-left:20px; }
.strat-card .strat-list li{ font-size:var(--fs-callout); line-height:var(--lh-callout);
  color:var(--fg-2); margin:var(--space-1) 0; }
.strat-tags{ display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-top:var(--space-4); }
.strat-tags .strat-h{ margin:0; }
.strat-code{ font-family:var(--font-mono); font-variant-numeric:var(--numeric);
  font-size:var(--fs-caption1); color:var(--fg); background:var(--bg);
  border:1px solid var(--border-soft); border-radius:var(--radius-sm); padding:2px 7px; }
@media (prefers-color-scheme:dark){
  .strat-card{ background:var(--panel-bg); border-color:var(--ap-dark-sep); }
  .strat-code{ background:var(--ap-dark-2); border-color:var(--ap-dark-sep); }
}
@media (max-width:640px){
  .strat-card{ padding:var(--space-4); }
}
@media (prefers-reduced-motion:reduce){ .strat-card{ transition:none; } }
"""


# --------------------------------------------------------------- 片段层
def _render_tags(label: str, values) -> str:
    """等宽代码行（持仓代码 / 委托档位：金融站点惯例，等宽 + 描边框避免歧义字符）。"""
    if not isinstance(values, list) or not values:
        return ""
    chips = "".join(f'<code class="strat-code">{esc(v)}</code>' for v in values)
    return (f'<div class="strat-tags"><span class="strat-h">{esc(label)}</span>'
            f'{chips}</div>')


def _render_card(item: dict) -> str:
    name = str(item.get("name", ""))
    category = str(item.get("category", ""))
    label = CATEGORY_LABEL.get(category, category)
    out = [f'<article class="strat-card" id="strat-{esc(name)}">']
    out.append('<div class="strat-head">')
    out.append(f'<h3 class="strat-title">{esc(item.get("display_name", name))}</h3>')
    out.append(f'<span class="chip strat-cat strat-cat-{esc(category)}">{esc(label)}</span>')
    out.append("</div>")

    if item.get("description"):
        out.append(f'<p class="strat-desc">{esc(item["description"])}</p>')

    facts = [(label_txt, fmt_percent(item[key]))
             for key, label_txt in NUMERIC_FIELDS if item.get(key) is not None]
    if facts:
        out.append('<dl class="strat-facts">')
        for label_txt, shown in facts:
            out.append(f'<div class="strat-fact"><dt>{esc(label_txt)}</dt>'
                       f'<dd>{esc(shown)}</dd></div>')
        out.append("</dl>")

    principles = item.get("principles")
    if isinstance(principles, list) and principles:
        out.append('<div class="strat-block"><h4 class="strat-h">核心原则</h4>'
                   '<ul class="strat-list">')
        out += [f"<li>{esc(p)}</li>" for p in principles]
        out.append("</ul></div>")

    rules = item.get("rules")
    if isinstance(rules, list) and rules:
        out.append(f'<div class="strat-block"><h4 class="strat-h">执行规则'
                   f'（{len(rules)} 条）</h4><ol class="strat-list">')
        out += [f"<li>{esc(r)}</li>" for r in rules]
        out.append("</ol></div>")

    for key, label_txt in LIST_FIELDS:
        out.append(_render_tags(label_txt, item.get(key)))
    out.append(_render_tags("映射标的", item.get("holdings_mapped")))
    out.append("</article>")
    return "\n".join(line for line in out if line)


def render_fragment(strategy_dir: Path = DEFAULT_STRATEGY_DIR) -> str:
    """渲染全部策略为单个 HTML 片段；目录缺失/无策略返回空字符串。

    空片段而非异常：构建链路（build_site → publish）不得因策略配置缺失而断供。
    加载失败原因打到 stderr，CI 日志可查，不做静默吞异常。
    """
    try:
        strategies = load_all_strategies(Path(strategy_dir))
    except StrategyError as exc:
        print(f"[warn] 策略片段渲染跳过: {exc}", file=sys.stderr)
        return ""
    if not strategies:
        return ""

    ordered = sorted(strategies.values(), key=order_key)
    buckets: dict[str, list[dict]] = {}
    for item in ordered:
        buckets.setdefault(str(item.get("category", "")), []).append(item)
    heads = [c for c in CATEGORY_ORDER if c in buckets]
    heads += sorted(c for c in buckets if c not in CATEGORY_ORDER)

    parts = ['<div class="strat">',
             f'<p class="strat-group-label">以下 {len(ordered)} 项策略由决策引擎策略'
             f'配置层声明式定义，按类别与名称排序自动呈现。</p>']
    for cat in heads:
        items = buckets[cat]
        parts.append(f'<div class="strat-group" data-category="{esc(cat)}">')
        group_label = CATEGORY_GROUP_LABEL.get(cat, cat)
        parts.append(f'<p class="strat-group-label">{esc(group_label)} · {len(items)} 项</p>')
        parts += [_render_card(i) for i in items]
        parts.append("</div>")
    parts.append("</div>")
    return "\n".join(parts)


def wrap_fragment(fragment: str) -> str:
    """包成可重复注入的标记对（首注入用此形，再注入按区间整体替换）。"""
    return f"{BEGIN_MARK}\n{fragment}\n{END_MARK}" if fragment else BEGIN_MARK


# --------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="声明式策略库 → 静态页 HTML 片段")
    ap.add_argument("--dir", default=str(DEFAULT_STRATEGY_DIR), help="策略配置目录")
    ap.add_argument("--out", default=None, help="写入文件；缺省输出到 stdout")
    ap.add_argument("--css", action="store_true", help="输出配套样式表而非片段")
    ap.add_argument("--wrap", action="store_true",
                    help="用 BEGIN/END 锚点注释包裹片段（注入前预处理用）")
    args = ap.parse_args(argv)

    if args.css:
        text = strategy_css().strip() + "\n"
        detail = f"样式表 {len(text)} 字节"
    else:
        fragment = render_fragment(Path(args.dir))
        count = fragment.count('<article class="strat-card"')
        text = wrap_fragment(fragment) if (args.wrap and fragment) else fragment
        if text and not text.endswith("\n"):
            text += "\n"
        detail = f"{count} 个策略 / {len(text)} 字节"

    if args.out:
        out = Path(args.out)
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"[fail] 写入失败 {out}: {exc}", file=sys.stderr)
            return 1
        print(f"[ok] {detail} → {out}", file=sys.stderr)
        return 0

    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
