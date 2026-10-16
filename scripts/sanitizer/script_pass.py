#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""script_pass.py — <script> 移除与数据可视化降级（变换层）

单一职责：处置正文里的 <script>，并保证**不丢内容**。

## 实测结论：3 个 script 是什么（2026-10-14 fund-market.html）
  1. `cdn.tailwindcss.com`      —— Tailwind Play CDN，**样式引擎**，驱动 197 个
     工具类。它不渲染任何内容，但删掉它页面会彻底失去全部样式（不是「样式变丑」
     是「没有样式」）。因此不能删，要**替换为等价的静态 CSS**。
  2. `chart.umd.js` (Chart.js)  —— 图表库，仅服务于第3 项。
  3. 内联 `new Chart(...)`      —— 渲染「板块穿透」环形图，数据为
     CPO 27.41 / 人工智能 7.33 / 标普500 9.36 / 红利低波 6.73 /
     纳斯达克100 5.35 / 其它 50.39。

## 处置：数据可视化降级为静态 CSS，不删数据
关键事实（已实测核对）：环形图的 6 个数据点在**右侧明细列表里已逐条以文字
呈现**（板块名 + 金额 + 百分比全部命中）。即图表是「已有信息的重复视觉表达」。
因此可以：
  · 用静态 CSS 条形图替换 canvas —— 信息不丢（甚至更易读、可访问性更好、
    深浅色下都可见，canvas 在深色模式下还会丢失对比度）；
  · 删除 Chart.js CDN 与内联初始化 —— 零 JS 达成。

若某天上游图表数据**不再**在别处重复，本模块会检测到「数据未在静态文本中
出现」并拒绝静默删除，改为在报告里标记 needs-manual-review（沉默失效防线）。

## Tailwind CDN：替换为预编译静态 CSS
不删除，直接删= 页面无样式。做法：
  · 一次性把正文用到的工具类预编译成 `assets/body-utilities.css`（随仓库提交）；
  · 发布时把该文件内容内联进正文 <style>，并移除 CDN <script>。
预编译产物**入库而非每次构建时实时跑 tailwind** —— 实时编译会让发布结果
依赖 npm 包的版本与生成顺序，直接破坏「同一天重跑字节一致」的发布幂等性。

## 注释卫生（2026-10-14 新增）
「是否仍有存活图表引用」的检测必须排除 HTML 注释：上游在已删除的
`<script>` 前常留 `<!-- Chart.js 渲染脚本 -->`，把注释当引用会让下一轮
消毒假报 needs-manual-review（旧日期页面每次重跑响 3 次 → 退出码 2
常态化 → 警告疲劳）。脚本安全移除后，这类点名库的注释作为悬空引用
一并清除；「图表数据见右侧列表」等编辑性注释不碰。

## 非 Chart.js 脚本也不静默放行（2026-10-15 补）
实测 stock-review.html 引用 echarts CDN：旧指纹表没有它 → 全程静默存活，
零 JS 契约破口且报告零条目。现指纹表覆盖 ECharts；孤儿 CDN（删脚本后
无人引用）整体移除，存活的内联脚本标记 needs-manual-review 留痕，绝不
静默放行。

## CDN 指纹只认 <script> 上下文（B-6，2026-10-15 设计师门禁）
「是否仍有存活图表引用」的检测曾对全文搜 _CHART_CDN 指纹：正文/figcaption
里出现「Chart.js」字样（介绍图表库的文案）被当成存活引用 → 误报
needs-manual-review 阻断发布。库名出现在文案里不是引用，出现在
<script> 里才是。故 live_ref 判定限定在 script 块内（见 _live_chart_refs）。
"""
from __future__ import annotations

import re

# ---- script 标签 ----
_SCRIPT_WITH_SRC = re.compile(r'<script\b[^>]*\bsrc=["\'][^"\']*["\'][^>]*>\s*</script>',
                              re.I | re.S)
_SCRIPT_BLOCK = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
_EVENT_ATTR = re.compile(r'\son[a-z]+\s*=\s*"[^"]*"', re.I)
_JS_URL = re.compile(r'(?:src|href)\s*=\s*["\']javascript:[^"\']*["\']', re.I)

# Tailwind / Chart.js CDN 指纹
_TAILWIND_CDN = re.compile(r"cdn\.tailwindcss\.com", re.I)
# 图表库指纹：Chart.js 家族 + ECharts（2026-10-15 实测上游 stock-review.html
# 引用 echarts CDN，旧指纹表没有它 → 静默存活，零 JS 契约破口）
_CHART_CDN = re.compile(r"chart\.umd\.js|chart\.min\.js|Chart\.js|echarts", re.I)
_CHART_NEW = re.compile(r"new\s+Chart\s*\(", re.I)
_CANVAS = re.compile(r"<canvas\b[^>]*>\s*</canvas>", re.I)
_CANVAS_OPEN = re.compile(r"<canvas\b[^>]*>", re.I)

# HTML 注释（孤儿注释清理用；存活引用判定已改为 script 上下文匹配，见 B-6）
_COMMENT_RE = re.compile(r"[ \t]*<!--[\s\S]*?-->")


def _strip_chart_comments(html: str) -> tuple[str, int]:
    """清除点名图表库的说明注释，返回 (新文本, 清除处数)。

    脚本移除后这类注释即悬空引用（指向不存在之物），既是 artifact 里的
    谎言，也是下一轮消毒假阳性的来源。只删点名库的注释，
    「图表数据见右侧列表」这类编辑性注释不碰。
    """
    removed = 0

    def repl(m: re.Match) -> str:
        nonlocal removed
        if _CHART_CDN.search(m.group(0)):
            removed += 1
            return ""
        return m.group(0)

    return _COMMENT_RE.sub(repl, html), removed


def find_chart_scripts(html: str) -> list[str]:
    """返回所有 script 块的原文（诊断用）。"""
    return _SCRIPT_BLOCK.findall(html)


def _live_chart_refs(html: str) -> list[str]:
    """<script> 上下文内存活的图表库引用（B-6：CDN 指纹只认 script）。

    2026-10-15 设计师实测：正文/figcaption 里出现「Chart.js」字样（介绍
    图表库的文案）被全文指纹匹配当成存活引用 → 误报 needs-manual-review
    阻断发布。库名在文案里不是引用，在 <script> 里才是 —— 判定因此限定
    在 script 块内。HTML 注释同样不算（注释清理见 _strip_chart_comments）。
    """
    return [sc for sc in find_chart_scripts(html) if _CHART_CDN.search(sc)]


def find_inline_scripts(html: str) -> list[str]:
    """无 src 的内联 script 块（可能有初始化逻辑/数据）。"""
    return [sc for sc in find_chart_scripts(html)
            if not re.search(r"\bsrc=", sc, re.I)]


def orphan_cdn_scripts(html: str) -> list[str]:
    """页面无任何内联脚本时的外部库 CDN 块——没有可调用方，属死代码。

    2026-10-15 实测：stock-review.html 引了 echarts CDN，但全页没有一处
    echarts.init/setOption（连图表容器都没有），CDN 纯属死代码。旧实现只认
    Chart.js 指纹，这类脚本静默存活 —— 既违反「详情页零 JS」契约，又让每次
    发布多一个外部请求。有内联脚本时一律不判孤儿（调用方存在，只是本模块
    看不懂，交 needs-manual-review，不擅自删）。
    """
    if find_inline_scripts(html):
        return []
    return _SCRIPT_WITH_SRC.findall(html)


def _chart_labels_and_data(script_text: str) -> tuple[list[str], list[float]]:
    """从 Chart.js 配置里抽出 labels 与 data（尽力解析，失败返回空）。

    只支持最常见的字面量数组写法：`labels: ["A","B"]` / `data: [1.2, 3.4]`。
    解析不出来时上层会走「拒绝静默删除」分支。
    """
    labels: list[str] = []
    data: list[float] = []
    m = re.search(r"labels\s*:\s*\[(.*?)\]", script_text, re.S)
    if m:
        labels = [s.strip().strip('"\'') for s in m.group(1).split(",") if s.strip()]
    m = re.search(r"data\s*:\s*\[([\d.\s,e+-]+)\]", script_text)
    if m:
        try:
            data = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", m.group(1))]
        except ValueError:
            data = []
    return labels, data


def _labels_present_in_text(labels: list[str], html: str) -> bool:
    """所有图表标签是否都能在页面静态文本里找到（数据不丢的前置校验）。"""
    if not labels:
        return False
    text = _SCRIPT_BLOCK.sub(" ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    return all(lb and lb in text for lb in labels)


def _static_chart_html(labels: list[str], data: list[float], unit: str = "%") -> str:
    """由图表原始数据生成静态 CSS 条形图（无 JS、无 canvas）。

    数值原样呈现，不做四舍五入以外的加工；总量写在figcaption 里，
    保证「看图得到的信息」与「读文字得到的信息」一致。
    """
    if not data:
        return ""
    total = sum(data)
    rows = []
    for lb, val in zip(labels, data):
        pct = (val / total * 100) if total else 0
        rows.append(
            f'<div class="viz-row"><span class="viz-lb">{lb}</span>'
            f'<span class="viz-track"><span class="viz-fill" style="width:{pct:.2f}%"></span></span>'
            f'<span class="viz-val">{val:g}{unit}</span></div>')
    return ('<figure class="viz-static" role="img" '
            f'aria-label="板块穿透占比静态图，共{len(labels)} 项">'
            + "".join(rows)
            + f'<figcaption class="viz-cap">合计 {total:g}{unit}'
              f'（由原环形图数据静态化，零JS）</figcaption></figure>')


def handle_scripts(html: str, report, utilities_css: str | None = None) -> str:
    """移除 script / 事件属性 / javascript: URL，并把图表降级为静态 CSS。

    utilities_css: 预编译的 Tailwind 工具类 CSS（由 build_body_css.py 生成并入库）。
        为 None 时不动 Tailwind CDN（宁可保留样式引擎，也不产出无样式页面）。
    """
    # ---- 1. 定位图表：拿到数据后再动 script（顺序不能反）----
    chart_data: tuple[list[str], list[float]] = ([], [])
    has_chart = False
    for sc in find_chart_scripts(html):
        if _CHART_NEW.search(sc) or _CHART_CDN.search(sc):
            lb, dt = _chart_labels_and_data(sc)
            if lb and dt:
                chart_data = (lb, dt)
                has_chart = True
                break

    # ---- 2. 数据安全校验：标签必须在静态文本里有对应，否则不删图表 ----
    if has_chart:
        labels, data = chart_data
        if _labels_present_in_text(labels, html):
            viz = _static_chart_html(labels, data)
            html = _CANVAS.sub(viz, html, count=1)
            report.add("chart-static",
                       f"环形图降级为静态 CSS 条形图（{len(labels)} 项，数据原样保留）")
        else:
            report.add("needs-manual-review",
                       "检测到图表但其数据未在静态文本中出现，保留 script 不做删除"
                       "（避免丢数据）")
            has_chart = False

    # ---- 3. Tailwind CDN → 内联预编译 CSS ----
    tw_hits = len(_TAILWIND_CDN.findall(html))
    if tw_hits:
        if utilities_css:
            html = _SCRIPT_WITH_SRC.sub("", html)
            block = f"<style data-origin=\"tailwind-static\">{utilities_css}</style>"
            html = re.sub(r"(<head\b[^>]*>)", r"\1\n" + block.replace("\\", "\\\\"),
                          html, count=1, flags=re.I)
            report.add("script",
                       f"Tailwind Play CDN({tw_hits}) → 内联预编译静态 CSS"
                       f"（{len(utilities_css)} 字节），样式能力等价")
        else:
            report.add("needs-manual-review",
                       "Tailwind CDN 存在但未提供预编译 CSS，保留 CDN 不删除"
                       "（删除会导致页面完全失去样式）")

    # ---- 4. 图表相关 script（Chart.js CDN + 初始化块）→ 移除 ----
    # 只删「确实是图表脚本」的块。绝不能整段 _SCRIPT_BLOCK.sub 一刀切：
    # 那会把 Tailwind CDN 之类与图表无关的 script 一起删掉（实测踩过：
    # 数据保护分支已经判定「保留」，却仍被这一步删干净，报告与行为自相矛盾）。
    # live_ref 只认 <script> 上下文（B-6）：正文提库名不算存活引用。
    live_ref = bool(_live_chart_refs(html))
    if has_chart:
        victims = [sc for sc in find_chart_scripts(html)
                   if _CHART_CDN.search(sc) or _CHART_NEW.search(sc)]
        for sc in victims:
            html = html.replace(sc, "", 1)
        report.add("script",
                   f"Chart.js CDN 与内联初始化已移除（{len(victims)} 块，数据已静态化）",
                   len(victims))
        live_ref = False
    # ---- 4.5 孤儿外部库 CDN → 死代码，移除 ----
    # 必须先于 live_ref 判定：echarts CDN 无 init 时既是「图表库引用」又是
    # 「孤儿」，按孤儿处理（移除+报告），不升级成 needs-manual-review。
    orphans = orphan_cdn_scripts(html)
    for sc in orphans:
        html = html.replace(sc, "", 1)
    if orphans:
        report.add("script",
                   f"移除孤儿外部脚本 CDN {len(orphans)} 个"
                   "（页面无内联脚本，无可调用方，属死代码）", len(orphans))
        live_ref = False
    elif live_ref:
        report.add("needs-manual-review",
                   "存在 Chart.js 引用但数据未安全静态化，保留相关 script 不做删除")
    # ---- 4.6 仍存活的内联脚本 → 本模块看不懂，显式标记 ----
    # 图表相关的不重复计（上面已按图表规则处置/标记过）；其余内联脚本
    # 一律留痕，杜绝「看不懂就静默放行」的沉默失效。
    leftovers = [sc for sc in find_inline_scripts(html)
                 if not (_CHART_CDN.search(sc) or _CHART_NEW.search(sc))]
    if leftovers:
        report.add("needs-manual-review",
                   f"存在 {len(leftovers)} 个内联脚本未经处置，保守保留"
                   "（避免丢数据/逻辑）", len(leftovers))
    if not live_ref:
        # 无存活图表引用：库说明注释（如 `<!-- Chart.js 渲染脚本 -->`）已是
        # 悬空引用，一并清除 —— 否则下一轮消毒会在注释里「检测到 Chart.js」
        # 误报 needs-manual-review（2026-10-14 实测：旧日期页面每次重跑
        # 都报 3 处假阳性，退出码 2 常态化 → 警告疲劳）。
        html, n = _strip_chart_comments(html)
        if n:
            report.add("script",
                       f"清除图表库说明注释 {n} 处（对应脚本已移除，注释属悬空引用）", n)

    # ---- 5. 事件属性 / javascript: URL ----
    ev = _EVENT_ATTR.findall(html)
    if ev:
        html = _EVENT_ATTR.sub("", html)
        report.add("script", f"移除内联事件属性 {len(ev)} 处", len(ev))
    ju = _JS_URL.findall(html)
    if ju:
        html = _JS_URL.sub("", html)
        report.add("script", f"移除 javascript: URL {len(ju)} 处", len(ju))

    return html