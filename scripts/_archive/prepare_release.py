#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_release.py — 每日产出 → GitHub 发布编排器（dry-run 默认）

流水线（六步）：
  1. 收集：从 5 个任务目录取 <date> 产出的 .md/.html（股票助手/基金盘面/基金指引/股票复盘/每日总复盘）
  2. 提取：从 market_data.json 的 verdict 取 Σ 评级；从 md 首行取标题
  3. 双语：生成 meta.json（title_zh/title_en/summary_zh/summary_en/rating/sigma/data_stage/tasks）
  4. 脱敏：对暂存文件逐条跑 desensitize.py（三层防御），残留即中止
  5. 聚合：调 build_index.py 生成 docs/index.html
  6. 清单：写 manifest.json（仓库/分支/文件清单），供代理侧执行 MCP push_files 推送

⚠️ MCP 边界（架构要点）：本脚本不直连 GitHub——MCP 工具是代理侧能力，本地无 SSH/gh CLI/
   GITHUB_TOKEN。--push 模式只做「校验 manifest + 打印推送指令」，实际推送由代理/定时任务
   读取 manifest.json 后调用 mcp__github__push_files 完成。

用法：
  python3 prepare_release.py --date 2026-10-14                 # dry-run（默认）
  python3 prepare_release.py --date 2026-10-14 --push          # 校验并输出 MCP 推送指令
  python3 prepare_release.py --date 2026-10-14 --keep-sensitive # 调试用：跳过脱敏（禁止用于推送）
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from desensitize import desensitize_text, check_residual  # noqa: E402

SOURCE_ROOT = Path("/Users/lianghaizhen/WorkBuddy")
STAGE = HERE.parent / "_stage"

# 任务目录 → 展示名（slug）
TASK_DIRS = {
    "股票助手": "stock-assistant",
    "基金每日盘面分析（11:00）": "fund-market",
    "基金每日操作指引（14:30）": "fund-guide",
    "股票复盘": "stock-review",
    "每日总复盘（15:30）": "daily-review",
}

# 双语词典（标题/摘要级；全文翻译由 LLM 在 v1.5 承担）
DICT_EN = {
    "股票助手": "Stock Assistant", "基金每日盘面分析": "Fund Market Analysis",
    "基金每日操作指引": "Fund Operation Guide", "股票复盘": "Stock Review",
    "每日总复盘": "Daily Review", "盘中研判": "Intraday Research",
    "竞价研判": "Auction Research", "信号矛盾": "Signal Conflict",
    "进攻": "Offense", "均衡": "Balanced", "防守": "Defense", "回避": "Avoid",
    "周三": "Wed", "周四": "Thu", "周五": "Fri", "周一": "Mon", "周二": "Tue",
}

WEEKDAYS = {"周一": "Mon", "周二": "Tue", "周三": "Wed", "周四": "Thu",
            "周五": "Fri", "周六": "Sat", "周日": "Sun"}


def translate_title(title_zh: str, rating: str) -> str:
    en = title_zh
    for zh, en_w in DICT_EN.items():
        en = en.replace(zh, en_w)
    for zh, en_w in WEEKDAYS.items():
        en = en.replace(zh, en_w)
    return en


def extract_meta(date: str, task_outputs: dict, market_data: dict) -> dict:
    """从任务产出提取 meta：标题取股票助手或总复盘的 md 首行；评级取 verdict。"""
    title_zh = f"每日市场研判 · {date}"
    for slug in ("daily-review", "stock-assistant", "fund-market"):
        md = task_outputs.get(slug, {}).get("md")
        if md and md.exists():
            for line in md.read_text(encoding="utf-8").splitlines():
                line = line.strip().lstrip("#").strip()
                if line and "·" in line:
                    title_zh = line
                    break
                if line and len(line) > 8:
                    title_zh = line
                    break
            break
    verdict = (market_data or {}).get("verdict", {})
    rating = verdict.get("rating", "信号矛盾")
    sigma = verdict.get("sigma", 0.0)
    stage = (market_data or {}).get("data_stage", "intraday")
    stage_en = {"pre_open": "Pre-open", "intraday": "Intraday", "close": "Close"}.get(stage, stage)
    tasks = [name for slug, name in TASK_DIRS.items() if slug in task_outputs]
    summary_zh = f"Σ 评级【{rating}】（{sigma:+.3f}），覆盖 {len(tasks)} 项任务产出，数据时点 {stage}。"
    summary_en = (f"Sigma rating [{rating}] ({sigma:+.3f}), covering {len(tasks)} task outputs, "
                  f"data stage {stage_en}.")
    return {
        "date": date,
        "title_zh": title_zh,
        "title_en": translate_title(title_zh, rating),
        "summary_zh": summary_zh,
        "summary_en": summary_en,
        "rating": rating,
        "sigma": sigma,
        "data_stage": stage,
        "tasks": tasks,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def main():
    ap = argparse.ArgumentParser(description="每日产出 GitHub 发布编排器")
    ap.add_argument("--date", required=True, help="日期 YYYY-MM-DD")
    ap.add_argument("--source-root", default=str(SOURCE_ROOT))
    ap.add_argument("--stage", default=str(STAGE))
    ap.add_argument("--repo", default="market-pulse-daily")
    ap.add_argument("--owner", default="seaquake970623")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--push", action="store_true", help="校验 manifest 并打印 MCP 推送指令")
    ap.add_argument("--keep-sensitive", action="store_true", help="调试：跳过脱敏（禁用于推送）")
    args = ap.parse_args()

    src_root = Path(args.source_root)
    stage = Path(args.stage)
    date = args.date
    daily_stage = stage / "docs" / "daily" / date
    if daily_stage.exists():
        shutil.rmtree(daily_stage)
    daily_stage.mkdir(parents=True)

    # ---- 1+2. 收集与提取 ----
    task_outputs = {}
    market_data = None
    for dir_name, slug in TASK_DIRS.items():
        d = src_root / dir_name / date
        if not d.is_dir():
            continue
        md = d / ({"股票助手": "stock_assistant.md", "基金每日盘面分析（11:00）": "fund_market_analysis.md",
                    "基金每日操作指引（14:30）": "fund_guide.md", "股票复盘": "stock_review.md",
                    "每日总复盘（15:30）": "daily_review.md"}[dir_name])
        html = md.with_suffix(".html")
        entry = {}
        if md.exists():
            entry["md"] = md
        if html.exists():
            entry["html"] = html
        if entry:
            task_outputs[dir_name] = entry
        md_json = d / "market_data.json"
        if md_json.exists() and market_data is None:
            market_data = json.loads(md_json.read_text(encoding="utf-8"))

    if not task_outputs:
        print(f"❌ {date} 无任何任务产出（检查目录: {src_root}/<任务名>/{date}/）")
        sys.exit(2)

    meta = extract_meta(date, task_outputs, market_data)
    print(f"=== 收集到 {len(task_outputs)} 个任务产出: {', '.join(task_outputs)} ===")
    print(f"    评级: {meta['rating']} Σ={meta['sigma']:+.3f} | 标题: {meta['title_zh']}")

    # ---- 3+4. 落盘暂存 + 脱敏 ----
    manifest_files = []
    for dir_name, entry in task_outputs.items():
        slug = TASK_DIRS[dir_name]
        for kind in ("md", "html"):
            src = entry.get(kind)
            if not src:
                continue
            dst = daily_stage / f"{slug}.{kind}"
            raw = src.read_text(encoding="utf-8")
            if args.keep_sensitive:
                dst.write_text(raw, encoding="utf-8")
                print(f"  [调试] 跳过脱敏: {dst.name}")
            else:
                new, stats = desensitize_text(raw)
                residual = check_residual(new)
                if residual:
                    print(f"❌ {src} 脱敏后仍有残留: {residual} → 中止发布")
                    sys.exit(1)
                dst.write_text(new, encoding="utf-8")
                n = sum(v for v in stats.values() if isinstance(v, int))
                print(f"  [脱敏] {dst.name}: 替换 {n} 处")
            manifest_files.append(f"docs/daily/{date}/{slug}.{kind}")
    (daily_stage / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_files.append(f"docs/daily/{date}/meta.json")

    # ---- 5. 聚合页 ----
    index_path = stage / "docs" / "index.html"
    r = subprocess.run([sys.executable, str(HERE / "build_index.py"),
                        "--daily-dir", str(stage / "docs" / "daily"),
                        "--out", str(index_path)],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print(f"❌ 聚合页生成失败: {r.stderr}")
        sys.exit(2)
    manifest_files.append("docs/index.html")

    # ---- 6. manifest ----
    manifest = {
        "date": date,
        "repo": args.repo,
        "owner": args.owner,
        "branch": args.branch,
        "files": manifest_files,
        "push_channel": "mcp__github__push_files（代理侧执行；本地无 SSH/gh CLI/GITHUB_TOKEN）",
        "push_command_hint": (
            f"读取 {stage}/manifest.json 的 files 清单，对每个文件读取 {stage}/ 下同路径内容，"
            f"单次调用 mcp__github__push_files(owner={args.owner}, repo={args.repo}, "
            f"branch={args.branch}, files=[{{path,content}}...], message='daily: {date}')"
        ),
        "pushed": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== dry-run 完成: {len(manifest_files)} 个文件已暂存至 {stage}/ ===")
    for f in manifest_files:
        print(f"  {f}")
    if args.push:
        print("\n=== MCP 推送指令（由代理执行）===")
        print(f"  {manifest['push_command_hint']}")
        print("  执行后把 manifest.json 的 pushed 置 true 并提交回仓库")
    else:
        print("（dry-run 模式：未推送。加 --push 查看 MCP 推送指令）")
    sys.exit(0)


if __name__ == "__main__":
    main()
