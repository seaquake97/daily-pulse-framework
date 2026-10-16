#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""freshness.py — 消毒代码时点 vs 产物时点护栏（发布管线契约层）

单一职责：回答「待消毒/待发布的产物是否陈旧于 sanitizer 代码」。
本模块不做任何变换，只做时点比对 —— 供 publish_to_github.py 的
run_sanitize 在消毒步骤前调用。

## 为什么需要（2026-10-15 门禁事故）
设计师扫描时发现 stage 产物曾陈旧于 sanitizer 代码（产物 19:00 <
代码 19:27）：新写的消毒规则尚未应用到旧产物上，扫描出的「残留」
是虚假残留，而按旧代码消毒的产物可能带着已修复类缺陷（如 B-3 的
fg-on-fg）被直接发布。随后的重跑治愈了当次事故，但需要护栏防再发。

## 护栏语义
mtime 是粗代理，但「不存在代码新于产物却直接发布的路径」是硬验收：
  · 正常发布路径 —— 产物全部重新消毒（run_sanitize 本就每轮重跑目标
    日期目录），陈旧产物被强制纳入本轮消毒并在 manifest 留痕（stale_forced）；
  · --no-sanitize 回退路径 —— 若存在陈旧产物则**阻断**（返回 None，
    编排器按契约退出码 3 结束）。回退通道可以原样发布新写盘的产物，
    但不能原样发布早于消毒代码的历史产物。

## 扫描范围（2026-10-15 跨日期腐败事故后收窄）
调用方（publish_to_github.run_sanitize）只传目标日期目录
_stage/docs/daily/<date>：护栏与消毒同范围，历史日期不在本轮发布
范围，其时点由各自发布轮次负责。此前传 daily 全树会把「昨日已消毒
已加框的页面」重新纳入处理链，正是腐败根因；目标日期的页面是步骤 4
刚写入的（mtime=now），正常路径不会触发陈旧——护栏主要保护
--no-sanitize 与手工场景。

文件系统 mtime 有秒级（或更粗）精度，比对时留 _MTIME_EPS 余量，
避免「同一秒内写入」被误判为陈旧。
"""
from __future__ import annotations

from pathlib import Path

# sanitizer 包目录（本文件所在目录）：代码时点的取样范围
SANITIZER_DIR = Path(__file__).resolve().parent

# mtime 比对余量（秒）：产物 mtime 落后代码不足此值不算陈旧
_MTIME_EPS = 1.0


def sanitizer_code_mtime() -> float:
    """scripts/sanitizer/ 下任一 .py 的最新 mtime（代码时点）。

    只取 .py（不含 __pycache__ 的 .pyc）：.pyc 是导入副产物，
    mtime 随解释器行为漂移，不能代表「规则代码」的时点。
    """
    pys = [p for p in SANITIZER_DIR.rglob("*.py") if p.is_file()]
    return max((p.stat().st_mtime for p in pys), default=0.0)


def stale_artifacts(daily: Path, code_mtime: float | None = None) -> list[Path]:
    """时点早于消毒代码的详情页产物（陈旧产物清单，按路径排序）。

    daily 为扫描范围目录。发布管线传 _stage/docs/daily/<date>（目标
    日期，与消毒范围一致）；目录不存在时返回空列表（首发布场景）。
    """
    if not daily.is_dir():
        return []
    if code_mtime is None:
        code_mtime = sanitizer_code_mtime()
    return [p for p in sorted(daily.rglob("*.html"))
            if p.is_file() and p.stat().st_mtime < code_mtime - _MTIME_EPS]
