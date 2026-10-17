#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""path_pass.py — 本机绝对路径脱敏（变换层）

单一职责：把正文里的本机路径脱敏，保留文件名。

## 为什么必须有这一层（安全 P0）

2026-10-16 实测：上游 15:05 复盘的正文里写着
「数据源：/Users/lianghaizhen/WorkBuddy/股票复盘/2026-10-15/settlement.json」，
渲染后直接出现在公开 GitHub Pages 上——**向全网泄漏本机用户名与目录结构**，
且对读者零信息价值。

## 为什么渲染层已经改过还要再做一层

`md_render/inline.py` 已在渲染入口脱敏，但**上游直传 html 不经过 inline()**
（如 `--no-sanitize` 回退通道、或未来新增的不经渲染器的产物）。
消毒链是所有 html 的最后一道闸——放在这里才真正兜得住。

## 脱敏规则

  /Users/<用户名>/<任意路径>/<文件名.ext>   →   …/<文件名.ext>
  /Users/<用户名>                          →   …（整体抹掉）

只保留文件名：读者要的是「用了哪个文件」，不是「它存在哪个目录」。
这不丢任何信息——路径部分对读者无意义。
"""
from __future__ import annotations

import re

# 匹配以文件扩展名结尾的绝对路径（保留文件名）
# ⚠ 分段必须**非贪婪 + 逐段锚定**：`(?:/[^\s"'<>]*)*?` 会把最后一段的前半截也
# 吃掉——实测 `.../2026-10-15/settlement.json` 被截成 `t.json`（"setlemen" 被
# 前一段的 `[^...]*` 吞掉）。改为逐段 `[^/]+`，让最后一段完整匹配文件名。
_FILE_PATH = re.compile(
    r"/Users/[^/\s\"'<>]+(?:/[^/\s\"'<>]+)*/([^/\s\"'<>]+\.(?:json|md|html|htm|csv|py|sh|yaml|yml|txt))")
# 匹配无扩展名的家目录残留（如 /Users/lianghaizhen 单独出现）
_HOME_ONLY = re.compile(r"/Users/[^/\s\"'<>]+")


def _scrub(text: str) -> str:
    text = _FILE_PATH.sub(r"…/\1", text)
    return _HOME_ONLY.sub("…", text)


def scrub_paths(html: str, report=None) -> str:
    """脱敏 html 中的本机绝对路径，返回新串（原地不改）。

    report 非空时记录改动条数，便于门禁查看（刻意不当作 error——
    上游正文带路径是常态，脱敏是兜底而非阻断）。
    """
    out = _scrub(html)
    if report is not None and out != html:
        n = sum(1 for a, b in zip(html.split(), out.split()) if a != b)
        try:
            report.add("path", f"本机绝对路径脱敏 {n} 处（保留文件名）")
        except AttributeError:
            pass
    return out
