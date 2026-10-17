#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_emoji_body.py — 上游详情页 body 全量 emoji 扫描（PM-07 回归门禁）

## 背景 / 踩坑记录
PM-07 之前，<span class="ip-mark"> 是 P0 扫描器的豁免范围——统计 emoji 时把
ip-mark 整体剥掉再数，导致藏在包裹体里的 emoji 原字符（♟️ / 🍜 等品牌标识）
稳定上线、扫描器看得见却消毒链碰不到。2026-10-16 实测 30 处，后收敛到 27/21 处。
修复后 ip-mark 本体升级为站点锁定的 SVG symbol（chess-pawn / noodle-bowl），
title/aria-label 改为中文文字语义，emoji 字符彻底消失。

## 本测试的定位（与已有测试互补，不重复）
  · test_emoji_zero_outside_ip_mark（test_sanitize_pipeline）是「剥 ip-mark 后
    统计」——它服务于「ip-mark 是合法豁免」的旧契约；
  · 本测试是「全量 body 扫描，不剥 ip-mark」——直接对 _stage/docs/daily 下所有
    详情页的 body 文本做 emoji 字符计数（含 ip-mark 内部），断言 0 处违规。
    这是 PM-07 闭环的硬门禁：任何一处 emoji 残留在 body（无论是否在 ip-mark 内）
    都必须响亮失败，堵死「扫描器剥 ip-mark 后看不到」的静默过闸通道。
  · 另含 test_no_legacy_ip_mark：旧形态 ip-mark（title/aria-label/内容三位一体
    都是 emoji 原字符）必须清零——PM-07 的核心堵漏点，回归即报警。

## 运行
python3 scripts/test_emoji_body.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE_DAILY = HERE.parent / "_stage" / "docs" / "daily"

# 与 scan_compliance.P0_EMOJI_RE 同口径（团队 P0 规则 §1：禁止 emoji 作为功能图标）
P0_EMOJI_RE = re.compile("[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]")

# 旧形态 ip-mark：title/aria-label/内容三者都还是「裸字符」（PM-07 前的残留）。
# 新形态 content 是 <svg…>，不会命中 [^<]*，故本正则天然只捕获旧形态。
LEGACY_IP_MARK_RE = re.compile(
    r'<span class="ip-mark" title="([^"]*)" aria-label="([^"]*)" '
    r'role="img">([^<]*)</span>')


class TestBodyEmojiZero(unittest.TestCase):
    """PM-07 闭环硬门禁：详情页 body 全量 emoji 扫描。"""

    def _daily_htmls(self) -> list[Path]:
        if not STAGE_DAILY.exists():
            self.skipTest(f"暂存详情页缺失：{STAGE_DAILY}（可由 publish_to_github.py 重建）")
        files = sorted(STAGE_DAILY.glob("*/*.html"))
        if not files:
            self.skipTest(f"暂存详情页为空：{STAGE_DAILY}")
        return files

    def test_body_no_emoji_anywhere(self):
        """body 全量 emoji 扫描（含 ip-mark 内部）：必须 0 处违规。

        不剥 ip-mark 直接对整页文本计数——这正是 PM-07 要堵的「剥壳豁免」通道。
        """
        for f in self._daily_htmls():
            with self.subTest(file=f.name):
                html = f.read_text(encoding="utf-8")
                hits = P0_EMOJI_RE.findall(html)
                self.assertEqual(hits, [], f"{f}: body 仍有 emoji 残留: {hits[:5]}")

    def test_no_legacy_ip_mark(self):
        """旧形态 ip-mark（emoji 作内容 / 标题）必须清零——PM-07 核心堵漏点。"""
        for f in self._daily_htmls():
            with self.subTest(file=f.name):
                html = f.read_text(encoding="utf-8")
                for m in LEGACY_IP_MARK_RE.finditer(html):
                    content, title, aria = m.group(3), m.group(1), m.group(2)
                    self.assertFalse(
                        P0_EMOJI_RE.search(content),
                        f"{f}: ip-mark 内容仍含 emoji 原字符: {content!r}")
                    self.assertFalse(
                        P0_EMOJI_RE.search(title),
                        f"{f}: ip-mark 语义标签仍含 emoji: {title!r}")
                    self.assertFalse(
                        P0_EMOJI_RE.search(aria),
                        f"{f}: ip-mark 语义标签仍含 emoji: {aria!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
