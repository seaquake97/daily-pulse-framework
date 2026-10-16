#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pipeline_selftest.py — 发布流水线全量自测（dry-run 证据包核心）

对 2026-10-14 / 2026-10-13 两个日期的真实任务产出，执行两段式脱敏：
  阶段一  scripts/desensitize.py（团队基础引擎，team-lead 维护）
  阶段二  scripts/redline_hardening.py（红线加固层，dev 维护）

校验五项硬指标：
  L1 泄漏归零   姓名/成本价/股份份数/持仓金额/组合暴露百分比/敏感词词面
  L2 市场保留   指数点位/涨跌幅/成交额/Σ评分/股息率等公开数据不被误杀
  L3 幂等       harden(harden(x)) == harden(x)，重复发布不产生新变化
  L4 结构完整   HTML 标签配平、MD 标题结构不塌
  L5 A/B 双面   A 面个人数据跨文件零残留；B 面公开数据逐文件保留
                （team-lead 2026-10-14 裁决的验收口径，防安全回归与误杀回归）

退出码：0 全部通过；1 有泄漏（含 A 面残留）；2 有误杀（B 面）/参数错误；
3 幂等失败；4 结构损坏。（与 publish_to_github.py 统一：0=通过/1=泄漏/
2=无产出或误杀/3=站点失败/4=manifest失败/5=结构幂等失败——本脚本聚焦脱敏层，
2 在此语义为「误杀」，发布编排器以 publish_to_github.py 的退出码定义为准。）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from desensitize import desensitize_text, check_residual          # noqa: E402
from redline_hardening import (harden, harden_verify, redline_scan,  # noqa: E402
                               REDLINE_GATE)

SRC = Path("/Users/lianghaizhen/WorkBuddy")

# (源文件, 格式, 敏感模式清单[正则], 公开数据清单[正则])
# 敏感 = 个人数据，必须零残留；公开 = 市场数据，必须保留（防误杀）
CASES = [
    ("基金每日盘面分析（11:00）/2026-10-14/fund_market_analysis.html", "html",
     [r"海震", r"34\.74", r"27\.41", r"63,322\.65", r"2,412\.05", r"16,287\.66", r"0\.57%"],
     [r"3,807\.50", r"\+0\.17%", r"38\.6%", r"≥2%", r"\+0\.125", r"12,316\.01"]),
    ("基金每日盘面分析（11:00）/2026-10-14/fund_market_analysis.md", "md",
     [r"海震", r"34\.74", r"27\.41", r"63,322\.65", r"2,412\.05", r"16,287\.66"],
     # 注：38.6%（上涨家数占比）被 v3 引擎误掩——已知 v3 问题，已上报 team-lead，
     # 不纳入本层验收；本层只保证不新增误杀。
     [r"3,807\.50", r"\+0\.17%", r"12,316\.01", r"2,929\.53", r"24,345\.22"]),
    ("每日总复盘（15:30）/2026-10-13/daily_review.html", "html",
     [r"海震", r"浮盈", r"成本摊薄", r"1\.696", r"\d+股", r"\d+份", r"1\.385",
      r"34\.74", r"27\.41", r"18\.50-24\.50", r"6\.50-8\.50", r"0\.850-1\.250"],
     [r"-2\.67%", r"-0\.44%", r"\+0\.10%", r"\+0\.31%", r"-1\.69%", r"4\.51%",
      r"4\.55%", r"-0\.30%", r"3800点"]),
    ("每日总复盘（15:30）/2026-10-13/stock_review.md", "md",
     [r"海震", r"浮盈", r"成本摊薄", r"1\.696", r"\d+股", r"\d+份", r"1\.385",
      r"18\.50-24\.50", r"6\.50-8\.50", r"0\.850-1\.250"],
     [r"3800\.86", r"12353\.70", r"2958\.34", r"1427\.18", r"4275\.68", r"1008\.66",
      r"16,891\.33", r"2909", r"2486", r"13\.91%", r"1\.45%", r"1\.06%", r"4\.5%"]),
    ("基金每日操作指引（14:30）/2026-10-13/fund_operation_guide.md", "md",
     [r"海震", r"15,080\.21", r"8,313\.80", r"1,599\.79", r"1,306\.20", r"23\.81%",
      r"13\.13%", r"\d+股", r"\d+份"],
     [r"-0\.83%", r"-0\.34%", r"-0\.21%", r"-0\.67%", r"-0\.19%", r"-0\.57%", r"-0\.91%"]),
    ("基金每日操作指引（14:30）/2026-10-14/fund_operation_guide.md", "md",
     [r"海震", r"4,357\.50", r"1,496\.62", r"7\.33%", r"2\.52%", r"\d+股", r"\d+份",
      r"浮盈", r"浮亏", r"13\.67", r"1\.061", r"13\.75~13\.80"],
     [r"板块跌 1\.10%", r"51 亿元", r"沪深300", r"创业板指"]),
    ("股票助手/2026-10-14/stock_assistant.html", "html",
     [r"海震", r"浮盈", r"1\.696", r"\d+股", r"\d+份", r"收益率"],
     [r"8,608 亿", r"3,946 亿", r"-1\.11%", r"-1\.15%", r"-1\.07%", r"-0\.31%",
      r"-0\.80pct", r"2\.02%", r"3\.54%", r"-0\.4pct", r"量比 1\.15"]),
    ("股票助手/2026-10-14/stock_assistant.md", "md",
     [r"海震", r"浮盈", r"1\.696", r"\d+股", r"\d+份", r"收益率",
      r"基准\s*\d", r"卖线\s*\d", r"买线\s*\d", r"\d+\.\d+-\d+\.\d+"],
     [r"8,608 亿", r"3,946 亿", r"上涨占比 33\.1%", r"1,788", r"3,609",
      r"\+0\.187", r"-0\.411", r"-0\.347", r"-0\.400", r"\+0\.109", r"\+1\.000",
      r"13\.19", r"-11\.14%", r"\+23\.76 亿", r"-18\.30 亿", r"量比 1\.15"]),
]

TAG_OPEN = re.compile(r"<(div|p|li|td|th|tr|table|ul|section|span|strong|em|h[1-6])\b")
TAG_CLOSE = re.compile(r"</(div|p|li|td|th|tr|table|ul|section|span|strong|em|h[1-6])>")

# ---------------------------------------------------------------- PM 红线门禁
# 模式唯一定义在 redline_hardening.REDLINE_GATE（市场语境行对数值模式豁免），
# 此处经 redline_scan 执行，杜绝三处模式漂移。
def redline_hits(text: str) -> dict:
    """返回 {模式: 次数}（空 = 放行）。"""
    hits = {}
    for item in redline_scan(text):
        label = item.split("×")[0]
        hits[label] = hits.get(label, 0) + int(item.split("×")[1].split("@")[0])
    return hits


# ---------------------------------------------------------------- A/B 双面
# team-lead 2026-10-14 裁决的验收口径：A 面个人数据（跨全部文件）必须掩；
# B 面公开数据（逐文件）必须保留。新增 _is_market_line 市场语境豁免后，
# A 面不得回归、B 面不得误杀。
A_LEAKS = [
    "1,403.64", "4,357.50", "2.36%", "1.65%", "34.74", "27.41", "width: 27.41",
    "18.50-24.50", "6.50-8.50", "0.850-1.250", "1.065", "1.020-1.025",
    "7.05", "7.25", "13.40", "5.15", "4.90", "20.40", "21.00", "4.20",
    "13.67", "19.89", "19.90", "0.955", "0.956",
]
# B 面逐文件保留（键 = 源文件名；v3 已知误杀的宽度表三项不纳入，见 run_case 注释）
B_PRESERVE = {
    "基金每日盘面分析（11:00）/2026-10-14/fund_market_analysis.html":
        ["100%", "11 只基金", "3,807.50", "+0.17%"],
    "基金每日盘面分析（11:00）/2026-10-14/fund_market_analysis.md":
        ["5273", "100%"],
    "每日总复盘（15:30）/2026-10-13/daily_review.html":
        ["-2.67%", "-0.44%", "+0.10%", "+0.31%", "4.51%", "4.55%"],
    "每日总复盘（15:30）/2026-10-13/stock_review.md":
        ["3800.86", "12353.70", "16,891.33", "13.91%", "4.5%"],
    "基金每日操作指引（14:30）/2026-10-14/fund_operation_guide.md":
        ["-2.82%", "51 亿元", "沪深300", "4280"],
    "股票助手/2026-10-14/stock_assistant.html":
        ["33.1%", "1,788", "5,397", "3,609", "8,608 亿"],
    "股票助手/2026-10-14/stock_assistant.md":
        ["上涨占比 33.1%", "8,608 亿", "13.19"],
}
# v3 已知误杀（非本层责任，已上报 team-lead）：基金 md 宽度表 57.7%/3.7%/38.6%
V3_KNOWN_OVERMASK = {"fund_market_analysis.md": ["57.7%", "3.7%", "38.6%"]}


def check_ab(outputs: dict) -> tuple[list[str], list[str]]:
    """A/B 双面校验。outputs: {源文件 rel: 脱敏后文本}。返回 (A面残留, B面误杀)。"""
    all_text = "\n".join(outputs.values())
    a_residual = [p for p in A_LEAKS if p in all_text]
    b_missed = []
    for rel, pats in B_PRESERVE.items():
        for p in pats:
            if rel in outputs and p not in outputs[rel]:
                b_missed.append(f"{Path(rel).name}:{p}")
    return a_residual, b_missed


def check_structure(text: str, fmt: str) -> list[str]:
    """粗粒度结构校验：标签配平 + MD 标题存在。"""
    problems = []
    if fmt == "html":
        for tag in ("div", "table", "tr", "td", "th", "ul", "li", "p", "section", "span"):
            o = len(re.findall(rf"<{tag}(?:\s[^>]*)?>", text))
            c = len(re.findall(rf"</{tag}>", text))
            if o != c:
                problems.append(f"标签不配平 <{tag}>: 开{o} 闭{c}")
        if "<html" not in text or "</html>" not in text:
            problems.append("html 骨架缺失")
    else:
        if not re.search(r"^#{1,3}\s+\S", text, re.M):
            problems.append("MD 标题结构缺失")
    return problems


def run_case(rel: str, fmt: str, sensitive: list[str], public: list[str]) -> dict:
    src = SRC / rel
    raw = src.read_text(encoding="utf-8")
    v3, stats_v3 = desensitize_text(raw)
    residual = check_residual(v3)
    out, rep = harden(v3, fmt=fmt)
    out2, _ = harden(out, fmt=fmt)
    leaks = harden_verify(out)

    result = {
        "file": rel, "v3_stats": stats_v3, "harden": rep,
        "v3_residual": residual, "harden_leaks": leaks,
        "sensitive_hits": {}, "public_missing": {}, "redline_hits": {},
        "idempotent": out2 == out,
        "structure": check_structure(out, fmt),
    }
    for pat in sensitive:
        n = len(re.findall(pat, out))
        if n:
            result["sensitive_hits"][pat] = n
    for pat in public:
        n = len(re.findall(pat, out))
        if n == 0:
            result["public_missing"][pat] = 0
    for label, n in redline_hits(out).items():
        result["redline_hits"][label] = n
    return result


def main() -> int:
    exit_code = 0
    print("=" * 72)
    print("发布流水线全量自测（两段式：desensitize v3 → redline_hardening）")
    print("=" * 72)
    for rel, fmt, sensitive, public in CASES:
        r = run_case(rel, fmt, sensitive, public)
        ok = (not r["sensitive_hits"] and not r["public_missing"]
              and r["idempotent"] and not r["structure"]
              and not r["harden_leaks"] and not r["redline_hits"])
        status = "PASS" if ok else "FAIL"
        print(f"\n[{status}] {r['file']}")
        print(f"  v3: {r['v3_stats']}")
        print(f"  harden: {r['harden']}")
        if r["v3_residual"]:
            print(f"  ⚠️ v3 残留: {r['v3_residual']}")
        if r["harden_leaks"]:
            print(f"  ❌ 加固层泄漏: {r['harden_leaks']}")
            exit_code = max(exit_code, 1)
        if r["sensitive_hits"]:
            print(f"  ❌ 敏感残留: {r['sensitive_hits']}")
            exit_code = max(exit_code, 1)
        if r["redline_hits"]:
            print(f"  ❌ PM 红线门禁命中: {r['redline_hits']}")
            exit_code = max(exit_code, 1)
        if r["public_missing"]:
            print(f"  ❌ 公开数据被误杀: {list(r['public_missing'])}")
            exit_code = max(exit_code, 2)
        if not r["idempotent"]:
            print("  ❌ 幂等失败：二次执行产生新变化")
            exit_code = max(exit_code, 3)
        if r["structure"]:
            print(f"  ❌ 结构问题: {r['structure']}")
            exit_code = max(exit_code, 4)

    # ---- L5 A/B 双面 ----
    print("\n" + "=" * 72)
    print("L5 A/B 双面验收（team-lead 2026-10-14 裁决口径）")
    print("=" * 72)
    ab_outputs = {}
    for rel, fmt, _, _ in CASES:
        raw = (SRC / rel).read_text(encoding="utf-8")
        v3, _ = desensitize_text(raw)
        out, _ = harden(v3, fmt=fmt)
        ab_outputs[rel] = out
    a_residual, b_missed = check_ab(ab_outputs)
    print(f"A 面（个人数据零残留，{len(A_LEAKS)} 项跨文件扫描）:")
    for p in A_LEAKS:
        print(f"  {'✓ 已掩' if p not in a_residual else '❌ 残留'} {p}")
    if a_residual:
        print(f"  ❌ A 面残留 {len(a_residual)} 项")
        exit_code = max(exit_code, 1)
    else:
        print("  ✅ A 面全部掩除")
    print(f"B 面（公开数据保留，逐文件）:")
    for rel, pats in B_PRESERVE.items():
        for p in pats:
            ok = p in ab_outputs.get(rel, "")
            print(f"  {'✓ 保留' if ok else '❌ 被掩'} {Path(rel).name}: {p}")
    if b_missed:
        print(f"  ❌ B 面误杀 {len(b_missed)} 项: {b_missed}")
        exit_code = max(exit_code, 2)
    else:
        print("  ✅ B 面全部保留")
    print("  备注: 基金 md 宽度表 57.7%/3.7%/38.6% 为 v3 引擎误杀（非本层），"
          "已上报 team-lead，不纳入本层验收")

    print("\n" + "=" * 72)
    print("退出码规范（与 publish_to_github.py 对齐）: 0=通过 1=泄漏(含A面) "
          "2=误杀(B面) 3=幂等失败 4=结构损坏")
    print(f"本次退出码: {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
