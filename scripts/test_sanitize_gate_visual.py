"""test_sanitize_gate_visual.py — 设计师门禁 round 2 · 消毒视觉正确性回归

覆盖 B-3 / B-4（2026-10-15 门禁实锤的 6 项阻塞中与「颜色语义」相关的两项）：

  B-3 渐变收敛 role 区分：
    · 深色渐变 → --surface-inverse（深色表面），不再落 --fg（文字 token）；
    · 深底浅字（原文字亮度 > 0.75 且 role=text）→ --fg-on-inverse；
    · 铁律：--rating-*-wash 禁作文字色；
    · 回归判据：不存在「同 token 同时作 background 与 color」的规则。
  B-4 style 层收敛补全：
    · :root 自定义属性（--up/--ink/--line/--card/--bg…）按语义角色收敛；
    · 声明级 hex（含 border 简写内）按同角色表收敛；
    · 循环防护：自环 / 与 token_pass 注入值互环 → 保留原值 + 显式留痕；
    · 协作验证：style 先于 token —— 收敛产出的 var() 由 token_pass 补全，
      二次运行字节一致。

与 test_sanitize_pipeline.py 的分工：那文件管接线契约/消毒不变量/注入幂等，
本文件管 round 2 新增的角色语义与收敛完备性。真实产出缺失即 skip。
运行：python3 scripts/test_sanitize_gate_visual.py
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "framework" / "scripts"))   # A-04
import paths

from sanitizer.core import sanitize_html  # noqa: E402

REAL_STOCK_REVIEW = paths.WORKBUDDY_ROOT / "股票复盘" / "2026-10-15" / "stock_review.html"

# B-3 构造例：深色封面渐变 + 白字（stage 产物 fg-on-fg 缺陷的最小复现）
INVERSE_FIXTURE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>'
    "header{background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);"
    "color:#fff;padding:20px}"
    ".card{background:#ffffff;color:#1c1917}"
    "</style></head><body><header><h1>深色封面</h1></header>"
    '<div class="card">正文</div></body></html>')

# B-4 构造例：:root 私有调色板 + 声明级 hex + border 简写 hex
CONVERGE_FIXTURE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>'
    ":root{--up:#dc2626;--ink:#0f172a;--line:#e2e8f0;--card:#ffffff;--bg:#f8fafc}"
    ".expert-badge{background:#e0f2fe;color:#0369a1}"
    ".card-title{border-bottom:2px solid #f1f5f9}"
    ".up{color:var(--up)}"
    "</style></head><body><p class=\"up\">涨</p></body></html>")


def _sanitize(text: str):
    return sanitize_html(text, utilities_css=None)


def _fg_on_fg_tokens(html: str) -> list[str]:
    """同一 CSS 规则里同一 token 同时作背景与前景的清单（B-3 回归判据）。"""
    problems: list[str] = []
    chunks = re.findall(r"<style\b[^>]*>(.*?)</style>", html, re.S | re.I)
    chunks += re.findall(r'style="([^"]*)"', html)
    for css in chunks:
        bodies = [m.group(2) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)] or [css]
        for body in bodies:
            bgs = set(re.findall(r"background(?:-color)?\s*:\s*var\((--[a-z0-9-]+)\)", body))
            fgs = set(re.findall(r"(?<![-\w])color\s*:\s*var\((--[a-z0-9-]+)\)", body))
            problems.extend(sorted(bgs & fgs))
    return problems


def _dangling(html: str) -> list[str]:
    """被引用但未定义的 token（悬空 var 会让属性回退 unset）。"""
    refs = set(re.findall(r"var\((--[a-z0-9-]+)", html))
    defs = set(re.findall(r"(--[a-z0-9-]+)\s*:", html))
    return sorted(refs - defs)


def _upstream_hex(html: str) -> list[str]:
    """上游来源裸 hex（剥掉 data-origin 注入块；#fff/#000 系为 P0 豁免色）。"""
    stripped = re.sub(r'<style data-origin="[^"]*">.*?</style>', " ", html, flags=re.S)
    stripped = re.sub(r"#(?:[fF]{3,6}|0{3,6})\b", " ", stripped)
    return re.findall(r"#[0-9a-fA-F]{3,8}\b", stripped)


class TestGradientInversePair(unittest.TestCase):
    """B-3：深色渐变 → --surface-inverse；深底浅字 → --fg-on-inverse。"""

    def test_dark_gradient_and_white_text_land_on_inverse_pair(self):
        out, rep = _sanitize(INVERSE_FIXTURE)
        # 冒号间距随上游书写形态（gradient_pass 原位替换函数文本，不规整间距）
        self.assertRegex(out, r"background:\s*var\(--surface-inverse\)")
        self.assertRegex(out, r"color:\s*var\(--fg-on-inverse\)")
        self.assertNotRegex(out, r"background[^;}]*var\(--fg\)",
                            "深色区块背景不得落文字 token --fg")
        self.assertEqual(_fg_on_fg_tokens(out), [], "不允许同 token 同作背景与前景")
        self.assertEqual(_dangling(out), [], "inverse 对必须被 token_pass 补全")
        self.assertGreaterEqual(rep.count_of("gradient"), 1)

    def test_no_same_token_background_and_color_real_output(self):
        if not REAL_STOCK_REVIEW.exists():
            self.skipTest(f"真实产出缺失：{REAL_STOCK_REVIEW}")
        out, _ = _sanitize(REAL_STOCK_REVIEW.read_text(encoding="utf-8"))
        self.assertEqual(_fg_on_fg_tokens(out), [], "真实产出仍有 fg-on-fg 规则")
        self.assertRegex(out, r"background:\s*var\(--surface-inverse\)")
        self.assertRegex(out, r"color:\s*var\(--fg-on-inverse\)")

    def test_wash_token_never_used_as_text_color(self):
        # 铁律：--rating-*-wash 只作背景。文字角色命中 wash 族 → 不映射 + 显式报告
        out, rep = _sanitize(
            '<html><head><style>.x{color:#fca5a5}</style></head><body>x</body></html>')
        self.assertNotIn("wash", out)
        self.assertGreaterEqual(rep.count_of("unmapped-color"), 1)
        self.assertIn("#fca5a5", out, "未映射保守保留原值，不猜")

    def test_inverse_pair_defined_in_both_modes(self):
        # 深浅双套：只注入浅色等于让深色模式用户看到「属性未设置」
        out, _ = _sanitize(INVERSE_FIXTURE)
        self.assertIn("--surface-inverse:var(--ap-ink)", out)
        self.assertIn("--fg-on-inverse:var(--ap-dark-ink)", out)
        self.assertIn("@media (prefers-color-scheme: dark)", out)


class TestStyleLayerConvergence(unittest.TestCase):
    """B-4：自定义属性按角色收敛 + 声明级 hex + 循环防护 + token 协作。"""

    def test_root_custom_properties_converged_by_role(self):
        out, _ = _sanitize(CONVERGE_FIXTURE)
        self.assertIn("--up: var(--quote-up)", out)      # 行情色（默认 text 角色）
        self.assertIn("--ink: var(--fg)", out)           # ink → text
        self.assertIn("--line: var(--border)", out)      # line → border
        self.assertIn("--card: var(--surface)", out)     # card → bg
        self.assertIn("--bg: var(--surface-alt)", out)   # 同名 token 但定义链无环
        self.assertEqual(_upstream_hex(out), [], "上游 :root 不得残留裸 hex")

    def test_declaration_level_hex_converged(self):
        out, _ = _sanitize(CONVERGE_FIXTURE)
        self.assertIn("background: var(--surface-alt)", out)              # #e0f2fe
        self.assertIn("color: var(--accent)", out)                        # #0369a1
        self.assertIn("border-bottom: 2px solid var(--surface-sunken)",   # #f1f5f9
                      out)

    def test_real_stock_review_no_upstream_hex_residue(self):
        if not REAL_STOCK_REVIEW.exists():
            self.skipTest(f"真实产出缺失：{REAL_STOCK_REVIEW}")
        out, rep = _sanitize(REAL_STOCK_REVIEW.read_text(encoding="utf-8"))
        self.assertEqual(_upstream_hex(out), [], "真实产出上游 hex 必须全收敛")
        self.assertEqual(rep.count_of("unmapped-color"), 0)
        self.assertEqual(_dangling(out), [], "收敛引用必须全部有着落")

    def test_cycle_guard_keeps_original_with_trace(self):
        # 自环：--fg: #0f172a → 收敛目标即自身，保留原值并留痕
        out, rep = _sanitize(
            '<html><head><style>:root{--fg:#0f172a}.a{color:var(--fg)}</style>'
            "</head><body>x</body></html>")
        self.assertIn("--fg:#0f172a", out)
        self.assertTrue(any("互环" in d for d in rep.details("style")), "必须留痕")
        # 互环：--ap-ink: #1d1d1f → 目标 --fg 的定义链回到 --ap-ink
        out2, _ = _sanitize(
            '<html><head><style>:root{--ap-ink:#1d1d1f}.a{color:var(--ap-ink)}</style>'
            "</head><body>x</body></html>")
        self.assertIn("--ap-ink:#1d1d1f", out2)

    def test_token_pass_fills_converged_references_idempotent(self):
        # style 先于 token 的协作：收敛产出的 var(--quote-up) 等着落；二次字节一致
        out, rep = _sanitize(CONVERGE_FIXTURE)
        self.assertEqual(_dangling(out), [])
        self.assertGreaterEqual(rep.count_of("token"), 1)
        out2, _ = _sanitize(out)
        self.assertEqual(out, out2, "二次运行必须字节一致")


if __name__ == "__main__":
    unittest.main(verbosity=2)
