#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rules.py — 持仓配置的校验规则集（纯标准库，零依赖）

与 validate_config.py 的分工：本文件只回答「这份配置合不合规」，
不含 CLI、不含文件 IO、不含 YAML 解析。规则集随契约版本（holdings.yaml 的 version）演进。

设计原则：
  · 硬错误阻断流水线——配置错了还往下跑等于带病出报告
  · 软警告提示但不放过——--strict 下也失败，供 CI 使用
  · 每条错误必须带 location（哪一段哪一条），让用户能直接定位
  · 每条硬错误都必须有反例测试，见 test_validate_config.py
"""
from __future__ import annotations

import re

# 契约版本（规则层的常量：rules 不依赖门面，门面 re-export 它）
SCHEMA_VERSION = 1

# 代码规范化统一走 codes.py —— 全框架唯一实现，与 parse_holdings.py 对齐。
# 不在 rules.py 内重复定义，也不从 validate_config 回引（门面会回引本文件，
# 形成循环导入；2026-10-16 实测会让整个测试套件 ImportError）。
from codes import code_mismatch, normalize_code


# ---------------------------------------------------------------------------
class Report:
    def __init__(self) -> None:
        self.errors: list = []
        self.warnings: list = []

    def err(self, loc: str, msg: str, hint: str = "") -> None:
        self.errors.append({"level": "error", "location": loc, "message": msg, "hint": hint})

    def warn(self, loc: str, msg: str, hint: str = "") -> None:
        self.warnings.append({"level": "warning", "location": loc, "message": msg, "hint": hint})

    @property
    def ok(self) -> bool:
        return not self.errors


# 注：market_of / normalize_code / code_mismatch 已移入 codes.py。
# 保留副本会导致「同一规则两份实现」，一旦漂移就是静默故障——
# 校验器说 ok 而实际取数打空。唯一实现比就近方便更重要。


def validate(cfg: dict, rep: Report) -> None:
    if not isinstance(cfg, dict):
        rep.err("root", "配置根节点必须是映射（键值对）", "检查文件是否为空或格式错乱")
        return

    for key in cfg:
        if key not in ("version", "profile", "market_data", "holdings", "snapshot"):
            rep.err(key, f"未知顶层键 '{key}'",
                    "合法键：version / profile / market_data / holdings / snapshot")
    if "version" not in cfg:
        rep.err("version", "缺少必填键 version", f"当前契约版本应为 {SCHEMA_VERSION}")
    elif cfg["version"] != SCHEMA_VERSION:
        rep.err("version", f"version={cfg['version']!r} 与当前契约 {SCHEMA_VERSION} 不符",
                "major 变更需运行迁移脚本，勿手改数字")

    prof = cfg.get("profile")
    if not isinstance(prof, dict):
        rep.err("profile", "缺少必填段 profile（owner / base_currency）")
    else:
        if not prof.get("owner"):
            rep.err("profile.owner", "owner 为空", "填你的标识，用于产物署名")
        if prof.get("base_currency") != "CNY":
            rep.err("profile.base_currency",
                    f"base_currency={prof.get('base_currency')!r}，当前仅支持 CNY")
        dp = prof.get("disclaimer_profile", "investing")
        if dp not in ("investing", "personal"):
            rep.err("profile.disclaimer_profile",
                    f"disclaimer_profile={dp!r} 非法", "可选：investing / personal")

    md = cfg.get("market_data")
    if isinstance(md, dict):
        if md.get("source", "westock-mcp") != "westock-mcp":
            rep.err("market_data.source",
                    "行情源必须为 westock-mcp",
                    "框架铁律：行情只走 MCP，HTTP 爬虫不可作为主源")

    hold = cfg.get("holdings")
    if not isinstance(hold, dict):
        rep.err("holdings", "缺少必填段 holdings（stocks / grid / funds）")
        return
    for seg in ("stocks", "grid", "funds"):
        if seg not in hold:
            rep.err(f"holdings.{seg}", f"缺少必填段 {seg}（无内容请写 []）")

    stocks = hold.get("stocks") or []
    grid = hold.get("grid") or []
    funds = hold.get("funds") or []
    for name, arr in (("stocks", stocks), ("grid", grid), ("funds", funds)):
        if not isinstance(arr, list):
            rep.err(f"holdings.{name}", f"{name} 必须是列表", "无内容写 []，不要留空值")

    if not stocks and not funds:
        rep.warn("holdings", "股票与基金均为空",
                 "引擎会降级为「仅大盘研判」，不产出持仓诊断")

    # 股票
    seen = {}
    for i, s in enumerate(stocks if isinstance(stocks, list) else []):
        loc = f"holdings.stocks[{i}]"
        if not isinstance(s, dict):
            rep.err(loc, "股票条目必须是映射"); continue
        for k in ("code", "name", "shares", "cost"):
            if k not in s or s[k] is None:
                rep.err(f"{loc}.{k}", f"股票缺少必填字段 {k}")
        code = s.get("code")
        if code is not None:
            norm = normalize_code(code)
            if not re.fullmatch(r"(sh|sz|bj)\d{6}", norm):
                rep.err(f"{loc}.code", f"code={code!r} 无法识别市场",
                        "须为 6 位数字；ETF 用 6 位基金代码")
            else:
                if norm in seen:
                    rep.err(f"{loc}.code", f"重复持仓 {norm}",
                            f"与 holdings.stocks[{seen[norm]}] 冲突")
                seen[norm] = i
                bad = code_mismatch(code)
                if bad:
                    rep.err(f"{loc}.code", bad, "去掉前缀只填 6 位数字可避免此问题")
        for k in ("shares", "available"):
            v = s.get(k)
            if v is not None and (not isinstance(v, int) or v < 0):
                rep.err(f"{loc}.{k}", f"{k}={v!r} 必须是非负整数")
        cost = s.get("cost")
        if cost is not None and (not isinstance(cost, (int, float)) or cost < 0):
            rep.err(f"{loc}.cost", f"cost={cost!r} 必须是非负数")
        if s.get("shares", 0) == 0:
            rep.warn(f"{loc}.shares", "持仓为 0",
                     "已清仓请从配置删除，勿留 0 占用行情请求配额")
        if s.get("available") and s.get("shares") and s["available"] > s["shares"]:
            rep.err(f"{loc}.available",
                    f"available={s['available']} > shares={s['shares']}",
                    "可用份额不可能超过持仓份额")

    # 网格
    gseen = {}
    for i, g in enumerate(grid if isinstance(grid, list) else []):
        loc = f"holdings.grid[{i}]"
        if not isinstance(g, dict):
            rep.err(loc, "网格条目必须是映射"); continue
        for k in ("code", "name", "enabled"):
            if k not in g:
                rep.err(f"{loc}.{k}", f"网格缺少必填字段 {k}")
        norm = normalize_code(g.get("code", ""))
        if g.get("code") is not None:
            if not re.fullmatch(r"(sh|sz|bj)\d{6}", norm):
                rep.err(f"{loc}.code", f"code={g.get('code')!r} 无法识别市场")
            elif norm in gseen:
                rep.err(f"{loc}.code", f"重复网格参数 {norm}",
                        f"与 holdings.grid[{gseen[norm]}] 冲突")
            else:
                gseen[norm] = i
                bad = code_mismatch(g.get("code", ""))
                if bad:
                    rep.err(f"{loc}.code", bad, "去掉前缀只填 6 位数字可避免此问题")
        en = g.get("enabled")
        if not isinstance(en, bool):
            rep.err(f"{loc}.enabled", f"enabled={en!r} 必须是 true/false",
                    "底仓长线持有写 false，不要留空")
            en = False
        rng = [g.get("range_low"), g.get("range_high")]
        if en:
            if None in rng:
                rep.err(f"{loc}.range_low", "启用网格时必须同时给出 range_low 与 range_high")
            elif rng[0] >= rng[1]:
                rep.err(f"{loc}.range_low",
                        f"区间非法：low={rng[0]} >= high={rng[1]}",
                        "下沿必须严格小于上沿")
            if g.get("base_price") is None:
                rep.err(f"{loc}.base_price", "启用网格时必须给出 base_price")
            elif rng[0] is not None and not (rng[0] <= g["base_price"] <= rng[1]):
                rep.warn(f"{loc}.base_price",
                         f"base_price={g['base_price']} 不在区间 "
                         f"[{rng[0]}, {rng[1]}] 内",
                         "基准价通常取区间中枢，越界说明参数未校准")
            if g.get("step_pct") is None:
                rep.err(f"{loc}.step_pct", "启用网格时必须给出 step_pct")
            elif not (0 < g["step_pct"] <= 50):
                rep.err(f"{loc}.step_pct", f"step_pct={g['step_pct']} 超出 (0, 50]")
        else:
            for k in ("range_low", "range_high", "step_pct"):
                if g.get(k) is not None:
                    rep.warn(f"{loc}.{k}",
                             f"enabled=false 但仍设置了 {k}={g[k]!r}",
                             "该值不会被引擎读取，确认是否漏改 enabled")
        mn, mx = g.get("min_position"), g.get("max_position")
        if isinstance(mn, int) and isinstance(mx, int) and mn > mx:
            rep.err(f"{loc}.min_position",
                    f"min_position={mn} > max_position={mx}", "底仓不应大于顶仓")
        if norm and norm in seen and en:
            sh = next((x for x in stocks if normalize_code(x.get("code", "")) == norm), None)
            if sh and isinstance(mn, int) and mn > (sh.get("shares") or 0):
                rep.warn(f"{loc}.min_position",
                         f"min_position={mn} 超过当前持仓 {sh.get('shares')}",
                         "网格会立即触发停卖，请确认参数")

    # 基金
    fseen = set()
    fund_amount = gold_amount = 0.0
    for i, f in enumerate(funds if isinstance(funds, list) else []):
        loc = f"holdings.funds[{i}]"
        if not isinstance(f, dict):
            rep.err(loc, "基金条目必须是映射"); continue
        if not f.get("name"):
            rep.err(f"{loc}.name", "基金缺少必填字段 name")
        ac = f.get("asset_class")
        if ac not in ("fund", "gold"):
            rep.err(f"{loc}.asset_class", f"asset_class={ac!r} 非法", "可选：fund / gold")
            continue
        code = f.get("code")
        if ac == "fund":
            if not code:
                rep.err(f"{loc}.code", "asset_class=fund 时 code 必填（6 位基金代码）")
            elif not re.fullmatch(r"\d{6}", str(code)):
                rep.err(f"{loc}.code", f"code={code!r} 不是 6 位数字")
            elif code in fseen:
                rep.err(f"{loc}.code", f"重复基金 {code}")
            else:
                fseen.add(str(code))
        amt = f.get("amount")
        if amt is not None and (not isinstance(amt, (int, float)) or amt < 0):
            rep.err(f"{loc}.amount", f"amount={amt!r} 必须是非负数")
        elif isinstance(amt, (int, float)):
            if ac == "gold":
                gold_amount += amt
            else:
                fund_amount += amt
        plan = f.get("plan")
        if plan is not None and plan not in (
                "regular", "smart", "smart_take_profit", "holding", "none"):
            rep.err(f"{loc}.plan", f"plan={plan!r} 非法",
                    "可选：regular / smart / smart_take_profit / holding / none")

    if not rep.errors and not stocks and funds:
        rep.err("holdings", "只有基金没有股票持仓",
                "确认是否漏填 stocks 段")


def build_summary(cfg: dict) -> dict:
    hold = (cfg or {}).get("holdings") or {}
    stocks = hold.get("stocks") or []
    funds = hold.get("funds") or []
    grid = hold.get("grid") or []
    return {
        "stock_count": len(stocks),
        "grid_enabled": len([g for g in grid if isinstance(g, dict) and g.get("enabled")]),
        "grid_total": len(grid),
        "fund_count": len([f for f in funds if isinstance(f, dict)
                           and f.get("asset_class") != "gold"]),
        "fund_amount": round(sum(f.get("amount") or 0 for f in funds
                                 if isinstance(f, dict) and f.get("asset_class") != "gold"), 2),
        "gold_amount": round(sum(f.get("amount") or 0 for f in funds
                                 if isinstance(f, dict) and f.get("asset_class") == "gold"), 2),
        "codes": [normalize_code(s.get("code", "")) for s in stocks if isinstance(s, dict)],
    }
