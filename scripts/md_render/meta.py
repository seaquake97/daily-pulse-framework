#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""md_render.meta — 标题规范与 meta 三级兜底（纯函数层，零 IO）

单一职责：给定 slug/date/md 正文/market_data.json（调用方读入），产出
FRAMEWORK-DESIGN §2.1 规范标题与（评级, 数据时点）元信息。

## 标题规范（§2.1，P-3 唯一正解）
    <TASK_NAMES[slug]> · YYYY-MM-DD（周X）<阶段标签>
阶段标签按任务的调度窗口固定（早盘竞价/午盘/尾盘/收盘，§2.1 表）——午盘与
尾盘同属 intraday，只有 slug 能区分，故 render_title 的 stage 参数只作语义
传入、不参与标签推导（调用方传 SLUG_STAGE 或 verdict.data_stage 均可）。

## meta 三级兜底（§2.3，v1.0「front-matter 强制」盲点的修正）
实测真相：3 份存量 md 均无 front-matter，但带裸 meta 行（`评级：**【进攻】**`、
`诊断状态：Σ 进攻`、`数据时点：…（data_stage: pre_open）`、`档位为：【信号矛盾】档`）。
    L1 front-matter（YAML 头，新任务书 md 才有）
    L2 正文前 50 行启发式（存量兼容）
    L3 market_data.json verdict（--market-data 传入）
    全缺 → rating=None / source="none"：渲染层出「数据缺口」徽章，**禁编造**。

TASK_NAMES / SLUG_STAGE 与 publish_to_github.py 同源同值（复制而非 import：
编排器是 CLI 入口，反向 import 会把整条发布管线拖进渲染进程）。一致性由
test_render_md.py 的 test_all_slugs（精确标题串）+ TASK_NAMES 相等断言守住，
防静默漂移。
"""
from __future__ import annotations

import re
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

# L2 启发式：评级。四式按优先级排列，同行首个命中即用——
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

# 标题清洗：井号 / emoji（含变体选择符与 ZWJ）/ md 强调符 / 表格竖线残留 / 链接取文本
_TITLE_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001F9FF\U0001FAFF\u2600-\u26FF\u2700-\u27BF\uFE00-\uFE0F\u200D]+")
_TITLE_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_DASH_SUFFIX_RE = re.compile(r"\s*[—–]\s+.*$")

_FM_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$")


def dow(date: str) -> str:
    """日期 → 周X（YYYY-MM-DD 非法时抛 ValueError，由 CLI 转退出码）。"""
    return WEEKDAY_ZH[datetime.strptime(date, "%Y-%m-%d").weekday()]


def render_title(slug: str, date: str, stage: str | None = None) -> str:
    """§2.1 规范标题。stage 仅语义传入（午盘/尾盘同属 intraday，标签由 slug 定）。"""
    name = TASK_NAMES.get(slug)
    if not name:
        raise ValueError(f"未知任务 slug: {slug!r}（可用: {', '.join(sorted(TASK_NAMES))}）")
    return f"{name} · {date}（{dow(date)}）{STAGE_LABEL[slug]}"


def _clean_title(raw: str) -> str:
    """标题清洗：去井号、去 emoji、去 markdown 强调符、链接取文本、剥行首
    破折号装饰与尾部表格竖线残留。

    与 publish_to_github._clean_title 同口径（entries.json 与页面标题一致），
    但不剥行首破折号——破折号副标题的处置在渲染层按标题级别决定（见
    document._render_heading：仅 md H1 剥，§3.1 标题铁律）。
    竖线只剥尾部残留：标题正文内的 `|`（如「决策卡 1 | 配置卡」）是内容，
    整串替换即丢字（正文 100% 无损铁律）。
    """
    t = _TITLE_EMOJI_RE.sub("", str(raw).strip().lstrip("#").strip())
    t = _TITLE_LINK_RE.sub(r"\1", t)
    t = re.sub(r"^\s*[—–\-·]+\s*", "", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"__(.+?)__", r"\1", t)
    t = t.replace("`", "").rstrip("|").strip()
    return re.sub(r"\s{2,}", " ", t).strip()


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


def extract_meta(md_text: str, market_data: dict | None = None) -> dict:
    """三级兜底提取。返回 {"rating", "stage", "source"}。

    source = 首个产出结果的层级（front-matter > heuristic > market_data）；
    全缺为 "none"——调用方据此渲染「数据缺口」，禁编造（§2.3）。
    """
    rating = stage = None
    src_rating = src_stage = None

    fm = _front_matter(md_text)                       # L1
    if fm:
        rating = _valid_rating(fm.get("rating"))
        stage = _valid_stage(fm.get("stage") or fm.get("data_stage"))
        src_rating = src_stage = "front-matter" if (rating or stage) else None

    if rating is None or stage is None:               # L2
        for line in md_text.splitlines()[:50]:
            if rating is None:
                rating = _l2_rating(line)
                if rating:
                    src_rating = "heuristic"
            if stage is None:
                stage = _l2_stage(line)
                if stage:
                    src_stage = "heuristic"
            if rating is not None and stage is not None:
                break

    if market_data and (rating is None or stage is None):   # L3
        verdict = market_data.get("verdict") or {}
        if rating is None:
            rating = _valid_rating(verdict.get("rating"))
            if rating:
                src_rating = "market_data"
        if stage is None:
            stage = _valid_stage(market_data.get("data_stage")
                                 or verdict.get("data_stage"))
            if stage:
                src_stage = "market_data"

    source = src_rating or src_stage or "none"
    return {"rating": rating, "stage": stage, "source": source}
