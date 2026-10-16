#!/usr/bin/env python3
"""test_render_md.py — 统一渲染器回归（FRAMEWORK-DESIGN v2.0 §2 契约）。

覆盖：三份真实 md 渲染合规性 / meta 三级兜底 / 标题规范全表 /
表格与任务列表结构 / 幂等 / 正文无损 / sanitize 固定点 / 接线行为。
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PY = "/Users/lianghaizhen/.workbuddy/binaries/python/envs/default/bin/python3"
sys.path.insert(0, str(HERE))

import render_md as RM  # noqa: E402

SRC = Path("/Users/lianghaizhen/WorkBuddy")
REAL_MD = [
    ("fund-guide", SRC / "基金每日操作指引（14:30）/2026-10-16/fund_operation_guide.md"),
    ("stock-assistant", SRC / "股票助手/2026-10-16/stock_assistant.md"),
    ("fund-market", SRC / "基金每日盘面分析（11:00）/2026-10-16/fund_market_analysis.md"),
]
P0_EMOJI = re.compile("[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF\uFE00-\uFE0F]")


def _render(slug, date, md_path, market_data=None):
    meta = RM.extract_meta(md_path.read_text(encoding="utf-8"), market_data)
    return RM.build_page(slug, date, meta, RM.render_md(md_path.read_text(encoding="utf-8"))), meta


class TestRealOutputs(unittest.TestCase):
    """三份真实 md：合规性 + 结构 + meta 兜底路径。"""

    def test_real_md_render_compliant(self):
        for slug, path in REAL_MD:
            with self.subTest(slug=slug):
                page, _ = _render(slug, "2026-10-16", path)
                self.assertEqual(page.count("<script"), 0, "零 script")
                self.assertNotIn("gradient", page, "零渐变")
                bare = re.findall(r"#[0-9a-fA-F]{3,6}\b", re.sub(r"var\([^)]*\)", "", page))
                self.assertEqual(bare, [], f"零裸 hex: {bare[:3]}")
                self.assertIn("data-sb-h", page)

    def test_meta_fallback_chain(self):
        # 存量 md 无 front-matter → L2 启发式或 L3 market_data
        path = REAL_MD[0][1]
        md_text = path.read_text(encoding="utf-8")
        md_obj = json.loads((path.parent / "market_data.json").read_text(encoding="utf-8"))
        meta = RM.extract_meta(md_text, md_obj)
        self.assertIn(meta["source"], ("heuristic", "market_data", "front-matter"))
        self.assertEqual(meta["rating"], "信号矛盾")
        self.assertEqual(meta["stage"], "intraday")

    def test_meta_all_missing_degrades_honestly(self):
        p = _write_tmp("# 标题\n无评级无时点的正文")
        meta = RM.extract_meta(p.read_text(encoding="utf-8"), None)
        self.assertIsNone(meta["rating"])
        self.assertEqual(meta["source"], "none")
        page, _ = _render("fund-guide", "2026-10-16", p, None)
        self.assertIn("tag-gap", page)
        self.assertNotIn("rating rating-", page, "禁编造评级徽章")

    def test_front_matter_priority(self):
        p = _write_tmp("---\nrating: 进攻\nstage: pre_open\n---\n\n# 标题\n正文")
        meta = RM.extract_meta(p.read_text(encoding="utf-8"), None)
        self.assertEqual(meta["rating"], "进攻")
        self.assertEqual(meta["source"], "front-matter")


class TestTitleSpec(unittest.TestCase):
    """标题规范全表（§2.1）。"""

    def test_all_slugs(self):
        cases = {
            "stock-assistant": "股票助手 · 2026-10-16（周五）早盘竞价",
            "fund-market": "基金盘面分析 · 2026-10-16（周五）午盘",
            "fund-guide": "基金操作指引 · 2026-10-16（周五）尾盘",
            "stock-review": "股票复盘 · 2026-10-16（周五）收盘",
            "daily-review": "每日总复盘 · 2026-10-16（周五）收盘",
        }
        for slug, want in cases.items():
            with self.subTest(slug=slug):
                self.assertEqual(RM.render_title(slug, "2026-10-16", "intraday"), want)

    def test_weekday(self):
        self.assertIn("（周四）", RM.render_title("fund-guide", "2026-10-15", "intraday"))


class TestStructures(unittest.TestCase):
    """表格 / 任务列表 / 标题层级 / 章节映射。"""

    def test_table(self):
        p = _write_tmp("# T\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 \\| 4 | 5 |\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertIn('<div class="tbl-wrap"><table class="tbl">', body)
        self.assertEqual(body.count("<th>"), 2)
        self.assertEqual(body.count("<td>"), 4)
        self.assertIn("3 | 4", body, "转义竖线还原")

    def test_task_list_badges(self):
        p = _write_tmp("# T\n\n- [x] 已完成项\n- [ ] 未完成项\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertIn("#i-check", body)
        self.assertIn("#i-ban", body)
        self.assertIn("已完成项", body)

    def test_heading_levels_aligned(self):
        p = _write_tmp("# H1\n\n## H2\n\n### H3\n\n正文")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertIn("<h3", body)
        self.assertIn("<h4", body)
        self.assertNotIn("<h1", body)
        self.assertNotIn("<h2", body)
        self.assertEqual(body.count('data-sb-h="rendered"'), 3)

    def test_section_class_mapping(self):
        p = _write_tmp("## 核心决策卡\n\n内容\n\n## 免责声明\n\n声明内容\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertIn('class="verdict-card"', body)
        self.assertIn('class="footer-note"', body)

    def test_heading_emoji_stripped(self):
        p = _write_tmp("# 📊 标题（14:30）— daily-decision-engine v1.3（套话）\n\n## 🚦 章节\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertNotIn("📊", body)
        self.assertNotIn("🚦", body)
        self.assertNotIn("daily-decision-engine v1.3", body)
        self.assertIn("标题（14:30）", body)

    def test_math_shell_stripped(self):
        p = _write_tmp("评分：$$\\Sigma = -0.011 \\quad (\\text{权重 } 1.00)$$\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertNotIn("$", body)
        self.assertNotIn("\\Sigma", body)
        self.assertIn("Σ = -0.011", body)
        self.assertIn("权重", body)

    def test_inline_markup(self):
        p = _write_tmp("**粗** *斜* `码` [链](http://x) ~~删~~\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertIn("<b>粗</b>", body)
        self.assertIn("<i>斜</i>", body)
        self.assertIn("<code>码</code>", body)
        self.assertIn('<a href="http://x">链</a>', body)
        self.assertIn("<del>删</del>", body)

    def test_xss_escaped(self):
        # 上游 md 的裸 HTML/脚本必须转义为实体，禁直通（P0）
        p = _write_tmp("<script>alert(1)</script> 与 <img onerror=x> 与 <50% 比较\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertEqual(body.count("<script"), 0)
        self.assertNotIn("<img onerror", body)
        self.assertIn("&lt;script&gt;", body)
        self.assertIn("&lt;50%", body)

    def test_dangerous_url_neutralized(self):
        p = _write_tmp("[点我](javascript:alert(1))\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertNotIn("javascript:", body)
        self.assertIn('href="#"', body)


class TestContract(unittest.TestCase):
    """幂等 / 正文无损 / sanitize 固定点。"""

    def test_idempotent(self):
        for slug, path in REAL_MD:
            with self.subTest(slug=slug):
                a, _ = _render(slug, "2026-10-16", path)
                b, _ = _render(slug, "2026-10-16", path)
                self.assertEqual(a, b)

    def test_content_lossless(self):
        for slug, path in REAL_MD:
            with self.subTest(slug=slug):
                page, _ = _render(slug, "2026-10-16", path)
                text = re.sub(r"<[^>]+>", "", page)
                text = (text.replace("&lt;", "<").replace("&gt;", ">")
                            .replace("&amp;", "&").replace("&quot;", '"'))
                # render 产物未过 sanitize，功能图标位 emoji 仍在——与 md 侧同口径剥除
                text = P0_EMOJI.sub("", text)
                text = re.sub(r"\s+", "", text)
                md = path.read_text(encoding="utf-8")
                miss = []
                for raw in md.splitlines():
                    s = raw.strip()
                    if not s or s.startswith(("|", "---", "<!--", "```")):
                        continue
                    # 标题行按渲染器同规则清洗（emoji/破折号副标题为设计内剥离）
                    if s.startswith("#"):
                        s = re.sub(r"\s*[—–]\s+.*$", "", RM._clean_title(s)) \
                            if s.startswith("# ") else RM._clean_title(s)
                        s = s.replace("\ufe0f", "").replace("\u200d", "")
                    # 设计内转换的对照口径：emoji→SVG（P0 正则剥离）、
                    # 数学记号按 _math_text 转写（内容保留）
                    s = P0_EMOJI.sub("", s)
                    s = re.sub(r"\$+([^$]+)\$+", lambda m: RM._math_text(m.group(1)), s)
                    # 只剥 md 语法符，保留内容连字符/括号（日期 2026-10-16 是内容）
                    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)  # 链接取文本
                    t = re.sub(r"[#*`>~]", "", t)
                    t = re.sub(r"^\s*(?:\d{1,2}[.、)]|[①-⑳]|[-*•])\s*", "", t).strip()
                    t = re.sub(r"\s+", "", t)
                    if len(t) >= 10 and t not in text:
                        miss.append(s[:40])
                self.assertEqual(miss, [], f"内容丢失: {miss[:3]}")

    def test_sanitize_fixed_point(self):
        for slug, path in REAL_MD[:1]:
            with self.subTest(slug=slug):
                page, _ = _render(slug, "2026-10-16", path)
                with tempfile.TemporaryDirectory() as td:
                    f = Path(td) / "page.html"
                    rep = Path(td) / "report.json"
                    f.write_text(page, encoding="utf-8")
                    for _ in range(2):
                        subprocess.run([PY, str(HERE / "sanitize_body.py"),
                                        "--dir", td, "--in-place",
                                        "--report", str(rep)],
                                       capture_output=True, text=True)
                    first = f.read_text(encoding="utf-8")
                    subprocess.run([PY, str(HERE / "sanitize_body.py"),
                                    "--dir", td, "--in-place"],
                                   capture_output=True, text=True)
                    self.assertEqual(first, f.read_text(encoding="utf-8"),
                                     "sanitize 固定点")
                    r = json.loads(rep.read_text(encoding="utf-8"))
                    counts = r["files"][0]["counts"]
                    self.assertEqual(counts.get("needs-manual-review", 0), 0,
                                     "渲染产物消毒零人工确认项")


def _write_tmp(text: str) -> Path:
    """写临时 md fixture，返回路径（调用方负责目录生命周期）。"""
    fd, name = tempfile.mkstemp(suffix=".md")
    import os
    os.write(fd, text.encode("utf-8"))
    os.close(fd)
    return Path(name)


if __name__ == "__main__":
    unittest.main(verbosity=1)
