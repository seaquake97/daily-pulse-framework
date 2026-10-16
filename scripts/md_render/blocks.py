#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""md_render.blocks — 块级 Markdown 解析（语法层，零表现依赖）

单一职责：把 md 文本切成块序列（dict 列表），不做任何 HTML 转义与渲染——
表现全部在 document.py / inline.py。块类型穷尽：
    heading / para / hr / code / table / list / quote / image / html(注释)

支持范围 = FRAMEWORK-DESIGN §2.4 实测裁剪：ATX 标题 / GFM 管道表格 / 任务列表 /
有序无序列表 / 嵌套列表 / 围栏代码 / 引用块 / 分隔线 / 独立图片行 / HTML 注释 /
行内代码 / 粗斜体（行内在 inline.py）。零数学公式：`$...$` 按普通文本进段落。

铁律：解析只做切分，**不丢行不并改文字**；围栏代码块内容 verbatim 保留
（仅转义与 emoji 处置在渲染层发生，且都有留痕）。
"""
from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(?P<hash>#{1,6})[ \t]+(?P<text>.*?)\s*$")
_HR_RE = re.compile(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,}|={3,})\s*$")
_FENCE_RE = re.compile(r"^\s*```")
_LIST_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<bullet>[-*+]|\d{1,9}[.)])[ \t]+(?P<text>.*)$")
_TASK_RE = re.compile(r"^\[([ xX])\][ \t]+(?P<text>.*)$")
_TABLE_DELIM_RE = re.compile(r"^\s*\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)+\|?\s*$")
_IMG_LINE_RE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)(?:\s+\"[^\"]*\")?\)$")

_PIPE_PH = "\x00PIPE\x00"


def _split_row(line: str) -> list[str]:
    """管道行 → 单元格列表。`\\|` 是字面管道（占位保护，不当分隔符）。"""
    s = line.strip().replace("\\|", _PIPE_PH)
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip().replace(_PIPE_PH, "|") for c in s.split("|")]


def _parse_align(delim_line: str) -> list[str | None]:
    out: list[str | None] = []
    for cell in _split_row(delim_line):
        left, right = cell.startswith(":"), cell.endswith(":")
        out.append("center" if left and right else ("left" if left else
                 ("right" if right else None)))
    return out


def _collect_code(lines: list[str], i: int, blocks: list) -> int:
    buf = []
    i += 1                                   # 跳过开围栏
    while i < len(lines) and not _FENCE_RE.match(lines[i]):
        buf.append(lines[i])
        i += 1
    blocks.append({"type": "code", "text": "\n".join(buf)})
    return i + 1 if i < len(lines) else i    # 跳过闭围栏（缺失则到 EOF）


def _collect_quote(lines: list[str], i: int, blocks: list) -> int:
    inner, raw = [], []
    while i < len(lines) and lines[i].lstrip().startswith(">"):
        raw.append(lines[i].lstrip()[1:].removeprefix(" "))
        inner.append(raw[-1])
        i += 1
    blocks.append({"type": "quote", "text": "\n".join(raw),
                   "blocks": parse_blocks("\n".join(inner))})
    return i


def _collect_html(lines: list[str], i: int, blocks: list) -> int:
    buf = []
    while i < len(lines):
        buf.append(lines[i])
        if "-->" in lines[i]:
            i += 1
            break
        i += 1
    blocks.append({"type": "html", "text": "\n".join(buf)})
    return i


def _collect_table(lines: list[str], i: int, blocks: list) -> int:
    header = _split_row(lines[i])
    align = _parse_align(lines[i + 1])
    i += 2
    rows = []
    while i < len(lines) and lines[i].strip() and "|" in lines[i]:
        cells = _split_row(lines[i])
        cells += [""] * (len(header) - len(cells))     # GFM：短行补空、长行截断
        rows.append(cells[:len(header)])
        i += 1
    blocks.append({"type": "table", "header": header, "align": align, "rows": rows})
    return i


def _collect_list(lines: list[str], i: int, blocks: list) -> int:
    items: list[dict] = []
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and (_LIST_RE.match(lines[j]) or lines[j][:1] in (" ", "\t")):
                i = j                                  # 松列表：空行后继续
                continue
            break
        m = _LIST_RE.match(line)
        if m:
            text = m.group("text")
            task = None
            tm = _TASK_RE.match(text)
            if tm:
                task = tm.group(1).lower() == "x"
                text = tm.group("text")
            items.append({"indent": len(m.group("indent").replace("\t", "    ")),
                          "ordered": m.group("bullet")[0] not in "-*+",
                          "task": task, "text": text})
            i += 1
            continue
        if line[:1] in (" ", "\t") and items:          # 缩进续行（惰性延续）
            items[-1]["text"] += "\n" + line.strip()
            i += 1
            continue
        break
    blocks.append({"type": "list", "items": items})
    return i


def _collect_para(lines: list[str], i: int, blocks: list) -> int:
    buf: list[str] = []
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            break
        if buf and (_HEADING_RE.match(line) or _HR_RE.match(line)
                    or _LIST_RE.match(line) or _FENCE_RE.match(line)
                    or line.lstrip().startswith((">", "<!--"))
                    or ("|" in line and i + 1 < n
                        and _TABLE_DELIM_RE.match(lines[i + 1]))):
            break
        buf.append(line)
        i += 1
    text = "\n".join(buf).strip()
    m = _IMG_LINE_RE.match(text)
    if m:
        blocks.append({"type": "image", "alt": m.group("alt"), "src": m.group("src")})
    else:
        blocks.append({"type": "para", "text": text})
    return i


def parse_blocks(text: str) -> list[dict]:
    """md 文本 → 块序列。文件头 front-matter 整体跳过（元数据不进正文）。"""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for k in range(1, len(lines)):
            if lines[k].strip() == "---":
                lines = lines[k + 1:]
                break
    blocks: list[dict] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if _FENCE_RE.match(line):
            i = _collect_code(lines, i, blocks)
            continue
        m = _HEADING_RE.match(line)
        if m:
            blocks.append({"type": "heading", "level": len(m.group("hash")),
                           "text": m.group("text")})
            i += 1
            continue
        if line.lstrip().startswith(">"):
            i = _collect_quote(lines, i, blocks)
            continue
        if "|" in line and i + 1 < n and _TABLE_DELIM_RE.match(lines[i + 1]):
            i = _collect_table(lines, i, blocks)
            continue
        if _HR_RE.match(line):
            blocks.append({"type": "hr"})
            i += 1
            continue
        if line.lstrip().startswith("<!--"):
            i = _collect_html(lines, i, blocks)
            continue
        if _LIST_RE.match(line):
            i = _collect_list(lines, i, blocks)
            continue
        i = _collect_para(lines, i, blocks)
    return blocks
