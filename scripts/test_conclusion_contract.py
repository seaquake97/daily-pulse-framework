#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_conclusion_contract.py — 结论先行摘要契约的机检断言

契约来源：docs/PRODUCT-CONTRACT.md（PM 许清楚，26 条红线）。
本文件把其中**可机检**的摘要层红线固化为测试——文档会过期，断言不会。

## 覆盖的契约

  T-6  截断必带省略号（PC-27 实锤：截断后无省略号 = 文本被改动而非节选，
       读者无从得知后面还有内容）
  T-7  摘要层零 markdown 残留（PC-1：反引号 / 星号 / 下划线 / 井号）
  T-10 摘要层零 emoji（团队 P0-1：emoji 只允许出现在正文与 ip-mark，
       不允许出现在由 md 派生的一行摘要里）
  T-11 降级态不得输出可执行动作（C-9 / PC-24，金融场景最高危：数据源降级
       时给出「定投额度上浮 ≤20%」会被读者直接执行）
  L-3  结论三段式结构（评级·Σ ｜ 标准动作 ｜ 关键事实），段序不可乱
  L-6  Σ 缺失必须是「数据缺口」，任何位置都不得出现伪造的 0.000

真实产出缺失即 skip（不伪造样本）。运行：python3 scripts/test_conclusion_contract.py
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent / "_stage" / "docs" / "daily"

P0_EMOJI = re.compile("[\U0001F300-\U0001F9FF\U0001FAFF☀-➿⬀-⯿]")
MD_RESIDUE = re.compile(r"[`*_#]")
SEGMENT_SEP = "｜"
FAKE_SIGMA = re.compile(r"Σ\s*[+－-]?0\.000(?!\s*数据缺口)")


def _entries() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for p in sorted(STAGE.glob("*/entries.json")):
        try:
            for e in json.loads(p.read_text(encoding="utf-8")):
                out.append((p.parent.name, e))
        except (OSError, ValueError):
            continue
    return out


class TestConclusionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = _entries()
        if not cls.data:
            raise unittest.SkipTest(f"真实 entries.json 缺失：{STAGE}")

    def test_t6_truncation_always_marks_ellipsis(self):
        """T-6：第三段若被截断，必须以 … 收尾。"""
        bad = []
        for date, e in self.data:
            parts = e.get("conclusion", "").split(SEGMENT_SEP)
            if len(parts) < 3:
                continue
            fact = parts[2].strip()
            if not fact:
                continue
            tail = fact[-1]
            # 结尾是完整标点/百分号/省略号即视为未截断或已正确标记
            if tail not in ("…", "%", "。", "）", ")", ".", "亿", "元", "股", "份"):
                bad.append(f"{date}/{e.get('slug')}: …{fact[-18:]}")
        self.assertEqual(bad, [], f"T-6 截断未标省略号（PC-27）：{bad[:5]}")

    def test_t7_t10_no_markdown_no_emoji(self):
        """T-7/T-10：摘要层零 markdown 残留、零 emoji。"""
        md_bad = [f"{d}/{e.get('slug')}" for d, e in self.data
                  if MD_RESIDUE.search(e.get("conclusion", ""))]
        self.assertEqual(md_bad, [], f"T-7 摘要含 markdown 残留：{md_bad[:5]}")
        emo_bad = [f"{d}/{e.get('slug')}" for d, e in self.data
                   if P0_EMOJI.search(e.get("conclusion", ""))]
        self.assertEqual(emo_bad, [], f"T-10 摘要含 emoji（P0-1）：{emo_bad[:5]}")

    def test_t11_degraded_never_emits_actionable_advice(self):
        """T-11 / C-9：降级态摘要不得含「上浮 / 可移 / 新增买入」等可执行指令。"""
        actionable = ("上浮", "可上移", "可移", "新增买入", "减仓", "加仓",
                      "暂停一切主动买入", "可降档", "可挂")
        bad = []
        for date, e in self.data:
            if not e.get("degraded"):
                continue
            c = e.get("conclusion", "")
            if "降级" not in c:
                bad.append(f"{date}/{e.get('slug')}: 降级态未标降级")
            hit = [w for w in actionable if w in c]
            if hit:
                bad.append(f"{date}/{e.get('slug')}: 降级态仍给动作 {hit}")
        self.assertEqual(bad, [], f"T-11 降级态输出可执行动作（PC-24）：{bad[:5]}")

    def test_l3_three_segment_structure(self):
        """L-3：结论至少两段（评级·Σ ｜ 动作），有事实则三段。"""
        bad = []
        for date, e in self.data:
            c = e.get("conclusion", "")
            parts = [p for p in c.split(SEGMENT_SEP) if p.strip()]
            if len(parts) < 2:
                bad.append(f"{date}/{e.get('slug')}: {c[:40]}")
                continue
            head = parts[0]
            if not (head.startswith("数据缺口") or "· Σ" in head
                    or head.startswith("数据源降级")):
                bad.append(f"{date}/{e.get('slug')}: 段一非结论 {head[:30]}")
        self.assertEqual(bad, [], f"L-3 结论结构异常：{bad[:5]}")

    def test_l6_no_fabricated_zero_sigma(self):
        """L-6：任何 entries.json 里都不得出现伪造的 Σ 0.000 / 0。"""
        bad = []
        for date, e in self.data:
            if e.get("sigma") is None:
                c = e.get("conclusion", "")
                if "数据缺口" not in c and "降级" not in c:
                    bad.append(f"{date}/{e.get('slug')}: Σ 缺失但结论未标缺口")
            else:
                if FAKE_SIGMA.search(e.get("conclusion", "")):
                    bad.append(f"{date}/{e.get('slug')}: 伪造 Σ 0.000")
        self.assertEqual(bad, [], f"L-6 伪造零值：{bad[:5]}")

    def test_meta_never_zero_fills_sigma(self):
        """L-6 延伸：meta.json 的 sigma 缺失必须是 null（不是 0.0）。"""
        bad = []
        for p in sorted(STAGE.glob("*/meta.json")):
            m = json.loads(p.read_text(encoding="utf-8"))
            if m.get("sigma") is None:
                continue
            if m.get("sigma") == 0 and m.get("rating") is None:
                bad.append(f"{p.parent.name}: sigma=0 但 rating 也缺失（补零痕迹）")
            if m.get("rating") is not None and m.get("sigma") == 0:
                bad.append(f"{p.parent.name}: sigma=0 且有评级（疑似 .get 默认值伪造）")
        self.assertEqual(bad, [], f"meta.json 补零痕迹：{bad}")

    def test_segment_length_within_cap(self):
        """C-2 字数上限：段一 ≤24、段二 ≤48、段三 ≤46（含标记）。

        超限即信息过载——摘要的作用是「一眼看出结论」，不是复述正文。
        """
        CAPS = (24, 48, 46)
        over = []
        for date, e in self.data:
            parts = [p.strip() for p in e.get("conclusion", "").split(SEGMENT_SEP)]
            for i, cap in enumerate(CAPS[:len(parts)]):
                if len(parts[i]) > cap:
                    over.append(f"{date}/{e.get('slug')} 段{i + 1}: "
                                f"{len(parts[i])}>{cap} 「{parts[i][:22]}…」")
        self.assertEqual(over, [], f"结论段超字数上限：{over[:5]}")

    def test_rating_arrow_redundant_coding_kept(self):
        """PC-1：凡出现评级徽章处，必须保留箭头冗余编码（ADR-003 色盲友好）。

        注：PM 初报「日期页无评级徽章」是误判——10-12/10-13 无 market_data，
        按 P0 诚实呈现「未标注/Σ 数据缺口」而非伪徽章（这才是正确行为）。
        断言改为「有评级必有徽章+箭头；无评级必须有缺口标记」，两头都锁。
        """
        missing = []
        for p in sorted(STAGE.glob("*/index.html")):
            html = p.read_text(encoding="utf-8")
            meta = json.loads((p.parent / "meta.json").read_text(encoding="utf-8"))
            has_badge = 'class="rating ' in html
            if meta.get("rating") is None:
                # 无评级：必须有诚实缺口标记，不得出现任何徽章
                if has_badge:
                    missing.append(f"{p.parent.name}: 无评级却出现评级徽章")
                elif "数据缺口" not in html and "未标注" not in html:
                    missing.append(f"{p.parent.name}: 无评级且无缺口标记")
                continue
            if not has_badge:
                missing.append(f"{p.parent.name}: 有评级但无徽章")
                continue
            # 徽章结构：<span class="rating rating-x"><svg…/> <span class="arrow">▲</span>文字</span>
            # 匹配到箭头 span 为止（此前只切到 </svg> 就停，漏检箭头缺失）
            badge = re.search(r'<span class="rating rating-\w+">(?:(?!</span>).)*'
                              r'(?:class="arrow"|</span>)', html, re.S)
            if badge and 'class="arrow"' not in badge.group(0):
                missing.append(f"{p.parent.name}: 徽章缺箭头冗余编码")
            elif not badge:
                missing.append(f"{p.parent.name}: 徽章结构不可解析")
        self.assertEqual(missing, [], f"PC-1 评级徽章契约：{missing[:5]}")


    def test_degraded_entry_never_shows_direction(self):
        """P0-1（架构师 A-04 实测）：降级条目不得同时呈现方向值。

        卡片同现「数据源降级」与「进攻 +0.510」= 两个互相矛盾的结论，
        读者不知道该信哪个；数据不可信时给出方向本身就是误导。
        """
        bad = []
        for date, e in self.data:
            if not e.get("degraded"):
                continue
            if e.get("rating") is not None:
                bad.append(f"{date}/{e.get('slug')}: 降级仍带 rating={e['rating']}")
            if e.get("sigma") is not None:
                bad.append(f"{date}/{e.get('slug')}: 降级仍带 sigma={e['sigma']}")
        self.assertEqual(bad, [], f"降级条目不得呈现方向值：{bad}")

    def test_json_feed_degraded_nulls_direction(self):
        """P0-1 延伸：feed.json 客户端会二次解读，降级项必须置 null。"""
        import json as _json
        p = STAGE.parent / "api" / "feed.json"
        if not p.exists():
            self.skipTest(f"feed.json 未生成：{p}")
        d = _json.loads(p.read_text(encoding="utf-8"))
        bad = []
        for day in d["days"]:
            for e in day["entries"]:
                if e.get("degraded") and (e.get("rating") or e.get("sigma") is not None):
                    bad.append(f"{day['date']}/{e['slug']}: "
                               f"rating={e.get('rating')} sigma={e.get('sigma')}")
        self.assertEqual(bad, [], f"feed.json 降级项须置空方向值：{bad}")

    def test_json_feed_contract(self):
        """L-7：机器可读数据源 /api/feed.json 的契约（ARCH-R6 §3.1）。

        feed.json 是小程序/PWA 的唯一数据入口，一旦缺字段/写错类型，
        客户端会静默拿到不完整数据——所以 schema 必须被断言锁住。
        """
        import json as _json
        p = STAGE.parent / "api" / "feed.json"
        if not p.exists():
            self.skipTest(f"feed.json 未生成：{p}")
        d = _json.loads(p.read_text(encoding="utf-8"))
        for k in ("version", "site", "disclaimer", "ratingScale", "days"):
            self.assertIn(k, d, f"feed.json 缺顶层键 {k}")
        self.assertIsInstance(d["days"], list)
        self.assertTrue(d["days"], "days 不得为空")
        day = d["days"][0]
        for k in ("date", "rating", "sigma", "stage", "entryCount", "url", "entries"):
            self.assertIn(k, day, f"feed.json day 缺键 {k}")
        for e in day["entries"]:
            for k in ("slug", "name", "time", "conclusion", "stage",
                      "degraded", "dataGap", "comparable"):
                self.assertIn(k, e, f"feed.json entry 缺键 {k}")
            self.assertIsInstance(e["degraded"], bool)
            self.assertIsInstance(e["dataGap"], bool)
            # 数据缺口态不得给出可执行动作（与 T-11 同一铁律）
            if e["dataGap"] and e.get("conclusion"):
                self.assertNotIn("Σ+", e["conclusion"],
                                 "数据缺口条目不得输出 Σ 数值")
        # 评级必须落在五档内或为空（不得出现未登记档位）
        for day_ in d["days"]:
            for r in [day_.get("rating")] + [x.get("rating") for x in day_["entries"]]:
                self.assertIn(r, d["ratingScale"] + [None],
                              f"未登记评级档位：{r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)