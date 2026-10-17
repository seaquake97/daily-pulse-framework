#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_body_css.py — 一次性预编译正文用到的 Tailwind 工具类（构建脚本）

为什么需要它
    fund-market.html 用 Tailwind Play CDN 在**浏览器里**实时编译 197 个工具类。
    直接删 CDN ≠ 删样式脚本，而是删掉整页样式（页面变成无格式白底文字）。
    本脚本把用到的工具类**预编译成静态 CSS 并入库**，发布时内联进正文，
    从而在零 JS 的前提下保持样式等价。

为什么必须入库而不是每次发布时编译
    发布幂等性要求「同一天重跑产出字节一致」。若在发布流程里实时调用
    tailwindcss，产物字节会随 npm 包版本、类名扫描顺序、构建时间而漂移，
    直接破坏幂等性。因此编译结果作为**源码资产**提交，发布只做读取+内联。

用法（改了正文类名才需要重跑）
    python3 scripts/build_body_css.py
    # → 写入 scripts/assets/body-utilities.css

范围与取舍
    · 只编译「正文里真实出现过的类」，不做全量 Tailwind —— 产物小、可审计。
    · 保留 Tailwind 默认调色板：颜色收敛由 style_pass 在产物上二次处理
      （把 hex 换成 var(--token)），这里负责的是**布局类**能落地。
    · 渐变工具类（bg-gradient-*）本项目不使用，编译产物里不保留任何
      linear/radial/conic-gradient（已由门禁校验）。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "framework" / "scripts"))   # A-04: 集中路径
import paths
OUT_DIR = HERE / "assets"
OUT_CSS = OUT_DIR / "body-utilities.css"
DEFAULT_SOURCE = paths.PROJECT_ROOT / "_stage" / "docs" / "daily" / "2026-10-14" / "fund-market.html"

TW_VERSION = "3.4.17"
GRADIENT_RE = re.compile(r"(?:linear|radial|conic)-gradient\s*\(", re.I)


def _npx() -> str | None:
    """定位 npx（构建期依赖，缺失时给出明确指引而非静默跳过）。"""
    for cand in ("npx", shutil.which("npx")):
        if cand and (cand == "npx" or Path(cand).exists()):
            return cand
    return None


def compile_utilities(source: Path, out_css: Path = OUT_CSS) -> int:
    """编译 source 里用到的 Tailwind 类，写入 out_css。返回 CSS 字节数。"""
    if not source.exists():
        raise FileNotFoundError(f"源正文不存在：{source}")
    npx = _npx()
    if not npx:
        raise RuntimeError(
            "未找到 npx，无法预编译 Tailwind。\n"
            "  处置：正文将保留 Tailwind CDN（不删样式引擎），并在报告中标记\n"
            "  needs-manual-review —— 这比产出无样式页面安全。\n"
            "  修复：安装 Node.js 后重跑 python3 scripts/build_body_css.py")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        raw = td / "content.html"
        raw.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        (td / "in.css").write_text(
            "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n",
            encoding="utf-8")
        (td / "tw.config.js").write_text(
            "module.exports = {content: [require('path').resolve(__dirname,'content.html')],"
            " theme:{extend:{}}, plugins:[]};\n", encoding="utf-8")
        built = td / "out.css"
        # --minify 会去掉注释与空白，产物更小且更稳定（减少无意义字节漂移）
        proc = subprocess.run(
            [npx, "--yes", f"tailwindcss@{TW_VERSION}", "-c", str(td / "tw.config.js"),
             "-i", str(td / "in.css"), "-o", str(built), "--minify"],
            capture_output=True, text=True, timeout=300)
        if proc.returncode != 0 or not built.exists():
            raise RuntimeError(f"tailwind 编译失败：{proc.stderr.strip()[:400]}")
        css = built.read_text(encoding="utf-8")

    # 门禁：产物里不允许残留任何渐变函数
    hits = GRADIENT_RE.findall(css)
    if hits:
        raise RuntimeError(
            f"编译产物含 {len(hits)} 处渐变，违反零渐变基线：{set(hits)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    header = ("/* 本文件由 scripts/build_body_css.py 生成，请勿手工编辑。\n"
              f"   源：{source.name}\n"
              f"   工具：tailwindcss@{TW_VERSION} --minify\n"
              "   作用：替代 Tailwind Play CDN，使正文在零 JS 下保持样式等价。\n"
              "   注意：颜色收敛由 sanitizer/style_pass.py 在产物上二次处理。*/\n")
    out_css.write_text(header + css, encoding="utf-8")
    return len(css)


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    try:
        size = compile_utilities(source)
    except Exception as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1
    print(json.dumps({"source": str(source), "out": str(OUT_CSS), "css_bytes": size},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())