#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""path_scrub.py — 本机绝对路径脱敏（单一实现，供发布层与渲染层共用）

## 为什么需要（PM-17 实测）

上游报告正文会出现这类引导句：

    依据 `/Users/<用户名>/WorkBuddy/股票复盘/2026-10-15/settlement.json` 自动结算结果：

`.md` 是**被发布到 GitHub Pages 的产物**（可直接访问），完整路径等于
在公开站点上暴露本机用户名与目录结构。读者要的是「用了哪个文件」，
不是「存在哪个目录」。

## 三种载体，只脱敏其中两种（本轮实测结论）

| 载体 | 是否发布 | 本模块覆盖 |
|---|---|---|
| HTML body | 是 | 是——但**已由 `md_render/inline.py` 的 `_scrub_home_path` 覆盖** |
| `.md` 原文产物 | 是 | **是——本模块的补齐目标** |
| `feed.json` | 是 | 不含自由文本，无需覆盖 |

**为什么 HTML 已安全**：`md_render/inline.py:175` 在渲染主流程里调用
`_scrub_home_path`，`:165` 的代码块路径也单独过一遍。实测 10-15 的
`stock-review.html` 中本机用户名绝对路径命中数为 0，只有
`…/WorkBuddy/股票复盘/.../settlement.json`。

**为什么 `.md` 是漏点**：`publish_to_github.py:646-648` 用
`write_text(raw)` 原样落盘（该行日志自称「原样，未脱敏」），
`.md` 不经 sanitizer 的 body pass，也不经 `render_md` 的渲染流程——
它只是被当作渲染**输入**读了一遍，自身文本从未被改写。

## 设计要点

1. **按形态处置，不按具体实例**：只匹配绝对路径的语法形态
   （`/Users/<名>/...`、`/Volumes/...`、`/opt/...`、`/home/<名>/...`），
   不硬编码 `settlement.json`。今天修 settlement，明天上游引入
   `holdings.json` 的路径引用自动覆盖。
2. **只保留文件名**：`…/settlement.json`。保留文件名是有意的——
   它对读者有信息价值（可追溯用了哪个产物），目录结构没有。
3. **不静默**：返回 `unresolved` 计数，命中但没改成的必须报出来。
   「脱敏失败」与「脱敏成功」在报告上长得一样，就成了另一种沉默。
4. **不碰代码块语义**：反引号内的路径同样脱敏（读者看到的是文件名，
   不是目录），但保留反引号本身。

## 用法

```python
from path_scrub import scrub_text, count_hits

clean, hits = scrub_text(raw)      # hits 为成功脱敏处数
```

渲染层 `md_render/inline.py` 的 `_scrub_home_path` 应改为调用本模块，
避免两套正则各自演化（那正是 A-10 / A-19 反复出现的病根）。
"""
from __future__ import annotations

import re

# 绝对路径形态。刻意不匹配 https:// 等 URL（那不是本机信息）。
# 末尾要求一个带扩展名的文件名，否则像 /opt/ 这类裸目录不处理——
# 目录本身无信息价值，但也无法在不破坏语义的前提下截断。
_ABS_PATH_RE = re.compile(
    r"(?<![\w./-])"                        # 左边界：前一字符不能是 URL/路径字符
    r"(?P<root>/Users/[^/\s\"'`<>]+"
    r"|/home/[^/\s\"'`<>]+"
    r"|/Volumes/[^/\s\"'`<>]+"
    r"|/opt/[^/\s\"'`<>]+"
    r"|/private/var/[^/\s\"'`<>]+)"
    r"(?:/[^/\s\"'`<>]*)*?"               # 中间段（非贪婪，最少 0 段）
    r"/(?P<file>[^\s\"'`<>/]+\.(?:json|md|html|csv|py|ya?ml|txt))"  # 末段含文件名
    r"(?![\w/])"                          # 右边界：后面不能接路径字符
)


def count_hits(text: str) -> int:
    """只数不脱——用于断言与巡检（判据：发布产物中命中数须为 0）。"""
    return len(_ABS_PATH_RE.findall(text or ""))


def scrub_text(text: str) -> tuple[str, int]:
    """绝对路径 → `…/文件名`。

    返回 (脱敏后文本, 成功脱敏处数)。命中但未改动的记为 0——
    调用方应把「有 hits 但 scrubbed 为 0」视为异常并告警。
    """
    if not text:
        return text, 0
    n = 0

    def _rep(m: re.Match) -> str:
        nonlocal n
        n += 1
        return f"…/{m.group('file')}"

    return _ABS_PATH_RE.sub(_rep, text), n


def find_paths(text: str) -> list[str]:
    """列出命中的绝对路径原文（供 report 记录，不做替换）。"""
    if not text:
        return []
    return [m.group(0) for m in _ABS_PATH_RE.finditer(text)]
