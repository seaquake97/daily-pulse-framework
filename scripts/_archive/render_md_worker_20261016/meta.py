#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""md_render.meta — 标题规范与 meta 三级兜底（纯函数层，零 IO）

单一职责：给定 slug/date/md 正文/market_data.json（调用方读入），产出
FRAMEWORK-DESIGN §2.1 规范标题与（评级, 数据时点）元信息。

## 标题规范（§2.1，P-3 唯一正解）
    <TASK_NAMES[slug]> · YYYY-MM-DD（周X）<阶段标签>
阶段标签按任务的调度窗口固定（早盘竞价/午盘/尾盘/收盘），与 slug 一一对应；
数据时点 stage 独立提取并做三值校验，两者不互相推导。

## meta 三级兜底（§2.3，v1.0「front-matter 强制」盲点的修正）
实测真相：3 份存量 md 均无 front-matter，但带裸 meta 行（`评级：**【进攻】**`、
`诊断状态：Σ 进攻`、`数据时点：…（data_stage: pre_open）`、`档位为：【信号矛盾】档`）。
    L1 front-matter（YAML 头，新任务书 md 才有）
    L2 正文前 50 行启发式（存量兼容）
    L3 market_data.json verdict（--market-data 传入）
    全缺 → rating=None：渲染层出「数据缺口」tag-gap，**禁编造**（§2.3）。

TASK_NAMES / SLUG_STAGE 与 publish_to_github.py 同源同值（复制而非 import：
编排器是 CLI 入口，反向 import 会把整条发布管线拖进渲染进程）。一致性由
test_render_md.py 的 test_task_names_match_publish 断言守住，防静默漂移。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# ---- 与 publish_to_github.py 同源的映射（一致性有测试断言）----
TASK_NAMES: dict[str, str] = {
    "fund-market": "基金盘面分析", "stock-assistant": "股票助手",
    "fund-guide": "基金操作指引", "stock-review": "股票复盘",
    "daily-review": "每日总复盘",
}

SLUG_STAGE: dict[str, str] = {
    "stock-assistant": "intraday",
    "fund-market": "intraday",
    "fund-guide": "intraday",
    "stock-review": "close",
    "daily-review": "close",
}

# 阶段标签（FRAMEWORK-DESIGN §2.1 表）：按任务调度窗口固定，不随提取值漂移
STAGE_LABEL: dict[str, str] = {
    "stock-assistant": "早盘竞价",
    "fund-market": "午盘",
    "fund-guide": "尾盘",
    "stock-review": "收盘",
    "daily-review": "收盘",
}

RATINGS = ("进攻", "均衡", "信号矛盾", "防守", "回避")
STAGES = ("pre_open", "intraday", "close")

WEEKDAY_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

# L2 启发式：评级。四式按优先级排列，同行的首个命中即用——
# 式1 覆盖 `评级：**【进攻】**`（股票助手）；式2 覆盖 `诊断状态：Σ 进攻`（基金盘面）；
# 式3 覆盖 `Σ 评级【进攻】`（无冒号变体）；式4 覆盖 `总档位为：【信号矛盾】档`（14:30 存量）。
# 冒号在式1/式2 中必填：防「评级驱动规则…触发【信号矛盾】档」这类阈值描述被误取。
_RATING_L2 = tuple(re.compile(p) for p in (
    r"评级(?:结果|判定|结论)?\s*[：:]\s*(?:\*\*)?\s*[【\[]?\s*(进攻|均衡|信号矛盾|防守|回避)",
    r"诊断状态\s*[：:]\s*(?:\*\*)?\s*(?:Σ\s*)?[【\[]?\s*(进攻|均衡|信号矛盾|防守|回避)",
    r"Σ\s*评级\s*[【\[]\s*(进攻|均衡|信号矛盾|防守|回避)",
    r"档位(?:为)?\s*[：:]?\s*[【\[]\s*(进攻|均衡|信号矛盾|防守|回避)",
))

# L2 启发式：数据时点。英文 token 优先（显式契约），中文关键词按行内出现位置取最早
_STAGE_EN_RE = re.compile(r"data_stage\s*[：:]\s*(pre_open|intraday|close)"
                          r"|\b(pre_open|intraday|close)\b")
_STAGE_ZH = (("集合竞价", "pre_open"), ("竞价", "pre_open"), ("早盘", "pre_open"),
             ("午盘", "intraday"), ("尾盘", "intraday"), ("盘中", "intraday"),
             ("收盘", "close"))

_FM_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$")


@dataclass
class Meta:
    """提取结果。src 记录命中层级（front-matter/heuristic/market-data/None），
    全缺时 rating/stage 为 None —— 诚实缺口，由渲染层出 tag-gap。"""
    rating: str | None = None
    rating_src: str | None = None
    stage: str | None = None
    stage_src: str | None = None


def dow(date: str) -> str:
    """日期 → 周X（YYYY-MM-DD 非法时抛 ValueError，由 CLI 转退出码）。"""
    return WEEKDAY_ZH[datetime.strptime(date, "%Y-%m-%d").weekday()]


def canonical_title(slug: str, date: str) -> str:
    """§2.1 规范标题。slug 未知/日期非法都是显式错误，不静默兜底。"""
    name = TASK_NAMES.get(slug)
    if not name:
        raise ValueError(f"未知任务 slug: {slug!r}（可用: {', '.join(sorted(TASK_NAMES))}）")
    return f"{name} · {date}（{dow(date)}）{STAGE_LABEL[slug]}"


def _front_matter(text: str) -> dict[str, str]:
    """L1：文件头 `---` 之间的 `key: value` 行（极简 YAML 子集，无第三方依赖）。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm: dict[str, str] = {}
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        m = _FM_KEY_RE.match(ln)
        if m:
            fm[m.group(1).strip().lower()] = m.group(2).strip().strip("\"'")
    return fm


def _valid_rating(value) -> str | None:
    return value if value in RATINGS else None


def _valid_stage(value) -> str | None:
    return value if value in STAGES else None


def _l2_rating(line: str) -> str | None:
    for rx in _RATING_L2:
        m = rx.search(line)
        if m:
            return _valid_rating(m.group(1))
    return None


def _l2_stage(line: str) -> str | None:
    m = _STAGE_EN_RE.search(line)
    if m:
        return _valid_stage(m.group(1) or m.group(2))
    hits = [(line.find(kw), st) for kw, st in _STAGE_ZH if kw in line]
    if hits:
        return _valid_stage(min(hits)[1])
    return None


def extract_meta(md_text: str, market_data: dict | None) -> Meta:
    """三级兜底提取（评级, 数据时点）。任一级命中即停；全缺返回全 None。"""
    meta = Meta()

    # L1 front-matter
    fm = _front_matter(md_text)
    if fm:
        meta.rating = _valid_rating(fm.get("rating"))
        meta.stage = _valid_stage(fm.get("stage") or fm.get("data_stage"))
        if meta.rating:
            meta.rating_src = "front-matter"
        if meta.stage:
            meta.stage_src = "front-matter"

    # L2 正文前 50 行启发式（存量 md 的裸 meta 行）
    if meta.rating is None or meta.stage is None:
        for line in md_text.splitlines()[:50]:
            if meta.rating is None:
                meta.rating = _l2_rating(line)
                if meta.rating:
                    meta.rating_src = "heuristic"
            if meta.stage is None:
                meta.stage = _l2_stage(line)
                if meta.stage:
                    meta.stage_src = "heuristic"
            if meta.rating is not None and meta.stage is not None:
                break

    # L3 market_data.json verdict（现有 load_market_data_for_slug 的数据源）
    if market_data:
        verdict = market_data.get("verdict") or {}
        if meta.rating is None:
            meta.rating = _valid_rating(verdict.get("rating"))
            if meta.rating:
                meta.rating_src = "market-data"
        if meta.stage is None:
            meta.stage = _valid_stage(market_data.get("data_stage")
                                      or verdict.get("data_stage"))
            if meta.stage:
                meta.stage_src = "market-data"

    # stage 兜底：按任务性质判定（与 publish extract_entry 的 SLUG_STAGE 同策略），
    # 不进 src —— 它不是提取结果，是既定事实的回落。
    return meta


def resolve_stage(meta: Meta, slug: str) -> str:
    """stage 最终值：提取值 → SLUG_STAGE 兜底。渲染器只用它做校验与日志。"""
    return meta.stage or SLUG_STAGE.get(slug, "close")
