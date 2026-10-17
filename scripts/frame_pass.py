#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""frame_pass.py — 上游详情页阅读框架注入（frame pass）

把 sanitizer 净化后的详情页包上站点铬件（slim 导航 / 680px 阅读容器 / 元信息行 /
站点页脚），规范依据 detail-frame-spec.md v1.1，动作 A-1 ~ A-10；片段组装复用
site_render 的 detail_* 系列。顺序是设计约束（§1.1/C-10）：sanitize → frame →
build_site，frame 依赖 sanitize 产出形态（h3/h4 + data-sb-h、收敛后的 Token 色值、最小 sprite
与 detail-tokens 标记），输出绝不再回消毒；注入 <style> 带 data-origin 标记防腐（见 STYLE_ORIGIN，
回归 test_frame_fixed_point.py）。幂等：<body data-df="v1">
整文件跳过；页脚「本页信息」只取 entries.json / 路径字段，不取墙钟（幂等铁律）。
处理对象 = daily/<date>/entries.json 中 html 非 null 的文件（C-1），depth 恒 ../../。

用法：python3 scripts/frame_pass.py --dir _stage/docs/daily [--dry-run] [--report P]
退出码：0 干净 / 1 参数·IO·结构错误 / 2 needs-manual-review（本规范内不产生）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import site_content as C          # noqa: E402  任务元信息（kicker 图标/文案）
import site_render as R           # noqa: E402  detail_* 铬件片段 + 徽章/chip 复用
import site_theme as T            # noqa: E402  Token + 图标 + 四层 CSS 装配

MARKER_ATTR = 'data-df="v1"'
MARKER_COMMENT = "<!-- detail-frame:v1 -->"
# 注入 <style> 的排除标记：style_pass 的 data-origin 闸门据此跳过 palette 原语收敛（漏标记即 2026-10-15 腐败通道）
STYLE_ORIGIN = 'data-origin="detail-frame"'
DEPTH = "../../"                       # 详情页相对 docs 根的深度（恒值）
SITE_TITLE_SUFFIX = " — 每日市场脉搏"

# <head> 元信息里的 emoji 剥离（与 sanitizer.emoji_inline.EMOJI_PATTERN 同口径）。
# head 不在 sanitizer 扫描范围内，故此处必须自带一份——A-4 注入 og:description
# 时用，堵住「emoji 随分享卡片外泄」这条 P0 缺口（2026-10-16 实锤 10-13 stock-review）。
_EMOJI_HEAD = re.compile(
    "[\U0001F300-\U0001F9FF\U0001FAFF"
    "☀-➿⬀-⯿\U0001F000-\U0001F02F\U0001F0A0-\U0001F0FF"
    "\U0001F100-\U0001F64F\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF"
    "⬀-⯿️‍⬅️‍➕]+")
# A-6/§3.7 body 布局工具类：space-[xy]-* 特异性 (0,3,0)，CSS 打不过，必须摘类名
_BODY_LAYOUT_RE = re.compile(r"^(p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|max-w-.*|mx-auto|my-auto|space-[xy]-.*|container|w-.*)$")
# A-5 后端最小 sprite：全量 sprite 更靠前且全覆盖，摘除消重复 id（S-9/G-7）
_MINIMAL_SPRITE_RE = re.compile(r"<!-- icon-subsprite:v1 -->\s*<svg\b.*?</svg\s*>", re.S | re.I)
# 引号感知：sanitize 产的 data-sb-h="1->3" 值内含 >，[^>]* 会在值内截断致 A-7 产出坏标签
_HEADING_RE = re.compile(r"<h(?P<lv>[1-6])(?P<attrs>(?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>(?P<body>.*?)</h(?P=lv)>", re.S | re.I)
_TABLE_RE = re.compile(r"<table\b.*?</table\s*>", re.S | re.I)           # A-9-1
_RATING_RE = re.compile(                                                # A-9-2
    r"<(span|div|p)(?P<attrs>[^>]*class=\"[^\"]*\brating\b[^\"]*\"[^>]*)>\s*(?P<text>[^<]*?)\s*</\1>", re.S)
# masthead = header 标签 / class 精确含 top|cover|hero 的 div（token 匹配防连字符误判）
_DIV_OPEN_RE = re.compile(r"<div\s+([^>]*)>", re.I)
_HEADER_OPEN_RE = re.compile(r"<header\b[^>]*>", re.I)

# C-14 类名冲突门禁：未登记的交叉类 = 构建失败（spec §12-4），合法结局仅三种：detail-frame.css 显式管辖 / A-9 主动施加 / 下述已登记方差。
ACCEPTED_VARIANCE = {
    "nav-links": "10-13 旧模板页内锚点导航同名；框架规则为 flex 横排，文字色由 .doc a 后置胜出",
    "foot-brand": "上游文章级署名行；框架 .foot-brand 仅限 max-width:38ch，不破版",
    "sub": "封面副标题；框架 .sub 规则均后代限定，裸 .sub 零命中",
    "ic-20": "图标子 sprite 尺寸工具类（site_theme.ICON_SIZES 已定义 .ic/.ic-20/.ic-24），上游 <svg class=\"ic ic-20\"> 合法使用；框架图标系统成员，非冲突类",
}
DESIGN_APPLIED = {"tbl": "A-9 主动施加：上游表格升格框架 Apple 表格 .tbl"}


def _conflict_gate(classes: set[str], where: str) -> list[str]:
    """C-14：未登记的交叉类 = 构建失败（防上游新类带偏框架组件，spec §12-4）。"""
    def cls_of(css: str) -> set[str]:
        return set(re.findall(r"\.([A-Za-z][A-Za-z0-9_-]*)",
                              re.sub(r"/\*.*?\*/", " ", css, flags=re.S)))
    fw = cls_of(T.components_css()) | cls_of(T.blocks_css())
    cross = sorted(classes & fw - cls_of(T.detail_frame_css()) - set(DESIGN_APPLIED))
    unknown = [c for c in cross if c not in ACCEPTED_VARIANCE]
    if unknown:
        raise SystemExit(f"[frame][FATAL] {where} 交叉类未登记: {', '.join(unknown)}"
                         "（合法结局仅：detail-frame.css 收录 / ACCEPTED_VARIANCE 记名方差）")
    return cross


def _enclosing_masthead(text: str, pos: int) -> tuple[int, int] | None:
    """pos 所在的最内层 masthead 容器区间（header / div.top|cover|hero）；无则 None。"""
    opens = [(m.start(), m.end(), "header") for m in _HEADER_OPEN_RE.finditer(text)]
    for m in _DIV_OPEN_RE.finditer(text):
        cm = re.search(r'class="([^"]*)"', m.group(1))
        if cm and {"top", "cover", "hero"} & set(cm.group(1).split()):
            opens.append((m.start(), m.end(), "div"))
    for start, end, tag in reversed([s for s in sorted(opens) if s[0] < pos]):
        depth, i = 1, end
        for tm in re.finditer(rf"<{tag}\b[^>]*>|</{tag}\s*>", text[i:], re.I):
            depth += -1 if tm.group(0).startswith("</") else 1
            if depth == 0:
                if i + tm.end() > pos:
                    return start, i + tm.end()
                break
    return None


def _inject_head(prefix: str, entry: dict | None) -> str:
    """A-2 color-scheme / A-3 Google Fonts 剥离 / A-4 title+description+og。"""
    prefix = re.sub(  # A-3：外链字体大陆不可达且与站点字体栈冲突；其余 link 保留（C-8）
        r'[ \t]*<link[^>]*href="https://fonts\.(?:googleapis|gstatic)\.com[^"]*"[^>]*>\n?', "", prefix)
    title, summary = (entry or {}).get("title") or "", (entry or {}).get("summary") or ""
    # A-4/设计侧 P0（2026-10-16 实锤）：og:description 曾直接用 md 摘要自由文本，
    # 上游的 🔺 箭头 emoji 泄漏进 <head> —— 分享到社交平台会显示成裸 emoji，
    # 违反团队 P0-1 且 sanitizer 只扫 body 不扫 head。
    # 修：优先用结论先行文本（已是纯文本契约），并再剥一次 emoji + 截断 160 字
    # （og:description 超过此长度会被社交平台截断，反而丢失结论）。
    summary = (entry or {}).get("conclusion") or summary
    summary = _EMOJI_HEAD.sub("", summary)
    summary = re.sub(r"\s{2,}", " ", summary).strip()[:160]
    tm = re.search(r"<title>(.*?)</title>", prefix, re.S | re.I)   # A-4 title 追加站点名
    new_title = ""
    if tm and "每日市场脉搏" not in tm.group(1):
        t = f"<title>{tm.group(1)}{SITE_TITLE_SUFFIX}</title>"
        prefix = prefix[:tm.start()] + t + prefix[tm.end():]
    elif not tm and title:
        new_title = f"\n<title>{C.esc(title)}{SITE_TITLE_SUFFIX}</title>"
    hm = re.search(r"<head[^>]*>", prefix, re.I)
    if not hm:
        return prefix
    add = new_title
    if not re.search(r'<meta[^>]*name="color-scheme"', prefix, re.I):   # A-2 缺失才补
        add += '\n<meta name="color-scheme" content="light dark">'
    metas = [("name", "description", summary), ("property", "og:title", title),
             ("property", "og:description", summary), ("property", "og:type", "article")]
    for attr, kind, val in metas:
        if val and not re.search(rf'<meta[^>]*{attr}="{kind}"', prefix, re.I):
            add += f'\n<meta {attr}="{kind}" content="{C.esc(val)}">'
    return prefix[:hm.end()] + add + prefix[hm.end():]


def _promote_title(inner: str, entry: dict | None) -> tuple[str, str, int]:
    """A-7：首个标题提升为 h1.doc-title；masthead 内的移出到容器之前（硬约束，防 fg-on-fg 隐形标题 §3.3）。返回 (新 inner, 备注, h1 结束位置)。"""
    m = _HEADING_RE.search(inner)
    if not m:
        title = (entry or {}).get("title") or ""
        if not title:
            return inner, "A-7 无标题且无 entry 标题可生成", -1
        h1 = f'<h1 class="doc-title" data-df-title="gen">{C.esc(title)}</h1>'
        return h1 + "\n" + inner, "A-7 标题生成(gen)", len(h1)
    attrs = m.group("attrs").rstrip()
    cm = re.search(r'class="([^"]*)"', attrs)
    if cm:
        cls = [c for c in cm.group(1).split() if c != "doc-title"] + ["doc-title"]
        attrs = attrs[:cm.start()] + f'class="{" ".join(cls)}"' + attrs[cm.end():]
    else:
        attrs += ' class="doc-title"'
    h1 = f'<h1{attrs} data-df-title="1">{m.group("body")}</h1>'
    mast = _enclosing_masthead(inner, m.start())
    if mast:                                   # 移出是硬约束不是优化项（§3.3）
        inner = inner[:m.start()] + inner[m.end():]
        return (inner[:mast[0]] + h1 + "\n  " + inner[mast[0]:],
                "A-7 标题移出 masthead", mast[0] + len(h1))
    return (inner[:m.start()] + h1 + inner[m.end():],
            "A-7 标题提升(原位)", m.start() + len(h1))


def _enhance(inner: str, rating, has_meta: bool) -> tuple[str, list[str]]:
    """A-9 结构化去重与增强（表格包裹 / 评级徽章升级 / .top meta 与空容器摘除）。"""
    notes: list[str] = []
    n = 0

    def wrap(m: re.Match) -> str:
        nonlocal n
        table = m.group(0)
        orig = table[:table.index(">") + 1]
        if inner[max(0, m.start() - 80):m.start()].rstrip().endswith('<div class="tbl-wrap">'):
            return table                          # C-6：已有父级不重复包
        km = re.search(r'class="([^"]*)"', orig)
        if km:
            cls = km.group(1).split()
            if "tbl" not in cls:
                cls.append("tbl")
            head = orig[:km.start()] + f'class="{" ".join(cls)}"' + orig[km.end():]
        else:
            head = orig[:-1] + ' class="tbl">'
        n += 1
        return f'<div class="tbl-wrap">{head}{table[len(orig):]}</div>'

    inner = _TABLE_RE.sub(wrap, inner)
    if n:
        notes.append(f"A-9 表格包裹 {n}")
    if rating:
        k = 0

        def badge(m: re.Match) -> str:
            nonlocal k
            km = re.search(r'class="([^"]*)"', m.group("attrs"))
            tokens = set(km.group(1).split()) if km else set()
            if "rating" not in tokens or any(t.startswith("rating-") for t in tokens):
                return m.group(0)                 # 非评级 / 已是徽章（含 doc-meta 徽章）
            if m.group("text").strip().strip("【】") != rating:
                return m.group(0)
            k += 1
            return R.rating_badge(rating)

        inner = _RATING_RE.sub(badge, inner)
        if k:
            notes.append(f"A-9 评级徽章升级 {k}")
    if has_meta:  # §3.5-3 .top .meta 摘除（信息已迁入 .doc-meta 才执行）
        m = re.search(r'(<div\s+class="top"[^>]*>)\s*<div\s+class="meta"[^>]*>.*?</div\s*>', inner, re.S | re.I)
        if m:
            inner = inner[:m.start()] + m.group(1) + inner[m.end():]
        em = re.search(r'\s*<div\s+class="top"[^>]*>(.*?)</div\s*>', inner, re.S | re.I)
        if em and "<" not in em.group(1) and not em.group(1).strip():
            inner = inner[:em.start()] + inner[em.end():]   # §3.5-4 空容器移除
    return inner, notes


def frame_one(html: str, entry: dict | None, date: str, slug: str) -> tuple[str, list[str]]:
    """单文件框架注入（A-1 ~ A-10）。返回 (新 HTML, 审计备注)。"""
    notes: list[str] = []
    bm = re.search(r"<body([^>]*)>(.*)</body\s*>", html, re.S | re.I)
    if not bm or not re.search(r"</head\s*>", html, re.I):
        raise ValueError("页面缺少 <body>/</head> 结构，无法注入框架")
    prefix, suffix, attrs = html[:bm.start()], html[bm.end():], bm.group(1)
    inner = bm.group(2)
    if (s := _MINIMAL_SPRITE_RE.sub("", inner)) != inner:    # A-5 摘除后端最小 sprite
        notes.append("A-5 摘除最小 sprite")
        inner = s
    up_cls = {c for m in re.finditer(r'class="([^"]*)"', inner)  # C-14 门禁（注入铬件前）
              for c in m.group(1).split()}
    notes.append("C-14 交叉类: " + (", ".join(_conflict_gate(up_cls, f"{date}/{slug}")) or "无"))
    inner, tnote, h1_end = _promote_title(inner, entry)     # A-7 标题提升与移出
    notes.append(tnote)
    meta = R.detail_meta(entry) if entry else ""            # A-8 元信息行插到 h1 之后
    if meta and h1_end >= 0:
        inner = inner[:h1_end] + "\n      " + meta + inner[h1_end:]
        notes.append("A-8 doc-meta")
    inner, enotes = _enhance(inner, (entry or {}).get("rating"), bool(meta))
    notes.extend(enotes)
    cm = re.search(r'class="([^"]*)"', attrs)               # A-6 body 类过滤 + 幂等标记
    old = cm.group(1).split() if cm else []
    kept = [c for c in old if not _BODY_LAYOUT_RE.match(c)]
    if len(kept) != len(old):
        notes.append("A-6 body 布局类过滤 %d: %s" % (
            len(old) - len(kept), " ".join(c for c in old if c not in kept)))
    class_attr = f' class="{" ".join(kept)}"' if kept else ""
    attrs_rest = re.sub(r'\s*class="[^"]*"', "", attrs)
    body_tag = (f'<body{attrs_rest}{class_attr} {MARKER_ATTR} '
                f'data-date="{date}" data-slug="{slug}">')
    name, _t, _b, ico = C.TASK_META.get(slug, (slug, "—", "", "file-text"))
    doc = (f'{MARKER_COMMENT}\n{T.icon_sprite()}\n'
           f'<a class="skip-link" href="#main">跳到主要内容</a>\n'
           f'{R.detail_nav(date, DEPTH)}\n<main id="main" class="frame">\n'
           f'<div class="doc">\n{R.detail_crumb(date, name, DEPTH)}\n'
           f'<p class="df-kicker">{T.icon(ico)}{C.esc(name)}</p>\n'
           f'{inner}\n</div>\n</main>\n'
           f'{R.detail_footer(DEPTH, entry, date)}\n')
    # A-1 ~ A-4：head 注入；四层 CSS 必须最后进 head（级联次序胜出，§5.2）
    prefix = _inject_head(prefix, entry)
    prefix = re.sub(r"</head\s*>", f"<style {STYLE_ORIGIN}>{T.inject_tokens(T.detail_frame_css())}</style>\n</head>",
                    prefix, count=1, flags=re.I)
    return prefix + body_tag + doc + "</body>" + suffix, notes


def run(daily_dir: Path, dry_run: bool = False, report_path: str | None = None) -> int:
    """批量框架注入。原子写（临时文件 + rename），崩溃不留下半框架页面。"""
    audits: list[dict] = []
    for date_dir in sorted(p for p in daily_dir.iterdir() if p.is_dir()):
        if not (ef := date_dir / "entries.json").is_file():
            continue
        try:
            entries = json.loads(ef.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"  [frame][warn] entries.json 解析失败，已跳过 {ef}: {e}")
            continue
        for e in entries:
            fname = e.get("html")
            if not fname:
                continue                                   # md-only 条目无详情页
            p = date_dir / fname
            if not p.is_file():
                print(f"  [frame][warn] entries.json 引用缺失: {p}")
                continue
            original = p.read_text(encoding="utf-8")
            if MARKER_ATTR in original:
                continue                                # 幂等：整文件跳过
            date, slug = date_dir.name, e.get("slug") or p.stem
            try:
                framed, notes = frame_one(original, e, date, slug)
            except ValueError as ex:
                print(f"  [frame][ERROR] {p.relative_to(daily_dir)}: {ex}")
                return 1
            audits.append({"file": str(p.relative_to(daily_dir)), "date": date,
                           "slug": slug, "changed": framed != original, "actions": notes})
            if not dry_run and framed != original:
                tmp = p.parent / (p.name + ".frame-tmp")
                tmp.write_text(framed, encoding="utf-8")
                tmp.replace(p)
            print(f"  [frame] {p.relative_to(daily_dir)}: {'; '.join(notes)}")
    if report_path:
        rp = Path(report_path)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps({"files": audits}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [frame][report] {rp}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="上游详情页阅读框架注入（sanitize 之后）")
    ap.add_argument("--dir", required=True, help="daily 目录（读其 <date>/entries.json）")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    ap.add_argument("--report", help="审计报告 JSON 落盘路径")
    args = ap.parse_args()
    d = Path(args.dir)
    if not d.is_dir():
        print(f"[ERROR] 目录不存在: {d}", file=sys.stderr)
        return 1
    return run(d, dry_run=args.dry_run, report_path=args.report)


if __name__ == "__main__":
    sys.exit(main())
