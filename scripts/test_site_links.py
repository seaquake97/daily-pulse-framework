#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_site_links.py — 全站内链完整性契约（防「点哪都点不动」类故障）

## 为什么有这套测试（2026-10-16 用户实锤）

用户点订阅页后「无法跳转到其他任何页面，点击首页和方法论都还是订阅页」。
根因不是少写一个链接，而是**页面层级与 depth 参数脱钩**：订阅页在
`docs/subscribe/` 子目录，却用 `depth="./"` 渲染导航，于是 `index.html`
被浏览器解析成 `/subscribe/index.html`（本页自己）、`methodology/` 解析成
`/subscribe/methodology/`（不存在）。肉眼点两下才发现，且只此一处。

另一处同源故障：方法论页（静态源）导航写死，漂移出指向裸 XML 的订阅入口。

## 契约

  L-1 存在性：每个页面里所有**站内** href（含 `<a>` 与 `<link rel=alternate>`）
      解析后必须指向 _stage/docs 下真实存在的文件或目录。
  L-2 深度一致：订阅页（一级子目录）导航 depth 必须是 `../`，日期/周/月/方法论
      （二级）必须是 `../../` 或 `../`——用「页面自身 URL 深度」反推校验，
      不硬编码期望值，新增页面时自动适配。
  L-3 无裸 XML 入口：body 内不得出现指向 feed.xml / rss.xml 的可点链接
      （订阅入口必须先落到订阅页；仅 head 的 autodiscovery 合法）。

运行：python3 scripts/test_site_links.py
真实产出缺失即 skip（不伪造样本）。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DOCS = ROOT / "_stage" / "docs"

HREF_RE = re.compile(r'(?:href)="([^"]+)"')
ANCHOR_RE = re.compile(r"^#")


def _pages() -> list[Path]:
    return sorted(DOCS.rglob("*.html")) if DOCS.is_dir() else []


def _depth_from_url(path: Path) -> int:
    """页面在 docs 下的目录层级：docs/x/index.html → 1；docs/index.html → 0。"""
    rel = path.relative_to(DOCS)
    return max(0, len(rel.parts) - 1)


class TestInternalLinksResolve(unittest.TestCase):
    """L-1：站内 href 全部可解析到真实目标。"""

    def test_all_internal_hrefs_resolve(self):
        pages = _pages()
        if not pages:
            self.skipTest(f"真实产出缺失：{DOCS}")
        broken: list[str] = []
        for page in pages:
            text = page.read_text(encoding="utf-8")
            for href in HREF_RE.findall(text):
                if href.startswith(("http://", "https://", "mailto:", "data:")):
                    continue
                if ANCHOR_RE.match(href):
                    continue
                target = href.split("#", 1)[0]
                if not target:
                    continue
                resolved = (page.parent / target).resolve()
                ok = resolved.exists()
                # 目录式链接（结尾 /）落到 index.html 也算有效
                if not ok and href.endswith("/"):
                    ok = (resolved / "index.html").exists()
                if not ok:
                    broken.append(f"{page.relative_to(DOCS)} -> {href}")
        self.assertEqual(broken, [], f"站内断链：{broken[:10]}")

    def test_no_raw_xml_link_in_body(self):
        """L-3：body 内不得有指向裸 XML 源的 <a>（仅 head autodiscovery 合法）。"""
        offenders = []
        for page in _pages():
            text = page.read_text(encoding="utf-8")
            body = text.split("</head>", 1)[-1]
            for href in HREF_RE.findall(body):
                if re.search(r"/(feed|rss)\.xml$", href):
                    offenders.append(f"{page.relative_to(DOCS)} -> {href}")
        self.assertEqual(offenders, [],
                         f"body 内出现裸 XML 订阅入口（应先落订阅页）：{offenders}")

    def test_head_has_no_emoji(self):
        """L-4：<head> 元信息零 emoji。

        2026-10-16 实锤：og:description 沿用 md 摘要自由文本，上游的 🔺 箭头
        emoji 泄漏进 head —— 分享到社交平台即显示裸 emoji（P0-1），而 sanitizer
        只扫 body 不扫 head，这条路径此前无人看守。
        """
        emoji = re.compile("[\U0001F300-\U0001F9FF☀-➿⬀-⯿]")
        bad = []
        for page in _pages():
            text = page.read_text(encoding="utf-8")
            head = text.split("</head>", 1)[0]
            hit = emoji.findall(head)
            if hit:
                bad.append(f"{page.relative_to(DOCS)}: {len(hit)} 个 {hit[:3]}")
        self.assertEqual(bad, [], f"head 内 emoji 泄漏（分享卡片会露出来）：{bad}")

    def test_meta_description_present_and_bounded(self):
        """L-5：每页有 description，且 og:description 不超 200 字（超了社交平台截断）。"""
        bad = []
        for page in _pages():
            text = page.read_text(encoding="utf-8")
            head = text.split("</head>", 1)[0]
            if 'name="description"' not in head:
                bad.append(f"{page.relative_to(DOCS)}: 缺 description")
            m = re.search(r'property="og:description" content="([^"]*)"', head)
            if m and len(m.group(1)) > 200:
                bad.append(f"{page.relative_to(DOCS)}: og:description {len(m.group(1))} 字")
        self.assertEqual(bad, [], f"meta description 契约：{bad}")


class TestNavDepthConsistency(unittest.TestCase):
    """L-2：导航 depth 与页面 URL 深度一致（按实际路径反推，不硬编码）。"""

    def test_nav_depth_matches_page_depth(self):
        for page in _pages():
            text = page.read_text(encoding="utf-8")
            m = re.search(r'<nav class="nav".*?</nav>', text, re.S)
            if not m:
                continue                      # 详情页用 slim 导航，另有契约
                continue
            nav = m.group(0)
            depth = _depth_from_url(page)
            want = "../" * depth
            # 导航里第一个 nav-brand 链接应恰好上跳 depth 层到 index.html
            brand = re.search(r'class="nav-brand" href="([^"]+)"', nav)
            self.assertIsNotNone(brand, f"{page.relative_to(DOCS)} 导航缺 brand")
            got = urlparse(brand.group(1)).path
            expect = Path(*([".."] * depth + ["index.html"])).as_posix()
            self.assertEqual(
                Path(got).as_posix(), expect,
                f"{page.relative_to(DOCS)} nav-brand 深度错配：{got}，应为 {expect}")

    def test_detail_nav_backlink_exists(self):
        """详情页 slim 导航的「返回时间线」必须指向存在的当日 index.html。"""
        missing = []
        for page in _pages():
            if page.name == "index.html":
                continue
            text = page.read_text(encoding="utf-8")
            m = re.search(r'class="df-back" href="([^"]+)"', text)
            if not m:
                continue
            tgt = (page.parent / m.group(1)).resolve()
            if not tgt.exists():
                missing.append(f"{page.relative_to(DOCS)} -> {m.group(1)}")
        self.assertEqual(missing, [], f"详情页返回链接断裂：{missing}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
