#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_report.py — 报告 md 章节契约校验（GAP-A2，纯标准库）

## 为什么需要它

「各个任务的风格还是不一致」的**上游真相**在此：五个任务过去各写各的
章节名与编号体系（`一、`/`01 `/`🚦` 四种混用），渲染层无法稳定映射区块，
只能靠正则猜测 —— 于是每页长得都不一样。

本脚本把 report_contract.yaml 变成可执行断言：
  R-1 必需章节齐备（按 semantic 匹配 title_pattern）
  R-2 章节顺序：结论类章节必须是第一个 h2
  R-3 标题卫生：禁 emoji、禁版本号副标题、禁空章节、禁层级跳跃
  R-4 数据一致性：正文评级/Σ 必须与 market_data.json 的 verdict 一致
        （这是最危险的一类——正文说「均衡」而代码算出「进攻」，
          读者按正文操作就是按错的方向操作）
  R-5 缺口纪律：data_gaps 非空时正文不得出现可执行动作指令

## 用法
    python3 check_report.py --md report.md --task fund-guide \
        [--market-data ../market_data.json]
    python3 check_report.py --dir <任务目录>/<日期> --task stock-review

退出码：0 通过｜1 契约未通过｜2 参数/IO 错误
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "report_contract.yaml"

EMOJI = re.compile("[\U0001F300-\U0001F9FF☀-➿⬀-⯿]")
# 版本号副标题：破折号后（可隔任意文字）出现 v1.3 / 版本号 / ver2 之类。
# 初版写成 `[—–-]\s*(v\d|版本|ver)` 要求破折号后紧跟版本号，
# 漏掉了实测最常见的「— daily-decision-engine v1.3」形态（2026-10-16 修正）。
VERSION_SUFFIX = re.compile(r"[—–-][^|\n]{0,40}?\b(v\d|ver\d|版本)", re.I)
ACTION_WORDS = ("上浮", "可上移", "新增买入", "执行买入", "减仓", "加仓",
                "挂买", "挂单买", "挂卖", "挂单卖", r"卖出\s*\d", r"买入\s*\d")
# 动作词豁免上下文（2026-10-16 实测误报修正）：
# 「昨日观点：甘肃能源 6.75 元挂买」是**回顾历史观点**，不是本轮动作指令。
# 无豁免会让契约误伤正确内容，久而久之大家就不看这个校验了——校验一旦
# 变成噪音就等于没有。豁免仅限「观点/昨日/已/历史」等回顾语境。
#
# ⚠ 表格行**不能**整体豁免：实测「网格做T卡」表格里写着「挂单卖出 500 股
# 做T」「下档买单设在 6.75 元」，是本轮可执行指令，藏在表格里不代表安全。
_REVIEW_CTX = re.compile(r"(昨日|观点|历史|已过|前一|上期|回顾|V\d)")


def _actionable_hits(md: str) -> list[str]:
    """定位真正的「本轮动作指令」，跳过回顾语境。

    判定：动作词所在**行**含回顾标记则不计；表格行仅当同行含回顾标记才豁免
    （实测动作指令常写在表格里，表格并非天然安全区）。
    """
    hits: list[str] = []
    for raw in md.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _REVIEW_CTX.search(line):
            continue
        for w in ACTION_WORDS:
            if re.search(w.replace(r"\s*", r"\s*"), line):
                hits.append(w)
    return sorted(set(hits))


# --------------------------------------------------------------------------
# 极简 YAML 子集解析（只支持本契约用到的形态：嵌套 map / list / 标量）
# 刻意不引第三方依赖：本框架的硬要求是「clone 完就能跑」。
# 支持：key: value、key:（空→块）、- 标量项、- key: value（map 项首键）
# 不支持：锚点、别名、块标量、多行流式集合（用到即报错，不静默忽略）
# --------------------------------------------------------------------------
def _strip_inline_comment(v: str) -> str:
    """剥行尾注释：`["a"]  # 说明` → `["a"]`。

    引号内的 `#` 不算注释（正则里常见）。行尾注释不剥会让内联列表带上
    一截说明文字，规则匹配随之失效（2026-10-16 实测踩过）。
    """
    out, quote = [], None
    for i, ch in enumerate(v):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            continue
        if ch == "#":
            # 需前面是行首或空白才算注释，避免误伤 'a#b'
            if i == 0 or v[i - 1] in " \t":
                break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(v: str):
    v = _strip_inline_comment(v.strip())
    # 行内列表 ["a", "b"] / ['a', 'b'] —— 逐字符拆分会让 verdict_keywords
    # 变成一串单字，任何标题都能"命中"，规则彻底失效（2026-10-16 实测）。
    if (v.startswith("[") and v.endswith("]")) or \
       (v.startswith("{") and v.endswith("}")):
        inner = v[1:-1].strip()
        if not inner:
            return [] if v[0] == "[" else {}
        sep = "," if v[0] == "[" else ","
        return [_scalar(p) for p in _split_flow(inner, sep)]
    v = v.strip('"').strip("'")
    if v in ("true", "True"):
        return True
    if v in ("false", "False"):
        return False
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d*\.\d+", v):
        return float(v)
    return v


def _split_flow(inner: str, sep: str) -> list[str]:
    """按分隔符切分，但**不切开引号内的分隔符**（'a, b' 是一个元素）。"""
    parts, buf, quote = [], [], None
    for ch in inner:
        if quote:
            if ch == quote:
                quote = None
            else:
                buf.append(ch)
        elif ch in "\"'":
            quote = ch
        elif ch == sep:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def parse_yaml_subset(text: str, _path: str = "root") -> dict:
    root: dict = {}
    stack = [(-1, root)]
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1] if stack else root

        if line.startswith("- "):
            body = line[2:].strip()
            if not isinstance(parent, list):
                raise ValueError(f"{_path}: 列表项出现在非列表上下文: {line!r}")
            if ":" in body and not body.startswith("http"):
                k, _, v = body.partition(":")
                item = {}
                parent.append(item)
                item[k.strip()] = _scalar(v)
                stack.append((indent, item))
            else:
                parent.append(_scalar(body))
            continue

        if ":" not in line:
            raise ValueError(f"{_path}: 无法解析行: {line!r}")
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val == "":
            child: dict = {}
            # 下一非空行若以 "- " 开头则是列表
            j = i
            while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith("#")):
                j += 1
            if j < len(lines):
                nxt = lines[j]
                nind = len(nxt) - len(nxt.lstrip())
                if nxt.strip().startswith("- ") and nind > indent:
                    child = []
                    parent[key] = child
                    stack.append((indent, child))
                    i = j
                    continue
            parent[key] = child
            stack.append((indent, child))
        else:
            if isinstance(parent, list):
                # 列表项的续写键（如 "- semantic: verdict" 后的 title_pattern）
                if isinstance(parent[-1], dict):
                    parent[-1][key] = _scalar(val)
                    continue
            parent[key] = _scalar(val)
    return root


def load_contract() -> dict:
    if not CONTRACT.exists():
        print(f"[fatal] 契约缺失: {CONTRACT}", file=sys.stderr)
        raise SystemExit(2)
    try:
        return parse_yaml_subset(CONTRACT.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"[fatal] 契约解析失败: {exc}", file=sys.stderr)
        raise SystemExit(2)


# --------------------------------------------------------------------------
def _sections(md: str) -> list[tuple[int, str, str]]:
    """返回 [(level, title, body)]，body 为该标题到下一个标题前的内容。

    body 的定义含「下一级子标题」——因为 h2 常常只是分组标签，正文都在
    h3 里。实测「01 结论卡」下全是 h3，若把 body 截到下一个**同级或更高级**
    标题之前，它会永远被判为空章节（2026-10-16 实测修正）。
    """
    marks = [(m.start(), m.end(), len(m.group(1)), m.group(2).strip())
             for m in re.finditer(r"^(#{1,6})\s+(.+)$", md, re.M)]
    out = []
    for i, (_s, e, lvl, title) in enumerate(marks):
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(md)
        out.append((lvl, title, md[e:nxt]))
    return out


def check_report(md: str, task: str, market_data: dict | None) -> tuple[list[str], list[str]]:
    err: list[str] = []
    warn: list[str] = []
    contract = load_contract()
    tasks = contract.get("tasks", {})
    if task not in tasks:
        return ([f"未知任务 {task!r}（契约支持: {sorted(tasks)}）"], [])

    secs = _sections(md)
    h2 = [(t, b) for lvl, t, b in secs if lvl == 2]

    # R-3 标题卫生（对所有层级标题）
    for lvl, title, _b in secs:
        if EMOJI.search(title):
            err.append(f"标题含 emoji（P0-1）: {title!r}")
        if VERSION_SUFFIX.search(title):
            err.append(f"标题含版本号副标题: {title!r}")
    # 空章节：h2+ 才有意义。h1 是文档标题，其「正文」区天然只有下一个标题
    # （md 首 H1 会被渲染层剥离，规范标题由 build_page 注入），
    # 对 h1 判空会把每份正常文档都报一遍错（2026-10-16 实测修正）。
    #
    # 「有内容」= 直接正文非空 **或** 该标题后紧跟子章节。实测「01 结论卡」
    # 这类分组 h2 自身一行文字都没有，全部正文在 h3 里——它是合法结构，
    # 不是空章节（2026-10-16 实测修正）。
    for i, (lvl, title, body) in enumerate(secs):
        if lvl < 2 or body.strip():
            continue
        has_child = (i + 1 < len(secs) and secs[i + 1][0] > lvl)
        if not has_child:
            err.append(f"空章节: {title!r}")
    lvls = [lvl for lvl, _t, _b in secs]
    for a, b in zip(lvls, lvls[1:]):
        if b - a > 1:
            err.append(f"标题层级跳跃: h{a} → h{b}")

    # R-1 必需章节（逐标题匹配，避免 pattern 的 ^ 锚点在拼接串上失效）
    h2_titles = [t for t, _b in h2]
    for spec in tasks[task].get("required", []):
        pat = spec.get("title_pattern")
        sem = spec.get("semantic")
        if pat and not any(re.search(pat, t) for t in h2_titles):
            err.append(f"缺必需章节[{sem}]，需匹配: {pat}")

    # R-2 结论类章节必须靠前
    # 仅在 verdict 章节**存在**时检查顺序：缺失已由 R-1 报错，
    # 再叠一条「应在首位」纯属噪音，会掩盖真问题（2026-10-16 实测修正）。
    #
    # ⚠ 例外：**降级/数据源提示章节可置于结论之前**（实测「⚠️ 连接器未连接提示」
    # 排第一）。理由是产品逻辑——读者必须先知道本轮数据不可信，再看结论；
    # 把提示压在结论后面等于让人先信后疑。这是契约服从产品，不是反过来。
    #（2026-10-16 实测修正：契约一度要求结论绝对首位，与降级提示冲突）
    rules = contract.get("rules", {})
    vk = [str(x).strip() for x in rules.get("verdict_keywords", []) if x]
    notice_re = re.compile(r"(降级|连接器|数据源|缺口|提示|警告|不可用)")
    verdict_specs = [s for s in tasks[task].get("required", [])
                     if s.get("semantic") == "verdict"]
    verdict_present = (not verdict_specs) or any(
        any(re.search(s.get("title_pattern", r"(?!)"), t) for t in h2_titles)
        for s in verdict_specs)
    if vk and h2 and verdict_present:
        first = h2[0][0]
        first_is_notice = bool(notice_re.search(first))
        if first_is_notice:
            # 提示章在首位时，从第二个章节开始找结论卡
            rest = h2[1:]
            if rest and not any(k in rest[0][0] for k in vk):
                idx = next((i for i, (t, _b) in enumerate(rest)
                            if any(k in t for k in vk)), None)
                if idx is not None:
                    err.append(f"结论章节应紧随降级提示之后"
                               f"（实际在第 {idx + 2} 位: {rest[idx][0]!r}）")
        elif not any(k in first for k in vk):
            idx = next((i for i, (t, _b) in enumerate(h2)
                        if any(k in t for k in vk)), None)
            if idx is not None:
                err.append(f"结论章节应在首位（实际第 {idx + 1} 位: {h2[idx][0]!r}）")

    # R-4 数据一致性（最危险的一类）
    v = (market_data or {}).get("verdict") or {}
    if v.get("rating"):
        if v["rating"] not in md:
            err.append(f"正文未出现评级「{v['rating']}」——与 market_data 不符")
        wrong = [r for r in ("进攻", "均衡", "信号矛盾", "防守", "回避")
                 if r != v["rating"] and re.search(rf"(评级|档位|结论)[为是：: ]\s*{r}", md)]
        if wrong:
            err.append(f"正文出现与 market_data 冲突的评级: {wrong}")
    if isinstance(v.get("sigma"), (int, float)):
        found = re.findall(r"Σ\s*([+\-−]?\d+\.\d{3})", md)
        if found:
            bad = [f for f in found
                   if abs(float(f.replace("−", "-")) - v["sigma"]) > 0.0011]
            if bad:
                err.append(f"正文 Σ 值与 market_data 不符: {bad[:3]} "
                           f"(market_data={v['sigma']:+.3f})")

    # R-5 缺口纪律
    gaps = (market_data or {}).get("data_gaps")
    if isinstance(gaps, list) and gaps:
        hit = _actionable_hits(md)
        if hit:
            err.append(f"数据源降级轮不得给出可执行动作（data_gaps 非空），命中: {hit}")
        else:
            warn.append("data_gaps 非空：建议在正文显著位置标注「本轮数据源降级」")

    if not md.strip():
        err.append("报告为空")
    return err, warn


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="报告 md 章节契约校验（GAP-A2）")
    ap.add_argument("--md", help="单个 md")
    ap.add_argument("--dir", help="任务日期目录（含 md）")
    ap.add_argument("--task", required=True, help="任务 slug（见契约 tasks 段）")
    ap.add_argument("--market-data", help="对应 market_data.json（启用 R-4/R-5）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    mds: list[Path] = []
    if args.md:
        mds = [Path(args.md)]
    elif args.dir:
        d = Path(args.dir)
        cands = sorted(d.glob("*.md"))
        if not cands:
            print(f"[fatal] 目录内无 md: {d}", file=sys.stderr)
            return 2
        mds = cands[:1]
    else:
        ap.error("需 --md 或 --dir")

    md_data = None
    mdp = args.market_data or (Path(args.dir) / "market_data.json"
                               if args.dir else None)
    if mdp and Path(mdp).exists():
        try:
            md_data = json.loads(Path(mdp).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"[warn] market_data 读取失败，跳过 R-4/R-5: {exc}")

    all_err, all_warn, rows = 0, 0, []
    for p in mds:
        e, w = check_report(p.read_text(encoding="utf-8", errors="replace"),
                            args.task, md_data)
        all_err += len(e)
        all_warn += len(w)
        rows.append({"file": str(p), "error": e, "warn": w})

    if args.json:
        print(json.dumps({"task": args.task, "results": rows,
                          "errors": all_err, "warnings": all_warn},
                         ensure_ascii=False, indent=1))
    else:
        for r in rows:
            tag = "FAIL" if r["error"] else ("WARN" if r["warn"] else "OK")
            print(f"[{tag}] {r['file']}  (task={args.task})")
            for m in r["error"]:
                print(f"   [error] {m}")
            for m in r["warn"]:
                print(f"   [warn]  {m}")
        print(f"\n合计 error {all_err} | warning {all_warn}")
        print("[fail] 章节契约未通过" if all_err else "[ok] 章节契约通过")
    return 1 if all_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
