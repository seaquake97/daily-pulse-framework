"""统一内容契约（Unified Content Contract）。

六个每日定时任务共用的唯一结构来源：章节骨架、维度词典、SVG 图标语义映射、
数据时点标注格式与一致性校验。纯标准库，零第三方依赖。

调用方
------
生成侧：build_skeleton(slug) 取骨架，各任务只填内容，不自造结构。
门禁侧：validate_contract(path, market_data) 返回违规清单。

本模块只定义规则与拼装字符串，不做 IO 编排、不发请求、不写产出文件。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from content_dictionary import BANNED_DIMENSIONS, DIMENSIONS, ICONS

CONTRACT_VERSION = "1.0.0"

DATA_STAGES = ("pre_open", "intraday", "close")
BREADTH_SCOPES = ("a_only", "a_plus_bj")
RATINGS = ("进攻", "均衡", "信号矛盾", "防守", "回避")


# --------------------------------------------------------------------------
# 章节骨架
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Section:
    """骨架中的一个章节。required=True 为所有任务必选；否则按 applies_to 选入。"""

    key: str
    title_zh: str
    title_en: str
    required: bool = False
    applies_to: tuple[str, ...] = ()


SECTIONS: tuple[Section, ...] = (
    Section("verdict", "结论卡", "Verdict Card", required=True),
    Section("sigma_timeline", "日内 Σ 演进", "Intraday Sigma Timeline",
            applies_to=("stock-review", "daily-review", "v2-decision-engine")),
    Section("market_snapshot", "市场快照", "Market Snapshot",
            applies_to=("stock-assistant", "fund-market", "stock-review", "daily-review")),
    Section("signal_detail", "确定性信号明细", "Signal Detail",
            applies_to=("stock-assistant", "fund-market", "fund-guide",
                        "stock-review", "daily-review")),
    Section("bull_bear_evidence", "多空证据清单", "Bull-Bear Evidence",
            applies_to=("stock-assistant", "fund-market")),
    Section("sector_moneyflow", "板块资金流向", "Sector Money Flow",
            applies_to=("fund-market", "fund-guide", "stock-review", "daily-review")),
    Section("overseas_check", "外盘联动校验", "Overseas Linkage Check",
            applies_to=("fund-market", "fund-guide", "stock-review", "daily-review")),
    Section("portfolio_attribution", "组合加权归因", "Portfolio Attribution",
            applies_to=("fund-market", "fund-guide", "daily-review")),
    Section("fund_lookthrough", "基金穿透诊断", "Fund Look-through",
            applies_to=("fund-market", "fund-guide")),
    Section("position_action", "持仓动作卡", "Position Action Card",
            applies_to=("stock-assistant", "fund-guide", "stock-review", "daily-review")),
    Section("grid_order", "网格委托指令", "Grid Order Instruction",
            applies_to=("fund-guide",)),
    Section("expert_roundtable", "专家圆桌", "Expert Roundtable",
            applies_to=("stock-review", "daily-review", "v2-decision-engine")),
    Section("viewpoint_ledger", "观点台账", "Viewpoint Ledger",
            applies_to=("stock-assistant", "fund-guide", "stock-review", "daily-review")),
    Section("data_gap", "数据缺口", "Data Gap"),
    Section("watchlist", "待验证信号", "Watch Signals", required=True),
    Section("disclaimer", "免责声明", "Disclaimer", required=True),
)

SECTION_ORDER = tuple(s.key for s in SECTIONS)

# 章节标题白名单：由 SECTIONS 派生，不单独维护，避免两处定义漂移
SECTION_TITLES_ZH = frozenset(s.title_zh for s in SECTIONS)
SECTION_TITLES_EN = frozenset(s.title_en for s in SECTIONS)


# --------------------------------------------------------------------------
# 校验规则常量
# --------------------------------------------------------------------------
# emoji 码点白名单（显式枚举，不用区间）。
# 区间写法在 U+2600-U+27BF 段会误伤 U+2605/U+25B2/U+2194 等排版与评级符号，
# 而按实际用到的符号逐个列出，既覆盖 U+26A0/U+26A1 又不误判。
_EMOJI_CHARS = (
    "\U0001F300-\U0001F5FF"    # 常用图形符号
    "\U0001F600-\U0001F64F"    # 表情
    "\U0001F680-\U0001F6FF"    # 交通与地图
    "\U0001F900-\U0001F9FF"    # 补充符号
    "\U0001F1E6-\U0001F1FF"    # 区域指示
    "\u26A0\u26A1\u2705\u274C\u2757\u2753\u2B50"  # 杂项符号：仅取实际用作章节标记者
)
EMOJI_PATTERN = f"[{_EMOJI_CHARS}]"
RE_EMOJI = re.compile(EMOJI_PATTERN)
RE_EMOJI_FVS = re.compile(EMOJI_PATTERN + "\uFE0F?")
RE_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
RE_NUMBERED = re.compile(r"^\d{2}\.\s")
RE_SIGMA = re.compile(r"Σ\s*[=＝]\s*([+-]?\d+\.\d+)")
RE_SNAPSHOT_AT = re.compile(r"snapshot_at\s*[=＝:]\s*`?(\d{4}-\d{2}-\d{2} \d{2}:\d{2})`?")
RE_DATA_STAGE = re.compile(r"data_stage\s*[=＝:]\s*`?(\w+)`?")
RE_BREADTH = re.compile(r"breadth_scope\s*[=＝:]\s*`?(\w+)`?")


@dataclass
class Violation:
    """一条契约违规。severity: error=阻断发布，warn=提示。"""

    rule: str
    line: int
    message: str
    severity: str = "error"

    def as_dict(self) -> dict:
        return {"rule": self.rule, "line": self.line,
                "message": self.message, "severity": self.severity}


# --------------------------------------------------------------------------
# 生成侧
# --------------------------------------------------------------------------
def build_skeleton(slug: str) -> list[Section]:
    """返回该任务的章节骨架（保持 SECTIONS 声明顺序）。

    条件章节当日无数据时保留章节并写明无数据，禁止删除——结构稳定优先于行数。
    """
    return [s for s in SECTIONS if s.required or slug in s.applies_to]


def render_skeleton_md(slug: str) -> str:
    """把骨架渲染为章节标题行，供生成侧直接写入报告。"""
    out = []
    for i, sec in enumerate(build_skeleton(slug), start=1):
        out.append(f"## {i:02d}. {sec.title_zh}")
    return "\n".join(out)


def render_meta_block(sigma: float, data_stage: str, snapshot_at: str,
                      rating: str, valid_weight: float = 1.0,
                      breadth_scope: str = "") -> str:
    """渲染报告头部数据时点标注块。六字段固定顺序，与 market_data.json 同名。"""
    parts = [
        f"Σ = {sigma:+.3f}",
        f"data_stage=`{data_stage}`",
        f"snapshot_at=`{snapshot_at}`",
        f"rating={rating}",
        f"valid_weight={valid_weight:.2f}",
    ]
    if breadth_scope:
        parts.append(f"breadth_scope=`{breadth_scope}`")
    return "> " + " ｜ ".join(parts)


def render_sigma_line(sigma: float, data_stage: str, snapshot_at: str,
                      rating: str) -> str:
    """结论卡首行的 Σ 行：值与时点必须同行出现，禁止裸 Σ。"""
    return f"- Σ = **{sigma:+.3f}** ｜ data_stage=`{data_stage}` ｜ " \
           f"snapshot_at=`{snapshot_at}` ｜ rating=**{rating}**"


def render_sigma_timeline(rows: list[dict]) -> str:
    """渲染日内 Σ 演进带。rows 每项：time, snapshot_at, data_stage, sigma, rating, driver。

    收盘后任务强制输出，用于让读者一眼区分"观点演进"与"数据错误"。
    """
    lines = [
        "| 时点 | 快照时刻 | data_stage | Σ | 评级 | 驱动变化 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(f"| {r['time']} | {r['snapshot_at']} | `{r['data_stage']}` | "
                     f"{r['sigma']:+.3f} | {r['rating']} | {r.get('driver', '-')} |")
    return "\n".join(lines)


def comparable(sigmas: list[dict]) -> tuple[bool, str]:
    """判断一组 Σ 是否跨时点可比。breadth_scope 或 valid_weight 不一致即不可比。"""
    scopes = {s.get("breadth_scope") for s in sigmas if s.get("breadth_scope")}
    weights = {round(float(s.get("valid_weight", 1.0)), 2) for s in sigmas}
    if len(scopes) > 1:
        return False, f"breadth_scope 不一致（{'/'.join(sorted(scopes))}），Σ 跨时点不可比"
    if len(weights) > 1:
        return False, f"valid_weight 不一致（{sorted(weights)}），Σ 跨时点不可比"
    return True, "口径一致，Σ 可跨时点比较"


# --------------------------------------------------------------------------
# 门禁侧
# --------------------------------------------------------------------------
def validate_contract(path: Path, market_data: dict | None = None) -> list[Violation]:
    """扫描一份 Markdown 产出，返回违规清单。

    market_data 为该任务自己的 market_data.json；传入后额外校验 Σ 值是否
    与数据层一致（防止跨任务继承他任务结论）。
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    out: list[Violation] = []

    for i, line in enumerate(lines, start=1):
        if RE_EMOJI_FVS.search(line):
            out.append(Violation("EMOJI", i, f"产出含 emoji：{line.strip()[:60]}"))

        m = RE_HEADING.match(line)
        if m and len(m.group(1)) == 2:
            title = m.group(2)
            if not RE_NUMBERED.match(title):
                out.append(Violation(
                    "NUMBERING", i,
                    f"章节标题未用两位数字编号：{title[:40]}（规范：`## 03. 标题`）"))
            elif title[3:].strip() not in SECTION_TITLES_ZH | SECTION_TITLES_EN:
                out.append(Violation(
                    "SECTION_NAME", i,
                    f"章节名不在骨架内：{title[3:].strip()[:40]}"))

        for key, zh, old in BANNED_DIMENSIONS:
            if old in line:
                out.append(Violation(
                    "DIMENSION", i, f"维度名 `{old}` 已废弃，规范名为 `{zh}`（{key}）"))

    if RE_SIGMA.search(text):
        if not RE_SNAPSHOT_AT.search(text):
            out.append(Violation("SIGMA_SNAPSHOT_STAMP", 0,
                                 "报告出现 Σ 值但缺 snapshot_at 时点戳"))
        if not RE_DATA_STAGE.search(text):
            out.append(Violation("SIGMA_STAGE_STAMP", 0,
                                 "报告出现 Σ 值但缺 data_stage 时点标注"))

    dm = RE_DATA_STAGE.search(text)
    if dm and dm.group(1) not in DATA_STAGES:
        out.append(Violation("STAGE_ENUM", 0,
                             f"data_stage 非法：`{dm.group(1)}`，"
                             f"枚举值 {DATA_STAGES}"))

    br = RE_BREADTH.search(text)
    if br and br.group(1) not in BREADTH_SCOPES:
        out.append(Violation("BREADTH_SCOPE", 0,
                             f"breadth_scope 非法：`{br.group(1)}`，"
                             f"枚举值 {BREADTH_SCOPES}"))
    elif not br:
        out.append(Violation("BREADTH_SCOPE", 0,
                             "未声明 breadth_scope，跨时点 Σ 无法判定可比性", "warn"))

    if market_data:
        out.extend(_validate_sigma_value(text, market_data))
    return out


def _validate_sigma_value(text: str, market_data: dict) -> list[Violation]:
    """Σ 值必须等于本任务 market_data.json 的 verdict.sigma，禁止继承他任务值。"""
    out: list[Violation] = []
    verdict = market_data.get("verdict") or {}
    if "sigma" not in verdict:
        return [Violation("SIGMA_SOURCE", 0,
                          "market_data.json 缺 verdict.sigma，Σ 无法回溯校验")]
    declared = verdict["sigma"]
    for m in RE_SIGMA.finditer(text):
        found = float(m.group(1))
        if abs(found - declared) > 5e-4:
            out.append(Violation(
                "SIGMA_VALUE", text[:m.start()].count("\n") + 1,
                f"报告 Σ={found:+.3f} 与本任务 market_data.json 的 "
                f"verdict.sigma={declared:+.3f} 不一致"))
    return out


def validate_json_artifact(path: Path) -> list[Violation]:
    """校验 market_data.json 的时点标注完整性。"""
    out: list[Violation] = []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [Violation("JSON_INVALID", 0, f"无法解析：{exc}")]

    if data.get("data_stage") not in DATA_STAGES:
        out.append(Violation("STAGE_ENUM", 0,
                             f"data_stage 缺失或非法：`{data.get('data_stage')}`"))
    if not data.get("snapshot_at"):
        out.append(Violation("SNAPSHOT_AT", 0,
                             "market_data.json 缺 snapshot_at，无法回溯 Σ 对应时刻"))
    if not (data.get("verdict") or {}).get("sigma") is not None:
        out.append(Violation("SIGMA_SOURCE", 0, "verdict.sigma 缺失"))
    return out
