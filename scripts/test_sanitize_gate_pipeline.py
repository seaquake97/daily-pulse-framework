"""test_sanitize_gate_pipeline.py — 设计师门禁 round 2 · 消毒门禁行为回归

覆盖 B-5 / B-6 / B-7 / B-8（2026-10-15 门禁实锤的 6 项阻塞中与「门禁行为」
相关的四项）：

  B-5 emoji 兜底白名单化：IP 白名单（emoji_map.is_ip_mark）是唯一合法
     保留路径；其余未映射 emoji → needs-manual-review（退出码 2）+ 保守
     保留原字符，**不包 ip-mark**（包了即绕开 P0 扫描器，静默过闸）；
     is_protected（ADR-003）路径不受影响。
  B-6 Chart.js 指纹只认 <script> 上下文：正文/figcaption 提库名不误报
     needs-manual-review。
  B-7 ECharts 指纹覆盖 echarts@5.4.3 与 5.x 新域名；孤儿 CDN 移除且不
     升级为人工确认。
  B-8 发布时点护栏：产物 mtime 早于 scripts/sanitizer/*.py 时，
     --no-sanitize 阻断（退出码 3，不产 manifest）；正常路径强制重新
     消毒并在 manifest 留痕 stale_forced。核心验收：不存在「代码新于
     产物却直接发布」的路径。护栏扫描范围 = 目标日期目录（2026-10-15
     跨日期腐败事故后与消毒同范围收窄）：范围外陈旧产物不阻断、不留痕、
     不处理（test_stale_artifact_out_of_target_date_ignored）。

与 test_sanitize_pipeline.py 的分工：那文件管接线契约/消毒不变量/注入幂等，
本文件管 round 2 新增的门禁行为。运行：python3 scripts/test_sanitize_gate_pipeline.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import publish_to_github as pub                               # noqa: E402
from sanitizer.core import sanitize_html                      # noqa: E402
from sanitizer.script_pass import _CHART_CDN                  # noqa: E402

TEST_DATE = "2026-10-14"
P0_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF\uFE00-\uFE0F]")
IP_MARK_RE = re.compile(r'<span class="ip-mark"[^>]*>.*?</span>', re.S)

# B-5 构造例：未映射 emoji（🚀 不在映射表/IP 白名单）+ IP 标识 + 保护箭头
EMOJI_FIXTURE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"></head><body>'
    "<h1>标题</h1><p>\U0001F680 推进中</p><p>\U0001F35C 面馆</p><p>▲ 方向冗余</p>"
    "</body></html>")

# B-6 构造例：正文/figcaption 提及 Chart.js，但全页无 script
BODY_MENTION_FIXTURE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"></head><body>'
    "<h1>图表说明</h1><p>图表由 Chart.js 渲染，数据见下表。</p>"
    "<figcaption>Chart.js 环形图</figcaption></body></html>")

# B-7 构造例：孤儿 echarts CDN（5.x 新域名），无内联脚本
ECHARTS_ORPHAN_FIXTURE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
    '<script src="https://fastly.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js">'
    "</script></head><body><h1>无图表</h1></body></html>")

# B-8 构造例：本轮新写盘的干净来源（供 publish 收集）
CLEAN_SOURCE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
    "<title>护栏测试</title></head><body><h1>护栏测试固件</h1>"
    "<p>本页为发布时点护栏测试，非真实产出。</p></body></html>")

# B-8 构造例：历史日期陈旧产物（含未消毒的深色渐变）
STALE_HISTORY = (
    '<html><body><h1>旧产物</h1>'
    '<div style="background:linear-gradient(135deg,#0f172a,#1e293b)">x</div>'
    "</body></html>")


def _sanitize(text: str):
    return sanitize_html(text, utilities_css=None)


class TestEmojiFallbackWhitelist(unittest.TestCase):
    """B-5：IP 白名单外未映射 emoji → needs-manual-review，不静默。"""

    def test_unmapped_emoji_flagged_and_kept_raw(self):
        out, rep = _sanitize(EMOJI_FIXTURE)
        self.assertGreaterEqual(rep.count_of("needs-manual-review"), 1)
        self.assertIn("\U0001F680", out, "保守保留原字符（换皮不阉割）")
        # 不包 ip-mark：包了会被 P0 扫描器豁免，正是要堵的静默通道
        self.assertNotRegex(out, r'<span class="ip-mark"[^>]*>\U0001F680')
        # P0 扫描器口径（剥 ip-mark 后）必须能看见它
        residue = P0_EMOJI_RE.findall(IP_MARK_RE.sub("", out))
        self.assertIn("\U0001F680", residue)

    def test_ip_mark_and_protected_paths_unchanged(self):
        out, rep = _sanitize(EMOJI_FIXTURE)
        # K-1：IP 标识包裹机制保留（title/aria-label/role=img 承载文字语义）
        self.assertIn('<span class="ip-mark"', out)
        # PM-07（2026-10-16 总监裁决）：IP 标识图形本体升级为 SVG symbol，
        # ip-mark 不再是 emoji 的避难所——包内不再出现 emoji 原字符。
        self.assertIn("#i-noodle-bowl", out)                  # 🍜 → SVG 图标
        self.assertNotIn("\U0001F35C", out)                   # 关键：emoji 字符已清除
        # K-3：ADR-003 方向冗余编码（▲）禁止剥离 —— 原样保留在正文。
        self.assertIn("▲", out)
        # PM-07 重新归类：IP 标识从「保留原字符(emoji-kept)」改为
        # 「升级 SVG(emoji)」，故本例 🍜 走 emoji 而非 emoji-kept；
        # ▲ 不在 EMOJI_PATTERN 区间（U+25xx < U+2600），不被 emoji 通道
        # 触碰，等价「不动」保护。改用报告确认 🍜 走了 emoji 升级、且
        # 本例仅 🚀 命中 needs-manual-review（1 处），门禁口径稳定。
        self.assertGreaterEqual(rep.count_of("emoji"), 1)     # 🍜 → SVG 升级
        self.assertEqual(rep.count_of("needs-manual-review"), 1)  # 仅 🚀

    def test_unmapped_emoji_cli_exit_code_2(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "in.html"
            p.write_text(EMOJI_FIXTURE, encoding="utf-8")
            r = subprocess.run(
                [pub.MANAGED_PY, str(HERE / "sanitize_body.py"), "--in", str(p),
                 "--out", str(Path(td) / "out.html")],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("needs-manual-review", r.stdout)


class TestChartFingerprintScope(unittest.TestCase):
    """B-6：CDN 指纹只认 <script> 上下文；B-7：echarts 5.x 覆盖。"""

    def test_body_text_library_mention_no_false_positive(self):
        out, rep = _sanitize(BODY_MENTION_FIXTURE)
        self.assertEqual(rep.count_of("needs-manual-review"), 0,
                         "正文/figcaption 提库名不得误报 needs-manual-review")
        self.assertIn("Chart.js", out, "正文文案不动（只改呈现，不改内容）")

    def test_echarts_fingerprint_covers_5x_domains(self):
        urls = [
            "https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js",
            "https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js",
            "https://fastly.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js",
            "https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js",
        ]
        for u in urls:
            self.assertRegex(u, _CHART_CDN, f"指纹未覆盖：{u}")

    def test_orphan_echarts_removed_without_review(self):
        out, rep = _sanitize(ECHARTS_ORPHAN_FIXTURE)
        self.assertNotIn("<script", out)
        self.assertNotIn("echarts", out)
        self.assertEqual(rep.count_of("needs-manual-review"), 0,
                         "孤儿 CDN 按死代码移除，不升级为人工确认")

    def test_script_context_still_detected(self):
        html = ('<html><body><p>Chart.js 见图</p>'
                '<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.js">'
                "</script>"
                "<script>new Chart(document.getElementById('c'),{type:'doughnut',"
                'data:{labels:["ZZZ"],datasets:[{data:[1]}]}});</script></body></html>')
        _, rep = _sanitize(html)
        self.assertGreaterEqual(rep.count_of("needs-manual-review"), 1,
                                "script 内存活引用必须仍能检出（不能修出漏报）")


class TestPublishFreshnessGuard(unittest.TestCase):
    """B-8：产物陈旧于消毒代码 → --no-sanitize 阻断 / 正常路径强制重消毒。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.src, self.stage = self.tmp / "src", self.tmp / "stage"

    def tearDown(self):
        self._tmp.cleanup()

    def _write_source(self, html: str) -> None:
        d = self.src / "股票助手" / TEST_DATE
        d.mkdir(parents=True, exist_ok=True)
        (d / "stock_assistant.html").write_text(html, encoding="utf-8")

    def _stale_history(self, html: str, date: str = TEST_DATE) -> Path:
        """造一个陈旧产物，mtime 拨到 10 天前（必陈旧于消毒代码时点）。

        默认落在目标日期目录 —— 护栏与消毒同范围（2026-10-15 跨日期
        腐败事故后收窄）；显式传其他日期即构造「范围外陈旧产物」场景。
        """
        d = self.stage / "docs" / "daily" / date
        d.mkdir(parents=True, exist_ok=True)
        p = d / "old.html"
        p.write_text(html, encoding="utf-8")
        old = time.time() - 10 * 86400
        os.utime(p, (old, old))
        return p

    def _run(self, *extra: str):
        # 合成测试只提供 stock-assistant 单一任务产物；--task 收敛收集范围，
        # 隔离 A-03 缺失任务硬失败逻辑（详见 test_sanitize_pipeline._run_publish 注释）。
        return subprocess.run(
            [pub.MANAGED_PY, str(HERE / "publish_to_github.py"), "--date", TEST_DATE,
             "--task", "stock-assistant",
             "--source-root", str(self.src), "--stage", str(self.stage), *extra],
            capture_output=True, text=True)

    def test_stale_artifact_blocks_no_sanitize(self):
        self._write_source(CLEAN_SOURCE)
        self._stale_history(STALE_HISTORY)
        r = self._run("--no-sanitize")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("陈旧", r.stdout, "必须打印护栏阻断原因")
        self.assertFalse((self.stage / "manifest.json").exists(),
                         "护栏阻断不得产出 manifest（发布未完成）")

    def test_stale_artifact_force_resanitized(self):
        self._write_source(CLEAN_SOURCE)
        stale = self._stale_history(STALE_HISTORY)
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        healed = stale.read_text(encoding="utf-8")
        self.assertNotIn("gradient", healed, "陈旧产物必须被本轮消毒重新处理")
        self.assertIn("var(--surface-inverse)", healed)
        m = json.loads((self.stage / "manifest.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(m["sanitize"]["stale_forced"], 1,
                                "陈旧强制重消毒必须在 manifest 留痕")

    def test_fresh_publish_records_zero_stale(self):
        self._write_source(CLEAN_SOURCE)
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        m = json.loads((self.stage / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m["sanitize"]["stale_forced"], 0,
                         "全新写盘的产物不应判陈旧")

    def test_stale_artifact_out_of_target_date_ignored(self):
        """范围外陈旧产物：不阻断、不留痕、字节不动（防腐架构主修）。

        护栏与消毒同范围（仅目标日期目录）：历史日期的时点由各自发布
        轮次负责，本轮 publish 既不重消毒它，也不因它阻断回退通道。
        """
        self._write_source(CLEAN_SOURCE)
        stale = self._stale_history(STALE_HISTORY, date="2026-10-13")
        before = stale.read_bytes()
        r = self._run("--no-sanitize")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(stale.read_bytes(), before,
                         "范围外陈旧产物不得被本轮处理（防腐核心断言）")
        m = json.loads((self.stage / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m["sanitize"]["stale_forced"], 0,
                         "范围外陈旧产物不得进 manifest 留痕")


class TestStaleArtifactGapFill(unittest.TestCase):
    """B-8 配套：已注入页面再次消毒时，新规则的新引用必须补齐（不整段跳过）。

    旧实现见注入 MARKER 即整段跳过 —— 历史产物被新代码重新消毒时，新规则
    引入的新 token / 新图标引用会悬空，「代码新于产物」的陈旧路径改头换面
    复活。现在必须补缺口，且补充后保持字节幂等。
    """

    def test_token_gap_filled_on_marked_page(self):
        base, _ = _sanitize('<html><head><style>.a{color:#1c1917}</style></head>'
                            "<body><p>x</p></body></html>")
        self.assertIn("detail-tokens:v1", base)
        # 模拟新规则引入新引用（如 B-3 深底浅字规则落到此前未注入的 token）
        aged = base.replace(
            "</head>", "<style>.hero{color:var(--fg-on-inverse)}</style></head>")
        out, rep = _sanitize(aged)
        refs = set(re.findall(r"var\((--[a-z0-9-]+)", out))
        defs = set(re.findall(r"(--[a-z0-9-]+)\s*:", out))
        self.assertEqual(refs - defs, set(), "已注入页面的新缺口必须被补齐")
        self.assertGreaterEqual(rep.count_of("token"), 1)
        out2, _ = _sanitize(out)
        self.assertEqual(out, out2, "补充注入后必须字节幂等")

    def test_icon_gap_filled_on_marked_page(self):
        base, _ = _sanitize('<html><body><p>\u26a0 提示</p></body></html>')
        self.assertIn("icon-subsprite:v1", base)
        # 模拟新规则引入新引用（如返工 1 把新 emoji 补进映射表）
        aged = base.replace("</body>",
                            '<svg class="ic"><use href="#i-star"/></svg></body>')
        out, rep = _sanitize(aged)
        self.assertIn('<symbol id="i-star"', out, "新缺口 symbol 必须补齐")
        self.assertGreaterEqual(rep.count_of("icon"), 1)
        out2, _ = _sanitize(out)
        self.assertEqual(out, out2, "补充注入后必须字节幂等")


if __name__ == "__main__":
    unittest.main(verbosity=2)
