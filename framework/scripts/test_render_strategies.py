#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_render_strategies.py — 策略库前端呈现层测试（全离线，纯标准库）

覆盖六件事：真实 YAML 可渲染 / 标签配平 / 类别分组与排序 / 空目录降级 /
数值百分比口径 / 团队 P0-1（零 emoji）。另外补了三条交付线必守的工程约束：
CSS 零颜色字面量、渲染字节确定性、注入脚本 missing-anchor 显式报错。
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import render_strategies as R  # noqa: E402
import inject_strategies as I  # noqa: E402

REAL_STRATEGY_DIR = R.DEFAULT_STRATEGY_DIR
PY = sys.executable or "python3"

# 与 scripts/scan_compliance.P0_EMOJI_RE、test_emoji_body 同口径
P0_EMOJI_RE = re.compile("[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]")
HEX_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3,8})\b")
VOID_TAGS = frozenset("area base br col embed hr img input link meta param "
                      "source track wbr".split())
TAG_RE = re.compile(r"<!--.*?-->|<(/?)([a-zA-Z][a-zA-Z0-9-]*)[^>]*?(/?)>", re.S)

MINIMAL_YAML = (
    "name: minimal\n"
    "display_name: 最小可用策略\n"
    "track: stock\n"
            "category: defensive\n"
    "description: 只有必填字段，没有 principles\n"
    "rules:\n"
    "  - 规则A：跌破观察线分档买入\n"
)
NUMERIC_YAML = (
    "name: numeric\n"
    "display_name: 含数值字段策略\n"
    "track: stock\n"
            "category: execution\n"
    "description: 步长字段应渲染为百分比\n"
    "step_ratio_default: 0.02\n"
    "rules:\n"
    "  - 规则B：涨 2% 卖出一档\n"
)
XSS_YAML = (
    "name: xss\n"
    "display_name: <script>alert(1)</script>\n"
    "track: stock\n"
            "category: strategic\n"
    "description: 属性值里带 \" 与 &\n"
    "holdings_mapped:\n"
    '  - "><img src=x>\n'
    "rules:\n"
    "  - <b>不得绕过转义</b>\n"
)


def _write(d: Path, filename: str, text: str) -> None:
    (d / filename).write_text(text, encoding="utf-8")


def _tag_errors(html: str) -> list[str]:
    """标签配平检查：忽略注释与 void 元素，返回首个不匹配说明。"""
    stack: list[str] = []
    for closing, name, self_closing in TAG_RE.findall(html):
        tag = name.lower()
        if not tag:          # 注释分支被同一正则捕获，三个分组全空，须先滤掉
            continue
        if tag in VOID_TAGS or self_closing:
            continue
        if closing:
            if not stack:
                return [f"多余闭合标签 </{tag}>"]
            if stack[-1] != tag:
                return [f"期望 </{stack[-1]}>，实际 </{tag}>"]
            stack.pop()
        else:
            stack.append(tag)
    return [f"未闭合标签 <{tag}>" for tag in stack]


class PercentFormatTest(unittest.TestCase):
    def test_ratio_to_percent(self):
        self.assertEqual(R.fmt_percent(0.025), "2.5%")
        self.assertEqual(R.fmt_percent(0.02), "2%")
        self.assertEqual(R.fmt_percent(0.035), "3.5%")
        self.assertEqual(R.fmt_percent(1), "100%")
        self.assertEqual(R.fmt_percent(0.0), "0%")

    def test_non_numeric_passthrough(self):
        self.assertEqual(R.fmt_percent("未知"), "未知")


class RealStrategiesTest(unittest.TestCase):
    """对 3 份真实策略 YAML 的端到端渲染。"""

    def setUp(self):
        if not REAL_STRATEGY_DIR.is_dir():
            self.skipTest(f"真实策略目录缺失: {REAL_STRATEGY_DIR}")
        self.fragment = R.render_fragment(REAL_STRATEGY_DIR)

    def test_all_strategy_cards_rendered(self):
        """断言「目录里每个 yaml 都渲染出一张卡」，而非写死张数。

        2026-10-17 双轨隔离新增 2 个基金轨策略后，写死 3 的断言开始说谎——
        策略增减不该需要改测试，而测试漏检策略会让新增策略静默不上线。
        """
        yamls = sorted(REAL_STRATEGY_DIR.glob("*.yaml"))
        self.assertGreaterEqual(len(yamls), 5)
        self.assertEqual(self.fragment.count('<article class="strat-card"'), len(yamls))
        for f in yamls:
            self.assertIn(f'id="strat-{f.stem}"', self.fragment, f"策略 {f.name} 未渲染")

    def test_tags_balanced(self):
        self.assertEqual(_tag_errors(self.fragment), [])

    def test_no_emoji(self):
        self.assertEqual(P0_EMOJI_RE.findall(self.fragment), [])

    def test_category_grouping_and_order(self):
        """分组顺序 + 每类非空（ADR-007 §2.2：基金轨策略必须独立成组）。"""
        blocks = re.split(r'(?=<div class="strat-group")', self.fragment)
        groups: dict[str, list[str]] = {}
        order: list[str] = []
        for b in blocks:
            m = re.search(r'data-category="([a-z]+)"', b)
            if not m:
                continue
            cat = m.group(1)
            groups[cat] = re.findall(r'id="strat-([a-z0-9_]+)"', b)
            order.append(cat)
        known = ["strategic", "execution", "defensive", "trend"]
        self.assertEqual(order[:len(known)], known, "已知类别顺序错乱")
        self.assertTrue(set(order) <= set(known), f"出现未预期类别: {set(order)-set(known)}")
        for cat in known:
            self.assertTrue(groups.get(cat), f"类别 {cat} 下没有任何策略卡片")
        # 双轨在场：基金轨两个策略各自独立成卡（收割 H-1/H-2）
        self.assertIn("fund_dca_discipline", groups["execution"])
        self.assertIn("fund_nav_valuation", groups["trend"])

    def test_badges_and_numeric_fields(self):
        self.assertIn('class="chip strat-cat strat-cat-strategic">战略</span>', self.fragment)
        self.assertIn('class="chip strat-cat strat-cat-defensive">防御</span>', self.fragment)
        self.assertIn("<dt>默认步长</dt><dd>2.5%</dd>", self.fragment)

    def test_holdings_in_mono_style(self):
        self.assertIn('<code class="strat-code">sh600312</code>', self.fragment)
        # 执行类策略无 holdings_mapped，不应渲染空的映射标的
        self.assertEqual(self.fragment.count("映射标的"), 2)

    def test_byte_deterministic(self):
        self.assertEqual(R.render_fragment(REAL_STRATEGY_DIR), self.fragment)

    def test_css_has_no_hardcoded_color(self):
        css = R.strategy_css()
        self.assertEqual(HEX_COLOR_RE.findall(css), [])
        self.assertNotIn("linear-gradient", css)
        self.assertIn("prefers-color-scheme:dark", css)

    def test_css_tokens_all_defined(self):
        """CSS 引用的每个 Token 必须在 design-tokens.css 里有定义。

        var() 引用不存在的变量不会报错，只会静默失效（文字变透明/无圆角），
        属于最典型的沉默逻辑错误——宁可在构建期响亮失败。
        """
        tokens_css_path = ROOT / "design-tokens.css"
        if not tokens_css_path.is_file():
            self.skipTest(f"Token 文件缺失: {tokens_css_path}")
        defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", tokens_css_path.read_text("utf-8")))
        used = set(re.findall(r"var\((--[a-z0-9-]+)", R.strategy_css()))
        self.assertEqual(sorted(used - defined), [], "引用了未定义的 Token")


class EdgeCaseTest(unittest.TestCase):
    """用 tempfile 构造边界策略目录：空目录 / 最小策略 / 转义 / 未知类别。"""

    def test_empty_dir_returns_empty_fragment(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(R.render_fragment(Path(td)), "")

    def test_missing_dir_returns_empty_fragment(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "nope"
            self.assertEqual(R.render_fragment(missing), "")

    def test_minimal_strategy_without_principles(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "minimal.yaml", MINIMAL_YAML)
            frag = R.render_fragment(Path(td))
            self.assertIn("最小可用策略", frag)
            self.assertNotIn("核心原则", frag)
            self.assertEqual(_tag_errors(frag), [])

    def test_numeric_field_rendered_as_percent(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "numeric.yaml", NUMERIC_YAML)
            frag = R.render_fragment(Path(td))
            self.assertIn("<dd>2%</dd>", frag)
            self.assertNotIn("0.02", frag)

    def test_intra_group_sorted_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = MINIMAL_YAML
            _write(Path(td), "zebra.yaml", base.replace("minimal", "zebra"))
            _write(Path(td), "alpha.yaml", base.replace("minimal", "alpha"))
            ids = re.findall(r'id="strat-([a-z0-9_]+)"', R.render_fragment(Path(td)))
            self.assertEqual(ids, ["alpha", "zebra"])

    def test_unknown_category_sorted_last(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "known.yaml", MINIMAL_YAML)
            _write(Path(td), "odd.yaml",
                   MINIMAL_YAML.replace("minimal", "odd").replace("defensive", "trend"))
            heads = re.findall(r'data-category="([a-z]+)"', R.render_fragment(Path(td)))
            self.assertEqual(heads, ["defensive", "trend"])

    def test_html_escaping(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "xss.yaml", XSS_YAML)
            frag = R.render_fragment(Path(td))
            self.assertNotIn("<script>", frag)
            self.assertNotIn("<b>", frag)
            self.assertIn("&lt;script&gt;", frag)
            self.assertIn("&quot;", frag)
            self.assertEqual(_tag_errors(frag), [])


class InjectTest(unittest.TestCase):
    """注入脚本的落点契约：dry-run 不写盘 / 幂等 / 锚点缺失显式报错。"""

    PAGE = ('<!DOCTYPE html><html><head>\n</head><body>\n'
            f'{R.BEGIN_MARK}\n</body></html>\n')

    def _page(self, td: Path) -> Path:
        p = td / "index.html"
        p.write_text(self.PAGE, encoding="utf-8")
        return p

    def test_first_injection_wraps_anchor_pair(self):
        with tempfile.TemporaryDirectory() as td:
            result, rep = I.build(self._page(Path(td)), REAL_STRATEGY_DIR)
            self.assertTrue(rep["changed"])
            self.assertFalse(rep["had_endmark"])
            self.assertIn(R.END_MARK, result)
            self.assertIn(f'<style {R.STYLE_ORIGIN}>', result)
            self.assertEqual(_tag_errors(result), [])
            self.assertEqual(P0_EMOJI_RE.findall(result), [])

    def test_second_injection_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            page = self._page(Path(td))
            first, _ = I.build(page, REAL_STRATEGY_DIR)
            page.write_text(first, encoding="utf-8")
            second, rep = I.build(page, REAL_STRATEGY_DIR)
            self.assertTrue(rep["had_endmark"])
            self.assertEqual(second.count('id="strat-six_networks"'), 1)
            self.assertEqual(second, first)

    def test_missing_anchor_raises(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "index.html"
            p.write_text("<html><body>无锚点</body></html>", encoding="utf-8")
            with self.assertRaises(ValueError):
                I.build(p, REAL_STRATEGY_DIR)

    def test_cli_dry_run_writes_nothing_and_errors_on_missing_anchor(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "index.html"
            p.write_text("<html><head>\n</head><body>无锚点</body></html>",
                         encoding="utf-8")
            bad = subprocess.run([PY, str(HERE / "inject_strategies.py"),
                                  "--src", str(p)], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 3, bad.stderr)
            self.assertIn("锚点", bad.stderr)

            good = self._page(root)
            dry = subprocess.run([PY, str(HERE / "inject_strategies.py"),
                                  "--src", str(good)], capture_output=True, text=True)
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("dry-run", dry.stdout)
            self.assertEqual(good.read_text(encoding="utf-8"), self.PAGE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
