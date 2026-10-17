#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""publish_to_github.py — 每日产出 → GitHub 自动发布编排器（dry-run 默认）

流水线（七步）：
  1. 收集   从任务目录取 <date> 产出的 .md/.html（股票助手/基金盘面/基金指引/
            股票复盘/每日总复盘；总复盘与股票复盘共享 stock_review.md，按
            slug 去重只发布一次）
  2. 提取   从 market_data.json 的 verdict 取 Σ 评级/数据时点；标题取 md 首行
  3. 双语   生成 meta.json（title_zh/title_en/summary_zh/summary_en/rating/
            sigma/data_stage/tasks）
  4. 落盘   写入 _stage/docs/daily/<date>/（原样直写，尚未消毒）
  4.1 渲染   md-only 任务（如 14:30 基金指引，任务书只产 md）由统一渲染器
             scripts/render_md.py 补详情页 HTML（FRAMEWORK-DESIGN v2.0 §2.2：
             上游五套 HTML 生成器逐步废弃，本管线成为唯一呈现层生产者）。
             渲染成功必须回写 entry["html"]——否则 entries.json 记 null、
             frame_pass（C-1）跳过该页，产物永不加框。渲染失败返回退出码 3。
  4.5 消毒  调 scripts/sanitize_body.py 对 _stage/docs/daily/<date>（仅目标
            日期目录，不扫全树）做发布层消毒
            （emoji→SVG / 去渐变 / 色值收敛 Token / 摘 JS / 标题层级对齐 /
            图标引用闭环补全）。--no-sanitize 可回退为原样发布，该回退通道
            同步跳过 frame_pass（详情页保持原样字节，见测试契约定字节断言）。
            退出码契约：0 成功；2 有 needs-manual-review（警告不阻断，
            manifest 记 sanitize_warn）；其余非零失败（本编排器返回 3）。
            时点护栏（B-8）：产物陈旧于 sanitizer 代码时，正常路径强制
            重新消毒并留痕 stale_forced；--no-sanitize 遇到陈旧产物
            直接阻断（退出码 3）——不存在「代码新于产物却直接发布」的路径。
            护栏扫描范围与消毒一致（仅目标日期目录）：管线永不重处理不是
            本次写入的页面（2026-10-15 跨日期腐败事故的架构主修——全树
            消毒会把昨日已消毒+已加框的页面重新消毒，map_custom_properties
            腐蚀 frame 注入的 palette 原语，回归见 test_sanitize_scope.py）。
  5. 站点   调 scripts/build_site.py 生成日期页/周月归档/feed/sitemap/methodology
            （入口内先跑 frame_pass 给详情页包阅读框架，sanitize 之后；
             --no-sanitize 回退通道以 --no-frame 同步跳过）
  6. 清单   写 _stage/manifest.json（仓库/分支/文件清单/哈希/推送参数模板）
  7. 推送   --push 模式：校验 manifest 并打印完整推送调用参数，
            由代理（或定时任务）读取 manifest 后实际执行

⚠️ 推送通道：优先使用本地 fine-grained PAT（~/.config/gh-ip/token，走 git push）；
   无PAT 时退化为打印 manifest 供代理侧 MCP 执行。manifest.json 是本地与
   推送侧之间的契约。

用法：
  python3 publish_to_github.py --date 2026-10-14                  # dry-run（默认）
  python3 publish_to_github.py --date 2026-10-14 --task fund-market
  python3 publish_to_github.py --date 2026-10-14 --push           # 实际推送到 GitHub
  python3 publish_to_github.py --date 2026-10-14 --push --owner seaquake97
  python3 publish_to_github.py --date 2026-10-14 --no-sanitize    # 跳过消毒（回退通道）

退出码规范：
  0  成功（dry-run 完成 / 推送完成）
  1  保留（历史脱敏门禁退出码，已废弃）
  2  任务产物缺失（部分或全部：stdout 列出缺失任务名、缺失原因与预期
     目录）/ 无产出 / 参数错误
  3  站点生成失败（build_site）/ 正文消毒失败（sanitize）/ 时点护栏阻断（B-8）
  4  manifest 写入失败
  5  结构或幂等校验失败
  6  推送失败

缺失即中止（A-03，ADR-005 决策四）：collect() 逐条记录缺失任务，
main() 在缺失非空时于 manifest 写入前返回 2。缺席口的产物不进
_stage——「发布 4 条、看起来像成功」正是 2026-10-16 事故的形态
（15:05 stock-review 整条消失而退出码 0，读者无任何告警）。
上一轮的 manifest 是推送侧契约，失败轮不覆盖它（取舍见 ADR-006）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "framework" / "scripts"))   # A-04: 集中路径
import paths                                                       # noqa: E402

from sanitizer.freshness import sanitizer_code_mtime, stale_artifacts  # noqa: E402
import site_content as SC                                  # noqa: E402  结论先行摘要契约
import path_scrub as PS                                    # noqa: E402  .md 绝对路径脱敏

SOURCE_ROOT = paths.WORKBUDDY_ROOT
STAGE = paths.STAGE
MANAGED_PY = paths.MANAGED_PY

# 任务 slug → (任务目录, [候选文件名])；发布路径 docs/daily/<date>/<slug>.<ext>
TASK_SOURCES = {
    "fund-market": ("基金每日盘面分析（11:00）", ["fund_market_analysis.md", "fund_market_analysis.html"]),
    "stock-assistant": ("股票助手", ["stock_assistant.md", "stock_assistant.html"]),
    "fund-guide": ("基金每日操作指引（14:30）", ["fund_operation_guide.md", "fund_operation_guide.html"]),
    # ADR-005 决策一（GAP-PM §3.1 决策 1，与 A-03 同链）：stock-review 改指
    # 15:30 目录——实测 4/4 交易日有 stock_review.md；15:05 目录降级为可选
    # 副本（2026-10-16 该目录整条无 md/html，即 A-03 事故日）。只取 md，
    # 详情页由步骤 4.1 统一渲染，不再直搬上游 html。
    "stock-review": ("每日总复盘（15:30）", ["stock_review.md"]),
    # daily-review 与 stock-review 同读 15:30 目录但不同文件（md 与 html
    # 各归其位）。总复盘只发布 html，md 即同目录的 stock_review.md。
    "daily-review": ("每日总复盘（15:30）", ["daily_review.html"]),
}

# 展示名（meta.tasks 用）
TASK_NAMES = {
    "fund-market": "基金盘面分析", "stock-assistant": "股票助手",
    "fund-guide": "基金操作指引", "stock-review": "股票复盘",
    "daily-review": "每日总复盘",
}


# slug → (展示名, 发布时点, 一句话说明)  2026-10-14 新增：驱动每日时间线排序
TASK_META = {
    "stock-assistant": ("股票助手", "09:28", "竞价窗口的持仓级研判与条件单建议"),
    "fund-market":     ("基金盘面", "11:00", "基金加权涨跌穿透与板块轮动诊断"),
    "fund-guide":      ("基金操作指引", "14:30", "尾盘决策窗口的分层操作指令"),
    "stock-review":    ("股票复盘", "15:05", "收盘后多视角对抗辩论与决策卡"),
    "daily-review":    ("每日总复盘", "15:30", "当日全部研判的汇总归档与观点结算"),
}

# 市场数据源（按优先级）：总复盘 → 股票助手
# 仅用于「当日汇总 meta」的标题/评级，不代表任何单个任务的 Σ。
MARKET_DATA_DIRS = ["每日总复盘（15:30）", "股票助手"]

# P0 修复（2026-10-14）：per-slug 数据源。
# 事故记录：此前 load_market_data() 只按优先级取一份数据，再把它发给全部
# 5 个时间线条目，导致 09:28 任务被标上15:30 的收盘 Σ（-0.339 防守），
# 而其正文实为 +0.010 信号矛盾 —— 站点在替人说谎，比正文层缺陷严重一个量级。
# 现在每个 slug 必须取自己目录下的 market_data.json，取不到就诚实留 None，
# 由 validate 规则暴露缺口，绝不借用其他任务的数据。
SLUG_DATA_DIR = {
    "stock-assistant": "股票助手",
    "fund-market": "基金每日盘面分析（11:00）",
    "fund-guide": "基金每日操作指引（14:30）",
    "stock-review": "股票复盘",
    "daily-review": "每日总复盘（15:30）",
}

# 各任务数据时点（SLUG_STAGE）：自 A-19 起收敛为单一数据源
# framework/config/slug_stage.json，与 md_render/meta.py 同读一份，杜绝两处漂移。
# 09:28 是集合竞价快照，性质是 pre_open 而非 intraday —— 标错会让读者
# 把竞价结论当盘中结论读（PM PC-7 / C-11 实锤，裁决 OPEN-004）。
def _load_slug_stage() -> dict[str, str]:
    cfg = HERE.parent / "framework" / "config" / "slug_stage.json"
    return json.loads(cfg.read_text(encoding="utf-8"))

SLUG_STAGE = _load_slug_stage()

STAGE_MAP = {"pre_open": ("竞价时点", "Pre-open"), "intraday": ("盘中时点", "Intraday"),
             "close": ("收盘时点", "Close")}

RATING_EN = {"进攻": "Offense", "均衡": "Balanced", "信号矛盾": "Signal Conflict",
             "防守": "Defense", "回避": "Avoid"}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _sha256_file(p: Path) -> str:
    """文件字节哈希（不解码）：脏文件（如非 UTF-8）也要能进比对，
    让故障在消毒子进程的退出码契约里显式失败，而不是在本函数抛栈。"""
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def load_market_data(src_root: Path, date: str) -> dict | None:
    for d in MARKET_DATA_DIRS:
        p = src_root / d / date / "market_data.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  ⚠️ market_data.json 解析失败 {p}: {e}")
    return None


def load_market_data_for_slug(src_root: Path, date: str, slug: str) -> dict | None:
    """P0 修复：只取该 slug 自己的 market_data.json，禁止跨任务借用。

    取不到返回 None —— 调用方必须让Σ/rating 显示为「数据缺口」，
    不得用其他任务的值填充（这正是本次事故的根因）。
    """
    d = SLUG_DATA_DIR.get(slug)
    if not d:
        return None
    p = src_root / d / date / "market_data.json"
    if not p.exists():
        print(f"  ⚠️ [数据缺口] {slug}: {p} 不存在 → Σ/rating 将显示为不可用")
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️ market_data.json 解析失败 {p}: {e}")
        return None


def collect(src_root: Path, date: str, only_task: str | None) -> tuple[dict, list[dict]]:
    """收集 <date> 的任务产出。返回 ({slug: {ext: Path}}, [缺失任务记录])。

    A-03：缺失不再静默。每个被请求（未被 --task 过滤）但没收集到产物的
    slug 都进 missing，带 reason 供调用方区分两种缺失语义
    （ADR-005 决策四）：
      dir-missing   任务目录不存在——当日未运行
      no-artifacts  目录存在但候选文件全缺——运行了但没写出报告
    返回 (outputs, missing) 而非只回 outputs：缺一个 slug 与缺五个 slug
    在旧签名里长得一模一样（都是「少几项」），调用方无法如实上报。
    """
    outputs: dict[str, dict] = {}
    missing: list[dict] = []
    for slug, (dir_name, candidates) in TASK_SOURCES.items():
        if only_task and slug != only_task:
            continue
        d = src_root / dir_name / date
        if not d.is_dir():
            missing.append({"slug": slug, "dir": str(d), "reason": "dir-missing"})
            continue
        entry = {}
        for fname in candidates:
            p = d / fname
            if p.exists():
                entry[p.suffix.lstrip(".")] = p
        if entry:
            outputs[slug] = entry
        else:
            missing.append({"slug": slug, "dir": str(d), "reason": "no-artifacts"})
    return outputs, missing


def report_missing(missing: list[dict], got: int) -> None:
    """A-03：stdout 显式列出缺失任务。全部缺失与部分缺失同码（2）但可区分：
    行首标「全部/部分」，并给出每个任务的缺失原因与预期目录。"""
    total = got + len(missing)
    kind = "全部" if got == 0 else "部分"
    print(f"❌ {kind}任务产物缺失（实收 {got}/{total}）——发布中止（退出码 2）")
    for m in missing:
        why = ("任务目录不存在（当日未运行？）" if m["reason"] == "dir-missing"
               else "目录存在但无 md/html 产物（运行了但没写出报告？）")
        print(f"  - {TASK_NAMES[m['slug']]}（{m['slug']}）: {why}")
        print(f"    预期目录: {m['dir']}")


# 标题里的装饰性 emoji（📊📈🔍 等）——保留 1 个以内纯视觉符号意义不大，统一剥离
_TITLE_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]+")


def _clean_title(raw: str) -> str:
    """清洗标题：去井号、去 emoji、去 markdown 强调符、去表格竖线残留。"""
    t = _TITLE_EMOJI.sub("", raw.strip().lstrip("#").strip())
    t = re.sub(r"^\s*[—–\-·]+\s*", "", t)
    t = re.sub(r"^[#>\s]+", "", t)
    t = t.rstrip("|").strip()
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"__(.+?)__", r"\1", t)
    return re.sub(r"\s{2,}", " ", t).strip()


_META_LINE = re.compile(r"^\s*(?:[-*>]\s*)?(?:\*\*)?"
                        r"(?:生成时点|数据时点|分析日期|数据架构|架构类型|诊断状态|"
                        r"数据源|评级|时间|日期|数据日期|更新时间|生成时间|说明|备注|备注说明)"
                        r"(?:\*\*)?\s*[：:]")


_FACT_RE = re.compile(r"[+\-−]?\d+(?:\.\d+)?\s*%")
# 数据源降级标记：命中即在摘要尾部如实标注，绝不让降级看起来像正常产出
_DEGRADED_RE = re.compile(r"(未连接|无法调用|降级使用|数据缺口|无响应)")
# 列表编号行（「1.」「①」「第一步」）——是清单不是当天的结论性事实
_LIST_PREFIX_RE = re.compile(r"^(?:\d+[.、)]|[①-⑳]|[（(]\d+[)）])\s*")
# 摘要层 P0 清洗（C-3）：结论段是纯文本摘要，不是 markdown——
# 裸反引号在页面上就是「代码块围栏残留」，emoji 直接违反团队 P0-1。
_CONCLUSION_STRIP_RE = re.compile(
    r"[`*_#]|[\U0001F300-\U0001F9FF\U0001FAFF☀-➿⬀-⯿]")


def _key_fact(text: str, limit: int = 44) -> str:
    """从正文抽一句「带百分比的实数事实」作为摘要第三段（关键事实）。

    只取已有文字，不生成任何新数字。排除三类噪音（元信息行 / 列表编号 /
    代码块）——首版未排除时取到过「架构类型：100% 动态真实数据源架构」
    这类无信息量行（用户实锤摘要看不出结论的根因之一）。
    找不到合格短句即返回空串，摘要退化为两段，仍满足结论先行契约。

    C-3 铁律：截断只在词内发生时加省略号，且优先在**子句边界**截
    （逗号/分号/句号/顿号），避免把「小米」截成「小」这种改词事故；
    标点不加分。找不到子句边界才退化到硬截 + 省略号。
    """
    in_code = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line or line.startswith(("|", ">", "#", "---", "===", "<!--")):
            continue
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        s = re.sub(r"^[-*>]\s*", "", s).strip()
        if _META_LINE.match(s) or _LIST_PREFIX_RE.match(s):
            continue
        if _FACT_RE.search(s) and 6 <= len(s) <= 120:
            s = re.sub(r"\s+", " ", s)
            s = _CONCLUSION_STRIP_RE.sub("", s).strip()
            if len(s) <= limit:
                return s
            # 子句边界优先截断（≥ 半长才有信息量）
            cut = max((s.rfind(p, 0, limit + 1) for p in "，,；;。 "),
                      default=-1)
            if cut >= limit // 2:
                head = s[:cut].rstrip()
            else:
                head = s[:limit].rstrip()
            # C-3 铁律（PM PC-27 实锤）：截断后必须带省略号。
            # 无省略号 = 文本被改动而非节选——读者无从得知后面还有内容。
            return head + ("…" if len(head) < len(s) else "")
    return ""


def _first_paragraph(text: str, title: str, limit: int = 120) -> str:
    """取H1 之后第一段有实质内容的正文作为一句话摘要（详情页元信息用）。

    刻意跳过：H1 本身（会与标题重复）、引言元信息行（生成时点/架构类型等）、
    表格、分隔线、代码块 —— 这些都不是「这条产出讲了什么」。

    注意：时间线卡片与 RSS description 用的是结论先行摘要
    （SC.conclusion），本函数只作详情页 doc-meta 的补充说明。
    """
    in_code = False
    seen_h1 = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line:
            continue
        if line.startswith("# ") and not seen_h1:
            seen_h1 = True
            continue
        if line.startswith("#"):
            continue
        if line.startswith(("|", ">", "---", "===", "<!--", "***", "___")):
            continue
        # 元信息行：有明确字段名前缀 + 冒号，且较短
        if _META_LINE.match(line):
            continue
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        s = re.sub(r"^[-*>]\s*", "", s).strip()
        s = re.sub(r"\s{2,}", " ", s)
        if len(s) < 16:
            continue
        # 剥离代码反引号（正文里 `3,807.50` 这类内联代码对摘要无意义）
        if "`" in s:
            s = s.replace("`", "")
        # 去掉行首列表编号（"1. " / "① " / "- "），摘要不应带序号
        s = re.sub(r"^(?:\d{1,2}[.、)]|[①-⑳]|[-*•])\s*", "", s).strip()
        # 避免摘要与标题雷同
        if title and s[:24] == title[:24]:
            continue
        if len(s) < 16:
            continue
        return (s[:limit] + "…") if len(s) > limit else s
    return ""


def extract_entry(slug: str, entry: dict, market_data: dict | None, date: str) -> dict:
    """单份产出的时间线条目：规范标题 + 发布时点 + 摘要 + 评级。

    铁律（FRAMEWORK-DESIGN v2.0 §2.1）：标题一律用规范格式
    「<任务名> · YYYY-MM-DD（周X）<阶段标签>」——终结上游 H1 五花六门
    （实测五种格式：带版本号/带 emoji/破折号副标题/纯日期等）。
    Markdown 仅入库（md 字段），不在页面做导航展示。
    """
    from render_md import render_title  # 延迟 import：防 render_md→publish 循环

    name, default_time, blurb = TASK_META[slug]
    md, html = entry.get("md"), entry.get("html")
    summary = ""
    key_fact = ""
    degraded = False

    if md and md.exists():
        text = md.read_text(encoding="utf-8", errors="replace")
        summary = _first_paragraph(text, name)
        key_fact = _key_fact(text)
        degraded = bool(_DEGRADED_RE.search(text[:3000]))
        # 时点提取：只认与本日匹配的日期，防误取
        mt = re.search(r"(\d{4})[-年](\d{1,2})[-月](\d{1,2})日?\s*(\d{1,2}):(\d{2})",
                       text[:2500])
        if mt:
            got = f"{int(mt.group(1)):04d}-{int(mt.group(2)):02d}-{int(mt.group(3)):02d}"
            if got == date:
                t = f"{int(mt.group(4)):02d}:{mt.group(5)}"
            else:
                t = default_time
        else:
            t = default_time
    else:
        t = default_time


    verdict = (market_data or {}).get("verdict", {})
    # 数据时点按任务性质判定，而非套用全局 verdict.data_stage
    stage = SLUG_STAGE.get(slug) or (market_data or {}).get("data_stage", "close")
    # 规范标题（§2.1）：与渲染器 render_title 同源（SLUG_STAGE 优先）
    title = render_title(slug, date, SLUG_STAGE.get(slug) or stage)

    # P0：Σ 与 rating 必须来自本 slug 自己的数据。缺失时诚实置 None，
    # 由 build_site.py 渲染为「数据缺口」，严禁回落到 0.0 或借用他值。
    if market_data and verdict:
        rating = verdict.get("rating")
        sigma = verdict.get("sigma")
        sigma_src = "verdict"
    else:
        rating, sigma, sigma_src = None, None, "missing"

    # breadth_scope：宽度分母口径（架构师指出两个口径并存会导致 Σ 不可比）
    # 5574 含北交所/ 5273 仅 A 股。缺此项时跨时点 Σ 不可直接比较。
    md_obj = market_data or {}
    breadth = md_obj.get("market_breadth") or md_obj.get("breadth") or {}
    breadth_scope = breadth.get("scope")

    # C-9（PM PC-24，金融场景最高危）：数据源降级时**不得输出可执行动作**。
    # 原文可读性让「降级产出」与「正常产出」在摘要层无法区分——读者会照着
    # 非实时数据算出的档位去下单。降级态只陈述状态，标准动作与关键事实
    # 一律撤下，动作只在正文（带完整口径说明）里给。
    if degraded:
        conclusion = ("数据源降级 · 本轮结论不适用｜"
                      "取数非实时（详见正文数据源说明），标准动作暂不执行")
    else:
        conclusion = SC.conclusion(rating, sigma, key_fact)

    return {
        "slug": slug,
        "name": name,
        "time": default_time,        # 调度时点（排序键）
        "run_time": t,               # 实际生成时刻
        "title": title,
        # 结论先行摘要（一致性契约 C-2）：评级·Σ ｜ 标准动作 ｜ 关键事实。
        # summary 保留为详情页补充说明（自由文本，可能是数据源告警）。
        "conclusion": conclusion,
        "degraded": degraded,        # 数据源降级/缺口标记 → 时间线显式提示
        "summary": summary or blurb,
        "html": f"{slug}.html" if html else None,
        "md": f"{slug}.md" if md else None,
        "rating": rating,
        "sigma": sigma,
        "sigma_source": sigma_src,
        "stage": stage,
        "breadth_scope": breadth_scope,
        "snapshot_at": (market_data or {}).get("snapshot_at"),
        "comparable": bool(sigma is not None and breadth_scope),
    }


def extract_meta(date: str, outputs: dict, market_data: dict | None) -> dict:
    """双语 meta：标题取股票助手/总复盘 md 首行；评级取 verdict。"""
    title_zh = f"每日市场研判 · {date}"
    for slug in ("daily-review", "stock-assistant", "fund-market"):
        md = outputs.get(slug, {}).get("md")
        if md and md.exists():
            for line in md.read_text(encoding="utf-8").splitlines():
                line = line.strip().lstrip("#").strip()
                if line and len(line) > 8:
                    title_zh = line
                    break
            break
    verdict = (market_data or {}).get("verdict", {})
    # P0（PM C-4 实锤）：.get(key, default) 的默认值是「伪造」——
    # 无 market_data 时会产出 sigma=0.000 / rating=信号矛盾，让「无数据」
    # 看起来像「中性结论」。缺失一律置 None，由渲染层呈现「数据缺口」。
    rating = verdict.get("rating") if verdict else None
    sigma = verdict.get("sigma") if verdict else None
    if not isinstance(sigma, (int, float)) or isinstance(sigma, bool):
        sigma = None
    if rating not in RATING_EN:
        rating = None
    stage = (market_data or {}).get("data_stage", "intraday")
    stage_zh, stage_en = STAGE_MAP.get(stage, (stage, stage))
    rating_en = RATING_EN.get(rating, rating)
    tasks = [TASK_NAMES[s] for s in TASK_SOURCES if s in outputs]
    has_verdict = rating is not None and sigma is not None
    if has_verdict:
        summary_zh = (f"Σ 评级【{rating}】（{sigma:+.3f}），"
                      f"覆盖 {len(tasks)} 项任务产出，数据时点 {stage_zh}。")
        summary_en = (f"Sigma rating [{rating_en}] ({sigma:+.3f}), covering "
                      f"{len(tasks)} task outputs, data stage {stage_en}.")
    else:
        # 诚实降级：无 verdict 时不编造评级，只说明状态与已归档产出数
        missing = "评级与 Σ 值" if rating is None and sigma is None else \
                  ("Σ 值" if sigma is None else "评级")
        summary_zh = (f"{missing}数据缺口，覆盖 {len(tasks)} 项任务产出，"
                      f"数据时点 {stage_zh}；缺口不做补零，避免生成虚假结论。")
        summary_en = (f"Rating/Σ data gap, {len(tasks)} task outputs archived, "
                      f"data stage {stage_en}. Gaps are never zero-filled.")
    return {
        "date": date,
        "title_zh": title_zh,
        "title_en": f"Daily Market Research · {date}",
        "summary_zh": summary_zh,
        "summary_en": summary_en,
        "rating": rating,
        "sigma": sigma,
        "data_stage": stage,
        "tasks": tasks,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _verdict_label(meta: dict) -> str:
    """meta 的评级+Σ 文本标签。sigma 为 None 时显式标注「数据缺口」，绝不格式化 0.000。"""
    r, s = meta.get("rating"), meta.get("sigma")
    if s is None or r is None:
        return "数据缺口"
    return f"{r} Σ{s:+.3f}"


def _repo_rel(p: Path) -> str:
    """路径 → 仓库根相对串（跨机器可读）；不在仓库内则原样返回绝对路径。"""
    try:
        return str(p.resolve().relative_to(HERE.parent.resolve()))
    except ValueError:
        return str(p)


def _sanitize_manifest_section(report_path: Path, changed: int) -> dict:
    """从消毒报告 JSON 提取 manifest 的 sanitize 段。

    changed 由调用方以「消毒前后文件哈希比对」得出 —— 报告里的
    unmapped-color 等条目只说明「这里有未收敛色值」，不代表文件被改动，
    不能用报告条目计数冒充改动数（2026-10-14 设计决策）。
    """
    section = {"applied": True, "report_path": _repo_rel(report_path),
               "files_changed": changed, "manual_review": 0}
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        section["manual_review"] = sum(
            f.get("counts", {}).get("needs-manual-review", 0)
            for f in data.get("files", []))
    except (OSError, ValueError) as e:
        print(f"  [sanitize] 警告：报告读取失败 {report_path}: {e}")
    return section


def run_sanitize(stage: Path, date: str, skip: bool) -> dict | None:
    """步骤 4.5：对 _stage/docs/daily/<date>（仅目标日期）的上游正文做发布层消毒。

    位置是设计约束：必须在步骤 4 落盘之后、步骤 5 build_site 之前 ——
    框架页（index.html）由 build_site 生成且已全量合规，消毒只覆盖上游
    正文详情页（sanitize_body.py 自身也会跳过框架页）。

    扫描范围是硬约束（2026-10-15 跨日期腐败事故的架构主修）：只处理
    _stage/docs/daily/<date> 一个目录。管线每天只把目标日期的上游 HTML
    写入 stage（步骤 4 不重写历史日期），消毒若扫全树，就会把昨日已消毒
    +已加框的页面重新消毒 —— map_custom_properties 会腐蚀 frame_pass
    注入的 Apple palette 原语（--ap-white:#ffffff → var(--fg-on-inverse)），
    且腐败页再消毒字节稳定（固定点）不会自愈。范围收窄后，管线永不重处理
    不是本次写入的页面。frame 块的 data-origin 标记（前端并行修复）是
    防腐第一层，本范围收窄是第二层。

    时点护栏（B-8）：先比对产物 mtime 与 scripts/sanitizer/*.py 的
    mtime（同范围：只扫目标日期目录）。存在陈旧产物时：正常路径强制
    重新消毒（sanitize_body 本就每轮重跑目标日期，此处显式化并留痕）；
    --no-sanitize 回退路径则阻断 —— 回退通道允许原样发布本轮新写盘的
    产物，不允许发布早于消毒代码的产物，否则「代码新于产物却直接发布」
    的路径就存在了。目标日期的页面是步骤 4 刚写入的（mtime=now），
    正常路径不会触发陈旧——护栏主要保护 --no-sanitize 与手工场景。

    退出码契约（scripts/sanitize_body.py）：
      0  干净通过
      2  存在 needs-manual-review —— 打印警告但不阻断发布，
         manifest 记 sanitize_warn（内容被保守保留，需人工判断）
      其余非零 = 失败 —— 打印 stderr 摘要，调用方返回退出码 3

    硬失败与护栏阻断均返回 None；其余情况返回 manifest 的 sanitize 段。
    """
    target = stage / "docs" / "daily" / date
    report_path = stage.parent / "evidence" / "sanitize-report.json"

    # ---- 时点护栏：代码新于产物 → 强制重消毒 / 阻断回退通道 ----
    # 扫描范围与消毒一致（仅目标日期）：历史日期不在本轮发布范围，
    # 其时点由各自发布轮次负责，杜绝跨日期重处理（腐败事故根因）。
    code_mtime = sanitizer_code_mtime()
    stale = stale_artifacts(target, code_mtime)
    if stale:
        names = ", ".join(p.relative_to(target).as_posix() for p in stale[:5])
        more = f" 等 {len(stale)} 个" if len(stale) > 5 else ""
        print(f"  [sanitize] 护栏：{names}{more}产物时点早于消毒代码时点"
              f"（code_mtime={code_mtime:.0f}）→ 本轮强制重新消毒")
    if skip:
        if stale:
            print("[FAIL] --no-sanitize 与陈旧产物冲突：回退通道不得发布早于"
                  "消毒代码的产物（B-8 护栏，防「代码新于产物却直接发布」）")
            return None
        print("  [sanitize] --no-sanitize：跳过发布层消毒（回退通道，详情页原样发布）")
        return {"applied": False, "report_path": None,
                "files_changed": 0, "manual_review": 0, "stale_forced": 0}

    sp = HERE / "sanitize_body.py"
    if not sp.exists():
        print(f"[FAIL] 缺少消毒脚本: {sp}")
        return None

    # 改动数以「消毒前后哈希比对」为准，不依赖报告条目计数。
    # 扫描范围 = 目标日期目录：files_changed 只统计本次发布的文件。
    before = {p: _sha256_file(p)
              for p in sorted(target.rglob("*.html")) if p.is_file()}

    r = subprocess.run(
        [MANAGED_PY, str(sp),
         "--dir", str(target),
         "--in-place",
         "--report", str(report_path)],
        capture_output=True, text=True)
    for ln in r.stdout.strip().splitlines():
        print(f"  [sanitize] {ln}")

    if r.returncode not in (0, 2):
        detail = (r.stderr or r.stdout or "").strip()[:500]
        print(f"[FAIL] 消毒失败（exit {r.returncode}）: {detail}")
        return None
    if r.returncode == 2:
        print("  [sanitize] 警告：存在 needs-manual-review 项 —— 不阻断发布，"
              "需人工确认（明细见消毒报告）")

    after = {p: _sha256_file(p)
             for p in sorted(target.rglob("*.html")) if p.is_file()}
    changed = sum(1 for p, h in after.items() if before.get(p) != h)
    section = _sanitize_manifest_section(report_path, changed)
    section["stale_forced"] = len(stale)
    return section


def main() -> int:
    ap = argparse.ArgumentParser(description="每日产出 GitHub 发布编排器")
    ap.add_argument("--date", required=True, help="日期 YYYY-MM-DD")
    ap.add_argument("--task", choices=list(TASK_SOURCES), default=None,
                    help="只发布指定任务（默认全部）")
    ap.add_argument("--source-root", default=str(SOURCE_ROOT))
    ap.add_argument("--stage", default=str(STAGE))
    ap.add_argument("--repo", default="daily-market-pulse",
                    help="GitHub 仓库名（PM 决策：daily-market-pulse）")
    ap.add_argument("--owner", default="seaquake97")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--push", action="store_true",
                    help="实际推送到 GitHub（经push_repo.py；dry-run 为默认）")
    ap.add_argument("--no-sanitize", action="store_true",
                    help="跳过发布层消毒（回退通道：详情页原样发布）；"
                         "目标日期存在陈旧于消毒代码的产物时被 B-8 时点护栏阻断")
    ap.add_argument("--unified-render", action="store_true",
                    help="统一渲染模式：忽略上游旧模板 HTML，一律由 render_md.py "
                         "从 md 生成详情页（根治多任务风格分裂；历史日期重渲染用）")
    args = ap.parse_args()

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        print(f"❌ 日期格式错误: {args.date}（应为 YYYY-MM-DD）")
        return 2

    src_root = Path(args.source_root)
    stage = Path(args.stage)
    date = args.date
    daily_stage = stage / "docs" / "daily" / date
    daily_stage.mkdir(parents=True, exist_ok=True)

    # ---- 1+2. 收集与提取 ----
    outputs, missing = collect(src_root, date, args.task)
    if missing:
        # A-03：缺失即中止，且中止在 manifest 写入之前——缺席口的产物不进
        # _stage（「发布 4 条、看起来像成功」正是 2026-10-16 事故形态：
        # 15:05 stock-review 整条消失而退出码 0，读者无任何告警）；
        # 上一轮 manifest 也不被失败轮覆盖（它是推送侧契约，取舍见 ADR-006）。
        report_missing(missing, len(outputs))
        print("❌ 发布中止：当日产物不完整（修复缺失任务后可用同一命令重跑，幂等）")
        return 2
    if not outputs:
        print(f"❌ {date} 无任何任务产出（检查目录: {src_root}/<任务名>/{date}/）")
        return 2
    market_data = load_market_data(src_root, date)
    meta = extract_meta(date, outputs, market_data)
    print(f"=== 收集到 {len(outputs)} 个任务产出: {', '.join(TASK_NAMES[s] for s in outputs)} ===")
    print(f"    评级: {_verdict_label(meta)} | 标题: {meta['title_zh']}")

    # ---- 4. 落盘暂存（原样直写，无脱敏）----
    # --unified-render：只搬 md，不搬上游 html —— 详情页一律由步骤 4.1 的
    # 统一渲染器从 md 生成（用户实锤「各任务风格还是不一致」的根治开关：
    # fund-market 等上游模板带 124 处 Tailwind 类，套框架壳后仍与其它任务
    # 视觉分裂；统一渲染后全部任务共用同一套 md→HTML 语义结构）。
    published = []
    path_scrubbed_total = 0
    for slug, entry in outputs.items():
        for ext, src in sorted(entry.items()):
            if args.unified_render and ext == "html" and "md" in entry:
                print(f"  [跳过] {slug}.html: 统一渲染模式（由 md 经 render_md 生成）")
                continue
            raw = src.read_text(encoding="utf-8")
            # .md 是**被发布**的产物（GitHub Pages 可直接访问），上游正文里的
            # `/Users/<用户名>/WorkBuddy/.../settlement.json` 等于在公开站点上
            # 暴露本机路径。HTML 侧由 md_render.inline._scrub_home_path 覆盖，
            # 但 md 自身不经那条链路（它只被当作渲染输入读一遍），故在此脱敏。
            # 2026-10-16 实测：脱敏前全站 1 处命中（stock-review.md），
            # 脱敏后 0。HTML 侧同期命中数也是 0，两条链路都要守。
            n_scrubbed = 0
            if ext == "md":
                raw, n_scrubbed = PS.scrub_text(raw)
                path_scrubbed_total += n_scrubbed
            dst = daily_stage / f"{slug}.{ext}"
            dst.write_text(raw, encoding="utf-8")
            note = f"，脱敏 {n_scrubbed} 处绝对路径" if n_scrubbed else ""
            print(f"  [写入] {slug}.{ext}: {len(raw)} 字节{note}")
            published.append(f"{slug}.{ext}")
    if path_scrubbed_total:
        print(f"  [脱敏] 本次发布共处理 {path_scrubbed_total} 处本机绝对路径")
    # ---- 4.1 统一渲染（FRAMEWORK-DESIGN v2.0 §2.2）----
    # md-only 任务（如 14:30 基金指引，任务书只产 md）此前永远无详情页——
    # 用户实锤「14:30 推送是空的」。现由统一渲染器补 HTML：上游五套 HTML
    # 生成器逐步废弃，本管线成为唯一呈现层生产者，风格天然统一。
    # 默认：已有 html 的任务不渲染（任务书改造后自然切换，边跑边迁）。
    # --unified-render：有 md 一律重渲染，忽略上游 html。
    rendered, rendered_slugs = 0, []
    for slug, entry in outputs.items():
        if ("html" in entry and not args.unified_render) or "md" not in entry:
            continue
        md_dst = daily_stage / f"{slug}.md"
        html_dst = daily_stage / f"{slug}.html"
        md_src_dir = TASK_SOURCES[slug][0]
        market_src = src_root / md_src_dir / date / "market_data.json"
        cmd = [MANAGED_PY, str(HERE / "render_md.py"),
               "--md", str(md_dst), "--slug", slug, "--date", date,
               "--out", str(html_dst)]
        if market_src.exists():
            cmd += ["--market-data", str(market_src)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        for ln in r.stdout.strip().splitlines():
            print(f"  [render] {ln}")
        if r.returncode != 0:
            print(f"❌ 渲染失败 {slug}.md: {r.stderr.strip()[:300]}")
            return 3
        # 回写 entry["html"]：extract_entry 据此在 entries.json 记 html 字段，
        # frame_pass（C-1）只加框 html 非 null 的条目——不回写则渲染产物
        # 永不加框/不进导航，等于白渲染（2026-10-16 接线缺口实测教训）
        entry["html"] = html_dst
        rendered += 1
        rendered_slugs.append(slug)
        published.append(f"{slug}.html")
    if rendered:
        print(f"  [render] 本次为 {rendered} 个 md-only 任务生成详情页"
              f"（14:30/15:05 类任务不再空推送）")
    # 幂等性前提：meta.json 的 generated_at 是运行时刻，每次都变，会让
    # 「同一天重跑」产生字节差异 → 空提交噪声。此处置为稳定值(该日首次
    # 发布时点由 manifest.pushed_at 记录)，保证重跑字节一致。
    meta.pop("generated_at", None)
    (daily_stage / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # entries.json：每日时间线的数据源。每份产出带真实 H1 标题、发布时点、
    # 一句话摘要、评级与 Σ。页面按time 升序渲染，杜绝无信息量链接标签。
    entries = []
    for slug_i, ent_i in outputs.items():
        md_i = load_market_data_for_slug(src_root, date, slug_i)
        entries.append(extract_entry(slug_i, ent_i, md_i, date))
    # 排序用「任务调度时点」（9:28 竞价→ 11:00 → 14:30 → 15:05 → 15:30），
    # 这是内容的天然先后；run_time 另存真实生成时刻，不参与排序。
    entries.sort(key=lambda x: (TASK_META.get(x["slug"], ("", "99:99", ""))[1],
                                 x.get("run_time", "")))
    # C-9（PM 实测缺陷）：不同 slug 最终产出**同一份内容** → 时间线出现两条
    # 完全相同的条目，用户把一次研判数成两次（实测 3/3 天 stock_review.md 被
    # 15:05 与 15:30 同时消费，逐字节相同）。
    #
    # 去重键必须是**内容指纹**而非文件名：15:30 的 md 名为 daily_review.md，
    # 但它是 15:05 文件的副本；反过来 daily-review 的 md 字段为 null、
    # 内容来自上游 html——按路径去重永远抓不到这类重复（实测踩过）。
    seen_fp: dict[str, str] = {}
    deduped: list[dict] = []
    for en in entries:
        cands = [daily_stage / (en["md"] or ""), daily_stage / (en["html"] or "")]
        src = next((c for c in cands if c and c.exists()), None)
        if src is None:
            deduped.append(en)
            continue
        try:
            fp = hashlib.sha256(src.read_bytes()).hexdigest()
        except OSError:
            deduped.append(en)
            continue
        if fp in seen_fp:
            print(f"  ⚠️ 内容重复: {en['slug']} 与 {seen_fp[fp]} 内容指纹相同"
                  f"（{src.name}），时间线只保留先出现者")
            continue
        seen_fp[fp] = en["slug"]
        deduped.append(en)
    entries = deduped
    # P0-1（架构师 A-04 实测）：降级条目在**数据层**撤下方向值。
    # 只在渲染层撤是不够的——entries.json 与 feed.json 会被第三方直接消费，
    # 带着「进攻 +0.510」的降级数据会让应用层自己算出动作。源头置 null。
    for en in entries:
        if en.get("degraded"):
            en["rating"] = None
            en["sigma"] = None
            en["comparable"] = False
    (daily_stage / "entries.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [meta] rating={meta['rating']} tasks={len(meta['tasks'])}"
          f" | 本次发布 {len(published)} 个产出文件")
    for en in entries:
        gap = "  ⚠️ Σ/评级数据缺口（该任务无 market_data.json）" \
            if en["sigma"] is None else ""
        sig = "—" if en["sigma"] is None else f"{en['sigma']:+.3f}"
        print(f"[时间线] {en['time']}  {en['name']:<6} Σ{str(sig):>8}  "
              f"{en['title'][:44]}{gap}")

    # ---- 4.5. 发布层消毒（换皮不阉割）----
    # 顺序是设计约束：落盘之后、build_site 之前。框架页由步骤 5 生成且已
    # 全量合规，此处只消毒上游正文详情页（sanitize_body.py 亦跳过框架页）。
    # 扫描范围 = 目标日期目录（stage/docs/daily/<date>）：管线永不重处理
    # 不是本次写入的页面（2026-10-15 跨日期腐败事故架构主修）。
    sanitize = run_sanitize(stage, date, args.no_sanitize)
    if sanitize is None:
        return 3
    if sanitize["manual_review"]:
        print(f"  [sanitize] manifest 记 sanitize_warn={sanitize['manual_review']}"
              "（needs-manual-review 保守保留，不阻断发布）")

    # ---- 5. 站点层 ----
    site_files = []
    site_calls = [
        ("build_site.py", "站点层(首页+日期页+周月归档+feed+sitemap)",
         ["--stage", str(stage)] + (["--no-frame"] if args.no_sanitize else [])),
    ]
    for script, label, script_args in site_calls:
        sp = HERE / script
        if not sp.exists():
            print(f"❌ 缺少站点脚本: {sp}")
            return 3
        r = subprocess.run([MANAGED_PY, str(sp), *script_args],
                           capture_output=True, text=True)
        for ln in r.stdout.strip().splitlines():
            if ln.startswith("SITE_FILE:"):
                continue
            print(f"  [{label}] {ln}")
        if r.returncode != 0:
            print(f"❌ {label}生成失败: {r.stderr.strip()[:500]}")
            return 3
        site_files.extend(
            ln.split(":", 1)[1].strip() for ln in r.stdout.splitlines()
            if ln.startswith("SITE_FILE:"))
    index_rel = "docs/index.html"
    if index_rel not in site_files:
        site_files.insert(0, index_rel)

    # ---- 6. manifest（本地 ↔ 代理的推送契约）----
    # 全量快照式清单：docs/daily/ 下所有日期文件 + 站点文件。
    # 理由：周/月归档页与 feed 跨日期引用，若只带当天文件，乱序推送或
    # 新仓库首次推送会产生断链；push_files 为 upsert 语义，重推无副作用。
    all_daily = sorted(
        str(p.relative_to(stage))
        for p in (stage / "docs" / "daily").rglob("*")
        if p.is_file() and p.suffix in (".md", ".html", ".json"))
    manifest_files = all_daily + [f for f in site_files if f not in all_daily]
    files_meta = []
    for rel in manifest_files:
        p = stage / rel
        if not p.exists():
            print(f"❌ manifest 文件缺失: {rel}")
            return 4
        # 站点文件自 P-3 起含二进制产物（apple-touch-icon / icon-192 / icon-512
        # 三个 PNG）：必须按字节读。read_text(utf-8) 会在 PNG 魔数 0x89 处抛
        # UnicodeDecodeError，把整条发布管线炸掉（2026-10-17 实测）。
        raw = p.read_bytes()
        if not raw.strip():
            print(f"❌ manifest 文件为空: {rel}")
            return 4
        files_meta.append({"path": rel, "bytes": len(raw),
                           "sha256_16": _sha256_file(p)})
    manifest = {
        "date": date,
        "owner": args.owner,
        "repo": args.repo,
        "branch": args.branch,
        "message": f"daily: {date} ({_verdict_label(meta)})",
        "files": files_meta,
        "push_channel": "local git + fine-grained PAT（scripts/push_repo.py；"
                        "令牌存 ~/.config/gh-ip/token，不入命令行/remote URL/.git/config）",
        "sanitize": sanitize,
        "render": {"count": rendered, "slugs": rendered_slugs},
        "push_command": [
            "python3", str(HERE / "push_repo.py"),
            "--stage", str(stage), "--owner", args.owner,
            "--repo", args.repo, "--branch", args.branch,
            "--message", f"daily: {date} ({_verdict_label(meta)})",
        ],
        "pushed": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    # needs-manual-review 不阻断发布，但必须在 manifest 留痕（人工待办）
    if sanitize["manual_review"]:
        manifest["sanitize_warn"] = sanitize["manual_review"]
    manifest_path = stage / "manifest.json"
    try:
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"❌ manifest 写入失败: {e}")
        return 4

    # ---- 7. 输出 ----
    print(f"\n=== dry-run 完成: {len(files_meta)} 个文件已暂存至 {stage}/ ===")
    for f in manifest_files:
        print(f"  {f}")
    if not args.push:
        print("（dry-run 模式：未推送。加 --push 执行真实推送）")
        # dry-run 也校验推送前置条件，让配置问题在推送前暴露
        try:
            import push_repo
            push_repo.read_token()
            print(f"[预检] 令牌就位: {push_repo.TOKEN_FILE}")
        except Exception as e:
            print(f"[预检] ⚠️ {e}")
        return 0

    # ---- 真实推送 ----
    print(f"\n=== 推送中: {args.owner}/{args.repo}@{args.branch} ===")
    try:
        import push_repo
        rc = push_repo.push(stage, args.owner, args.repo, args.branch,
                            manifest["message"])
    except Exception as e:
        print(f"❌ 推送失败: {e}")
        print("   → 产出与暂存均已落盘，不影响主任务；修复后可用同一命令重推（幂等）")
        manifest["pushed"] = False
        manifest["push_error"] = str(e)[:300]
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        return 6

    manifest["pushed"] = True
    manifest["pushed_at"] = datetime.now().isoformat(timespec="seconds")
    manifest.pop("push_error", None)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print(f"  [完成] manifest.pushed=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
