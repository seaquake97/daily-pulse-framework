"""内容契约的数据层常量：维度词典与 SVG 图标语义映射。

与 content_contract.py 分离，把「词表」与「校验逻辑」隔开：
契约逻辑增删时不必触碰词表，反之亦然。纯标准库，无第三方依赖。

本模块只声明常量，不含 IO 与业务判断。
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# 维度词典：key -> (规范中文名, 英文名, 禁止的旧称)
# 规范名由 CONTENT-SPEC.md 锁定；旧称来自 2026-10-14 六任务实际产出扫描。
# --------------------------------------------------------------------------
DIMENSIONS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "verdict": ("结论卡", "Verdict Card", ("圆桌综合视角", "核心分析观点")),
    "sigma_timeline": ("日内 Σ 演进", "Intraday Sigma Timeline", ("Σ 演进", "观点演进")),
    "market_snapshot": ("市场快照", "Market Snapshot",
                        ("全场 A股动态行情家数与结构统计", "当前关键数据快照",
                         "全场A股动态行情家数与结构统计")),
    "signal_detail": ("确定性信号明细", "Signal Detail",
                      ("六信号明细", "六维确定性信号硬校验", "六维确定性信号硬校验结果",
                       "四层信号矩阵", "信号评分表", "信号面")),
    "bull_bear_evidence": ("多空证据清单", "Bull-Bear Evidence", ("多空证据",)),
    "index_quote": ("指数行情", "Index Quotes", ("核心大盘与风格指数表现", "大盘指数")),
    "sector_moneyflow": ("板块资金流向", "Sector Money Flow",
                         ("板块主力资金流向", "主力资金净流入 TOP 5 板块", "资金风向")),
    "overseas_check": ("外盘联动校验", "Overseas Linkage Check",
                       ("外盘企稳联动校验", "外盘联动与全球市场企稳校验",
                        "外盘与风格", "外盘全球指数企稳联动校验红线评估")),
    "portfolio_attribution": ("组合加权归因", "Portfolio Attribution",
                              ("加权归因", "组合收益加权归因",
                               "集中度诊断与渐进式调仓实操方案")),
    "fund_lookthrough": ("基金穿透诊断", "Fund Look-through",
                         ("逐基金穿透诊断", "持仓穿透与板块集中度深度分析",
                          "组合各标的预估表现明细", "穿透全组合十大重仓股票")),
    "concentration": ("板块集中度", "Sector Concentration", ("持仓穿透与板块集中度",)),
    "position_action": ("持仓动作卡", "Position Action Card",
                        ("持仓层：网格动作卡 / 观察卡", "持仓与标的诊断")),
    "grid_order": ("网格委托指令", "Grid Order Instruction",
                   ("股票与场内 ETF 网格操作指引", "15:00 前干预指令清单")),
    "expert_roundtable": ("专家圆桌", "Expert Roundtable",
                          ("子专家观点", "深度思考", "主持人札记", "主持人 Q&A")),
    "viewpoint_ledger": ("观点台账", "Viewpoint Ledger", ("观点台账与次日验证跟踪",)),
    "data_gap": ("数据缺口", "Data Gap", ("数据缺口清单",)),
    "watchlist": ("待验证信号", "Watch Signals",
                  ("明日待验证信号", "后续关注", "关键变量观察台", "综合视角失效条件")),
    "disclaimer": ("免责声明", "Disclaimer", ()),
}

# 扁平化为 (维度key, 规范名, 旧称)，供校验器线性扫描
BANNED_DIMENSIONS: tuple[tuple[str, str, str], ...] = tuple(
    (key, zh, old)
    for key, (zh, _en, olds) in DIMENSIONS.items()
    for old in olds
    if old and old != zh
)


# --------------------------------------------------------------------------
# SVG 图标语义映射：语义键 -> (中文语义, 24x24 stroke path)
#
# 契约只锁「语义 -> 图标含义」与 24x24 线性描边风格，不指定图标库：
# 渲染层可自行决定 inline <svg> / <img> / CSS mask 实现方式，
# 只要语义键与本表一致即可。跨任务混用不同图标库视为违规。
# --------------------------------------------------------------------------
ICONS: dict[str, tuple[str, str]] = {
    "verdict": ("裁定", "M12 3l7 3v6c0 4-3 7-7 8-4-1-7-4-7-8V6z"),
    "sigma": ("综合评分", "M5 19V5m0 0h9l-2.4 3L14 11H5"),
    "timeline": ("时点演进", "M4 19h16M4 19V5m0 14l4-5 3 3 5-7"),
    "breadth": ("市场广度", "M4 18V9m4 9V5m4 13v-6m4 6V8m4 10v-4"),
    "moneyflow": ("资金流向", "M4 8h11m-3-3l3 3-3 3M20 16H9m3 3l-3-3 3-3"),
    "overseas": ("外盘联动", "M12 3a9 9 0 100 18 9 9 0 000-18zM3 12h18M12 3c3 3.5 3 14 0 18"),
    "portfolio": ("组合归因", "M4 19V9m4 10V5m4 14v-7m4 7v-4m4 4v-2"),
    "fund": ("基金穿透", "M4 7h16v12H4zM9 7V5h6v2"),
    "position": ("持仓动作", "M12 4v16M4 12h16"),
    "grid": ("网格委托", "M4 4h16v16H4zM4 12h16M12 4v16"),
    "expert": ("专家圆桌", "M12 4a4 4 0 110 8 4 4 0 010-8zM5 20a7 7 0 0114 0"),
    "ledger": ("观点台账", "M6 4h11l3 3v13H6zM9 10h8M9 14h8M9 18h5"),
    "gap": ("数据缺口", "M12 4l9 16H3zM12 10v4m0 3v1"),
    "watch": ("待验证", "M12 4a8 8 0 100 16 8 8 0 000-16zM12 8v4l3 2"),
    "shield": ("风险红线", "M12 3l7 3v6c0 4-3 7-7 8-4-1-7-4-7-8V6z"),
    "doc": ("文档", "M6 3h8l4 4v14H6zM14 3v4h4"),
}
