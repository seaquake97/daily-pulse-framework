"""test_sanitize_pipeline.py — 发布层消毒管线回归（接线契约 + 消毒不变量 + 图标闭环）

  A. 接线静态契约：消毒调用位于「落盘之后、build_site 之前」；--no-sanitize 回退通道存在。
  B. 发布级集成（tmp source + tmp stage + 固件）：退出码 2 警告不阻断并记 sanitize_warn；
     --no-sanitize 原样发布；连跑两次详情页字节一致；消毒硬失败按契约返回 3。
  C. 消毒器不变量（真实产出 + 固件）：内容零丢失、emoji 归零（ip-mark 豁免）、script 归零、
     图标引用-定义闭环、注入块不重复、图表库注释零假阳性、报告结构、未知引用显式标记。

emoji 归零口径：ADR-003 个人 IP 标识以 <span class="ip-mark"> 显式保留（role="img"，非
功能图标），故断言剥除 ip-mark 包裹体后总监正则零命中；真实产出缺失即 skip，不伪造样本。
round 2 设计师门禁回归（B-3~B-8）拆至 test_sanitize_gate_visual.py 与
test_sanitize_gate_pipeline.py —— 本文件已近单文件 300 行硬上限，按规则拆分。
运行：python3 scripts/test_sanitize_pipeline.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import publish_to_github as pub                                       # noqa: E402
import site_theme as T                                                # noqa: E402
from sanitizer.core import load_utilities_css, sanitize_html, visible_text  # noqa: E402
from sanitizer.icon_pass import MARKER, icon_sizes                    # noqa: E402
from sanitizer.token_pass import MARKER as TOKEN_MARKER               # noqa: E402

PUBLISH_SRC = (HERE / "publish_to_github.py").read_text(encoding="utf-8")
TEST_DATE = "2026-10-14"
UPSTREAM = Path("/Users/lianghaizhen/WorkBuddy")

# 总监指定的 emoji 正则（含变体选择符）；ADR-003 显式保留的 IP 标识包裹体
# （emoji 归零的豁免范围）；可见文本 token（中文/拉丁词/数值/Σ/▲▼↔）
EMOJI_RE = re.compile("[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF\uFE00-\uFE0F]")
IP_MARK_RE = re.compile(r'<span class="ip-mark"[^>]*>.*?</span>', re.S)
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*|[0-9]+(?:\.[0-9]+)?%?|[\u4e00-\u9fff\u0370-\u03ff\u2190-\u21ff\u25a0-\u25ff]")

REAL_HTML = {
    "stock-assistant": UPSTREAM / "股票助手" / TEST_DATE / "stock_assistant.html",
    "fund-market": UPSTREAM / "基金每日盘面分析（11:00）" / TEST_DATE
                   / "fund_market_analysis.html",
    "daily-review": UPSTREAM / "每日总复盘（15:30）" / TEST_DATE / "daily_review.html",
    # QA P0 返工样本：✅/❌ 状态标记 + 悬空 token 都出自这份
    "stock-review-1015": UPSTREAM / "股票复盘" / "2026-10-15" / "stock_review.html",
}

CLEAN_FIXTURE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>消毒管线测试固件</title>
<style>body{background:#ffffff;color:#1c1917}.card{background:#fee2e2}</style>
</head>
<body>
<h1>固件报告标题</h1>
<h2>固件章节</h2>
<p>⚠️ 风险提示：本页为测试固件，非真实产出。</p>
<div class="card">持仓建议：网格动作卡。</div>
</body>
</html>"""

# 图表标签不在静态文本中 → script_pass 判 needs-manual-review 并保守保留 script
REVIEW_FIXTURE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
    "<title>待人工确认</title></head><body><h1>需人工确认固件</h1>"
    '<canvas id="c" width="200" height="120"></canvas>'
    '<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.js"></script>'
    "<script>new Chart(document.getElementById('c'), {type:'doughnut', "
    'data:{labels:["ZZZ","YYY"], datasets:[{data:[1,2]}]}});</script>'
    "</body></html>")


# 图表标签在静态文本中有冗余 → 安全静态化；脚本前的库说明注释必须被清掉
CHART_FIXTURE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
    "<title>图表固件</title></head><body><h1>图表固件</h1>"
    '<!-- Chart.js 渲染脚本 --><canvas id="c"></canvas>'
    '<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.js"></script>'
    "<script>new Chart(document.getElementById('c'), {type:'doughnut', "
    'data:{labels:["甲板块","乙板块"], datasets:[{data:[60,40]}]}});</script>'
    "<ul><li>甲板块 60%</li><li>乙板块 40%</li></ul></body></html>")


# CSS content 字符串符号不是文本节点 emoji（content:"➔"），误替换会损坏样式表 → stash 保护
CSS_CONTENT_FIXTURE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
    '<style>.x li::before{content:"\u2794"}</style></head><body>'
    "<h1>CSS 保护固件</h1><p>\u2705 已确认</p></body></html>")


def _sanitize(text: str):
    return sanitize_html(text, utilities_css=load_utilities_css())


def _real_cases():  # (slug, 原文)；真实产出缺失即 skip，不伪造样本
    for slug, p in REAL_HTML.items():
        if not p.exists():
            raise unittest.SkipTest(f"真实产出缺失：{p}")
        yield slug, p.read_text(encoding="utf-8")


def _write_source(root: Path, html: str) -> None:
    d = root / "股票助手" / TEST_DATE
    d.mkdir(parents=True, exist_ok=True)
    (d / "stock_assistant.html").write_text(html, encoding="utf-8")


def _run_publish(source: Path, stage: Path, *extra: str):
    return subprocess.run(
        [pub.MANAGED_PY, str(HERE / "publish_to_github.py"), "--date", TEST_DATE,
         "--source-root", str(source), "--stage", str(stage), *extra],
        capture_output=True, text=True)


def _detail(stage: Path) -> Path:
    return stage / "docs" / "daily" / TEST_DATE / "stock-assistant.html"


def _manifest(stage: Path) -> dict:
    return json.loads((stage / "manifest.json").read_text(encoding="utf-8"))


class TestWiringContract(unittest.TestCase):
    """A. publish_to_github.py 接线静态契约。"""

    def test_sanitize_sits_between_write_and_build(self):
        write = PUBLISH_SRC.index("dst.write_text(raw")        # 步骤 4 落盘
        sanitize = PUBLISH_SRC.index("sanitize = run_sanitize(")  # 步骤 4.5 调用点
        build = PUBLISH_SRC.index('("build_site.py"')          # 步骤 5 站点层
        self.assertLess(write, sanitize, "消毒必须晚于步骤 4 落盘")
        self.assertLess(sanitize, build, "消毒必须早于步骤 5 build_site")

    def test_subprocess_invokes_sanitize_cli(self):
        self.assertIn("sanitize_body.py", PUBLISH_SRC)
        for flag in ('"--dir"', '"--in-place"', '"--report"'):
            self.assertIn(flag, PUBLISH_SRC, f"消毒调用缺少 {flag}")

    def test_no_sanitize_fallback_flag(self):
        self.assertIn('"--no-sanitize"', PUBLISH_SRC)
        self.assertIn("run_sanitize(stage, date, args.no_sanitize)", PUBLISH_SRC)

    def test_managed_python_available(self):
        self.assertTrue(Path(pub.MANAGED_PY).exists(), pub.MANAGED_PY)


class TestPublishIntegration(unittest.TestCase):
    """B. 发布级集成：每个用例独立 tmp source + tmp stage。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.src, self.stage = self.tmp / "src", self.tmp / "stage"

    def tearDown(self):
        self._tmp.cleanup()

    def test_exit_code_2_warns_without_blocking(self):
        _write_source(self.src, REVIEW_FIXTURE)
        r = _run_publish(self.src, self.stage)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        m = _manifest(self.stage)
        self.assertTrue(m["sanitize"]["applied"])
        self.assertGreaterEqual(m["sanitize"]["manual_review"], 1)
        self.assertIn("sanitize_warn", m, "needs-manual-review 必须留痕")
        # 保守保留：被判需人工确认的 script 不被删除
        self.assertIn("<script", _detail(self.stage).read_text(encoding="utf-8"))

    def test_no_sanitize_publishes_raw_bytes(self):
        _write_source(self.src, CLEAN_FIXTURE)
        r = _run_publish(self.src, self.stage, "--no-sanitize")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        m = _manifest(self.stage)
        self.assertFalse(m["sanitize"]["applied"])
        self.assertIsNone(m["sanitize"]["report_path"])
        self.assertEqual(m["sanitize"]["files_changed"], 0)
        self.assertNotIn("sanitize_warn", m)
        detail = _detail(self.stage).read_text(encoding="utf-8")
        self.assertEqual(detail, CLEAN_FIXTURE, "回退通道必须原样发布")
        self.assertIn("⚠", detail)

    def test_rerun_produces_identical_detail_bytes(self):
        _write_source(self.src, CLEAN_FIXTURE)
        self.assertEqual(_run_publish(self.src, self.stage).returncode, 0)
        first = _detail(self.stage).read_bytes()
        self.assertEqual(_run_publish(self.src, self.stage).returncode, 0)
        self.assertEqual(_detail(self.stage).read_bytes(), first,
                         "同日重跑详情页必须字节一致（幂等铁律）")

    def test_sanitize_hard_failure_returns_3(self):
        _write_source(self.src, CLEAN_FIXTURE)
        # 目标日期目录内的脏文件（非 UTF-8）→ 消毒子进程崩溃 → 编排器按契约返回 3。
        # 消毒扫描范围 = 目标日期目录（2026-10-15 跨日期腐败事故后收窄），
        # 脏文件必须落在目标日期内才能触达消毒链。
        broken = self.stage / "docs" / "daily" / TEST_DATE
        broken.mkdir(parents=True)
        (broken / "broken.html").write_bytes(b"<h1>\xff\xfe</h1>")
        r = _run_publish(self.src, self.stage)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("消毒失败", r.stdout, "必须打印 stderr 摘要")
        self.assertFalse((self.stage / "manifest.json").exists())


class TestSanitizerInvariantsRealOutputs(unittest.TestCase):
    """C1. 真实产出上的消毒不变量（剥标签后逐项断言）。"""

    def test_content_zero_loss(self):
        for slug, raw in _real_cases():
            with self.subTest(slug=slug):
                out, _ = _sanitize(raw)
                lost = (set(TOKEN_RE.findall(visible_text(raw)))
                        - set(TOKEN_RE.findall(visible_text(out))))
                self.assertEqual(lost, set(), f"{slug} 可见文本丢失: {sorted(lost)[:10]}")

    def test_emoji_zero_outside_ip_mark(self):
        for slug, raw in _real_cases():
            with self.subTest(slug=slug):
                out, _ = _sanitize(raw)
                residue = EMOJI_RE.findall(IP_MARK_RE.sub("", out))
                self.assertEqual(residue, [],
                                 f"{slug} 仍有未转换/未保留的 emoji: {residue[:5]}")

    def test_script_zero(self):
        for slug, raw in _real_cases():
            with self.subTest(slug=slug):
                out, _ = _sanitize(raw)
                self.assertEqual(re.findall(r"<script", out, re.I), [])

    def test_icon_reference_closure(self):
        total_refs = 0
        for slug, raw in _real_cases():
            with self.subTest(slug=slug):
                out, _ = _sanitize(raw)
                refs = set(re.findall(r"#i-([A-Za-z0-9_-]+)", out))
                defs = set(re.findall(r'<symbol id="i-([A-Za-z0-9_-]+)"', out))
                total_refs += len(refs)
                self.assertTrue(refs <= defs,
                                f"{slug} 悬空引用: {sorted(refs - defs)}")
                self.assertTrue(defs <= set(T.SYMBOLS),
                                f"{slug} 定义不在锁定表: {sorted(defs - set(T.SYMBOLS))}")
        self.assertGreater(total_refs, 0, "真实产出零图标引用，闭环测试失去意义")


class TestInjectionAndReport(unittest.TestCase):
    """C2. 注入幂等 / CSS 规则 / 报告结构 / 未知引用。"""

    def test_injection_not_duplicated_and_idempotent(self):
        out1, _ = _sanitize(CLEAN_FIXTURE)
        out2, _ = _sanitize(out1)
        self.assertEqual(out1, out2, "二次消毒必须字节一致")
        self.assertEqual(out1.count(MARKER), 1, "注入标记必须唯一")
        self.assertEqual(out1.count('data-origin="icon-subsprite"'), 1)
        self.assertEqual(out1.count('<svg width="0" height="0"'), 1)

    def test_icon_css_rules_and_locked_sizes(self):
        out, _ = _sanitize(CLEAN_FIXTURE)
        css = re.search(r'<style data-origin="icon-subsprite">(.*?)</style>',
                        out, re.S).group(1)
        sizes, stroke = icon_sizes()
        for cls, key in ((".ic{", "ic"), (".ic-20{", "ic-20"), (".ic-24{", "ic-24")):
            self.assertIn(cls, css)
            self.assertIn(f"width:{sizes[key]}", css)
        self.assertEqual([sizes[k] for k in ("ic", "ic-20", "ic-24")],
                         ["16px", "20px", "24px"], "尺寸必须与锁定 Token 同源")
        self.assertEqual(stroke, "1.75")
        self.assertIn(".ic-wrap{", css)
        self.assertIn("currentColor", css, "描边必须走 currentColor")
        self.assertIn("fill:none", css)

    def test_report_json_structure(self):
        with tempfile.TemporaryDirectory() as td:
            p, rep = Path(td) / "in.html", Path(td) / "report.json"
            p.write_text(CLEAN_FIXTURE, encoding="utf-8")
            r = subprocess.run(
                [pub.MANAGED_PY, str(HERE / "sanitize_body.py"), "--in", str(p),
                 "--out", str(Path(td) / "out.html"), "--report", str(rep)],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            entry = json.loads(rep.read_text(encoding="utf-8"))["files"][0]
            for k in ("source", "total", "counts", "changes"):
                self.assertIn(k, entry)
            self.assertIn("icon", entry["counts"], "图标注入必须进审计报告")

    def test_unknown_symbol_ref_flagged(self):
        html = '<html><body><svg class="ic"><use href="#i-nope"/></svg></body></html>'
        out, rep = _sanitize(html)
        self.assertGreaterEqual(rep.count_of("needs-manual-review"), 1,
                                "无法闭环的引用必须显式标记，不静默放过")
        self.assertIn("#i-nope", out, "未知引用保守保留，交人工处理")

    def test_chart_comment_no_false_positive_on_second_pass(self):
        """图表安全静态化后，库说明注释必须清掉，且不得在下一轮假报需人工确认。"""
        out1, rep1 = _sanitize(CHART_FIXTURE)
        out2, rep2 = _sanitize(out1)
        self.assertNotIn("<script", out1)
        self.assertNotIn("Chart.js", out1, "库注释必须随脚本一并清除（悬空引用）")
        self.assertEqual(rep1.count_of("needs-manual-review"), 0)
        self.assertEqual(out1, out2, "二次消毒必须字节一致")
        self.assertEqual(rep2.count_of("needs-manual-review"), 0,
                         "已消毒页面不得因残留注释假报 needs-manual-review")


class TestEmojiSegmentCoverage(unittest.TestCase):
    """返工 1（QA P0）：EMOJI_PATTERN 段缺口——✅/❌ 曾原样漏过消毒。"""

    def test_status_marks_converted_zero_p0_residue(self):
        p = REAL_HTML["stock-review-1015"]
        if not p.exists():
            self.skipTest(f"真实产出缺失：{p}")
        out, _ = _sanitize(p.read_text(encoding="utf-8"))
        residue = EMOJI_RE.findall(IP_MARK_RE.sub("", out))
        self.assertEqual(residue, [], f"P0 全段残留: {residue[:5]}")
        self.assertNotIn("\u2705", out, "✅ 必须转 SVG")
        self.assertNotIn("\u274c", out, "❌ 必须转 SVG")
        self.assertIn("#i-check", out)
        self.assertIn("#i-ban", out)

    def test_pattern_covers_p0_segments_not_rating_arrows(self):
        from sanitizer.emoji_inline import EMOJI_PATTERN
        for ch in ("\u2705", "\u274c", "\u26d4", "\u2757"):   # 新补两段内的代表
            self.assertTrue(EMOJI_PATTERN.fullmatch(ch), f"{ch!r} 未被覆盖")
        for ch in ("\u25b2", "\u25bc", "\u2194"):             # ADR-003 冗余编码
            self.assertIsNone(EMOJI_PATTERN.fullmatch(ch), f"{ch!r} 不应被覆盖")

    def test_css_content_string_not_polluted(self):
        out, _ = _sanitize(CSS_CONTENT_FIXTURE)
        self.assertIn('content:"\u2794"', out, "CSS 内容字符串不得被 emoji 替换污染")
        self.assertIn("#i-check", out, "正文 emoji 仍须转换")

    def test_market_breadth_trio_converted(self):
        """2026-10-16：fund-guide 市场宽度清单的 ➖平盘/🔥涨停/❄️跌停曾以
        needs-manual-review 保守保留（P0 缺口），补映射后必须转 SVG 且零残留。"""
        fixture = (
            "<html><body><h1>市场宽度</h1><ul>"
            "<li><b>\u2796 平盘家数</b>：95 家</li>"
            "<li><b>\U0001F525 涨停板数</b>：50 家</li>"
            "<li><b>\u2744\ufe0f 跌停板数</b>：20 家</li>"
            "</ul></body></html>")
        out, report = _sanitize(fixture)
        self.assertNotIn("\u2796", out, "➖ 必须转 SVG")
        self.assertNotIn("\U0001F525", out, "🔥 必须转 SVG")
        self.assertNotIn("\u2744", out, "❄️ 必须转 SVG")
        self.assertIn("#i-minus", out)
        self.assertIn("#i-trending-up", out)
        self.assertIn("#i-trending-down", out)
        self.assertIn("平盘家数", out, "可见文本一字不删")
        self.assertIn("涨停板数", out)
        self.assertIn("跌停板数", out)
        review = report.details("needs-manual-review")
        self.assertEqual(review, [], f"补映射后不得再报待人工确认: {review[:3]}")


class TestTokenInjection(unittest.TestCase):
    """返工 2：悬空 var() Token 注入（深浅双套 + 幂等 + 不覆盖页面定义）。"""

    def test_real_stock_review_tokens_closed_and_idempotent(self):
        p = REAL_HTML["stock-review-1015"]
        if not p.exists():
            self.skipTest(f"真实产出缺失：{p}")
        out1, rep = _sanitize(p.read_text(encoding="utf-8"))
        refs = set(re.findall(r"var\((--[a-z0-9-]+)", out1))
        defs = set(re.findall(r"(--[a-z0-9-]+)\s*:", out1))
        self.assertEqual(refs - defs, set(), f"悬空 token: {sorted(refs - defs)}")
        self.assertGreater(rep.count_of("token"), 0, "必须发生注入")
        out2, _ = _sanitize(out1)
        self.assertEqual(out1, out2, "二次运行必须字节一致")
        self.assertEqual(out1.count(TOKEN_MARKER), 1)

    def test_injection_preserves_dark_structure_no_override(self):
        html = ('<!DOCTYPE html><html><head><style>:root{--mine:#123456}'
                '.a{color:var(--fg)}</style></head><body><p>x</p></body></html>')
        out, _ = _sanitize(html)
        self.assertIn("--fg:var(--ap-ink)", out)
        self.assertIn("@media (prefers-color-scheme: dark)", out, "必须保留深浅结构")
        self.assertIn(':root:not([data-theme="light"])', out)
        self.assertIn("--fg:var(--ap-dark-ink)", out, "深色值必须一并注入")
        self.assertEqual(out.count("--mine:#123456"), 1, "页面自有定义不得被覆盖")

    def test_unmapped_token_reported_not_silent(self):
        html = ('<!DOCTYPE html><html><head><style>.a{color:var(--no-such-token)}'
                "</style></head><body><p>x</p></body></html>")
        out, rep = _sanitize(html)
        self.assertGreaterEqual(rep.count_of("unmapped-token"), 1,
                                "规范源没有的 token 必须显式记录")
        self.assertIn("--no-such-token", out, "悬空引用保守保留，交人工处理")


if __name__ == "__main__":
    unittest.main(verbosity=2)