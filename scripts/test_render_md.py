#!/usr/bin/env python3
"""test_render_md.py — 统一渲染器回归（FRAMEWORK-DESIGN v2.0 §2 契约）。

覆盖：三份真实 md 渲染合规 / meta 三级兜底 / 标题规范全表 / 表格与任务列表 /
XSS 转义 / 幂等 / 正文无损 / sanitize 固定点 / emoji 零容忍 / publish 接线。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
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


def _write_tmp(text: str) -> Path:
    fd, name = tempfile.mkstemp(suffix=".md")
    os.write(fd, text.encode("utf-8"))
    os.close(fd)
    return Path(name)


def _render(slug, date, md_path, market_data=None):
    raw = md_path.read_text(encoding="utf-8")
    meta = RM.extract_meta(raw, market_data)
    return RM.build_page(slug, date, meta, RM.render_md(raw)), meta


class TestRealOutputs(unittest.TestCase):
    """三份真实 md：合规性 + meta 兜底路径。"""

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
        # C-14 契约（2026-10-16 实证）：tag-gap 在 site_blocks.css 有定义但
        # detail-frame.css 未收录，frame_pass 门禁 SystemExit FATAL；缺口徽章
        # 必须用 `.tag gap` 双类（§4 `.doc .tag.gap` 是其再皮肤规则）
        self.assertIn('class="tag gap"', page)
        self.assertNotIn("tag-gap", page, "禁连字符复合类：撞 frame_pass C-14")
        self.assertNotIn("rating rating-", page, "禁编造评级徽章")

    def test_meta_l3_market_data_fallback(self):
        # L1/L2 全缺时回落 market_data.json verdict（--market-data 传入）
        p = _write_tmp("# 标题\n正文既无评级行也无数据时点行")
        md_obj = {"verdict": {"rating": "防守", "sigma": -0.32},
                  "data_stage": "close"}
        meta = RM.extract_meta(p.read_text(encoding="utf-8"), md_obj)
        self.assertEqual((meta["rating"], meta["stage"], meta["source"]),
                         ("防守", "close", "market_data"))
        # L3 也缺 → 仍诚实降级，禁编造
        meta2 = RM.extract_meta(p.read_text(encoding="utf-8"), {"verdict": {}})
        self.assertEqual((meta2["rating"], meta2["source"]), (None, "none"))

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
        # TASK_NAMES 与 publish 同源复制（禁反向 import 拖垮发布管线），
        # 漂移即标题错位——此处钉死两表一致
        import publish_to_github as P
        self.assertEqual(RM.TASK_NAMES, P.TASK_NAMES)

    def test_weekday(self):
        self.assertIn("（周四）", RM.render_title("fund-guide", "2026-10-15", "intraday"))


class TestStructures(unittest.TestCase):
    """表格 / 任务列表 / 标题层级 / 章节映射 / 行内 markup / XSS。"""

    def test_table(self):
        p = _write_tmp("# T\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 \\| 4 | 5 |\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertIn('<div class="tbl-wrap"><table class="tbl">', body)
        self.assertEqual((body.count("<th>"), body.count("<td>")), (2, 4))
        self.assertIn("3 | 4", body, "转义竖线还原")

    def test_task_list_badges(self):
        p = _write_tmp("# T\n\n- [x] 已完成项\n- [ ] 未完成项\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        for frag in ("#i-check", "#i-ban", "已完成项"):
            self.assertIn(frag, body)

    def test_heading_levels_aligned(self):
        """首个 md H1 剥离（规范标题由 build_page 注入），H2/H3 → h4。"""
        p = _write_tmp("# H1\n\n## H2\n\n### H3\n\n正文")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertNotIn("<h1", body)
        self.assertNotIn("<h2", body)
        self.assertNotIn("<h3", body, "H1 已剥离，H2/H3 统一降为 h4")
        self.assertEqual(body.count('data-sb-h="rendered"'), 2, "H2/H3 两级")

    def test_first_h1_stripped_but_later_kept(self):
        """回归：只剥首个 H1；子章节 H1（上游少见的写法）必须保留。"""
        p = _write_tmp("# 主标题\n\n正文甲\n\n# 附录标题\n\n正文乙\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertNotIn("主标题", body, "首个 H1 由规范标题承载")
        self.assertIn("附录标题", body, "第二个 H1 是子章节，必须保留")
        self.assertIn("正文甲", body)
        self.assertIn("正文乙", body)

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

    def test_math_shell_stripped(self):
        p = _write_tmp("评分：$$\\Sigma = -0.011 \\quad (\\text{权重 } 1.00)$$\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertNotIn("$", body)
        self.assertNotIn("\\Sigma", body)
        self.assertIn("Σ = -0.011", body)
        self.assertIn("权重", body)
        # 回归：\; 分支禁误伤 HTML 实体分号（2026-10-16 实测坑）
        p2 = _write_tmp("小于 <50% 与 $x \\; y$\n")
        body2 = RM.render_md(p2.read_text(encoding="utf-8"))
        self.assertIn("&lt;50%", body2, "实体分号必须保留")

    def test_inline_markup(self):
        p = _write_tmp("**粗** *斜* `码` [链](http://x) ~~删~~\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        for frag in ("<b>粗</b>", "<i>斜</i>", "<code>码</code>",
                     '<a href="http://x">链</a>', "<del>删</del>"):
            self.assertIn(frag, body)

    def test_xss_escaped(self):
        # 上游 md 的裸 HTML/脚本必须转义为实体，禁直通（P0）
        p = _write_tmp("<script>alert(1)</script> 与 <img onerror=x> 与 <50% 比较\n")
        body = RM.render_md(p.read_text(encoding="utf-8"))
        self.assertEqual(body.count("<script"), 0)
        self.assertNotIn("<img onerror", body)
        for frag in ("&lt;script&gt;", "&lt;50%"):
            self.assertIn(frag, body)

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
                # render 产物未过 sanitize，功能图标位 emoji 仍在——同口径剥除
                text = P0_EMOJI.sub("", text)
                text = re.sub(r"\s+", "", text)
                md = path.read_text(encoding="utf-8")
                miss = []
                first_h1_skipped = False
                for raw in md.splitlines():
                    s = raw.strip()
                    if not s or s.startswith(("|", "---", "<!--", "```")):
                        continue
                    # 标题行按渲染器同规则清洗（emoji/破折号副标题为设计内剥离）
                    if s.startswith("# "):
                        # 首个 md H1 由 build_page 注入的规范标题承载（设计内替换），
                        # 其余 H1 是子章节，正文必须出现。
                        if not first_h1_skipped:
                            first_h1_skipped = True
                            continue
                        s = re.sub(r"\s*[—–]\s+.*$", "", RM._clean_title(s))
                        s = s.replace("\ufe0f", "").replace("\u200d", "")
                    # 设计内转换的对照口径：emoji→SVG、数学记号按 _math_text 转写
                    s = P0_EMOJI.sub("", s)
                    s = re.sub(r"\$+([^$]+)\$+", lambda m: RM._math_text(m.group(1)), s)
                    # 引用行首 > 先剥（内容中的 > 如「>15 亿元」是内容，保留）
                    if s.startswith(">"):
                        s = s.lstrip(">").strip()
                    t = re.sub(r"~~(.+?)~~", r"\1", s)  # 删除线取内容
                    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)  # 链接取文本
                    # 只剥真语法符：# ** * `（~ 与 > 是内容字符：20.85~21.00、>15 亿）
                    t = re.sub(r"[#*`]", "", t)
                    t = re.sub(r"^\s*(?:\d{1,2}[.、)]|[①-⑳]|[-*])\s*", "", t).strip()
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

    def test_real_md_zero_emoji_p0(self):
        # P0：功能图标禁 emoji——渲染产物零 emoji（emoji_map 命中转 SVG，装饰性剥离留痕）
        for slug, path in REAL_MD:
            with self.subTest(slug=slug):
                page, _ = _render(slug, "2026-10-16", path)
                self.assertEqual(P0_EMOJI.findall(page), [],
                                 "渲染产物禁 emoji（P0）")


class TestPublishWiring(unittest.TestCase):
    """接线契约：publish 步骤 4.1 渲染 md-only 任务后必须回写 entry["html"]。"""

    def test_cli_render_and_entry_html_contract(self):
        import publish_to_github as P
        with tempfile.TemporaryDirectory() as td:
            md_path = Path(td) / "fund-guide.md"
            md_path.write_text("# 指引\n\n## 核心决策卡\n\n结论：均衡。\n",
                               encoding="utf-8")
            html_path = Path(td) / "fund-guide.html"
            r = subprocess.run([PY, str(HERE / "render_md.py"),
                                "--md", str(md_path), "--slug", "fund-guide",
                                "--date", "2026-10-16", "--out", str(html_path)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(html_path.is_file(), "渲染产物必须落盘")
            entry = {"md": md_path, "html": html_path}     # ← publish 回写点
            e = P.extract_entry("fund-guide", entry, None, "2026-10-16")
            self.assertEqual(e["html"], "fund-guide.html")
            self.assertEqual(e["title"], "基金操作指引 · 2026-10-16（周五）尾盘")
            # 负向契约：不回写则 entries.json 记 null，frame_pass（C-1）跳过
            e0 = P.extract_entry("fund-guide", {"md": md_path}, None, "2026-10-16")
            self.assertIsNone(e0["html"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
