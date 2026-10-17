#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yaml_min.py — 受限 YAML 子集解析器（纯标准库，零依赖）

为什么要自己写：PyYAML 不是标准库，而框架的硬约束是「别人的机器上 clone 完就能跑」，
不能要求用户先 pip install。代价是只支持 holdings.yaml 需要的语法子集；
遇到子集外的语法**显式报错并给出行号**，绝不猜、绝不静默吞掉——
配置写错要立刻炸，不能带病运行到出报告那天。

支持：块状映射/序列、缩进嵌套、# 注释、单双引号、int/float/bool/null、
      序列项内联首键（- key: value）、空集合 [] 与 {}
不支持：锚点(&) 别名(*) 标签(!!) 多文档(---) 块标量(| >) 非空流式集合 复杂键(?)

单独成模块的理由：解析与校验是两个独立关注点，且各自有独立演进节奏——
解析器可被 MEMORY.md -> YAML 迁移工具复用，校验规则则随契约版本升级。
"""
from __future__ import annotations

import re


class ConfigError(Exception):
    """配置解析失败（带行号）。"""


# ---------------------------------------------------------------------------
# 极简 YAML 子集解析器
# ---------------------------------------------------------------------------
# 明确不支持的语法：锚点/别名/标签/多文档。这些是 YAML 的动态特性，
# 配置契约不需要，放进来只会让「配置写错」与「配置写对」都变得不可预测。
_UNSUPPORTED_PATTERNS = (
    (re.compile(r"(^|:\s)&[A-Za-z_]"), "锚点(anchor &)"),
    (re.compile(r"(^|:\s)\*[A-Za-z_]"), "别名(alias *)"),
    (re.compile(r"!!"), "标签(tag !!)"),
    (re.compile(r"^---\s*$"), "多文档(---)"),
    (re.compile(r"^\.\.\.\s*$"), "文档结束符(...)"),
)


def _strip_comment(line: str) -> str:
    """去掉行尾注释，但不动引号内的 # 。"""
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            continue
        if ch == "#":
            # 仅当 # 前是行首或空白时才算注释（避免砍掉 a#b 这种值）
            if not out or out[-1] in " \t":
                break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(raw: str, line_no: int):
    """把标量文本转成 Python 值。"""
    s = raw.strip()
    if not s or s in ("null", "~", "Null", "NULL"):
        return None
    if s in ("[]",):
        return []
    if s in ("{}",):
        return {}
    if s[:1] in "[{" and len(s) > 1:
        raise ConfigError(
            f"第 {line_no} 行：暂不支持流式集合 {s[:12]!r}。"
            f"请展开为块状写法（每个元素一行），详见 ARCH-R5-FRAMEWORK.md §3.2"
        )
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        inner = s[1:-1]
        if s[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")
        else:
            inner = inner.replace("''", "'")
        return inner
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if re.fullmatch(r"[-+]?\d+", s):
        return int(s)
    if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?", s):
        return float(s)
    if re.fullmatch(r"[-+]?\d+[eE][-+]?\d+", s):
        return float(s)
    if s[:1] in "|>":
        raise ConfigError(
            f"第 {line_no} 行：暂不支持块标量 {s!r}。"
            f"请把内容写成单行双引号字符串"
        )
    return s


class _Line:
    __slots__ = ("indent", "text", "no")

    def __init__(self, indent: int, text: str, no: int):
        self.indent, self.text, self.no = indent, text, no


def _tokenize(text: str) -> list:
    lines, out = text.splitlines(), []
    for no, raw in enumerate(lines, 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ConfigError(
                f"第 {no} 行：缩进不可用 Tab，请改用空格（YAML 规范且跨解析器安全）"
            )
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        for pattern, name in _UNSUPPORTED_PATTERNS:
            if pattern.search(stripped):
                raise ConfigError(
                    f"第 {no} 行：暂不支持 {name}。"
                    f"请改用基础块状写法，详见 ARCH-R5-FRAMEWORK.md §3.2"
                )
        out.append(_Line(len(stripped) - len(stripped.lstrip()), stripped.strip(), no))
    return out


def _parse_block(lines: list, i: int, indent: int, index: dict, prefix: str):
    """解析一个缩进块。返回 (value, next_index)。"""
    if i >= len(lines):
        return None, i
    if lines[i].text.startswith("- "):
        return _parse_seq(lines, i, indent, index, prefix)
    return _parse_map(lines, i, indent, index, prefix)


def _parse_seq(lines: list, i: int, indent: int, index: dict, prefix: str):
    items = []
    while i < len(lines) and lines[i].indent == indent and lines[i].text.startswith("- "):
        line = lines[i]
        body = line.text[2:].strip()
        item_path = f"{prefix}[{len(items)}]"
        index[item_path] = line.no
        if ":" in body and not (body.startswith(("\"", "'")) and body.count(":") > 0
                                and body.index(":") > body.index(body[0])):
            # 序列项内联首个键：- key: value
            virtual = [_Line(indent + 2, body, line.no)]
            j = i + 1
            while j < len(lines) and lines[j].indent > indent:
                virtual.append(lines[j])
                j += 1
            val, _ = _parse_map(virtual, 0, indent + 2, index, item_path)
            items.append(val)
            i = j
        else:
            if j_has_child(lines, i + 1, indent):
                val, i = _parse_block(lines, i + 1, lines[i + 1].indent, index, item_path)
            else:
                val, i = _scalar(body, line.no), i + 1
            items.append(val)
    return items, i


def j_has_child(lines: list, i: int, indent: int) -> bool:
    return i < len(lines) and lines[i].indent > indent


def _parse_map(lines: list, i: int, indent: int, index: dict, prefix: str):
    out = {}
    while i < len(lines) and lines[i].indent == indent:
        line = lines[i]
        if line.text.startswith("- "):
            break
        m = re.match(r'^("(?:[^"]*)"|\'(?:[^\']*)\'|[^:]+?)\s*:(?:\s+(.*))?$', line.text)
        if not m:
            raise ConfigError(f"第 {line.no} 行：无法解析 '{line.text}'（期望 key: value）")
        key, rest = m.group(1).strip().strip("\"'"), (m.group(2) or "").strip()
        if key in out:
            raise ConfigError(f"第 {line.no} 行：重复键 '{key}'")
        child = f"{prefix}.{key}" if prefix else key
        index[child] = line.no
        if rest:
            out[key] = _scalar(rest, line.no)
            i += 1
        elif i + 1 < len(lines) and lines[i + 1].indent > indent:
            out[key], i = _parse_block(lines, i + 1, lines[i + 1].indent, index, child)
        elif i + 1 < len(lines) and lines[i + 1].text.startswith("- ") \
                and lines[i + 1].indent == indent:
            out[key], i = _parse_seq(lines, i + 1, indent, index, child)
        else:
            out[key], i = None, i + 1
    return out, i


def parse_yaml_subset(text: str):
    """把配置文件文本解析成 dict。受限语法，非法即抛 ConfigError。"""
    value, _index = parse_yaml_subset_indexed(text)
    return value


def parse_yaml_subset_indexed(text: str):
    """同 parse_yaml_subset，额外返回 路径 -> 行号 的索引。

    错误必须带行号，否则用户拿到「holdings.stock.positions[3].shares 不是整数」
    只能自己数行。索引在解析时顺带产出，不做第二遍扫描——
    同一份文本只解析一次，也就不存在「两套解析器结论不一致」的可能。
    """
    lines = _tokenize(text)
    index: dict = {}
    if not lines:
        return {}, index
    value, consumed = _parse_block(lines, 0, lines[0].indent, index, "")
    if consumed != len(lines):
        raise ConfigError(
            f"第 {lines[consumed].no} 行：缩进异常，无法解析（检查是否混用 Tab 或层级错位）"
        )
    return value, index


# ---------------------------------------------------------------------------
# 校验规则
