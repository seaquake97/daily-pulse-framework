#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rules.py — 持仓配置校验规则集门面（纯标准库，零依赖）

与 validate_config.py 的分工：本文件只回答「这份配置合不合规」，
不含 CLI、不含文件 IO、不含 YAML 解析。

v2 变更（ADR-007 §2.2 / U1 / U6）
--------------------------------
结构从 v1 的三段（stocks / grid / funds）改为**双轨结构**：

    version: 2
    profile / risk / cash
    holdings:
      stock: { positions, grid }     场内可交易标的，可网格可做 T
      fund:  { positions, plans }    场外基金，禁网格键
      gold                          实物/积存金，单列不进 fund

**不保留 v1 读取能力。** 这是有意的取舍，不是省事：
  · v1 的 funds 段允许 asset_class=gold 混在基金里，与「基金轨只收场外基金」
    的判据直接冲突；若同时支持两版，校验器就得为 gold 在两套结构里各写一次
    统计分支，同一条规则两份实现，漂移就是静默故障；
  · v1 没有 listing 字段，无法表达「这只到底是场内还是场外」。
    而归属判据恰恰是 v2 的核心（由数据决定，不由代码硬编码）——
    缺这个字段的 v1 配置在 v2 里根本无法无损升级；
  · v1 已被 portfolio.yaml 取代，MEMORY.md 只是人工编辑的源文档
    （ADR-007 §4：方向是 MEMORY.md → yaml 一次性迁移，此后 yaml 为准）。
    保留一个正在退场的格式的读取能力，是纯负债。
遇到 version:1 时直接报错并给出迁移路径，而不是「尽力猜着读」。

模块划分（依赖严格单向，无环）：
    codes -> rules_core -> rules_stock -> rules
                       -> rules_fund  -> rules
"""
from __future__ import annotations

from rules_core import (
    E_CASH, E_PROFILE, E_RISK, E_STRUCTURE, E_UNKNOWN_KEY, E_VERSION,
    SCHEMA_VERSION, SUPPORTED_VERSIONS, Report, W_EMPTY,
)

TOP_KEYS = ("version", "profile", "risk", "cash", "holdings")
PROFILE_KEYS = ("owner", "base_currency", "mode", "note")
RISK_KEYS = ("max_single_position_pct", "max_total_drawdown_pct",
             "grid_step_pct_cap", "fund_holding_days_min")
CASH_KEYS = ("currency", "amount", "note")

V1_MIGRATION_HINT = (
    "检测到 v1 配置（三段 stocks/grid/funds）。v2 改为双轨结构："
    "holdings.stock{positions,grid} 收场内标的，holdings.fund{positions,plans} "
    "收场外基金，积存金移入 holdings.gold。"
    "参考 config/portfolio.example.yaml 手工迁移，或用 "
    "scripts/migrate_memory_to_portfolio.py 从 MEMORY.md 生成。"
)


def validate(cfg: dict, rep: Report) -> None:
    """校验整份配置。rep 携带行号索引时错误带行号。"""
    if not isinstance(cfg, dict):
        rep.err("root", "配置根节点必须是映射（键值对）", "检查文件是否为空或格式错乱")
        return

    for key in cfg:
        if key not in TOP_KEYS:
            rep.err(key, f"未知顶层键 '{key}'",
                    f"合法键：{' / '.join(TOP_KEYS)}", E_UNKNOWN_KEY)

    version = cfg.get("version")
    if version is None:
        rep.err("version", "缺少必填键 version",
                f"当前契约版本应为 {SCHEMA_VERSION}", E_VERSION)
        # 版本缺失时继续校验会产出一堆误导性错误（按 v2 结构去挑 v1 的键），
        # 只补一条可执行的迁移提示后返回。
        if any(k in cfg for k in ("holdings", "profile")):
            rep.err("version", V1_MIGRATION_HINT, "", E_VERSION)
        return
    if version not in SUPPORTED_VERSIONS:
        rep.err("version",
                f"version={version!r} 不受支持（当前支持 {list(SUPPORTED_VERSIONS)}）",
                "major 变更需迁移，勿手改数字", E_VERSION)
        if version == 1:
            rep.err("version", V1_MIGRATION_HINT, "", E_VERSION)
        return

    _validate_profile(cfg.get("profile"), rep)
    _validate_risk(cfg.get("risk"), rep)
    _validate_cash(cfg.get("cash"), rep)
    _validate_holdings(cfg.get("holdings"), rep)


def _validate_profile(prof, rep: Report) -> None:
    if not isinstance(prof, dict):
        rep.err("profile", "缺少必填段 profile（owner / base_currency / mode）",
                "mode=personal 表示自用存档", E_PROFILE)
        return
    for k in ("owner", "base_currency", "mode"):
        if not prof.get(k):
            rep.err(f"profile.{k}", f"profile 缺少必填字段 {k}", "", E_PROFILE)
    if prof.get("base_currency") not in (None, "CNY"):
        rep.err("profile.base_currency",
                f"base_currency={prof.get('base_currency')!r}，当前仅支持 CNY",
                "", E_PROFILE)
    if prof.get("mode") not in (None, "personal", "publishing"):
        rep.err("profile.mode", f"mode={prof.get('mode')!r} 非法",
                "可选：personal（自用）/ publishing（对外发布）", E_PROFILE)


def _validate_risk(risk, rep: Report) -> None:
    """风控参数段。ADR-007 §2.3：风控不撤，改为随建议下发，故必须有此段。"""
    if risk is None:
        rep.err("risk", "缺少必填段 risk",
                "ADR-007 §2.3：风控参数随每条建议下发，不允许缺省", E_RISK)
        return
    if not isinstance(risk, dict):
        rep.err("risk", "risk 必须是映射", "写成 {max_single_position_pct: 20}", E_RISK)
        return
    for k in risk:
        if k not in RISK_KEYS:
            rep.err(f"risk.{k}", f"未知键 '{k}'",
                    f"本段合法键：{' / '.join(RISK_KEYS)}", E_UNKNOWN_KEY)
    for k in ("max_single_position_pct", "max_total_drawdown_pct",
              "grid_step_pct_cap"):
        v = risk.get(k)
        if v is None:
            rep.err(f"risk.{k}", f"缺少必填字段 {k}",
                    "风控参数不允许缺省：没有上限就等于没有风控", E_RISK)
        elif isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 < v <= 100:
            rep.err(f"risk.{k}", f"{k}={v!r} 必须是 (0, 100] 的数值",
                    "单位是百分比", E_RISK)
    v = risk.get("fund_holding_days_min")
    if v is None:
        rep.err("risk.fund_holding_days_min",
                "缺少必填字段 fund_holding_days_min",
                "场外赎回费窗口的下限，天数", E_RISK)
    elif isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 3650:
        rep.err("risk.fund_holding_days_min",
                f"fund_holding_days_min={v!r} 必须是 0~3650 的整数", "", E_RISK)


def _validate_cash(cash, rep: Report) -> None:
    if cash is None:
        rep.err("cash", "缺少必填段 cash", "写成 {currency: CNY, amount: 0}", E_CASH)
        return
    if not isinstance(cash, dict):
        rep.err("cash", "cash 必须是映射", "", E_CASH)
        return
    for k in cash:
        if k not in CASH_KEYS:
            rep.err(f"cash.{k}", f"未知键 '{k}'",
                    f"本段合法键：{' / '.join(CASH_KEYS)}", E_UNKNOWN_KEY)
    if cash.get("currency") not in (None, "CNY"):
        rep.err("cash.currency",
                f"currency={cash.get('currency')!r}，当前仅支持 CNY", "", E_CASH)
    amt = cash.get("amount")
    if amt is None:
        rep.err("cash.amount", "缺少必填字段 amount", "可用现金（元）", E_CASH)
    elif isinstance(amt, bool) or not isinstance(amt, (int, float)) or amt < 0:
        rep.err("cash.amount", f"amount={amt!r} 必须是非负数", "", E_CASH)


def _validate_holdings(hold, rep: Report) -> None:
    """调度双轨校验。两条轨的规则彼此独立，任一段缺失不阻断另一段——
    允许「只做基金」或「只做股票」的用户，这也是框架被复用时的常见形态。"""
    from rules_fund import validate_fund
    from rules_stock import validate_stock
    if not isinstance(hold, dict):
        rep.err("holdings", "缺少必填段 holdings（stock / fund / gold）",
                "无内容也要显式写出来", E_STRUCTURE)
        return
    for k in ("stock", "fund", "gold"):
        if k not in hold:
            rep.err(f"holdings.{k}", f"缺少必填段 {k}",
                    "缺省写 {} 或 []，不要留空", E_STRUCTURE)
    if isinstance(hold.get("stock"), dict):
        validate_stock(hold.get("stock"), rep)
    if isinstance(hold.get("fund"), dict):
        validate_fund(hold.get("fund"), rep)
    _validate_gold(hold.get("gold"), rep)

    sp = (hold.get("stock") or {}).get("positions") or []
    fp = (hold.get("fund") or {}).get("positions") or []
    if not sp and not fp:
        rep.warn("holdings", "股票轨与基金轨均为空",
                 "引擎会降级为「仅大盘研判」，不产出持仓诊断", W_EMPTY)


def _validate_gold(gold, rep: Report) -> None:
    """积存金/实物黄金单列。

    MEMORY.md 时代黄金靠「代码列为 - 且名称含黄金」被启发式识别成 GOLD，
    这是隐式契约。v2 把它显式化为独立段，且**禁止混入 fund.positions**：
    黄金不是基金，计入 fund_amount 会污染基金轨的统计口径与赎回窗口判断。
    """
    if gold is None:
        # `gold:`（空值）与 `gold: []` 语义不同：前者是「写漏了」，
        # 与 stock/fund 段「缺段 vs 空段」同一原则，必须报错而非放过。
        rep.err("holdings.gold", "gold 段为空值",
                "无黄金请显式写 gold: []", E_STRUCTURE)
        return
    if not isinstance(gold, list):
        rep.err("holdings.gold", "gold 必须是列表", "无内容写 []")
        return
    for i, g in enumerate(gold):
        loc = f"holdings.gold[{i}]"
        if not isinstance(g, dict):
            rep.err(loc, "黄金条目必须是映射")
            continue
        for k in g:
            if k not in ("name", "amount", "note"):
                rep.err(f"{loc}.{k}", f"未知键 '{k}'",
                        "本段合法键：name / amount / note", E_UNKNOWN_KEY)
        if not g.get("name"):
            rep.err(f"{loc}.name", "黄金条目缺少必填字段 name", "", E_REQUIRED)
        amt = g.get("amount")
        if amt is None:
            rep.err(f"{loc}.amount", "缺少必填字段 amount", "", E_REQUIRED)
        elif isinstance(amt, bool) or not isinstance(amt, (int, float)) or amt < 0:
            rep.err(f"{loc}.amount", f"amount={amt!r} 必须是非负数", "", E_CASH)


def build_summary(cfg: dict) -> dict:
    """汇总视图，供 CLI 打印与 --export 使用。

    track 字段是 v2 的关键增量：导出后每个标的都自带归属，
    下游任务无需再靠「在哪个段里」反推轨道。
    """
    from codes import normalize_code
    hold = (cfg or {}).get("holdings") or {}
    stock = hold.get("stock") or {}
    fund = hold.get("fund") or {}
    sp = [s for s in (stock.get("positions") or []) if isinstance(s, dict)]
    grid = [g for g in (stock.get("grid") or []) if isinstance(g, dict)]
    fp = [f for f in (fund.get("positions") or []) if isinstance(f, dict)]
    gold = [g for g in (hold.get("gold") or []) if isinstance(g, dict)]
    return {
        "schema_version": (cfg or {}).get("version"),
        "stock_count": len(sp),
        "grid_enabled": len([g for g in grid if g.get("enabled")]),
        "grid_total": len(grid),
        "fund_count": len(fp),
        "plan_count": len([p for p in (fund.get("plans") or []) if isinstance(p, dict)]),
        "gold_count": len(gold),
        "stock_amount": round(sum(
            (s.get("shares") or 0) * (s.get("cost") or 0) for s in sp), 2),
        "fund_amount": round(sum(f.get("amount") or 0 for f in fp), 2),
        "gold_amount": round(sum(g.get("amount") or 0 for g in gold), 2),
        "tracks": {
            "stock": [normalize_code(s.get("code", "")) for s in sp],
            "fund": [str(f.get("code", "")) for f in fp],
        },
    }