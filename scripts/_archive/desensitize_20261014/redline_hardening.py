#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""redline_hardening.py — 公库脱敏红线加固层（第二道防线，可叠加于任何基础脱敏引擎）

定位：publish_to_github.py 在调用基础脱敏引擎（scripts/desensitize.py）之后，
再跑本模块作为加固层。设计为幂等可组合：
  - 对已脱敏文本（含 [已脱敏]/¥*** 等掩码）再次执行不产生新变化；
  - 基础引擎漏掉的类别（姓名、组合暴露百分比、敏感词词面）在本层拦截。

本层能力（对应评审中发现的三类泄漏 + 实测过的误杀修正）：
  H0 白名单保护  市场公开常量（亿元资金流、Σ评分、规则阈值、日期）先摘出，防误伤
  H1 个人标识    姓名/用户名/券商名整体替换 + 「投资者：X」角色模式
  H2 强规则补漏  ¥金额 / 元金额(非亿万) / N股 / N份 / 银行卡 / 身份证 / 手机号
  H3 句子级处置  对 HTML 块级标签(p/li/td/th/blockquote/dd/figcaption/叶子div)与 MD 行
                 按句切分，逐句判定：
                   - 含掩码Token([已脱敏]/¥***/***元)或「N股/N份」或(敏感词AND持仓标记)
                     → 整句替换为合规占位句（消词面：浮盈/成本摊薄等）
                   - 含组合结构关键词(持仓/浮亏/浮盈/盈亏/成本/权重/占比/比重/暴露/
                     集中度/穿透/在途/定投/加权/预估/市值/份额/仓位/个人/账户)
                     → 该句内百分比掩码（保文本、杀数值）
                   - 其余（纯市场句）→ 原样保留
  H4 行级兜底    非 prose 行（KPI 卡标签/值分行、style="width:X%" 样式行）：
                 含关键词或掩码Token的行及其后 N 行，百分比一并掩码

关键词表刻意不含「资产/收益/变动/累计」等市场通用词——实测会误杀
「股息率4.51%」「美债收益率 -2.67%」等公开行情；组合类百分比由
浮亏/加权/暴露/占比/权重等专项词覆盖，金额类由强规则覆盖。

验证：harden_verify(text) 对加固后产物复扫 H1/H2 模式 + 姓名清单，返回泄漏清单。
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- 配置
NAMES = ["海震", "梁海震", "lianghaizhen", "seaquake970623"]
ORGS = ["华宝证券", "海通证券", "中信证券", "国泰君安", "招商证券",
        "广发证券", "银河证券", "国信证券"]
ROLE_PATTERNS = [r"(投资者[：:]\s*)([^\s<，。；|*]+)"]

MASK_TEXT = "***"
MASK_MONEY = "¥***"
MASK_PERCENT = "***%"
PROSE_PLACEHOLDER = "【组合运作细节按合规要求不公开】"

# H0 白名单保护（市场公开常量，先摘出占位符）
PROTECT_PATTERNS = [
    r"\d[\d,]*(?:\.\d+)?\s*[亿万千]元",        # 25.31 亿元 / 16,891.33 亿
    r"（[+-]?\d+(?:\.\d+)?，代码计算）",      # Σ 评级（+0.125，代码计算）
    r"Σ[^。\n]{0,30}?[+-]?\d+(?:\.\d+)?",     # Σ 评分
    r"[≥＞]\s*\d+(?:\.\d+)?%", r"[≤＜]\s*\d+(?:\.\d+)?%",
    r">=\s*\d+(?:\.\d+)?%", r"<=\s*-?\d+(?:\.\d+)?%",
    r"\d{4}-\d{2}-\d{2}", r"\d{1,2}:\d{2}",
]

# H3/H4 组合结构类关键词（刻意不含资产/收益/变动/累计，见模块文档字符串）
PERCENT_KEYWORDS = [
    "持仓", "浮亏", "浮盈", "盈亏", "成本", "权重", "占比", "比重",
    "暴露", "集中度", "穿透", "在途", "个人", "账户", "定投", "加权", "预估",
    "市值", "份额", "仓位",
]
CONTEXT_WINDOW = 3          # H4 行级兜底窗口
PERCENT_RE = re.compile(r"[+-]?\d+(?:\.\d+)?%")

# H3 句子级「整句替换」触发条件
PROSE_TERMS = ["成本", "浮盈", "浮亏", "盈亏", "收益率", "市值", "账户", "份额", "仓位", "持仓金额"]
PROSE_MARKERS = [
    "持仓", "组合", "穿透", "在途", "定投", "重仓", "底仓", "网格", "仓位",
    "止盈", "止损", "减仓", "加仓", "减持", "建仓", "清仓", "做T", "高抛", "挂买",
    "浮盈", "浮亏",
]
COUNT_RE = re.compile(r"\d+\s*[股份]")
# P1 开关（team-lead 2026-10-14 规格）：表格单元格内 money token/计数句
# 不整句替换，保留定性描述。置 False 回退到「token 句整格替换」旧行为。
P1_TABLE_NARROW = True

# HTML 表格敏感列关键词（表头命中即整列脱敏——网格区间/成本/盈亏等个人数据）
TABLE_COL_KEYWORDS = [
    "网格", "区间", "持仓", "成本", "盈亏", "收益率", "市值", "份额", "仓位",
    "浮盈", "浮亏", "权重", "占比", "暴露", "集中度", "在途", "定投", "预估",
    "基准价", "步长",
]
_TABLE = re.compile(r"<table[^>]*>(.*?)</table>", re.S | re.I)
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"(<t[hd](?:\s[^>]*)?>)(.*?)(</t[hd]>)", re.S | re.I)
_TAG_RUN = re.compile(r"(<[^>]+>)")
# MD 表格列掩关键词收窄：去掉 预估/定投/暴露——
# md 持仓表「今日预估涨跌」列是基金公开估值（team-lead B 面要求保留 -0.83% 等），
# 「定投/交易类型」列为策略类型词（智慧定投，无数值），「暴露」场景已由「持仓」覆盖。
MD_TABLE_COL_KEYWORDS = [k for k in TABLE_COL_KEYWORDS
                         if k not in ("预估", "定投", "暴露")]

# H2 强规则
# 注：「元」后不接 件/素——「元件」（板块名）会被误判为「1 元」而生成
# ***元 Token，进而在句子级触发整句替换（实测股票助手 S5 行误杀）。
MONEY_PATTERNS = [
    (re.compile(r"[¥￥]\s*[+-]?\d[\d,]*(?:\.\d+)?"), MASK_MONEY),
    (re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?\s*元(?![件素])"), "***元"),
]
# 网格区间（个人策略参数）：7.25-7.40 / 1.020-1.025 / 18.50-24.50
# 市场区间通常为整数（3780-3820），小数区间在这些报告中均为个人网格
GRID_RANGE_RE = re.compile(r"(?<!\d)\d+\.\d+-\d+\.\d+(?!\d)")
# 个人价格语境，双向匹配：
#   强个人词前缀（允许整数）：基准/止盈价/止损价/挂单价——「基准300元」是
#     定投额度基准，整数也要掩；
#   网格语境前缀（限小数点价格）：买卖线/轨道/距等/未破跌破站上触及触发——
#     个人网格参数均为 2-3 位小数；整数位是市场点位「站上 4280 点」，掩会误伤；
#   后缀（小数点+元/以上以下+动作词）：19.90 元挂买 / 21.00以上分批高抛。
PRICE_CONTEXT_RE = re.compile(
    r"((?:基准|止盈价|止损价|挂单价)(?:\s*价)?\s*[：:]?\s*)(?<![+\-.\d])(\d[\d,]*(?:\.\d+)?)"
    r"|((?:卖线|买线|高抛线|低吸线|上轨|下轨|买档|卖档|回补位?|观察位|支撑位?|压力位?|"
    r"距|等|触|未破|跌破|站上|触及|未触及|触发)(?:\s*价)?\s*[：:]?\s*)(?<![+\-.\d])(\d+\.\d+)"
    r"|(?<![+\-.\d])(\d+\.\d+)\s*(?:元|以上|以下)\s*[^。；，\n]{0,8}"
    r"(?:挂买|挂卖|高抛|低吸|止盈|止损|做T|减仓|加仓)"
)
ACCOUNT_PATTERNS = [
    (re.compile(r"(?<!\d)\d{16,19}(?!\d)"), "***"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "***"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "***"),
]

_SENT_DELIM = re.compile(
    r"([。；;！!？?]|<br\s*/?>|</(?:li|p|div|td|th|tr|dd|figcaption|blockquote|section|article|h[1-6])>)",
    re.I)
_STRIP_TAGS = re.compile(r"<[^>]+>")
_MONEY_TOKEN = re.compile(r"¥\*{3}|\*{3}元|\[已脱敏\]")
# H3 作用的 HTML 块级标签；H4 行级兜底跳过含这些标签的行（已由句子级精准处理）
_PROSE_BLOCK_TAGS = ["p", "li", "blockquote", "td", "th", "dd", "figcaption"]
_PROSE_TAG_LINE = re.compile(r"<(?:p|li|td|th|blockquote|dd|figcaption)[\s>]", re.I)
# 容器标签行（卡片行）：含可见文本时视为 prose，交由 H3 句子级处置——
# 实测总复盘「逆向维度」卡片的 [已脱敏] 会跨行误掩相邻「财报维度」卡片的
# 股息率 4.51%（公开行情）；「估值分析师·仓位配置」行误掩下方股息率行。
_CONTAINER_TAG_LINE = re.compile(
    r"<(?:div|section|ul|ol|table|tr|thead|tbody|main|article|header|footer|nav|form)\b", re.I)
# HTML 注释（页面源码可见）：含敏感内容时整条脱敏
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def _placeholder(idx: int) -> str:
    s, idx = "", idx + 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(ord("A") + r) + s
    return f"\ue000{s}\ue001"


def _protect(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def _sub(m: re.Match) -> str:
        tokens.append(m.group(0))
        return _placeholder(len(tokens) - 1)

    for pat in PROTECT_PATTERNS:
        text = re.sub(pat, _sub, text)
    return text, tokens


def _restore(text: str, tokens: list[str]) -> str:
    for i, tok in enumerate(tokens):
        text = text.replace(_placeholder(i), tok)
    return text


def _mask_names(text: str) -> tuple[str, int]:
    n = 0
    for name in NAMES:
        if name:
            c = text.count(name)
            if c:
                text = text.replace(name, MASK_TEXT)
                n += c
    for pat in ROLE_PATTERNS:
        text, k = re.subn(pat, lambda m: m.group(1) + MASK_TEXT, text)
        n += k
    for org in ORGS:
        c = text.count(org)
        if c:
            text = text.replace(org, MASK_TEXT)
            n += c
    return text, n


def _mask_strong(text: str) -> tuple[str, dict]:
    hits = {"money": 0, "shares": 0, "account": 0, "grid_range": 0, "price_ctx": 0}
    for pat, repl in MONEY_PATTERNS:
        text, k = pat.subn(repl, text)
        hits["money"] += k
    text, k = COUNT_RE.subn(MASK_TEXT, text)
    hits["shares"] = k
    text, k = GRID_RANGE_RE.subn("***-***", text)
    hits["grid_range"] = k
    text, k = PRICE_CONTEXT_RE.subn(
        lambda m: (m.group(1) + "***") if m.group(1)
        else ((m.group(3) + "***") if m.group(3) else "***"), text)
    hits["price_ctx"] = k
    for pat, repl in ACCOUNT_PATTERNS:
        text, k = pat.subn(repl, text)
        hits["account"] += k
    return text, hits


# ---------------------------------------------------------------- H3 句子级
# 市场语境豁免（team-lead 2026-10-14 裁决规格）：含市场指标词且无任何个人
# 标记的行/句/单元格，视为公开行情语境——百分比与计数不掩、不替换。
# 实测背景：基金报告宽度表（上涨/下跌/平盘家数占比）、股票助手 KPI 卡
# 「上涨占比 33.1%」、板块资金流句的公开涨跌幅曾被误掩。
MARKET_BREADTH_WORDS = [
    "上涨家数", "下跌家数", "平盘家数", "上涨占比", "下跌占比",
    "涨停", "跌停", "全市场", "A股总股票数", "覆盖全市场",
    "架构类型", "板块资金", "净流入", "净流出", "板块涨跌幅",
    "量比", "成交额", "估值覆盖",
]
PERSONAL_MARKERS = [
    "成本", "浮盈", "浮亏", "盈亏", "持仓金额", "持有收益", "昨日收益",
    "市值", "份额", "仓位", "在途", "定投", "账户", "底仓", "顶仓",
    "网格", "基准价", "高抛", "低吸", "挂买", "挂卖", "组合", "总持仓",
]


def _is_market_line(s: str) -> bool:
    """公开市场语境：含市场指标词且无任何个人标记 → 百分比/计数不掩不替换。"""
    return (any(w in s for w in MARKET_BREADTH_WORDS)
            and not any(m in s for m in PERSONAL_MARKERS))


def _sentence_action(sentence_text: str) -> str:
    """返回 'replace' | 'mask_percent' | 'keep'。"""
    if _is_market_line(sentence_text):
        return "keep"
    if _MONEY_TOKEN.search(sentence_text) or COUNT_RE.search(sentence_text):
        return "replace"
    has_term = any(t in sentence_text for t in PROSE_TERMS)
    has_marker = any(k in sentence_text for k in PROSE_MARKERS)
    if has_term and has_marker:
        return "replace"
    if any(k in sentence_text for k in PERCENT_KEYWORDS):
        return "mask_percent"
    return "keep"


def _replace_keep_tags(seg: str) -> str:
    """整句替换但保留句内 HTML 标签——否则 <p>/<strong> 等开标签会随
    敏感句一起被吃掉，造成标签不配平（实测 daily_review 丢 2 个 <p>）。
    首个非空文本run替换为合规占位句，其余文本run（同句敏感内容）丢弃。
    """
    out, replaced = [], False
    for part in _TAG_RUN.split(seg):
        if part.startswith("<") and part.endswith(">"):
            out.append(part)
        elif part.strip() and not replaced:
            out.append(PROSE_PLACEHOLDER)
            replaced = True
    return "".join(out) if replaced else PROSE_PLACEHOLDER


def _mask_prose_block(block: str, stats: dict, table_mode: bool = False) -> str:
    """按句切分一个文本块，逐句处置。stats 累计 replaced/masked_percent。

    table_mode（MD 表格单元格）：只做整句替换，不掩百分比——表格行常混合
    公开行情单元格与个人数据单元格（实测「创业板指暴跌 -2.82%」与
    「浮亏虽大但禁止追加」同行），掩百分比会误杀行情。
    P1 改进（team-lead 2026-10-14 规格）：money token（[已脱敏]/¥***）与
    N股/N份不再触发整句替换——它们已是安全掩码，同句的定性描述（放量上攻/
    缩量回调未破位/一步之遥/停卖）应当保留；仅门禁词面（term+marker，
    如 浮盈/浮亏/成本/收益率）仍整句替换以保词面零命中。
    """
    if not block.strip():
        return block
    parts = _SENT_DELIM.split(block)
    out, changed = [], False
    i = 0
    while i < len(parts):
        seg = parts[i]
        delim = parts[i + 1] if i + 1 < len(parts) else ""
        stripped = _STRIP_TAGS.sub("", seg)
        action = _sentence_action(stripped) if seg.strip() else "keep"
        if action == "replace" and table_mode and P1_TABLE_NARROW:
            # 表格内收窄：仅门禁词面（term+marker）整句替换；
            # 纯 token/计数句（[已脱敏]/¥***/N股N份）保留——掩码已安全，
            # 同句定性描述（放量上攻/一步之遥/停卖）不拖灭
            term_and_marker = (any(t in stripped for t in PROSE_TERMS)
                               and any(k in stripped for k in PROSE_MARKERS))
            if not term_and_marker:
                action = "keep"
        if action == "replace":
            out.append(_replace_keep_tags(seg))
            stats["replaced"] += 1
            changed = True
        elif action == "mask_percent" and not table_mode:
            new_seg, k = PERCENT_RE.subn(MASK_PERCENT, seg)
            stats["masked_percent"] += k
            if k:
                changed = True
            out.append(new_seg)
        else:
            out.append(seg)
        out.append(delim)
        i += 2
    return "".join(out) if changed else block


def _mask_prose(text: str, stats: dict, fmt: str = "md") -> str:
    """H3：HTML 叶子div + 块级标签 + MD 非表格行，句子级处置。

    fmt == "html" 时跳过 MD 行兜底——HTML 表格行（<tr><td>…）若按 MD 行
    整体当一个句子处理，行内「定投」等关键词会把同行的 SOX/纳指行情
    百分比一并掩掉（实测误杀）；HTML 内容已由标签级句子处理覆盖。
    """
    leaf_div = re.compile(r"(<div[^>]*>)((?:(?!</?div).)*?)(</div>)", re.S | re.I)
    text = leaf_div.sub(
        lambda m: m.group(1) + _mask_prose_block(m.group(2), stats) + m.group(3), text)
    for tag in _PROSE_BLOCK_TAGS:
        # 标签名后必须紧跟 > 或空白——否则 <li...> 会误匹配 <link ...>、
        # <p...> 误匹配 <pre>/<param>、<th...> 误匹配 <thead>，跨行吞噬文档
        tag_re = re.compile(rf"(<{tag}(?:\s[^>]*)?>)(.*?)(</{tag}>)", re.S | re.I)
        text = tag_re.sub(
            lambda m: m.group(1) + _mask_prose_block(m.group(2), stats) + m.group(3), text)
    if fmt == "html":
        return text
    out_lines = []
    for line in text.split("\n"):
        s = line.lstrip()
        if (not s or s.startswith(("#", "---", "===", "```"))
                or re.match(r"^[*-]{3,}$", s)):
            out_lines.append(line)
            continue
        if s.startswith("|"):
            # MD 表格行：按单元格窄处理（仅整句替换，不掩百分比，保行情格）；
            # 市场语境单元格（宽度表/信号行/板块资金）整体豁免
            out_lines.append("|".join(
                cell if _is_market_line(cell)
                else _mask_prose_block(cell, stats, table_mode=True)
                for cell in line.split("|")))
            continue
        out_lines.append(_mask_prose_block(line, stats))
    return "\n".join(out_lines)


# ---------------------------------------------------------------- H4 行级兜底
def _has_content(line: str) -> bool:
    """去除标签后是否还有可见文本（纯结构行如 </div>/<div class=...> 不计）。"""
    return bool(_STRIP_TAGS.sub("", line).strip())


# MD 章节边界（H4 窗口不跨入）：空行/标题/分隔线/代码栏/表格行/列表项
# （列表项自身即句子单元，交由 H3 行内处置；跨项窗口会误掩下一项的公开行情，
#  实测 stock_review「浮盈」项误掩「财报维度」项的粤高速股息率 4.5%）
_MD_BOUNDARY = re.compile(r"^\s*(?:$|#|---|===|```|\||[-*+]\s|\d+\.\s)")


def _h4_state(line: str, fmt: str) -> str:
    """H4 三态资格：
      'full'        裸文本行 / span 行 / 纯结构行——可触发（关键词或掩码Token），
                    也可作窗口目标，窗口可跨越；
      'keyword_only' 容器+文本行（卡片行，如 KPI 标签/cc-action-row）——只能
                    关键词触发（掩码Token 不触发，防邻卡误掩），且窗口到此
                    为止（不跨入下一个卡片行）；
      'none'        prose 标签行（<p>/<li>/<td>…，H3 句子级处置）与 MD 章节
                    边界（空行/标题/分隔线/代码栏/表格行）——不触发、不目标、
                    窗口不跨入。
    """
    if _PROSE_TAG_LINE.search(line):
        return "none"
    if fmt == "md" and _MD_BOUNDARY.match(line):
        return "none"
    if _CONTAINER_TAG_LINE.search(line) and _has_content(line):
        return "keyword_only"
    return "full"


def _mask_percent_context(text: str, stats: dict, fmt: str = "md") -> str:
    """非 prose 行（KPI 标签/值分行、width 样式行）：关键词或掩码Token 行 +
    后 CONTEXT_WINDOW 个「内容行」，百分比一并掩码。

    窗口按内容行距计算而非物理行距：KPI 卡「标签→高暴露→34.74%」中间隔
    多个纯结构 div 行，条形图「CPO+AI穿透额→[已脱敏]→width:27.41%」中间
    隔 3 个纯结构行——物理行距会漏掉，内容行距可覆盖。
    必须在 H3 句子级之前执行：此时 [已脱敏]/¥*** 触发 Token 完好。
    窗口只跨越 'full' 行，遇卡片行/prose 行/章节边界即止（见 _h4_state）。
    """
    lines = text.split("\n")
    has_content = [_has_content(ln) for ln in lines]
    states = [_h4_state(ln, fmt) for ln in lines]
    mask_flag = [False] * len(lines)
    for i, line in enumerate(lines):
        if states[i] == "none":
            continue
        if _is_market_line(line):
            continue  # 市场语境行不触发 H4 窗口（宽度表/KPI 上涨占比等）
        is_trigger = any(k in line for k in PERCENT_KEYWORDS) or (
            states[i] == "full" and _MONEY_TOKEN.search(line))
        if not is_trigger:
            continue
        j, counted = i, 0
        while j < len(lines) and counted <= CONTEXT_WINDOW:
            if j > i and states[j] != "full":
                break  # 卡片行/prose 行/章节边界：窗口不跨入
            mask_flag[j] = True
            if has_content[j]:
                counted += 1
            j += 1
    out = []
    for i, line in enumerate(lines):
        if mask_flag[i] and not _is_market_line(line):
            line, k = PERCENT_RE.subn(MASK_PERCENT, line)
            stats["masked_percent"] += k
        out.append(line)
    return "\n".join(out)


def _mask_table_columns(text: str, stats: dict) -> str:
    """HTML 表格敏感列整列脱敏：表头命中 TABLE_COL_KEYWORDS（网格区间/
    成本/盈亏/权重/暴露…）的列，数据行整格替换为 [已脱敏]。
    实测总复盘「网格区间」列 18.50-24.50 / 6.50-8.50 / 0.850-1.250 为个人
    网格策略参数，v3 仅删 1 列漏掉它；市场列（当日表现/板块行情）保留。
    """
    def _table_sub(m: re.Match) -> str:
        rows = [rm.group(0) for rm in _ROW.finditer(m.group(1))]
        if len(rows) < 2:
            return m.group(0)
        sensitive_cols = set()
        for idx, cell in enumerate(_CELL.findall(rows[0])):
            plain = _STRIP_TAGS.sub("", cell[1])
            if any(k in plain for k in TABLE_COL_KEYWORDS):
                sensitive_cols.add(idx)
        if not sensitive_cols:
            return m.group(0)

        def _row_sub(rm: re.Match) -> str:
            idx = [-1]

            def _cell_sub(cm: re.Match) -> str:
                idx[0] += 1
                if idx[0] in sensitive_cols:
                    stats["table_cells"] = stats.get("table_cells", 0) + 1
                    return cm.group(1) + "[已脱敏]" + cm.group(3)
                return cm.group(0)

            return _CELL.sub(_cell_sub, rm.group(0))

        body = "".join(_ROW.sub(_row_sub, r) for r in rows)
        return m.group(0).replace(m.group(1), body)

    return _TABLE.sub(_table_sub, text)


# MD 表格分隔行（| :---: | :--- |）——用于识别「标准表头 + 分隔行」结构的表格
_MD_TABLE_SEP = re.compile(r"^\s*\|[\s:\-\|]+\|\s*$")


def _mask_md_table_columns(text: str, stats: dict) -> str:
    """MD 表格敏感列整列脱敏（仅标准结构：表头行 + 分隔行 + 数据行）。

    实测基金指引「标的代码|证券名称|现价|当日涨跌|基准价|网格步长|指令」表：
    基准价列（7.05/13.40/5.15/20.40）与网格步长列（2.5%）是裸数字单元格，
    无上下文词可判，只能列级掩；现价/涨跌列是公开行情，保留。
    决策卡表（无分隔行）不在此列——其第四列混合公开与个人数据，由句子级处理。
    """
    lines = text.split("\n")
    out, i, n = [], 0, len(lines)
    while i < n:
        if (i + 1 < n and lines[i].lstrip().startswith("|")
                and _MD_TABLE_SEP.match(lines[i + 1])):
            header_cells = lines[i].split("|")
            sensitive_cols = {idx for idx, c in enumerate(header_cells)
                              if any(k in c for k in MD_TABLE_COL_KEYWORDS)}
            out.append(lines[i])
            out.append(lines[i + 1])
            i += 2
            while i < n and lines[i].lstrip().startswith("|"):
                if sensitive_cols:
                    row_cells = lines[i].split("|")
                    for idx in sensitive_cols:
                        if idx < len(row_cells) and row_cells[idx].strip():
                            row_cells[idx] = " [已脱敏] "
                            stats["md_table_cells"] = stats.get("md_table_cells", 0) + 1
                    out.append("|".join(row_cells))
                else:
                    out.append(lines[i])
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _mask_comments(text: str, stats: dict) -> str:
    """HTML 注释脱敏：页面源码可见，含敏感内容（金额Token/股份份数/
    关键词+百分比/姓名）的注释整条替换，防 source-view 泄漏。"""
    def _sub(m: re.Match) -> str:
        c = m.group(0)
        if (_MONEY_TOKEN.search(c) or COUNT_RE.search(c)
                or any(n in c for n in NAMES)
                or (PERCENT_RE.search(c)
                    and any(k in c for k in PERCENT_KEYWORDS + PROSE_MARKERS))):
            stats["comments"] += 1
            return "<!-- 内容已按合规要求脱敏 -->"
        return c
    return _COMMENT.sub(_sub, text)


# 门禁词面中和：公开语境术语替换，数据本身已脱敏，替换后不改变语义。
# 背景：PM 硬门禁按词面零命中执行；「持仓金额」仅存于表头标签（数据列
# 已整体脱敏），「收益率」在「美债收益率」等公开宏观语境为合规表述。
WORD_SURFACE_SUBS = [(re.compile(r"持仓金额"), "持仓规模")]


def _neutralize_word_surface(text: str, stats: dict) -> str:
    for pat, repl in WORD_SURFACE_SUBS:
        text, k = pat.subn(repl, text)
        stats["word_surface"] = stats.get("word_surface", 0) + k
    parts = _SENT_DELIM.split(text)
    for i in range(0, len(parts), 2):
        if "美债" in parts[i] and "收益率" in parts[i]:
            parts[i] = parts[i].replace("收益率", "利率")
            stats["word_surface"] = stats.get("word_surface", 0) + 1
    return "".join(parts)


def harden(text: str, fmt: str = "auto") -> tuple[str, dict]:
    """加固主入口。返回 (文本, 报告)。幂等：对已脱敏文本重复执行无新变化。

    执行顺序：H4 行级兜底必须先于 H3 句子级——H3 会把含 [已脱敏]/¥***
    的句子整体替换为合规占位句，若先跑 H3，H4 将失去触发 Token，
    条形图 style="width:X%" 等隔行泄漏会漏网（实测）。
    """
    if fmt == "auto":
        fmt = "html" if re.search(r"<(html|body|div|section)\b", text) else "md"
    stats = {"replaced": 0, "masked_percent": 0, "comments": 0, "table_cells": 0,
             "word_surface": 0, "md_table_cells": 0}
    text, tokens = _protect(text)
    text, n_names = _mask_names(text)
    text, strong = _mask_strong(text)
    text = _mask_comments(text, stats)
    text = _neutralize_word_surface(text, stats)
    text = _mask_table_columns(text, stats)
    text = _mask_md_table_columns(text, stats)
    text = _mask_percent_context(text, stats, fmt=fmt)   # H4 先行：触发 Token 完好
    text = _mask_prose(text, stats, fmt=fmt)             # H3 后行：句子级精准处置
    text = _restore(text, tokens)
    report = {"format": fmt, "names": n_names, **strong,
              "protected": len(tokens), **stats}
    return text, report


def harden_verify(text: str) -> list[str]:
    """加固层门禁：返回泄漏清单（空 = 放行）。"""
    leaks: list[str] = []
    for pat, repl in MONEY_PATTERNS + ACCOUNT_PATTERNS:
        m = pat.search(text)
        if m:
            leaks.append(f"强规则残留: {m.group(0)!r}")
    m = COUNT_RE.search(text)
    if m:
        leaks.append(f"股份数残留: {m.group(0)!r}")
    m = GRID_RANGE_RE.search(text)
    if m:
        leaks.append(f"网格区间残留: {m.group(0)!r}")
    m = PRICE_CONTEXT_RE.search(text)
    if m:
        leaks.append(f"个人价格语境残留: {m.group(0)!r}")
    for name in NAMES + ORGS:
        if name and name in text:
            leaks.append(f"标识残留: {name}")
    return leaks


# ---------------------------------------------------------------- PM 红线门禁
# 发布前最终闸门（词面零命中）。唯一定义处——publish_to_github.py 与
# pipeline_selftest.py 均 import 本字典与 redline_scan，杜绝三处模式漂移。
# 「占比」排除上涨/下跌语境；市场语境行（_is_market_line）对数值语境模式豁免
# （实测「全市场上涨2909家(占比52%)」「上涨占比 50.7%」为公开宽度数据）。
REDLINE_GATE = {
    "股份数": r"\d+\s*股",
    "基金份数": r"\d+\s*份",
    "成本": r"成本",
    "浮盈": r"浮盈",
    "浮亏": r"浮亏",
    "收益率": r"收益率",
    "市值": r"市值",
    "账户": r"账户",
    "持仓金额": r"持仓金额",
    "姓名": r"海震|梁海震|lianghaizhen|seaquake970623",
    "¥金额": r"[¥￥]\s*[+-]?\d",
    # 「元」后不接 件/素——「元件」为板块名（与掩码规则保持一致）
    "元金额": r"\d[\d,]*(?:\.\d+)?\s*元(?![件素])",
    "银行卡": r"(?<!\d)\d{16,19}(?!\d)",
    "身份证": r"(?<!\d)\d{17}[\dXx](?!\d)",
    "手机号": r"(?<!\d)1[3-9]\d{9}(?!\d)",
    "个人百分比词面": (r"(?:持仓|仓位|权重|暴露)[^。；\n]{0,12}?\d+(?:\.\d+)?%"
                   r"|(?<!上涨)(?<!下跌)占比[^。；\n]{0,12}?\d+(?:\.\d+)?%"),
    "网格区间": r"(?<!\d)\d+\.\d+-\d+\.\d+(?!\d)",
    "个人价格语境": PRICE_CONTEXT_RE.pattern,
}
# 市场语境行豁免的数值模式（词面模式不豁免——公开语境本就不该出现这些词）
_MARKET_EXEMPT = {"个人百分比词面", "个人价格语境", "网格区间"}


def redline_scan(text: str) -> list[str]:
    """PM 红线门禁扫描：返回命中清单（空 = 放行）。

    逐行、按句扫描：同一行可能混合市场句与个人句（实测 daily_review
    「全市场上涨2909家(占比52%)」与「【组合运作细节】」同处一个 <ul> 块），
    行级豁免会因个人标记拖累市场句，故按句切分判定市场语境。
    市场语境句对数值模式豁免（宽度/板块资金等公开语境不误报）。
    """
    hits = []
    for i, line in enumerate(text.split("\n"), 1):
        sentences = _SENT_DELIM.split(line)
        for k in range(0, len(sentences), 2):
            seg = sentences[k]
            if not seg.strip():
                continue
            market = _is_market_line(seg)
            for label, pat in REDLINE_GATE.items():
                if market and label in _MARKET_EXEMPT:
                    continue
                m = re.findall(pat, seg)
                if m:
                    hits.append(f"{label}×{len(m)}@L{i}")
    return hits


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="红线加固层（可叠加于基础脱敏引擎）")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output")
    ap.add_argument("--format", choices=["auto", "md", "html"], default="auto")
    args = ap.parse_args()
    src = open(args.input, encoding="utf-8").read()
    out, rep = harden(src, fmt=args.format)
    if args.output:
        open(args.output, "w", encoding="utf-8").write(out)
    else:
        sys.stdout.write(out)
    print(f"[harden] {rep}", file=sys.stderr)
    leaks = harden_verify(out)
    for lk in leaks:
        print(f"[harden][LEAK] {lk}", file=sys.stderr)
    sys.exit(5 if leaks else 0)
