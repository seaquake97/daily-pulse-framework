#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
desensitize.py — 日报内容脱敏器（GitHub 公开仓库专用）v3-final

分层防御：
  L1 JSON 键黑名单：成本/盈亏/市值/持仓/收益/在途等个人财务字段整体替换（递归任意深度；
     公开行情键白名单优先：price/change_percent/amount(成交额)/评级字段等不脱敏）
  L2 正则强规则：券商名、上下文账号（账号后4位）、手机号、身份证、银行卡
  L3a 上下文货币：敏感词 + 同句紧间隔(≤10字符，可跨HTML标签，不跨逗号句号) + 金额 → 金额替换
  L3b 股份数量：① 敏感词后的 N股/N份；② N股/N份 + 底仓/顶仓/持仓；③ 日报正文全局 N股/N份
  L3c 句子级单位金额：同一句含敏感词 → 该句所有带单位金额（元/块/万元 或 ¥前缀）掩码；
     不掩裸数字（公开价格 4.90/7.25 保留）、不掩"亿"（公开成交额/市值保留）
  L3d HTML 表格列黑名单：表头含敏感词（持仓金额/累计持有收益/定投在途/占比等）整列单元格替换
  L3e HTML 内联脚本移除：内联 <script>（图表数据常含穿透明细）整体移除；外链 src 保留
  硬门禁：脱敏后 ¥金额/N股/N份/账号/身份证/银行卡/券商名/手机号 必须零命中，否则禁止发布

设计原则：
  - 市场公开数据（指数点位、涨跌幅、成交额、PE、网格价格线、评级信号分）一律保留——内容 IP 本体
  - 个人财务数据（金额、持仓数量、成本、盈亏、占比、组合表现）一律替换——隐私红线
  - 宁可误杀不可漏杀：误杀只损失信息量，漏杀泄露不可逆
  - 单次左到右正则替换（v1 的窗口重叠算法在 MASK 长度变化时损坏文本，已废弃）

用法：
  python3 desensitize.py --file report.html [--out out.html]   # 单文件
  python3 desensitize.py --dir _stage/docs [--ext .html,.md]   # 目录批处理
  python3 desensitize.py --selftest                            # 内置单测（真实敏感串夹具）
退出码：0=通过 / 1=残留敏感串 / 2=用法或IO错误
"""
import argparse
import json
import re
import sys
from pathlib import Path

MASK = "[已脱敏]"

# ---------- L1: JSON 键黑名单 ----------
SENSITIVE_KEYS = [
    "cost", "pnl", "profit", "gain", "income", "market_value", "mv",
    "holding", "holdings", "position", "shares", "quantity", "qty",
    "amount", "balance", "equity", "principal", "invested",
    "成本", "盈亏", "收益", "市值", "持仓", "股数", "数量", "份额",
    "金额", "总额", "总投入", "剩余", "在途", "可用", "浮动", "累计",
    "昨日收益", "持有收益", "定投额", "占比", "比重", "权重",
]
PUBLIC_JSON_KEYS = {
    "price", "change_percent", "chg_pct", "chg", "time", "date", "name",
    "code", "symbol", "sector", "volume_ratio", "pe_ratio", "chg_5d",
    "chg_10d", "chg_20d", "chg_60d", "chg_ytd", "total_amount_yi",
    "up", "down", "flat", "limit_up", "limit_down", "rating", "sigma",
    "signals", "weights", "valid_weight", "degraded", "data_stage",
}

# ---------- L2: 正则强规则 ----------
RE_BROKER = re.compile(r"华宝证券|海通证券|中信证券|国泰君安|招商证券|广发证券|银河证券|国信证券")
RE_ACCOUNT = re.compile(r"((?:账号|账户|资金账号|证券账号)[：:\s]*)(\d{4})")
RE_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
RE_IDCARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
RE_BANKCARD = re.compile(r"(?<!\d)\d{16,19}(?!\d)")

# ---------- L3a: 上下文货币（敏感词 + 紧间隔 + 金额） ----------
_SENS_WORDS = ("成本|盈亏|浮盈|浮亏|市值|持仓金额|持有收益|昨日收益|总持仓|计划总投入"
               "|剩余可投|在途|定投|底仓|顶仓|减仓|加仓|高抛|低吸|挂买|挂卖|持仓|持有|组合|加权")
# 间隔 ≤10 字符（含 HTML 标签如 </td><td>），但不跨逗号/句号/分号/换行——防"底仓停卖，4.90"误伤公开价格
_MONEY = r"((?:[¥￥]\s?)?\d[\d,]*(?:\.\d+)?(?:\s?(?:元|块|万元|亿))?)"
RE_CONTEXT_AFTER = re.compile(rf"({_SENS_WORDS})([^。；\n，,]{{0,10}}?){_MONEY}")
# ---------- L3b: 股份数量 ----------
RE_SHARES_BEFORE = re.compile(r"(\d[\d,]*\s?(?:股|份))([^。；\n，,]{0,6}?)(底仓|顶仓|持仓)")
RE_SHARES_ANY = re.compile(r"(?<![A-Za-z0-9])\d[\d,]*\s?(?:股|份)")
# ---------- L3c: 句子级单位金额 ----------
RE_SENT_SPLIT = re.compile(r"([^。；\n]+[。；\n]?)")
RE_UNIT_MONEY = re.compile(r"((?:[¥￥]\s?)?\d[\d,]*(?:\.\d+)?\s?(?:元|块|万元))")
# ---------- L3c-2: 全局 ¥ 金额（本域报告中 ¥ 前缀一律为个人金额；市场数据用裸数字/亿/元） ----------
RE_YEN_MONEY = re.compile(r"[¥￥]\s?\d[\d,]*(?:\.\d+)?")
# ---------- L3c-3: 含脱敏痕迹句子的百分比（个人语境，如"CPO：¥16,287.66，占比 27.41%"） ----------
RE_PERCENT = re.compile(r"[+-]?\d+(?:\.\d+)?%")
# ---------- L3d: 表格列黑名单 ----------
SENSITIVE_HEADERS = ["持仓金额", "持有收益", "累计持有收益", "昨日收益", "成本", "盈亏",
                     "浮盈", "浮亏", "市值", "在途", "定投", "占纯基金比重", "总权重",
                     "穿透持仓金额", "金额", "份额", "股数", "仓位", "总资产",
                     "集中度", "可投", "总额"]
# 语境相关表头：仅当表格不是市场宽度表时才掩。
# 「占比/比重」在基金穿透表是个人持仓占比（必须掩），在市场宽度表是公开指标
# （上涨/下跌/平盘家数占比，掩之即误杀——实测 57.7%/3.7%/38.6% 被整列误掩）。
AMBIGUOUS_HEADERS = ["占比", "比重"]
# 市场宽度表判定标记：表头或数据行含这些词 → 公开行情表，语境相关列不掩
MARKET_TABLE_MARKERS = ["上涨家数", "下跌家数", "平盘家数", "A股总股票数",
                        "涨停家数", "跌停家数", "全市场", "市场宽度"]
RE_MD_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
RE_MD_SEP_ROW = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
# ---------- L3e: 内联脚本 ----------
RE_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[\s\S]*?</script>", re.I)
# ---------- 硬门禁 ----------
HARD_PATTERNS = [
    ("货币金额(¥)", re.compile(r"[¥￥]\s?\d")),
    ("股份数量", RE_SHARES_ANY),
    ("账号", re.compile(r"(?:账号|账户)[：:\s]*\d{4}")),
    ("身份证", RE_IDCARD),
    ("银行卡", RE_BANKCARD),
    ("券商名", RE_BROKER),
    ("手机号", RE_PHONE),
]


def _is_sensitive_key(key: str, path: str = "$") -> bool:
    k = str(key).lower()
    # 路径上下文优先：indices/total_amount 下的字段均为公开行情（如 amount=成交额）
    if ".indices" in path or "total_amount" in path:
        return False
    if k in PUBLIC_JSON_KEYS:
        return False
    return any(s.lower() in k for s in SENSITIVE_KEYS)


def desensitize_json(obj, path="$", hits=None):
    """递归脱敏 JSON。返回 (新对象, 命中列表)"""
    if hits is None:
        hits = []
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _is_sensitive_key(k, path) and not isinstance(v, (dict, list)):
                hits.append((f"{path}.{k}", str(v)[:40]))
                out[k] = MASK
            else:
                sub, _ = desensitize_json(v, f"{path}.{k}", hits)
                out[k] = sub
        return out, hits
    if isinstance(obj, list):
        return [desensitize_json(v, f"{path}[{i}]", hits)[0] for i, v in enumerate(obj)], hits
    return obj, hits


def _mask_sentence_money(text: str) -> int:
    """L3c：同一句含敏感词 → 掩码该句所有带单位金额（元/块/万元/¥前缀）。不掩裸数字与"亿"。"""
    n = 0

    def fix(m):
        nonlocal n
        sent = m.group(0)
        if re.search(_SENS_WORDS, sent):
            new, c = RE_UNIT_MONEY.subn(MASK, sent)
            n += c
            return new
        return sent

    return RE_SENT_SPLIT.sub(fix, text), n


def _mask_html_tables(html: str) -> tuple:
    """L3d：表头含敏感词的表格列整列替换。返回 (新html, 替换列数)"""
    n_cols = 0

    def process_table(m):
        nonlocal n_cols
        block = m.group(0)
        row_ms = list(re.finditer(r"<tr[\s\S]*?</tr>", block))
        if not row_ms:
            return block
        header_i = next((i for i, rm in enumerate(row_ms) if "<th" in rm.group(0)), None)
        if header_i is None:
            return block
        ths = re.findall(r"<th[^>]*>([\s\S]*?)</th>", row_ms[header_i].group(0))
        sens = [j for j, t in enumerate(ths)
                if any(h in re.sub(r"<[^>]+>", "", t) for h in SENSITIVE_HEADERS)]
        if not sens:
            return block
        n_cols += len(sens)
        new_rows = []
        for i, rm in enumerate(row_ms):
            row = rm.group(0)
            if i == header_i:
                new_rows.append(row)
                continue
            cells = list(re.finditer(r"<td[^>]*>[\s\S]*?</td>", row))
            if len(cells) != len(ths):
                new_rows.append(row)  # 列数不一致（colspan 等）保守跳过
                continue
            new_row = row
            for j in reversed(sens):
                if j < len(cells):
                    c = cells[j]
                    inner = re.sub(r"(<td[^>]*>)([\s\S]*?)(</td>)",
                                   lambda mm: mm.group(1) + MASK + mm.group(3), c.group(0))
                    new_row = new_row[:c.start()] + inner + new_row[c.end():]
            new_rows.append(new_row)
        out, last = [], 0
        for rm, nr in zip(row_ms, new_rows):
            out.append(block[last:rm.start()])
            out.append(nr)
            last = rm.end()
        out.append(block[last:])
        return "".join(out)

    new_html = re.sub(r"<table[\s\S]*?</table>", process_table, html)
    return new_html, n_cols


def _mask_md_tables(text: str) -> tuple:
    """L3d-MD：Markdown 管道表格列黑名单（表头含敏感词 → 该列数据单元格替换）。"""
    n = 0
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        if RE_MD_TABLE_ROW.match(lines[i]):
            j = i
            while j < len(lines) and RE_MD_TABLE_ROW.match(lines[j]):
                j += 1
            block = lines[i:j]
            header_cells = [c.strip() for c in block[0].strip().strip("|").split("|")]
            data_start = 2 if len(block) > 1 and RE_MD_SEP_ROW.match(block[1]) else 1
            # 市场宽度表豁免：表头+数据行含市场标记 → 语境相关列（占比/比重）不掩
            block_text = "\n".join(block[:4])
            is_market_table = any(m in block_text for m in MARKET_TABLE_MARKERS)
            header_pool = SENSITIVE_HEADERS + ([] if is_market_table else AMBIGUOUS_HEADERS)
            sens = [k for k, h in enumerate(header_cells)
                    if any(s in h for s in header_pool)]
            if sens:
                for r in range(data_start, len(block)):
                    cells = block[r].split("|")
                    if len(cells) != len(header_cells) + 2:
                        continue  # 列数不一致保守跳过
                    for k in sens:
                        idx = k + 1
                        if idx < len(cells):
                            cells[idx] = f" {MASK} "
                            n += 1
                    block[r] = "|".join(cells)
            out.extend(block)
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out), n


def desensitize_text(text: str) -> tuple:
    """对 HTML/Markdown 文本执行 L2+L3。返回 (新文本, 统计dict)。HTML 自动识别。"""
    is_html = bool(re.search(r"<(html|table|td|div|p)[\s>]", text, re.I))
    stats = {"broker": 0, "account": 0, "phone": 0, "idcard": 0, "bankcard": 0,
             "context_money": 0, "sentence_money": 0, "shares": 0,
             "table_cols": 0, "md_table_cols": 0, "yen_money": 0,
             "sentence_percent": 0, "script_removed": 0}
    out = text
    if is_html:
        out, n = RE_INLINE_SCRIPT.subn("<!-- [隐私] 内联脚本数据已移除 -->", out)
        stats["script_removed"] = n
        out, n = _mask_html_tables(out)
        stats["table_cols"] = n
    out, c = RE_BROKER.subn(MASK, out); stats["broker"] += c
    out, c = RE_ACCOUNT.subn(lambda m: m.group(1) + MASK, out); stats["account"] += c
    out, c = RE_PHONE.subn(MASK, out); stats["phone"] += c
    out, c = RE_IDCARD.subn(MASK, out); stats["idcard"] += c
    out, c = RE_BANKCARD.subn(MASK, out); stats["bankcard"] += c
    out, c = RE_CONTEXT_AFTER.subn(lambda m: m.group(1) + m.group(2) + MASK, out)
    stats["context_money"] += c
    out, c = RE_SHARES_BEFORE.subn(lambda m: MASK + m.group(2) + m.group(3), out)
    stats["shares"] += c
    out, c = RE_SHARES_ANY.subn(MASK, out)
    stats["shares"] += c
    out, c = _mask_sentence_money(out)
    stats["sentence_money"] = c
    if not is_html:
        out, c = _mask_md_tables(out)
        stats["md_table_cols"] = c
    # 全局 ¥ 金额（本域报告惯例：¥ 前缀=个人金额）
    out, c = RE_YEN_MONEY.subn(MASK, out)
    stats["yen_money"] = c
    # 含脱敏痕迹的句子 → 剩余百分比一并掩码（个人语境；公开句子的百分比保留；
    # 表格行跳过——同行已脱敏单元格会误伤该行公开涨跌列，今日 HTML 实证）
    def _mask_pct(m):
        sent = m.group(0)
        if MASK in sent and "<td" not in sent and "<tr" not in sent and "<th" not in sent \
                and not sent.lstrip().startswith("|"):
            return RE_PERCENT.sub(MASK, sent)
        return sent
    out, c = RE_SENT_SPLIT.subn(_mask_pct, out)
    stats["sentence_percent"] = c
    return out, stats


def check_residual(text: str) -> list:
    """硬门禁：返回仍能匹配的敏感模式列表（必须为空）"""
    residuals = []
    for name, pat in HARD_PATTERNS:
        for m in pat.finditer(text):
            residuals.append((name, m.group(0)))
    return residuals


def process_file(path: Path, out_path: Path = None) -> dict:
    raw = path.read_text(encoding="utf-8")
    result = {"file": str(path), "masked": {}, "residual": []}
    if path.suffix == ".json":
        try:
            data = json.loads(raw)
            new, hits = desensitize_json(data)
            result["masked"] = {"json_keys": len(hits)}
            dumped = json.dumps(new, ensure_ascii=False, indent=2)
            result["residual"] = check_residual(dumped)
            (out_path or path).write_text(dumped, encoding="utf-8")
        except json.JSONDecodeError:
            new, stats = desensitize_text(raw)
            result["masked"] = {k: v for k, v in stats.items() if v}
            result["residual"] = check_residual(new)
            (out_path or path).write_text(new, encoding="utf-8")
    else:
        new, stats = desensitize_text(raw)
        result["masked"] = {k: v for k, v in stats.items() if v}
        result["residual"] = check_residual(new)
        (out_path or path).write_text(new, encoding="utf-8")
    return result


def selftest() -> bool:
    """内置单测：真实敏感串夹具。必消串全消、公开数据全留、硬门禁零命中、结构不损坏、幂等。"""
    md_fixture = """# 每日研判
总持仓（基金+黄金）：63,322.65 元；计划总投入：100,000 元；剩余可投资金：约 36,677.35 元。
江苏银行 成本 1.696，浮盈 +1,082.38 元，市值 1,252.00 元。
持仓 100 股底仓；卫星ETF持有 20000 份，成本摊薄至 1.385。
1000 股已是最小底仓，停卖；4.90 以下挂买。
组合加权涨跌 -0.67%；沪深300 PE 13.19，上证指数 3801.13 点（+0.01%），成交额 8,608 亿。
网格：甘肃能源冲高 7.25-7.40 高抛；电力ETF 1.065 挂卖。
券商：华宝证券，账号 5526，联系人 13812345678，身份证 11010119900307721X。
定投额度 -30% 至 70 元/日；2 笔买入在途合计 192.00 元。

### 穿透重仓股明细（前十大占基金资产 60% 假设）

| 排名 | 重仓股票名称与代码 | 穿透持仓金额 | 占纯基金比重 | 今日实时涨跌 |
|---|---|---|---|---|
| 1 | **新易盛** (300502) | `¥1,754.89` | **2.95%** | `-3.36%` |
| 2 | **中际旭创** (300308) | `¥1,754.89` | **2.95%** | `-2.73%` |

### 基金持仓表

| 标的 | 代码 | 持仓金额 | 持有收益 | 昨日收益 | 占纯基金比重 |
|---|---|---|---|---|---|
| 景顺长城沪港深精选股票A | 000979 | 15,080.21 | -1,599.79 | -608.35 | 25.38% |
| 景顺长城品质长青混合A | 010350 | 8,313.80 | -1,306.20 | -341.14 | 13.99% |

### 板块穿透汇总

* **CPO (光模块/算力硬件)**：`¥16,287.66`，占比 **27.41%**
* **人工智能 (创业板AI)**：`¥4,357.50`，占比 **7.33%**

### 市场公开数据（必须保留）

上涨占比 33.1%（1,788/5,397），涨停 45 家、跌停 5 家。两市成交额 8,608 亿元，量比 1.15。
"""
    html_fixture = """<html><body>
<p>江苏银行 成本 1.696，浮盈 +1,082.38 元。</p>
<table><tr><th>标的</th><th>持仓金额</th><th>累计持有收益</th><th>今日涨跌</th></tr>
<tr><td>江苏银行</td><td>1,252.00</td><td>+1,082.38</td><td>+0.48%</td></tr>
<tr><td>粤高速A</td><td>12,096.00</td><td>+1,813.43</td><td>+2.54%</td></tr></table>
<script>const data = [{name:"江苏银行", cost:1.696, mv:1252.00}];</script>
<script src="https://cdn.example.com/lib.js"></script>
<p>公开数据：上证 3801.13 点 +0.01%，成交额 8,608 亿，PE 13.19。</p>
</body></html>"""
    json_fixture = {
        "holdings": {"sh600919": {"name": "江苏银行", "price": 12.46, "change_percent": 0.48,
                                   "shares": 100, "cost_price": 1.696, "market_value": 1252.0,
                                   "pnl": 1082.38, "amount": 602522450}},
        "indices": {"sh000001": {"price": 3801.13, "amount": 394592079610, "time": "2026-10-14"}},
    }
    ok = True
    md_out, md_stats = desensitize_text(md_fixture)
    html_out, html_stats = desensitize_text(html_fixture)
    json_out, json_hits = desensitize_json(json_fixture)

    must_vanish_md = ["63,322.65", "100,000", "36,677.35", "1.696", "1,082.38",
                      "1,252.00", "华宝", "5526", "13812345678", "11010119900307721X",
                      "20000", "1.385", "-0.67%", "70 元", "192.00",
                      # 穿透表与基金表（今日基金报告真实形态）
                      "¥1,754.89", "¥16,287.66", "¥4,357.50", "15,080.21", "-1,599.79",
                      "8,313.80", "-1,306.20", "-608.35", "-341.14", "25.38%", "13.99%",
                      "27.41%", "7.33%", "2.95%"]
    must_keep_md = ["3801.13", "+0.01%", "8,608", "13.19", "7.25", "7.40", "1.065", "4.90",
                    # 公开市场数据必须保留（不被"占比"类规则误杀）
                    "33.1%", "1,788/5,397", "45 家", "5 家", "1.15"]
    must_vanish_html = ["1,252.00", "12,096.00", "+1,082.38", "+1,813.43", "1.696", "cost"]
    must_keep_html = ["3801.13", "+0.01%", "8,608", "13.19", "+0.48%", "+2.54%",
                      "cdn.example.com/lib.js"]
    h = json_out["holdings"]["sh600919"]
    idx = json_out["indices"]["sh000001"]

    checks = [
        ("MD 必消串漏网", [s for s in must_vanish_md if s in md_out]),
        ("MD 公开数据误杀", [s for s in must_keep_md if s not in md_out]),
        ("MD 硬门禁残留", check_residual(md_out)),
        ("HTML 必消串漏网", [s for s in must_vanish_html if s in html_out]),
        ("HTML 公开数据误杀", [s for s in must_keep_html if s not in html_out]),
        ("HTML 硬门禁残留", check_residual(html_out)),
        ("HTML 表格结构保留", [] if html_out.count("<tr>") == 3 and html_out.count("<td") == 8 else ["表格结构损坏"]),
        ("HTML 内联脚本已移除", [] if "const data" not in html_out else ["内联脚本未移除"]),
        ("HTML 外链脚本保留", [] if "cdn.example.com/lib.js" in html_out else ["外链被误删"]),
        ("JSON 持仓字段脱敏", [] if (h["cost_price"] == MASK and h["market_value"] == MASK
                                    and h["pnl"] == MASK and h["shares"] == MASK) else ["JSON 持仓字段未脱敏"]),
        ("JSON 公开行情保留", [] if (h["price"] == 12.46 and h["change_percent"] == 0.48
                                    and idx["price"] == 3801.13 and idx["amount"] == 394592079610
                                    and idx["time"] == "2026-10-14") else ["JSON 公开行情被误杀"]),
        ("JSON 无残留", check_residual(json.dumps(json_out, ensure_ascii=False))),
    ]
    print("=== desensitize.py v3 自测 ===")
    for name, fails in checks:
        status = "✅" if not fails else f"❌ {fails}"
        print(f"  {name}: {status}")
        if fails:
            ok = False
    md_out2, _ = desensitize_text(md_out)
    idem = md_out2 == md_out
    print(f"  幂等性: {'✅' if idem else '❌'}")
    if not idem:
        ok = False
    print(f"  统计: md={md_stats}")
    print(f"        html={html_stats} json_keys={len(json_hits)}")
    print(f"结论: {'PASS ✅' if ok else 'FAIL ❌'}")
    if not ok:
        print("--- MD 脱敏样本 ---"); print(md_out[:600])
        print("--- HTML 脱敏样本 ---"); print(html_out[:800])
    return ok


def main():
    ap = argparse.ArgumentParser(description="日报内容脱敏器 v3")
    ap.add_argument("--file", help="单文件路径")
    ap.add_argument("--dir", help="目录批处理")
    ap.add_argument("--out", help="输出路径（单文件模式，缺省原地）")
    ap.add_argument("--ext", default=".html,.md,.json", help="目录模式扩展名")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(0 if selftest() else 1)
    if not args.file and not args.dir:
        ap.error("必须指定 --file / --dir / --selftest")

    results = []
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"❌ 文件不存在: {p}")
            sys.exit(2)
        results.append(process_file(p, Path(args.out) if args.out else None))
    else:
        d = Path(args.dir)
        if not d.is_dir():
            print(f"❌ 目录不存在: {d}")
            sys.exit(2)
        exts = tuple(e.strip() for e in args.ext.split(","))
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix in exts:
                results.append(process_file(p))

    total = sum(sum(v for v in r["masked"].values() if isinstance(v, int)) for r in results)
    leaked = [r for r in results if r["residual"]]
    print(f"=== 脱敏完成: {len(results)} 个文件, 替换 {total} 处 ===")
    for r in results:
        flag = " ⚠️残留!" if r["residual"] else ""
        print(f"  {Path(r['file']).name}: {r['masked'] or '无需脱敏'}{flag}")
    if leaked:
        print("❌ 硬门禁发现残留，禁止推送:")
        for r in leaked:
            print(f"  {r['file']}: {r['residual']}")
        sys.exit(1)
    print("✅ 硬门禁零命中，允许进入发布队列")
    sys.exit(0)


if __name__ == "__main__":
    main()
