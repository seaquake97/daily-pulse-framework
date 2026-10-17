#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""gen_app_icon.py — PWA / apple-touch 图标生成（纯标准库，禁 Pillow）

为什么手写 PNG：构建机不保证有 Pillow，而 PWA 三件套（P-3）是站点产出的
组成部分——为一枚 180px 图标引入第三方成像依赖不划算。zlib + struct 手写
PNG（truecolor 8bit / 滤波 0 / 无 tIME 等时间块）→ 同输入必得同字节，
满足发布幂等铁律（连续两次运行 PNG 字节一致）。

图标语义（与 design-tokens.css 同源）：
  · 背景 = 交互蓝 #0071e3（--ap-blue，站点 CTA / 焦点环同色）；
  · 中央 = 白色 Σ 字形，三横两斜，全部由矩形 + 平行四边形（多边形扫描线
    偶数规则填充）拼成，无位图资源、无外部依赖。
  · Σ 是本站的评分符号（五档评级 · Σ 值），图标即品牌。

产出（三档，同一几何按尺寸缩放）：
  apple-touch-icon.png  180×180（iOS 主屏）
  icon-192.png          192×192（PWA manifest）
  icon-512.png          512×512（PWA manifest）

用法：
  python3 gen_app_icon.py [--out <目录>]   # 默认 _stage/docs
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE.parent / "_stage" / "docs"

# 颜色字面量理由（P0-3 的唯一例外形态）：PNG 是二进制位图，不存在 CSS 变量
# 的解析环境，取值必须落成字节。两个值与 design-tokens.css 的
# --ap-blue(#0071e3) / --ap-white(#ffffff) 逐字一致——改 token 须同步此处。
BG = (0x00, 0x71, 0xE3)
FG = (0xFF, 0xFF, 0xFF)

SIZES = (("apple-touch-icon.png", 180), ("icon-192.png", 192), ("icon-512.png", 512))


def _put(px: bytearray, w: int, x: int, y: int, color: tuple[int, int, int]) -> None:
    i = (y * w + x) * 3
    px[i:i + 3] = bytes(color)


def _fill_rect(px: bytearray, w: int, h: int,
               x0: float, y0: float, x1: float, y1: float,
               color: tuple[int, int, int]) -> None:
    """矩形填充（像素中心在矩形内即命中，硬边、无抗锯齿，几何确定）。"""
    for y in range(max(0, int(y0 + 0.5)), min(h, int(y1 + 0.5))):
        for x in range(max(0, int(x0 + 0.5)), min(w, int(x1 + 0.5))):
            _put(px, w, x, y, color)


def _fill_poly(px: bytearray, w: int, h: int,
               pts: list[tuple[float, float]],
               color: tuple[int, int, int]) -> None:
    """多边形扫描线填充（even-odd 规则）。Σ 的两斜即两个平行四边形。"""
    ys = [p[1] for p in pts]
    y_lo, y_hi = max(0, int(min(ys) + 0.5)), min(h, int(max(ys) + 0.5))
    n = len(pts)
    for y in range(y_lo, y_hi):
        yc = y + 0.5
        cross: list[float] = []
        for i in range(n):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            if (ay <= yc < by) or (by <= yc < ay):
                cross.append(ax + (yc - ay) / (by - ay) * (bx - ax))
        cross.sort()
        for i in range(0, len(cross) - 1, 2):
            for x in range(max(0, int(cross[i] + 0.5)),
                           min(w, int(cross[i + 1] + 0.5))):
                _put(px, w, x, y, color)


def _draw_sigma(px: bytearray, w: int, h: int) -> None:
    """白色 Σ：三横两斜。全部几何按画布尺寸归一化，任意尺寸同构。"""
    g = 0.58 * w                       # 字形包围盒（正方形，对角线 45°）
    x0, x1 = (w - g) / 2, (w + g) / 2
    y0, y1 = (h - g) / 2, (h + g) / 2
    cx, cy = w / 2, h / 2
    bt = 0.088 * w                     # 横画 / 斜画厚度（垂直度量）

    # 三横：上 / 中 / 下（中横收窄居中，经典 Σ 字形）
    _fill_rect(px, w, h, x0, y0, x1, y0 + bt, FG)
    _fill_rect(px, w, h, x0, y1 - bt, x1, y1, FG)
    _fill_rect(px, w, h, cx - 0.31 * g, cy - bt / 2, cx + 0.31 * g, cy + bt / 2, FG)
    # 两斜：左上 → 中心 → 右下（平行四边形，垂直厚度同为 bt）
    _fill_poly(px, w, h, [(x0, y0), (x0 + bt, y0), (cx + bt, cy), (cx, cy)], FG)
    _fill_poly(px, w, h, [(cx, cy), (cx + bt, cy), (x1, y1), (x1 - bt, y1)], FG)


def _png_bytes(w: int, h: int, rgb: bytes) -> bytes:
    """最小 truecolor PNG 编码器（标准库 zlib + struct，无时间块 → 字节确定）。"""
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)                                   # filter type 0 (None)
        raw += rgb[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8bit / truecolor
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def icon_png(size: int) -> bytes:
    """size×size 的蓝底白 Σ PNG 字节。"""
    px = bytearray(BG * (size * size))
    _draw_sigma(px, size, size)
    return _png_bytes(size, size, bytes(px))


def write_all(out_dir: Path) -> list[Path]:
    """生成三档图标到 out_dir，返回落盘路径（已存在则覆盖，字节确定）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, size in SIZES:
        data = icon_png(size)
        p = out_dir / name
        p.write_bytes(data)
        written.append(p)
        print(f"[gen_app_icon] {p} ({size}x{size}, {len(data)} bytes)")
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PWA / apple-touch 图标生成（纯标准库）")
    ap.add_argument("--out", default=None,
                    help=f"输出目录（默认 {DEFAULT_OUT}）")
    args = ap.parse_args(argv)
    out = Path(args.out) if args.out else DEFAULT_OUT
    write_all(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
