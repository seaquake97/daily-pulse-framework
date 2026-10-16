#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report.py — 消毒审计报告（sanitizer 包的最底层，无依赖）

职责：记录 sanitize 过程中的每一处改动，供回溯与门禁核对。

设计要点：
  · 只追加，不聚合 —— 保留原始顺序，便于逐条比对；
  · 记录「改了什么」而非「改成什么」的完整快照，避免报告体积失控；
  · counts() 给出分类计数，供publish 层打印与测试断言。

依赖方向：本模块不 import 任何上层模块（纯数据结构）。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Change:
    """一处可回溯的改动。

    kind: 改动类别（emoji / gradient / script / style / heading / icon / token
                      / unmapped-color / unmapped-token）
    detail: 人类可读描述（必须能定位到原文片段）
    count: 该条覆盖的实例数（默认 1）
    """
    kind: str
    detail: str
    count: int = 1


@dataclass
class SanitizeReport:
    """一次 sanitize 调用的完整审计记录。

    invariants（在__post_init__ 断言）：
      · changes 只增不改 → 报告本身可作为幂等性的比对基线。
    """
    source: str = ""
    changes: list[Change] = field(default_factory=list)

    def add(self, kind: str, detail: str, count: int = 1) -> None:
        """记录一处改动。count < 1 视为输入错误，直接拒绝（防脏数据进门禁）。"""
        if count < 1:
            raise ValueError(f"change count 必须 >= 1，收到 {count}（kind={kind}）")
        self.changes.append(Change(kind=kind, detail=detail, count=count))

    def extend(self, kind: str, details: list[str]) -> None:
        """批量记录同类改动；空列表不产生任何条目。"""
        for d in details:
            self.add(kind, d)

    # ---- 查询（供测试与门禁断言） ----
    def kinds(self) -> set[str]:
        """出现过的改动类别集合。"""
        return {c.kind for c in self.changes}

    def count_of(self, kind: str) -> int:
        """某类别的实例总数（各条 count 之和）。"""
        return sum(c.count for c in self.changes if c.kind == kind)

    def counts(self) -> dict[str, int]:
        """按类别汇总的改动计数，键按字母序（保证输出稳定 → 幂等可比）。"""
        out: dict[str, int] = {}
        for c in self.changes:
            out[c.kind] = out.get(c.kind, 0) + c.count
        return {k: out[k] for k in sorted(out)}

    def details(self, kind: str | None = None) -> list[str]:
        """按类别取明细（None = 全部），保持记录顺序。"""
        return [c.detail for c in self.changes if kind is None or c.kind == kind]

    @property
    def total(self) -> int:
        """改动总实例数。"""
        return sum(c.count for c in self.changes)

    def summary(self) -> str:
        """单行摘要（publish 层日志用）。键序稳定 → 可直接做字节比对。"""
        if not self.changes:
            return "no-change"
        return ", ".join(f"{k}={v}" for k, v in self.counts().items())

    def to_dict(self) -> dict:
        """结构化导出（写JSON 证据用）。"""
        return {
            "source": self.source,
            "total": self.total,
            "counts": self.counts(),
            "changes": [{"kind": c.kind, "detail": c.detail, "count": c.count}
                        for c in self.changes],
        }