#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""build_site.py — 站点结构层生成器（编排入口，只做装配）

职责边界（code-organization §4 硬规则：入口文件只装配）：
  · 扫描 _stage/docs/daily/<date>/ 下的 meta.json + entries.json；
  · 分组（周 / 月）、调用 site_pages 渲染、落盘；
  · 打印 SITE_FILE:<路径> 协议行供 publish_to_github.py 收集。
详情页阅读框架注入（frame_pass：slim 导航/阅读容器/页脚）在本入口内编排，
顺序是设计约束（§1.1/C-10）：sanitize → frame → 框架页生成；--no-frame 可关。
本文件不含 CSS、不含 HTML 片段、不含业务判断：
  样式 → design-tokens.css + site_components.css（经 site_theme 注入）
  片段 → site_render    整页 → site_pages    语义 → site_content

输出：
  docs/index.html                首页（日期分组 + 每日时间线）
  docs/daily/<date>/index.html   日期页
  docs/weekly/<YYYY-Www>/index.html   周归档页
  docs/monthly/<YYYY-MM>/index.html   月归档页
  docs/feed.xml                  RSS 2.0（条目级：每个任务条目一个 item，P-2）
  docs/rss.xml                   RSS 别名（兼容默认 rss.xml 路径的阅读器）
  docs/subscribe/index.html     订阅页（RSS 产品化入口：地址 + 阅读器指引）
  docs/sitemap.xml               全量 URL
  docs/methodology/index.html    方法论页
  docs/manifest.webmanifest     PWA 清单（P-3）
  docs/apple-touch-icon.png     iOS 主屏图标 180×180（P-3，纯标准库绘制）
  docs/icon-192.png / icon-512.png   PWA 图标两档（P-3）

用法：
  python3 build_site.py --stage <_stage 目录> [--base-url <URL>] [--methodology-src <文件>] [--no-frame]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import frame_pass as F          # noqa: E402  详情页阅读框架注入（sanitize 之后）
import gen_app_icon as GI       # noqa: E402  PWA 图标（纯标准库绘制，P-3）
import site_pages as P            # noqa: E402
import site_theme as T            # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_METHODOLOGY = HERE.parent / "site" / "methodology" / "index.html"


def _pwa_manifest() -> str:
    """PWA 清单（P-3）。background/theme 色用字面量：清单是独立 JSON 文件，
    浏览器不对其解析 CSS 变量，var(--token) 在此无效；取值与
    design-tokens.css 的 --ap-white(#ffffff) / --ap-blue(#0071e3) 逐字一致
    （浅色画布 + 交互蓝），改 token 须同步此处。
    start_url/scope 用相对 "./"：清单位于 docs/ 根，相对解析对
    GitHub Pages 项目路径 / 自定义域名 / 本地静态服务三种部署全部成立。"""
    return json.dumps({
        "name": "每日市场脉搏",
        "short_name": "市场脉搏",
        "description": "数据驱动的 A 股 / 基金每日研判档案",
        "lang": "zh-CN",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0071e3",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png",
             "purpose": "any maskable"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png",
             "purpose": "any maskable"},
        ],
    }, ensure_ascii=False, indent=2) + "\n"


def load_dates(daily_dir: Path) -> list[dict]:
    """加载全部日期 meta + entries（倒序，最新在前）。

    entries.json 是时间线的唯一数据源（由 publish_to_github.py 写入）；
    缺失时降级为空列表，页面渲染「本期无分项产出记录」，不伪造条目。
    """
    metas: list[dict] = []
    for p in sorted(daily_dir.glob("*/meta.json"), reverse=True):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            m.setdefault("entries", [])
            ef = p.parent / "entries.json"
            if ef.exists():
                m["entries"] = json.loads(ef.read_text(encoding="utf-8"))
            metas.append(m)
        except (OSError, ValueError) as e:
            # 单个日期损坏不阻断整站生成：跳过并显式告警，绝不静默吞掉
            print(f"  [warn] meta.json 解析失败，已跳过 {p}: {e}")
    return metas


def group_by_period(metas: list[dict]) -> tuple[dict[str, list], dict[str, list]]:
    """按 ISO 周 / 月分组。日期非法则跳过该条，不让一条脏数据毁掉整页。"""
    weeks: dict[str, list] = {}
    months: dict[str, list] = {}
    for m in metas:
        date = m.get("date", "")
        try:
            iso = datetime.strptime(date, "%Y-%m-%d").isocalendar()
        except (ValueError, TypeError):
            print(f"  [warn] 非法 date 字段，已跳过: {date!r}")
            continue
        weeks.setdefault(f"{iso.year}-W{iso.week:02d}", []).append(m)
        months.setdefault(date[:7], []).append(m)
    return weeks, months


def main() -> int:
    ap = argparse.ArgumentParser(description="站点结构层生成器（Apple 设计语言）")
    ap.add_argument("--stage", required=True, help="_stage 目录")
    ap.add_argument("--base-url", default="https://seaquake97.github.io/daily-market-pulse/")
    ap.add_argument("--methodology-src", default=None)
    ap.add_argument("--no-frame", action="store_true",
                    help="跳过详情页阅读框架注入（frame_pass，仅回退通道用）")
    args = ap.parse_args()

    # Token 层自检：关键变量缺失即构建失败，避免产出「看着正常其实没样式」的静默页面
    T.require_tokens(T.load_tokens())

    stage = Path(args.stage)
    daily_dir = stage / "docs" / "daily"
    if not daily_dir.is_dir():
        print(f"[fail] daily 目录不存在: {daily_dir}")
        return 2

    metas = load_dates(daily_dir)
    # frame_pass：详情页包站点铬件。顺序是设计约束（§1.1/C-10）——必须晚于
    # sanitize_body.py 且输出绝不再回消毒；框架页随后生成，两者互不覆盖。
    if not args.no_frame and F.run(daily_dir) != 0:
        print("[fail] frame_pass 注入失败，已中止（详情页保持 sanitize 后原状）")
        return 3
    weeks, months = group_by_period(metas)
    generated: list[str] = []

    def emit(rel: str, content: str) -> None:
        p = stage / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        generated.append(rel)

    emit("docs/index.html", P.home(metas))
    for m in metas:
        emit(f"docs/daily/{m['date']}/index.html", P.day(m))

    # 周报 / 月报总览页：导航的 weekly/ 与 monthly/ 入口必须真实可达。
    # 此前只生成具体期页 → 5 个页面 × 2 入口 = 80 处死链，线上 404（PM 实测）。
    emit("docs/weekly/index.html",
         P.archive_index("weekly", [(w, f"周报 {w}") for w in sorted(weeks, reverse=True)]))
    emit("docs/monthly/index.html",
         P.archive_index("monthly", [(m, f"月报 {m}") for m in sorted(months, reverse=True)]))

    for wk, ms in sorted(weeks.items(), reverse=True):
        emit(f"docs/weekly/{wk}/index.html",
             P.group(f"周归档 · {wk}", f"Weekly archive {wk}", ms, "../../",
                     "weekly", f"周报 {wk}"))
    for mo, ms in sorted(months.items(), reverse=True):
        emit(f"docs/monthly/{mo}/index.html",
             P.group(f"月归档 · {mo}", f"Monthly archive {mo}", ms, "../../",
                     "monthly", f"月报 {mo}"))

    emit("docs/feed.xml", P.feed(metas, args.base_url))
    # rss.xml 别名：部分阅读器 / 聚合工具默认找 rss.xml，404 会直接判「无订阅源」
    emit("docs/rss.xml", P.feed(metas, args.base_url))
    # feed.json：机器可读数据源（小程序 / PWA / 第三方集成，ARCH-R6 §3.1）
    emit("docs/api/feed.json", P.json_feed(metas, args.base_url))
    # PWA 三件套（P-3）：清单 + 三档图标。图标由纯标准库绘制（禁 Pillow），
    # 同输入必得同字节；走 SITE_FILE 协议，publish 全量推送不落件。
    emit("docs/manifest.webmanifest", _pwa_manifest())
    for p in GI.write_all(stage / "docs"):
        generated.append(str(p.relative_to(stage)))
    emit("docs/subscribe/index.html", P.subscribe(metas, args.base_url))
    emit("docs/sitemap.xml", P.sitemap(
        metas, args.base_url,
        ["subscribe/", "methodology/"] + [f"weekly/{w}/" for w in weeks] + [f"monthly/{m}/" for m in months]))

    src = Path(args.methodology_src) if args.methodology_src else DEFAULT_METHODOLOGY
    if src.exists():
        # 用「当期数据日期」而非运行时刻：后者每次都变，破坏发布幂等性
        stamp = metas[0].get("date", "") if metas else ""
        html = src.read_text(encoding="utf-8").replace("__GENERATED_AT__", stamp)
        # 导航注入：静态方法论页复用 site_render._nav()（全站导航单一生产者）。
        # 2026-10-16 前该页导航在本文件写死，漂移出 href="../feed.xml" —— 方法论页
        # 右上角订阅入口直达裸 XML（用户实锤）。凡静态页需要导航，一律走占位符。
        html = html.replace("<!--__NAV__-->", P.R.nav_block("../", "methodology"))
        # 方法论页与结构层共用同一套 Token + 组件样式，避免两套设计语言分裂
        emit("docs/methodology/index.html",
             html.replace("/*__TOKENS__*/", T.inject_tokens()))
    else:
        print(f"  [warn] methodology 源不存在，已跳过: {src}")

    total = sum(len(m.get("entries", [])) for m in metas)
    gaps = sum(1 for m in metas for e in m.get("entries", []) if e.get("sigma") is None)
    print(f"站点结构层: {len(metas)} 个日期页 / {total} 条时间线条目"
          f"（其中 Σ 数据缺口 {gaps} 条）/ {len(weeks)} 周归档 / {len(months)} 月归档"
          f" / feed / rss.xml 别名 / subscribe 订阅页 / sitemap / methodology"
          f" / PWA 三件套（manifest + 3 图标）")
    for rel in generated:
        print(f"SITE_FILE:{rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())