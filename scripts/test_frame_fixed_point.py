"""test_frame_fixed_point.py — frame 注入块 sanitize 固定点回归（防腐通道封堵）

背景：2026-10-15 跨日期腐败事故。publish 管线（修复前）对 _stage/docs/daily 全树
消毒，把前日已消毒+已加框的页面重新消毒；sanitizer/style_pass 的
map_custom_properties 对**无 data-origin 标记**的 <style> 块收敛自定义属性，
frame 注入块因此中招——palette 原语 --ap-white:#ffffff 被换成 var() 间接引用，
深色模式 --ap-black 变亮色、黑底表面发白，且腐败态是消毒不动点（不会自愈）。
架构主修在 publish 侧（仅消目标日期，后端域）；本测试守住本域第二道防线：
frame 产物必须带 data-origin 标记，且「万一再被全树消毒」字节不变。

覆盖：
  A. 产物契约：frame_one 的 <style> 带 data-origin="detail-frame"；A-7 提升的
     h1 属性不被 data-sb-h 值内的 > 截断（无 3"> 垃圾、class 不丢）；
  B. 固定点（正 fixture）：sanitize → frame → 再 sanitize 字节一致；palette
     原语保持字面值；frame 结构 nav/main/footer/h1 计数不变；打印块不换皮；
  C. 区分力（负 fixture）：删掉 data-origin 标记后再 sanitize，字节必须改变且
     出现 var() 腐蚀签名——证明 B 不是永真测试；
  D. 真实上游源（缺失即 skip，不伪造样本）：全管线复现后再消毒字节一致。

运行：python3 scripts/test_frame_fixed_point.py
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

import frame_pass as F                                          # noqa: E402
from sanitizer.core import load_utilities_css, sanitize_html    # noqa: E402

REAL_SRC = paths.WORKBUDDY_ROOT / "股票助手" / "2026-10-16" / "stock_assistant.html"
REAL_ENTRIES = HERE.parent / "_stage" / "docs" / "daily" / "2026-10-16" / "entries.json"

# 上游固件：带 h1（sanitize 降级 h3 + data-sb-h="1->3"，frame 再提升回 h1）、
# 私有调色板、内联色值、表格（A-9 包裹路径全覆盖）；类名避开框架类（C-14 门禁）。
UPSTREAM_FIXTURE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>固定点回归固件</title>
<style>:root{--up-ink:#1c1917}.up-note{color:#0f172a}</style>
</head>
<body>
<h1>固件报告标题</h1>
<div class="up-note" style="background:#fee2e2">持仓建议：网格动作卡。</div>
<table><tr><th>标的</th><th>动作</th></tr><tr><td>甲</td><td>加仓</td></tr></table>
<h2>固件章节</h2>
<p>结论：确定性计算，同数据必得同结论。</p>
</body>
</html>"""

ENTRY = {"title": "固件报告标题", "summary": "固定点回归固件摘要",
         "rating": None, "sigma": None, "time": "09:30", "run_time": "09:31"}

_STRUCT_RE = re.compile(r"<(nav|main|footer|h1)\b")


def _sanitize(text: str) -> str:
    out, _ = sanitize_html(text, utilities_css=load_utilities_css())
    return out


def _frame(html: str) -> str:
    framed, _notes = F.frame_one(html, ENTRY, "2026-10-16", "stock-assistant")
    return framed


def _struct(html: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in _STRUCT_RE.finditer(html):
        out[m.group(1)] = out.get(m.group(1), 0) + 1
    return out


def _build_framed() -> str:
    """正 fixture 的完整形态：真实管线 sanitize → frame（带修复的代码）。"""
    return _frame(_sanitize(UPSTREAM_FIXTURE))


class TestFrameArtifactContract(unittest.TestCase):
    """A. frame_one 产物契约（标记 + 标题属性完整性）。"""

    def test_style_block_carries_data_origin(self):
        framed = _build_framed()
        self.assertEqual(framed.count(f"<style {F.STYLE_ORIGIN}>"), 1,
                         "frame 注入 <style> 必须且只能有一个，且带 data-origin 标记")

    def test_heading_attrs_not_truncated_by_gt_in_value(self):
        # data-sb-h="1->3" 值内含 >：旧 [^>]* 解析会切成 <h1 data-sb-h="1- class=...>
        framed = _build_framed()
        h1 = re.search(r"<h1\b[^>]*>.*?</h1>", framed, re.S)
        self.assertIsNotNone(h1)
        self.assertNotIn('3">', h1.group(0), "h1 属性截断会漏出 3\"> 垃圾文本")
        self.assertIn('class="doc-title"', h1.group(0), "class 必须在 h1 上完整保留")
        self.assertIn('data-df-title="1"', h1.group(0))
        self.assertIn("固件报告标题", h1.group(0))


class TestFixedPoint(unittest.TestCase):
    """B. 固定点：已加框页面再消毒，字节与结构零漂移。"""

    def setUp(self):
        self.framed = _build_framed()

    def test_resanitize_is_byte_identical(self):
        out = _sanitize(self.framed)
        self.assertEqual(out, self.framed,
                         "已加框页面再消毒必须字节一致（防腐固定点）")

    def test_palette_primitives_stay_literal(self):
        out = _sanitize(self.framed)
        self.assertRegex(out, r"--ap-white:\s*#ffffff")
        self.assertRegex(out, r"--ap-black:\s*#000000")
        self.assertNotRegex(out, r"--ap-white:\s*var\(",
                            "palette 原语被收敛成 var() = 腐败复现")

    def test_frame_structure_counts_unchanged(self):
        out = _sanitize(self.framed)
        self.assertEqual(_struct(out), _struct(self.framed),
                         "nav/main/footer/h1 计数再消毒后必须不变")

    def test_print_block_not_reskinned(self):
        out = _sanitize(self.framed)
        self.assertIn("background:var(--ap-white); color:var(--ap-black);", out)
        self.assertNotIn("background: var(--surface); color: var(--fg);", out,
                         "打印块被 map_css 换皮 = 恒白/恒黑语义丢失")

    def test_footer_chrome_headings_stable(self):
        out = _sanitize(self.framed)
        self.assertEqual(out.count("<h4>归档</h4>"), 1,
                         "页脚栏目标题必须保持 h4 原样（h3 会被 heading_pass 降级）")


class TestMarkerDiscrimination(unittest.TestCase):
    """C. 区分力：无标记的 frame 块必须被消毒改变——证明 B 不是永真。"""

    def test_marker_removal_makes_sanitize_change_bytes(self):
        framed = _build_framed()
        unmarked = framed.replace(f"<style {F.STYLE_ORIGIN}>", "<style>", 1)
        self.assertNotIn(F.STYLE_ORIGIN, unmarked, "负 fixture 必须真的删掉标记")
        out = _sanitize(unmarked)
        self.assertNotEqual(out, unmarked,
                            "删标记后再消毒必须改变字节（否则正测试无区分力）")
        self.assertRegex(out, r"--ap-white:\s*var\(",
                         "腐蚀签名：palette 原语被换成 var() 间接引用")

    def test_corruption_is_deterministic_signature(self):
        # 腐败形态与 2026-10-15 事故一致：--ap-white → var(--fg-on-inverse)
        framed = _build_framed()
        unmarked = framed.replace(f"<style {F.STYLE_ORIGIN}>", "<style>", 1)
        out = _sanitize(unmarked)
        self.assertIn("--ap-white: var(--fg-on-inverse)", out)


class TestRealSourceFixedPoint(unittest.TestCase):
    """D. 真实上游源全管线复现（缺失即 skip，不伪造样本）。"""

    def test_real_page_resanitize_is_byte_identical(self):
        if not REAL_SRC.exists():
            self.skipTest(f"真实上游源缺失：{REAL_SRC}")
        entry = dict(ENTRY)
        if REAL_ENTRIES.is_file():
            import json
            for e in json.loads(REAL_ENTRIES.read_text(encoding="utf-8")):
                if e.get("slug") == "stock-assistant":
                    entry = e
                    break
        framed = _frame(_sanitize(REAL_SRC.read_text(encoding="utf-8")))
        self.assertIn(f"<style {F.STYLE_ORIGIN}>", framed)
        out = _sanitize(framed)
        self.assertEqual(out, framed, "真实页面再消毒必须字节一致")
        self.assertRegex(out, r"--ap-white:\s*#ffffff")
        self.assertNotRegex(out, r"--ap-black:\s*var\(")


if __name__ == "__main__":
    unittest.main(verbosity=2)
