#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yaml_emit.py — YAML 子集生成器（纯标准库，零依赖）

为什么需要「写」的 counterpart：yaml_min.py 只负责读。迁移脚本要从
MEMORY.md 的表格文本生成 portfolio.yaml，必须能写；而框架不允许依赖 PyYAML。

与 yaml_min.py 是一对镜像，**共用同一语法子集**：
本模块只产出 yaml_min 能解析的写法（块状、2 空格缩进、必要时加引号），
所以「生成的文件必定能通过自家解析器」是结构性保证，不靠测试兜底。

幂等性：同一输入 dict 必得同一字节输出——键序由插入序决定，
不排序、不含时间戳。迁移脚本可复跑且不产生无意义 diff。
"""
from __future__ import annotations

# 需要加引号的场景：空串、纯数字型字符串（会被读回成 int）、
# 含特殊字符或首尾空格、看起来像 bool/null、易被误读为结构的值。
_PLAIN_SAFE = set("abcdefghijklmnopqrstuvwxyz"
                  "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                  "0123456789_-./+=@%")


def _needs_quote(s: str) -> bool:
    if s == "" or s.strip() != s:
        return True
    if s.lower() in ("true", "false", "yes", "no", "on", "off",
                     "null", "~", "none"):
        return True
    try:
        float(s)
        return True          # "3.0" 必须加引号，否则读回来变成 float
    except ValueError:
        pass
    if any(ch not in _PLAIN_SAFE for ch in s):
        return True
    return s[0] in "-?:,[]{}#&*!|>'\"%" or ": " in s or " #" in s


def _scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v) if isinstance(v, float) else str(v)
    s = str(v)
    return f'"{s}"' if _needs_quote(s) else s


def _emit(node, indent: int, out: list, in_seq: bool = False) -> None:
    """把 dict / list / 标量递归写成块状 YAML。"""
    pad = " " * indent
    if isinstance(node, dict):
        for k, v in node.items():
            key = f'"{k}"' if _needs_quote(str(k)) else str(k)
            prefix = f"{pad}- " if in_seq else f"{pad}{key}:"
            if isinstance(v, (dict, list)) and v:
                out.append(prefix)
                _emit(v, indent + 2, out)
            else:
                out.append(f"{prefix} {_scalar(v)}" if not isinstance(v, (dict, list))
                           else f"{prefix} " + ("[]" if isinstance(v, list) else "{}"))
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, dict) and item:
                first = True
                for k, v in item.items():
                    key = f'"{k}"' if _needs_quote(str(k)) else str(k)
                    prefix = f"{pad}- " if first else f"{pad}  "
                    first = False
                    if isinstance(v, (dict, list)) and v:
                        out.append(f"{prefix}{key}:")
                        _emit(v, indent + 4, out)
                    else:
                        out.append(f"{prefix}{key}: "
                                   + (_scalar(v) if not isinstance(v, (dict, list))
                                      else ("[]" if isinstance(v, list) else "{}")))
            elif isinstance(item, (dict, list)):
                out.append(f"{pad}- " + ("[]" if isinstance(item, list) else "{}"))
            else:
                out.append(f"{pad}- {_scalar(item)}")


def dump_yaml(data: dict, header: str = "") -> str:
    """把 dict 序列化为 YAML 文本（不含尾随换行，由调用方决定）。"""
    out: list = []
    if header:
        out.extend(f"# {ln}" if ln else "#" for ln in header.splitlines())
        out.append("")
    _emit(data, 0, out)
    return "\n".join(out) + "\n"