#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dark_mode.py — 深色模式可读性契约回归

## 为什么有这��套测试（2026-10-16 用户实锤「深色模式观感较差」）

根因不是"颜色没调好"，而是**一类结构性漏改**：Token 层大量组件色直接引用
LAYER 0 浅色原语（`--ap-ink` = #1d1d1f 近黑），深色 media 块漏了对应覆写。
后果是黑底（--ap-black #000）上出现对比度约 1.1:1 的近黑正文——肉眼"发灰/
看不清"，但任何"截图看着还行"的目检都会放过它。

实测漏网 5 个：`--tl-title-fg` / `--tl-summary-fg` / `--tl-kicker-fg` /
`--tl-dot-stage-close` / `--foot-fg`（首页时间线标题与摘要整体不可读）。

## 契约（守护两类问题）

  D-1 Token 覆盖完整性：任何**值引用 --ap-ink* / --ap-hairline*** 的 token，
      若未在 `prefers-color-scheme: dark` 块内覆写 → 失败。
      LAYER 0 原语本身豁免（它们本就是固定色，由上层 token 负责反色）。
  D-2 深色对比度下界：所有 `--ap-dark-ink*` 前景在 `--ap-black` 画布上的
      WCAG 对比度必须 ≥ 4.5:1（正文级 AA），≥3:1 的大字/装饰另算。

运行：python3 scripts/test_dark_mode.py
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TOKENS = ROOT / "design-tokens.css"

# LAYER 0 原语豁免名单：这些是固定色板，深色不覆写（由上层 token 引用后反色）
PRIMITIVES = ("--ap-ink", "--ap-ink-secondary", "--ap-ink-tertiary",
              "--ap-hairline", "--ap-hairline-soft", "--ap-white", "--ap-black",
              "--ap-surface", "--ap-canvas", "--ap-dark-")

_DEF_RE = re.compile(r"^\s{2,4}(--[a-z0-9-]+)\s*:\s*([^;]+);", re.M)
_DARK_BLOCK_RE = re.compile(r"@media \(prefers-color-scheme: dark\) \{(.*?)\n\}", re.S)

# 相对亮度（WCAG 2.1）
def _rel_lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(fg: str, bg: str) -> float:
    l1, l2 = _rel_lum(fg), _rel_lum(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


class TestDarkModeContract(unittest.TestCase):
    css = TOKENS.read_text(encoding="utf-8")

    def dark_block(self) -> str:
        m = _DARK_BLOCK_RE.search(self.css)
        self.assertIsNotNone(m, "未找到 prefers-color-scheme: dark 块")
        return m.group(1)

    def test_d1_light_primitive_tokens_all_overridden(self):
        """D-1：引用浅色 ink/hairline 原语的 token 必须在深色块有覆写。"""
        dark_tokens = set(re.findall(r"(--[a-z0-9-]+)\s*:", self.dark_block()))
        missing = []
        for name, val in _DEF_RE.findall(self.css):
            if name in dark_tokens or name.startswith(PRIMITIVES):
                continue
            if re.search(r"var\((--ap-ink|--ap-hairline)", val):
                missing.append(f"{name}: {val.strip()}")
        self.assertEqual(missing, [],
                         f"深色模式漏覆写（黑底上近黑文字不可读）：{missing}")

    def test_d2_dark_ink_contrast_on_black(self):
        """D-2：深色前景原语在纯黑画布上的对比度 ≥ 4.5:1（正文 AA）。

        原语值取自 LAYER 0 定义处（唯一定义点，深色块只做 var() 引用——
        这正是防腐要求的形态：字面值只出现在一处，避免 map_custom_properties
        多点改写产生漂移）。
        """
        primitives = dict(_DEF_RE.findall(self.css))
        canvas = primitives.get("--ap-black", "#000000").strip()
        self.assertTrue(canvas.startswith("#"), f"--ap-black 应为字面值，实际 {canvas}")
        for name, floor in (("--ap-dark-ink", 4.5), ("--ap-dark-ink-2", 4.5),
                            ("--ap-dark-ink-3", 4.5)):
            self.assertIn(name, primitives, f"缺少深色前景原语 {name}")
            hexv = primitives[name].strip()
            self.assertTrue(hexv.startswith("#"), f"{name} 应为字面值，实际 {hexv}")
            ratio = _contrast(hexv, canvas)
            self.assertGreaterEqual(
                ratio, floor,
                f"{name}({hexv}) on {canvas} 对比度 {ratio:.2f}:1 < {floor}:1")

    def test_d3_palette_primitives_never_rewritten(self):
        """D-3：防腐不变量——LAYER 0 色板原语必须是字面值，不得写成 var() 引用。

        曾发生 map_custom_properties 把 detail-frame 注入块里的
        `--ap-white: #ffffff` 腐蚀为 `var(--fg-on-inverse)`，深色模式下黑底
        表面发白。本测试守住「原语只在此处定义且为字面��」。
        """
        primitives = dict(_DEF_RE.findall(self.css))
        for prim in ("--ap-white", "--ap-black", "--ap-dark-1", "--ap-dark-2",
                     "--ap-dark-ink", "--ap-dark-sep"):
            self.assertIn(prim, primitives, f"缺少色板原语 {prim}")
            self.assertFalse(
                primitives[prim].strip().startswith("var("),
                f"{prim} 被改写为 var() 引用（防腐腐蚀）：{primitives[prim].strip()}")
        # 深色块不得重定义 LAYER 0 原语（重定义即多点改写风险）
        dark = self.dark_block()
        redefined = [p for p in ("--ap-white", "--ap-black", "--ap-dark-1")
                     if re.search(rf"^\s*{p}\s*:", dark, re.M)]
        self.assertEqual(redefined, [], f"深色块重定义 LAYER 0 原语：{redefined}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
