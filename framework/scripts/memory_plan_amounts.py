#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory_plan_amounts.py — 从 MEMORY.md 散文段解析每期定投额（纯标准库）

单独成模块的理由：这段逻辑解析的是**自然语言**（句式不统一、一个金额对多个
标的、简称与全称无可推导关系），是整个迁移里最容易出错也最难读懂的一块。
把它从迁移主流程里剥出来，才能各自守住 300 行上限，也让「金额是怎么来的」
这个问题有一个单独的落点可查。

本模块**不含任何真实金额或基金代码**：金额一律从 MEMORY.md 原文解析，
代码里只保留「简称 → 全称关键词」这类名称词汇。
"""
from __future__ import annotations

import re


def parse_plan_amounts(text: str) -> list:
    """从「基金风格」散文段解析每期定投额，返回 [(名称片段, 下限, 上限)]。

    为什么从散文解析而不是在代码里建一张「代码→金额」表：
    那张表等于把真实持仓金额写进代码，既违反「真实数据只存在于
    config/portfolio.yaml」，也会在 MEMORY.md 更新后静默过期。
    散文段与三表同属 MEMORY.md，跟着一起更新，才是同一事实源。

    句式不统一（「汇添富… 70元/天」有单位、「景顺沪港深 60-210」没有；
    「标普500/纳指100 各100元/天」一个金额对两个标的），故按分隔符切段后
    取**段末的数字**（数字总在名称之后），再剥掉「各」「智慧止盈定投」这类
    连接词与计划类型词，剩下的才是标的简称。
    """
    out = []
    for ln in text.splitlines():
        if "基金风格" not in ln:
            continue
        body = ln.split("：", 1)[-1]
        for seg in re.split(r"[、；]", body):
            # 段末的「数字 或 数字-数字」，允许尾随「元/天」等单位
            m = re.search(r"(\d+)\s*(?:-\s*(\d+))?\s*(?:元.*)?$", seg.strip())
            if not m:
                continue
            # 名称 = 数字之前的部分。剥掉冒号、分节标题与计划类型词：
            # 「定投：标普500/纳指100」「：景顺沪港深」里的这些前缀不是标的名。
            name = seg[:m.start()]
            name = re.sub(r"^[^：:]*：", "", name.strip())
            name = re.sub(r"(智慧止盈定投|智慧定投|普通定投|定投持仓|合计约|各|约)",
                          "", name).strip(" ：:、")
            if not name:
                continue
            lo = float(m.group(1))
            hi = float(m.group(2)) if m.group(2) else lo
            # 金额取整：元/天的定投额本就是整数，写成 60.0 会在
            # config 里留下无意义的小数位，也让「重跑产出无 diff」更难核对。
            lo_i, hi_i = int(lo), int(hi)
            # 「A/B 各N元」是一个金额对两个标的：按斜杠拆成两条，
            # 否则只有先匹配到的那只能拿到金额，另一只静默变空。
            for one in ([p.strip() for p in name.split("/") if p.strip()]
                        if "/" in name else [name]):
                out.append((one, lo_i, hi_i))
        break
    return out


# 散文简称 → 基金全称里的关键词。只放**名称词汇**，不含任何金额或代码：
# 简称与全称之间不存在可推导关系（「纳指100」不会出现在「摩根纳斯达克100…」里），
# 只能查表；而金额仍一律从 MEMORY.md 原文解析，不进代码。
NAME_ALIASES = {
    "纳指100": "纳斯达克100",
    "创业板AI": "创业板人工智能",
}


def _match_plan_amount(name: str, amounts: list):
    """按名称把散文里的金额匹配到基金表里的具体标的。

    参数方向容易搞反，这里写明：name 是**基金表里的全称**
    （如「景顺长城沪港深精选股票A」），amounts 里存的是**散文里的简称**
    （如「景顺沪港深」）。两者不是前缀关系——简称可能插在全称中间
    （「景顺沪港深」vs「景顺长城沪港深精选股票A」），所以判据是
    「简称的字符按序出现在全称里」，不是简单的 `in`。

    匹配顺序：字面包含 → 别名展开 → 子序列。三级都失败返回 None，
    调用方留空并在摘要里报出「未匹配」，不猜金额。
    """
    expanded = []
    for frag, lo, hi in amounts:
        for alias, real in NAME_ALIASES.items():
            if frag == alias:
                frag = real
        expanded.append((frag, lo, hi))
    keys = [name] + ([p for p in name.split("/") if p] if "/" in name else [])

    def subseq(frag: str, full: str) -> bool:
        it = iter(full)
        return all(ch in it for ch in frag)

    for full in keys:
        for frag, lo, hi in expanded:
            if frag and (frag in full or subseq(frag, full)):
                return lo, hi
    return None
