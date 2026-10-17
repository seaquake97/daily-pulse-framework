#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diagnostics.py — 决策日志诊断收集器（纯标准库，零依赖）

与 rules_core.Report 的区别，不能省掉这一层：
  · rules_core.Report 的行号来自 yaml_min 的 line_index，键是 YAML 路径；
    决策日志条目常由引擎在内存里构造，没有文件行号，硬套 YAML 行号索引只会
    产出一堆 line=0 的假定位。
  · 决策日志需要按**条目**聚合（A-13 跨条目统计同观察点动作数），
    以及按**观察点**聚合（A-08 互斥判定），这两种聚合错误报告的结构不支持。

因此这里定义自己的 Report：定位串用 `decision_log[3].observation_point.trigger`
这类点分路径，行号由可选的 line_index 提供（条目来自 YAML 文件时才有）。
对外形状与 rules_core.Report 保持一致（errors/warnings/ok/err/warn），
下游 CI 断言与格式化函数可以照抄现有写法。
"""
from __future__ import annotations

from contracts import E_STRUCTURE


def item_loc(index: int, *suffix) -> str:
    """位置串构造：`decision_log[3]` + `.action.amount`。"""
    base = f"decision_log[{index}]"
    return ".".join((base,) + suffix) if suffix else base


class JournalReport:
    """诊断收集器。

    line_index 可选：条目由 YAML 文件读入时传入（键为上述位置串），
    内存构造的条目不传——此时行号为 0，不猜行号（与 rules_core.Report 同纪律）。
    """

    def __init__(self, line_index: dict | None = None) -> None:
        self.errors: list = []
        self.warnings: list = []
        self.line_index = line_index or {}

    def _locate(self, loc: str) -> dict:
        no = self.line_index.get(loc, 0)
        if not no:
            # 逐级回退到最近已知祖先（`...action.amount` 命中不了就退到 `...action`）。
            # 守卫写成「probe 变短才继续」：对不含 "." 的 loc（如 decision_log[3]），
            # rsplit 会原样返回自身，只判空会死循环。这与 rules_core.Report 同坑。
            probe = loc
            while "." in probe:
                probe = probe.rsplit(".", 1)[0]
                no = self.line_index.get(probe, 0)
                if no:
                    break
        return {"location": loc, "line": no}

    def err(self, loc: str, msg: str, hint: str = "", code: str = E_STRUCTURE) -> None:
        item = {"level": "error", "message": msg, "hint": hint, "code": code}
        item.update(self._locate(loc))
        self.errors.append(item)

    def warn(self, loc: str, msg: str, hint: str = "", code: str = E_STRUCTURE) -> None:
        item = {"level": "warning", "message": msg, "hint": hint, "code": code}
        item.update(self._locate(loc))
        self.warnings.append(item)

    @property
    def ok(self) -> bool:
        return not self.errors

    def codes(self) -> set:
        return {e.get("code") for e in self.errors}

    def for_entry(self, index: int) -> list:
        """取某条目的全部错误。条目位置串前缀是 `decision_log[i]`，
        用 `decision_log[1]` 与 `decision_log[10]` 做前缀比较会互相污染
        （后者不是前者的字符串前缀所以安全，但 `decision_log[1]` 也不该匹配
        不到任何 [10] 开头的更长路径）——这里额外校验括号数字避免这种巧合。"""
        head = f"decision_log[{index}]"
        return [e for e in self.errors
                if e.get("location", "").split(".")[0] == head]

    def summary(self) -> dict:
        return {"ok": self.ok, "error_count": len(self.errors),
                "warning_count": len(self.warnings),
                "codes": sorted(self.codes())}


def format_diagnostics(rep: JournalReport, prefix: str = "error") -> list:
    """格式化输出，与 validate_config._fmt 同款形状（含行号、错误码、提示）。"""
    out = []
    for item in (rep.errors if prefix == "error" else rep.warnings):
        line = f"第 {item['line']} 行" if item.get("line") else "位置未知"
        head = f"[{prefix}] {item['location']}（{line}）"
        code = f" [{item.get('code', '')}]" if item.get("code") else ""
        tail = f"\n        提示: {item['hint']}" if item.get("hint") else ""
        out.append(f"{head}{code}: {item['message']}{tail}")
    return out