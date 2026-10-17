"""test_sanitize_scope.py — 消毒范围收窄回归（2026-10-15 跨日期腐败事故架构主修）

事故根因（总监实锤）：run_sanitize 曾以 --dir _stage/docs/daily（全树）调用
sanitize_body.py。发布管线每天只把目标日期的上游 HTML 写入 stage（步骤 4
不重写历史日期），但消毒扫全树 → 昨日已消毒+已加框的页面被重新消毒 →
map_custom_properties 腐蚀 frame_pass 注入的 Apple palette 原语
（--ap-white:#ffffff → --ap-white: var(--fg-on-inverse)，style_pass.py:289
的 data-origin 闸门只认自家注入块，frame 块当时无标记）。10-12~10-15
详情页上线腐败；腐败页再消毒字节稳定（固定点），不会自愈。

防腐两层，本文件守第二层（架构主修）：
  第一层（前端并行）：frame 块补 data-origin="detail-frame"，sanitizer
    既有闸门（style_pass.py:289）即刻排除它；
  第二层（本文件）：消毒范围 = 目标日期目录，管线永不重处理不是本次
    写入的页面。freshness 护栏同范围收窄。

覆盖：
  A. 范围断言：publish --date X 后，日期 Y（Y≠X）详情页字节零变化
     （双日期 stage fixture，含同日重跑）；固件经「对照敏感」校验——
     全量消毒确实会把它腐蚀成事故形态，防止测试拿不敏感固件空转；
  B. 目标日期页面仍被消毒（正常路径工作）；
  C. --no-sanitize 语义不变（applied=false、report_path=None、原样字节）；
  D. manifest 的 sanitize 段与消毒报告只覆盖目标日期（files_changed 计数）；
  E. 幻影引用修复：CSS 注释里的 var(--token) 不进 referenced_tokens，
     不污染 unmapped-token 报告（真实腐败页实测）。

运行：python3 scripts/test_sanitize_scope.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import publish_to_github as pub                               # noqa: E402
from sanitizer.core import load_utilities_css, sanitize_html  # noqa: E402
from sanitizer.token_pass import referenced_tokens            # noqa: E402

TARGET_DATE = "2026-10-16"     # 本轮发布日 X
HISTORY_DATE = "2026-10-15"    # 昨日 Y（Y≠X）

# 目标日期上游源（未消毒）：深色渐变 + 深底浅字 + 待转换 emoji
TARGET_SOURCE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">\n'
    "<title>目标日期源</title>\n"
    "<style>.hero{background:linear-gradient(135deg,#0f172a,#1e293b);"
    "color:#fff}</style>\n"
    "</head>\n<body><h1>目标日期</h1><p>⚠️ 提示</p></body></html>")

# 昨日已发布页（Y）：已消毒 + 已加框（body data-df 标记 → frame_pass 幂等
# 跳过），style 块含 frame 注入的 Apple palette 原语 --ap-white:#ffffff
# （无 data-origin —— 2026-10-15 前真实状态，正是被腐蚀的对象）。
HISTORY_PAGE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">\n'
    "<title>历史详情页</title>\n"
    "<!-- detail-frame:v1 -->\n"
    "<style>:root{--ap-white:#ffffff;--ap-ink:#1c1917}"
    ".doc{color:var(--ap-ink)}</style>\n"
    '<!-- detail-tokens:v1 --><style data-origin="detail-tokens">'
    ":root{--fg:var(--ap-ink)}</style>\n"
    "</head>\n"
    '<body data-df="v1" data-date="2026-10-15" data-slug="stock-review">\n'
    '<main id="main" class="frame"><div class="doc">\n'
    '<h1 class="doc-title" data-df-title="1">历史详情页</h1>\n'
    "<p>昨日已消毒已加框的页面。</p>\n"
    "</div></main></body></html>")

# 幻影引用固件：CSS 注释里的示例文本不是真实引用（复现 detail-frame.css
# 规范注释「一律 var(--token) 引用」字样）
PHANTOM_FIXTURE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">\n'
    "<style>/* 规范：一律 var(--token) 引用，禁字面量 */\n"
    ".doc{color:var(--ap-ink)}</style>\n"
    "</head>\n<body><h1>幻影引用固件</h1></body></html>")


def _sanitize(text: str):
    return sanitize_html(text, utilities_css=load_utilities_css())


class TestSanitizeScopeNarrowed(unittest.TestCase):
    """防腐核心：publish --date X 只处理 X 的页面，Y 的页面字节零变化。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.src, self.stage = self.tmp / "src", self.tmp / "stage"

    def tearDown(self):
        self._tmp.cleanup()

    def _write_target_source(self) -> None:
        d = self.src / "股票助手" / TARGET_DATE
        d.mkdir(parents=True, exist_ok=True)
        (d / "stock_assistant.html").write_text(TARGET_SOURCE, encoding="utf-8")

    def _history_fixture(self) -> Path:
        """昨日已发布页面（Y）：meta + entries + 已加框详情页。"""
        d = self.stage / "docs" / "daily" / HISTORY_DATE
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({
            "date": HISTORY_DATE,
            "title_zh": "每日市场研判 · 2026-10-15",
            "title_en": "Daily Market Research · 2026-10-15",
            "summary_zh": "昨日汇总。", "summary_en": "Yesterday digest.",
            "rating": "均衡", "sigma": 0.0, "data_stage": "close",
            "tasks": ["股票复盘"]}, ensure_ascii=False), encoding="utf-8")
        (d / "entries.json").write_text(json.dumps([{
            "slug": "stock-review", "name": "股票复盘", "time": "15:05",
            "run_time": "15:05", "title": "历史详情页",
            "summary": "昨日已消毒已加框的页面。", "html": "stock-review.html",
            "md": None, "rating": "均衡", "sigma": 0.0,
            "sigma_source": "verdict", "stage": "close",
            "breadth_scope": "5273", "snapshot_at": None,
            "comparable": True}], ensure_ascii=False), encoding="utf-8")
        p = d / "stock-review.html"
        p.write_text(HISTORY_PAGE, encoding="utf-8")
        return p

    def _target_page(self) -> Path:
        return self.stage / "docs" / "daily" / TARGET_DATE / "stock-assistant.html"

    def _run(self, *extra: str):
        # 合成测试只提供 stock-assistant 单一任务产物；--task 收敛收集范围，
        # 隔离 A-03 缺失任务硬失败逻辑（详见 test_sanitize_pipeline._run_publish 注释）。
        return subprocess.run(
            [pub.MANAGED_PY, str(HERE / "publish_to_github.py"),
             "--date", TARGET_DATE, "--task", "stock-assistant",
             "--source-root", str(self.src),
             "--stage", str(self.stage), *extra],
            capture_output=True, text=True)

    def test_history_page_bytes_unchanged_after_publish(self):
        """A. 范围断言（含同日重跑）：Y 的详情页字节零变化。"""
        self._write_target_source()
        history = self._history_fixture()
        before = history.read_bytes()
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(history.read_bytes(), before,
                         "publish --date X 后日期 Y 的详情页必须字节零变化")
        r2 = self._run()
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual(history.read_bytes(), before,
                         "同日重跑后日期 Y 的详情页仍须字节零变化")
        self.assertIn("--ap-white:#ffffff", before.decode("utf-8"),
                      "固件必须含未被腐蚀的 palette 原语（否则断言空洞）")

    def test_history_fixture_is_sanitize_sensitive(self):
        """对照：全量消毒确实会腐蚀该固件——防测试拿不敏感固件空转。"""
        out, _ = _sanitize(HISTORY_PAGE)
        self.assertNotEqual(out, HISTORY_PAGE, "固件必须对消毒敏感")
        self.assertIn("--ap-white: var(--fg-on-inverse)", out,
                      "必须复现事故腐败形态（map_custom_properties 腐蚀原语）")

    def test_target_date_page_is_sanitized(self):
        """B. 正常路径仍工作：目标日期页面被消毒。"""
        self._write_target_source()
        self._history_fixture()
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        page = self._target_page().read_text(encoding="utf-8")
        self.assertNotIn("linear-gradient", page, "渐变必须收敛")
        self.assertNotIn("#0f172a", page, "深色渐变字面量必须收敛")
        self.assertIn("var(--surface-inverse)", page)
        self.assertNotIn("⚠", page, "emoji 必须转换")
        self.assertIn("i-alert-triangle", page, "图标引用必须闭环补全")

    def test_no_sanitize_keeps_target_raw_and_history_untouched(self):
        """C. --no-sanitize 语义不变：原样字节 + applied=false。"""
        self._write_target_source()
        history = self._history_fixture()
        h_before = history.read_bytes()
        r = self._run("--no-sanitize")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        page = self._target_page().read_text(encoding="utf-8")
        self.assertEqual(page, TARGET_SOURCE, "回退通道必须原样发布")
        m = json.loads((self.stage / "manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(m["sanitize"]["applied"])
        self.assertIsNone(m["sanitize"]["report_path"])
        self.assertEqual(m["sanitize"]["files_changed"], 0)
        self.assertEqual(history.read_bytes(), h_before,
                         "回退通道同样不得重处理日期 Y 的页面")

    def test_manifest_and_report_cover_target_date_only(self):
        """D. manifest 的 sanitize 段与消毒报告只覆盖目标日期。"""
        self._write_target_source()
        self._history_fixture()
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        m = json.loads((self.stage / "manifest.json").read_text(encoding="utf-8"))
        sec = m["sanitize"]
        self.assertTrue(sec["applied"])
        self.assertEqual(sec["files_changed"], 1,
                         "files_changed 只统计目标日期被消毒文件")
        self.assertTrue(sec["report_path"].endswith("evidence/sanitize-report.json"))
        report = json.loads(
            (self.stage.parent / "evidence" / "sanitize-report.json")
            .read_text(encoding="utf-8"))
        sources = [f["source"] for f in report["files"]]
        self.assertTrue(sources, "报告不应为空")
        self.assertTrue(all(TARGET_DATE in s for s in sources), sources)
        self.assertFalse(any(HISTORY_DATE in s for s in sources), sources)
        self.assertEqual(m["date"], TARGET_DATE,
                         "manifest 已记录 date，报告按目标日期覆盖写不留歧义")


class TestPhantomTokenReference(unittest.TestCase):
    """E. CSS 注释里的示例文本不是真实引用（2026-10-15 报告污染修复）。"""

    def test_comment_reference_excluded(self):
        refs = referenced_tokens(PHANTOM_FIXTURE)
        self.assertIn("--ap-ink", refs, "真实引用必须仍能检出（不能修出漏报）")
        self.assertNotIn("--token", refs, "注释里的示例文本不是引用")

    def test_no_unmapped_token_report_from_comment(self):
        _, rep = _sanitize(PHANTOM_FIXTURE)
        self.assertEqual(rep.count_of("unmapped-token"), 0,
                         "幻影引用不得污染 unmapped-token 报告")

    def test_real_corrupted_stage_page_phantom_excluded(self):
        """真实腐败页实测：注释里的 var(--token) 全部不进 referenced 集合。"""
        p = (HERE.parent / "_stage" / "docs" / "daily" / HISTORY_DATE
             / "stock-review.html")
        if not p.is_file():
            self.skipTest(f"stage 产物缺失（总监将按 5 日期从源重建）：{p}")
        html = p.read_text(encoding="utf-8")
        self.assertGreaterEqual(html.count("var(--token)"), 1,
                                "固件应含注释内幻影引用（实测 3 处）")
        self.assertNotIn("--token", referenced_tokens(html),
                         "注释内幻影引用不得进 referenced 集合")


if __name__ == "__main__":
    unittest.main(verbosity=2)
